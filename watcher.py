"""
울산대학교 공지에서 대회·공모전 공고를 찾아 새 글이 올라오면 이메일로 알려주는 스크립트.

두 곳을 본다.

  1. 대표 홈페이지 일반공지 - 공모전·경진대회·해커톤 공고가 가장 많이 올라온다.
     교외 기관 공고까지 학교가 받아서 올려주는 곳이라 물량이 여기 몰린다.
  2. SW중심대학사업단 공지 - 학내 SW 대회(캡스톤, 프로그래밍 경진대회 등).
     여기만 학교 전산망 밖(CloudFront + 외부 CMS)이라 공개 JSON API로 가져온다.

학교 서버는 IP당 요청 수를 제한한다. 러너에서 다섯 번째 요청부터 연결이 거절된
적이 있어서, 대표 홈페이지는 키워드마다 검색하지 않고 목록 두 페이지만 받아
제목을 직접 거른다. 목록 2페이지면 나흘치라 2시간 주기로는 넉넉하다.
평소 한 회차에 나가는 요청은 목록 3번 + 새 글 상세 몇 번이다.

동작 방식:
1. 각 게시판에서 후보 글 목록을 모은다.
2. 제목이 TARGET_KEYWORDS에 걸리고 state/seen.json에 없는 글이면
   상세 페이지를 읽어 본문·작성일·첨부파일을 가져온다.
3. 이메일로 발송하고 글 번호를 state/seen.json에 기록한다.

게시판을 처음 감시할 때는(= state에 그 게시판 기록이 없을 때) 메일을 보내지 않고
현재 글을 읽음 처리만 한다. 나중에 게시판을 추가해도 과거 글이 쏟아지지 않는다.
"""

import argparse
import json
import os
import re
import smtplib
import time
from email.header import Header
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

STATE_FILE = Path(__file__).parent / "state" / "seen.json"

# (연결, 응답) 타임아웃. 러너(미국)에서 국내 서버로 붙을 때 연결이 느리게 잡히는
# 일이 있어 연결 쪽을 넉넉히 준다.
TIMEOUT = (15, 30)

# 요청 사이 간격. 학교 서버는 짧은 시간에 요청이 몰리면 연결 자체를 거절한다.
REQUEST_DELAY = 3.0

# 제목에 이 중 하나라도 들어 있으면 알림 대상. 띄어쓰기와 대소문자는 무시하고 비교한다.
# 장학 공고까지 받고 싶으면 "장학"을 넣으면 된다.
TARGET_KEYWORDS = [
    "대회",
    "공모전",
    "공모",
    "해커톤",
    "hackathon",
    "경진",
    "경연",
    "챌린지",
    "challenge",
    "아이디어톤",
    "콘테스트",
    "contest",
]

# 위 키워드에 걸려도 이미 끝난 소식은 뺀다. 남의 수상 소식까지 받을 이유는 없다.
EXCLUDE_KEYWORDS = ["수상자", "명단", "최종 결과", "결과 안내", "개최 취소"]

# 대표 홈페이지에는 교외 기관 공고가 그대로 올라와서 '한우 곤포 나르기 대회',
# '댄스 경연대회' 같은 것까지 섞인다. 그래서 그 게시판만 대회 단어에 더해
# 이 중 하나가 제목에 있어야 알림을 보낸다. SW사업단 게시판은 전부 SW 대회라 안 건다.
SW_KEYWORDS = [
    "ai", "인공지능", "sw", "소프트웨어", "프로그래밍", "코딩", "코테",
    "해커톤", "hackathon", "데이터", "빅데이터", "알고리즘",
    "앱", "애플리케이션", "웹", "ict", "디지털", "정보통신", "전산",
    "로봇", "자율주행", "임베디드", "드론", "반도체",
    "정보보호", "보안", "클라우드", "블록체인", "메타버스", "가상현실", "vr",
    "게임", "챗봇", "머신러닝", "딥러닝", "캡스톤", "오픈소스", "사물인터넷", "iot",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _clean(text: str) -> str:
    """줄바꿈·연속 공백·nbsp를 공백 하나로 정리한다."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _normalize(text: str) -> str:
    """키워드 비교용. 띄어쓰기 차이를 무시하려고 공백을 전부 없앤다."""
    return re.sub(r"\s+", "", text).lower()


def _contains(title: str, keyword: str) -> bool:
    """
    제목에 키워드가 들어 있는지 본다.

    한글은 띄어쓰기를 무시하고 찾는다("국가 근로" == "국가근로").
    영문·숫자만인 키워드는 단어 단위로 찾는다. 그냥 부분 문자열로 찾으면
    'it'이 'digital'에, 'ar'이 'start'에 걸려서 엉뚱한 글이 딸려온다.
    """
    if re.fullmatch(r"[a-z0-9]+", keyword):
        return re.search(rf"\b{re.escape(keyword)}\b", title.lower()) is not None
    return _normalize(keyword) in _normalize(title)


def _build_session() -> requests.Session:
    """
    연결을 재사용하는 세션. 매 요청마다 TCP 연결을 새로 열면 학교 서버가
    도중에 연결을 안 받아줘서 ConnectTimeout·Connection refused가 난다.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=3,
        connect=3,
        read=2,
        backoff_factor=3,  # 재시도 간격 3초 → 6초 → 12초
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


SESSION = _build_session()


def _fetch(url: str, params: dict | None = None, headers: dict | None = None):
    resp = SESSION.get(url, params=params, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return resp


def _get(url: str, params: dict) -> BeautifulSoup:
    return BeautifulSoup(_fetch(url, params).text, "html.parser")


def _body_text(element) -> str:
    if element is None:
        return "(본문을 불러오지 못했습니다)"
    text = element.get_text("\n", strip=True).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", text)


class Board:
    """감시 대상 게시판의 공통 부분."""

    def __init__(self, board_id: str, name: str, tag: str,
                 require_any: list[str] | None = None):
        self.board_id = board_id
        self.name = name
        self.tag = tag  # 메일 제목 앞에 붙는 말
        # 대회 단어에 더해 이 중 하나가 더 있어야 통과시킨다(없으면 안 건다)
        self.require_any = list(require_any) if require_any else []

    def matches(self, title: str) -> str | None:
        """제목이 조건에 걸리면 걸린 키워드를, 아니면 None을 돌려준다."""
        if any(_contains(title, word) for word in EXCLUDE_KEYWORDS):
            return None

        hit = next((k for k in TARGET_KEYWORDS if _contains(title, k)), None)
        if not hit:
            return None

        if self.require_any:
            extra = next((k for k in self.require_any if _contains(title, k)), None)
            if not extra:
                return None
            return hit if extra == hit else f"{hit}+{extra}"

        return hit


class UnivBoard(Board):
    """
    대표 홈페이지 CMS 게시판(www.ulsan.ac.kr/kor/CMS/Board/Board.do).

    제목 검색도 되지만 키워드마다 요청이 한 번씩 들어간다. 학교 서버가 요청 수를
    제한해서 목록 두 페이지만 받고 제목은 여기서 직접 거른다. 키워드를 아무리
    늘려도 요청 수는 그대로다.
    """

    BASE_URL = "https://www.ulsan.ac.kr/kor/CMS/Board/Board.do"

    def __init__(self, mcode: str, mgr_seq: str, pages_to_check: int = 2, **kwargs):
        super().__init__(**kwargs)
        self.mcode = mcode
        self.mgr_seq = mgr_seq
        self.pages_to_check = pages_to_check

    def post_url(self, post_id: str) -> str:
        return (
            f"{self.BASE_URL}?mCode={self.mcode}&mode=view"
            f"&mgr_seq={self.mgr_seq}&board_seq={post_id}"
        )

    def fetch_candidates(self) -> dict[str, dict]:
        candidates: dict[str, dict] = {}
        for page in range(1, self.pages_to_check + 1):
            soup = _get(self.BASE_URL, {"mCode": self.mcode, "page": page})
            for row in soup.select("table.board-list-table tbody tr"):
                link = row.select_one("td.subject a[href*='board_seq=']")
                if not link:
                    continue
                m = re.search(r"board_seq=(\d+)", link.get("href", ""))
                if not m:
                    continue
                date_el = row.select_one("td.date")
                # 상단 고정 공지는 페이지마다 반복되므로 글 번호로 덮어쓴다.
                candidates[m.group(1)] = {
                    "post_id": m.group(1),
                    "title": _clean(link.get_text()),
                    "date": _clean(date_el.get_text()) if date_el else "",
                }
        return candidates

    def fetch_detail(self, post_id: str) -> dict:
        soup = _get(self.BASE_URL, {
            "mCode": self.mcode,
            "mode": "view",
            "mgr_seq": self.mgr_seq,
            "board_seq": post_id,
        })

        title_el = soup.select_one("h4.vtitle")
        category_el = title_el.select_one("span.cate") if title_el else None
        if category_el:
            category_el.extract()  # 제목에서 [일반] 같은 분류 표시를 뗀다

        info = soup.select("div.vtitle-winfo span.txt")

        return {
            "title": _clean(title_el.get_text()) if title_el else "",
            "writer": _clean(info[0].get_text()) if info else "",
            "date": _clean(info[1].get_text()) if len(info) > 1 else "",
            "content": _body_text(soup.select_one("#boardContents")),
            "attachments": [
                _clean(a.get_text()) for a in soup.select("ul.board-view-filelist li a")
            ],
            "url": self.post_url(post_id),
        }


class SwBoard(Board):
    """
    SW중심대학사업단 공지(sw.ulsan.ac.kr).

    이 사이트만 학교 전산망 밖에 있다. 화면은 CloudFront에서 오고 게시판 데이터는
    외부 CMS(didisam)의 공개 JSON API로 나온다. 요청 제한이 없고 목록 한 번이면
    제목·작성일·글번호가 전부 온다. HTML을 안 긁으니 화면이 바뀌어도 잘 안 깨진다.
    """

    API_BASE = "https://prd-community.didisam.com/api/v3/sampage/notice"
    SITE_BASE = "https://sw.ulsan.ac.kr/site"

    def __init__(self, slug: str = "swulsan", page_size: int = 30, **kwargs):
        super().__init__(**kwargs)
        self.slug = slug
        self.page_size = page_size

    def post_url(self, post_id: str) -> str:
        return f"{self.SITE_BASE}/{self.slug}/notices/{post_id}"

    def _api(self, path: str = "", params: dict | None = None) -> dict:
        # 어느 사이트의 게시판인지는 헤더의 slug로 가른다.
        resp = _fetch(f"{self.API_BASE}{path}", params=params, headers={"slug": self.slug})
        return resp.json()["result"]

    def fetch_candidates(self) -> dict[str, dict]:
        result = self._api("/community", {"page_size": self.page_size, "page": 1})

        candidates: dict[str, dict] = {}
        for row in result.get("data", []):
            post_id = str(row["notice_id"])
            # 상단 고정 공지는 목록에 두 번 나오므로 글 번호로 덮어쓴다.
            candidates[post_id] = {
                "post_id": post_id,
                "title": _clean(row.get("title", "")),
                "date": (row.get("insert_date") or "")[:10],
            }
        return candidates

    def fetch_detail(self, post_id: str) -> dict:
        row = self._api(f"/{post_id}")

        content = _body_text(BeautifulSoup(row.get("contents") or "", "html.parser"))
        if not content.strip():
            # 포스터 이미지 한 장만 올리는 공지가 흔하다.
            content = "(본문이 이미지로만 되어 있습니다. 링크에서 확인하세요.)"

        return {
            "title": _clean(row.get("title", "")),
            "writer": _clean(row.get("nick_name") or ""),
            "date": (row.get("insert_date") or "")[:10],
            "content": content,
            "attachments": [
                _clean(f.get("attachment_title", "")) for f in (row.get("attachment") or [])
            ],
            "url": self.post_url(post_id),
        }


BOARDS = [
    UnivBoard(
        board_id="univ-notice",
        name="울산대학교 일반공지",
        tag="울산대 SW대회",
        require_any=SW_KEYWORDS,
        mcode="MN113",
        mgr_seq="35",
    ),
    SwBoard(
        board_id="sw-notice",
        name="SW중심대학사업단 공지",
        tag="SW 대회",
    ),
]


def load_state() -> dict[str, set]:
    if not STATE_FILE.exists():
        return {}
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))

    # 예전에는 게시판이 하나뿐이라 seen_ids 배열 하나로 저장했다.
    if "seen_ids" in data:
        return {"sw-notice": set(data["seen_ids"])}

    return {board_id: set(ids) for board_id, ids in data.get("seen", {}).items()}


def save_state(state: dict[str, set]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seen": {board_id: sorted(ids) for board_id, ids in sorted(state.items())}}
    STATE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def format_body(item: dict) -> str:
    lines = [
        f"게시판: {item['board_name']}",
        f"걸린 키워드: {item['keyword']}",
        f"제목: {item['title']}",
    ]
    if item["writer"]:
        lines.append(f"작성자: {item['writer']}")
    if item["date"]:
        lines.append(f"작성일: {item['date']}")
    lines.append(f"링크: {item['url']}")
    if item["attachments"]:
        lines.append("첨부파일: " + ", ".join(item["attachments"]))
    lines += ["", "----- 공지 원문 -----", item["content"]]
    return "\n".join(lines)


def send_email(items: list[dict]) -> None:
    missing = [name for name in ("EMAIL_USER", "EMAIL_PASS") if not os.environ.get(name)]
    if missing:
        raise SystemExit(
            f"환경변수 {', '.join(missing)}가 비어 있습니다. "
            "GitHub Secrets에 넣었는지 확인하세요. 메일 없이 확인만 하려면 --dry-run."
        )

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    email_user = os.environ["EMAIL_USER"]
    email_pass = os.environ["EMAIL_PASS"]

    # EMAIL_TO는 쉼표로 여러 개를 적을 수 있다. 예) 학교 메일, 개인 메일
    recipients = [
        addr.strip()
        for addr in os.environ.get("EMAIL_TO", email_user).split(",")
        if addr.strip()
    ] or [email_user]

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(email_user, email_pass)

        for item in items:
            msg = MIMEText(format_body(item), "plain", "utf-8")
            msg["Subject"] = Header(f"[{item['board_tag']}] {item['title']}", "utf-8")
            msg["From"] = email_user
            msg["To"] = ", ".join(recipients)
            server.sendmail(email_user, recipients, msg.as_string())
            print(f"메일 발송 완료: {item['title']}")


def _detail_from_list_row(board: Board, post_id: str, row: dict) -> dict:
    """
    상세 페이지를 못 읽었을 때 목록에서 아는 것만으로 만든 대체 항목.

    본문이 없어도 '새 공고가 떴다 + 링크'는 전달돼야 알림 노릇을 한다.
    """
    return {
        "title": row["title"],
        "writer": "",
        "date": row["date"],
        "content": "(학교 서버 접속이 막혀 본문을 가져오지 못했습니다. 위 링크에서 확인하세요.)",
        "attachments": [],
        "url": board.post_url(post_id),
    }


def collect_new_items(board: Board, seen: set, with_details: bool = True) -> tuple[list[dict], set]:
    """
    게시판에서 알림 보낼 글과, 이번에 확인한 전체 글 번호를 돌려준다.

    with_details=False면 목록만 읽고 상세는 건너뛴다. 최초 감시 때는 어차피
    메일을 안 보내므로 요청 수를 줄이려고 쓴다.
    """
    candidates = board.fetch_candidates()
    if not with_details:
        return [], set(candidates)

    new_items = []
    # 본문 수집이 한 번 막히면 그 회차에는 더 두드리지 않는다. 막힌 뒤에도 계속
    # 요청하면 차단만 길어지고, 어차피 링크는 목록에서 이미 알고 있다.
    detail_blocked = False

    for post_id, row in candidates.items():
        if post_id in seen:
            continue
        keyword = board.matches(row["title"])
        if not keyword:
            continue

        detail = None
        if not detail_blocked:
            try:
                detail = board.fetch_detail(post_id)
            except requests.RequestException as exc:
                detail_blocked = True
                print(
                    f"[{board.name}] 본문을 못 읽었습니다({post_id}): "
                    f"{type(exc).__name__}. 제목과 링크만 넣어 보냅니다."
                )

        if detail is None:
            detail = _detail_from_list_row(board, post_id, row)

        detail.update(
            keyword=keyword,
            post_id=post_id,
            board_id=board.board_id,
            board_name=board.name,
            board_tag=board.tag,
        )
        if not detail["title"]:
            detail["title"] = row["title"]
        new_items.append(detail)

    return new_items, set(candidates)


def main() -> None:
    parser = argparse.ArgumentParser(description="울산대 대회·공모전 공지 감시")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="메일을 보내지 않고 무엇이 걸렸는지 화면에만 출력한다(state도 건드리지 않음).",
    )
    args = parser.parse_args()

    state = load_state()
    items_to_send: list[dict] = []
    failures: list[str] = []

    for board in BOARDS:
        first_run = board.board_id not in state
        seen = state.get(board.board_id, set())

        # 한쪽 게시판이 죽어도 나머지는 확인하고, 대신 마지막에 종료 코드를 1로 낸다.
        try:
            new_items, all_ids = collect_new_items(board, seen, with_details=not first_run)
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 로그만 남기고 계속한다
            print(f"[{board.name}] 수집 실패: {type(exc).__name__}: {exc}")
            failures.append(board.name)
            continue

        if first_run:
            state[board.board_id] = all_ids
            print(
                f"[{board.name}] 최초 감시: 기존 글 {len(all_ids)}건을 읽음 처리했습니다. "
                "(메일 발송 없음)"
            )
            continue

        if not new_items:
            print(f"[{board.name}] 새로운 공지가 없습니다.")
            continue

        print(f"[{board.name}] 새 공지 {len(new_items)}건")
        items_to_send.extend(new_items)

    if args.dry_run:
        for item in items_to_send:
            print("=" * 60)
            print(format_body(item))
        print("=" * 60)
        print(f"dry-run: 메일 {len(items_to_send)}건을 보낼 차례였습니다. state는 그대로 둡니다.")
        return

    if items_to_send:
        send_email(items_to_send)
        for item in items_to_send:
            state.setdefault(item["board_id"], set()).add(item["post_id"])

    save_state(state)

    if failures:
        raise SystemExit(f"수집에 실패한 게시판: {', '.join(failures)}")


if __name__ == "__main__":
    main()
