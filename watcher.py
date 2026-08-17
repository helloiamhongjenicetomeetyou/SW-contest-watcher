"""
울산대학교 공지 게시판을 감시해서 장학 관련 공고가 새로 올라오면 이메일로 알려주는 스크립트.

울산대에는 장학 공고만 모아둔 공개 게시판이 없다. 교내장학 공고는
UWINS(로그인 필요) 안쪽에 있고, 밖에서 볼 수 있는 건 두 갈래다.

  1. 대표 홈페이지 일반공지 - 국가장학금·국가근로, 교외 재단장학 공고가 올라온다.
     이 게시판은 제목 검색이 GET으로 동작하므로 키워드로 바로 질의한다.
  2. ICT융합학부 공지 - 학부 우수장학·봉사장학처럼 대표 홈페이지에 안 올라오는
     공고가 여기에만 있다. 검색이 없어서 최근 페이지를 훑어 제목을 맞춰본다.

동작 방식:
1. 각 게시판에서 후보 글 목록을 모은다.
2. 제목에 TARGET_KEYWORDS 중 하나가 들어 있고 state/seen.json에 없는 글이면
   상세 페이지를 읽어 본문 전체·작성일·첨부파일을 가져온다.
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

# (연결, 응답) 타임아웃. GitHub Actions 러너(미국)에서 국내 서버로 붙을 때
# 연결이 느리게 잡히는 일이 있어 연결 쪽을 넉넉히 준다.
TIMEOUT = (15, 30)

# 요청 사이 간격. 짧은 시간에 몰아치면 학교 서버가 연결을 안 받아준다.
REQUEST_DELAY = 1.0

# 제목에 이 중 하나라도 들어 있으면 알림 대상.
# 특정 장학금만 받고 싶으면 여기를 이름으로 바꾼다. 예) ["우수장학", "국가근로장학"]
TARGET_KEYWORDS = ["장학"]

# 위 키워드에 걸려도 제목에 이 단어가 있으면 거른다.
# 신청과 무관한 글(예: "[한국장학재단] 공공데이터 개방 목록 안내")이 자꾸 오면 여기에 추가한다.
EXCLUDE_KEYWORDS: list[str] = []

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
    return re.sub(r"\s+", "", text)


def _build_session() -> requests.Session:
    """
    연결을 재사용하는 세션. 매 요청마다 TCP 연결을 새로 열면 학교 서버가
    도중에 연결을 안 받아줘서 ConnectTimeout이 난다(러너 IP 기준 제한으로 보인다).
    keep-alive로 연결을 붙들고, 그래도 실패하면 간격을 늘려가며 재시도한다.
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


def _get(url: str, params: dict) -> BeautifulSoup:
    resp = SESSION.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return BeautifulSoup(resp.text, "html.parser")


def _body_text(element) -> str:
    if element is None:
        return "(본문을 불러오지 못했습니다)"
    text = element.get_text("\n", strip=True).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", text)


class UnivBoard:
    """
    대표 홈페이지 CMS 게시판(www.ulsan.ac.kr/kor/CMS/Board/Board.do).

    제목 검색(searchID=sch001)이 GET으로 열려서 키워드당 한 번만 요청하면 된다.
    페이지를 훑는 방식과 달리 공지가 한꺼번에 몰려도 놓치지 않는다.
    """

    def __init__(self, board_id: str, name: str, tag: str, mcode: str, mgr_seq: str):
        self.board_id = board_id
        self.name = name
        self.tag = tag
        self.mcode = mcode
        self.mgr_seq = mgr_seq
        self.base_url = "https://www.ulsan.ac.kr/kor/CMS/Board/Board.do"

    def post_url(self, post_id: str) -> str:
        return (
            f"{self.base_url}?mCode={self.mcode}&mode=view"
            f"&mgr_seq={self.mgr_seq}&board_seq={post_id}"
        )

    def fetch_candidates(self, keywords: list[str]) -> dict[str, dict]:
        candidates: dict[str, dict] = {}
        for keyword in keywords:
            soup = _get(self.base_url, {
                "mCode": self.mcode,
                "mode": "list",
                "mgr_seq": self.mgr_seq,
                "searchID": "sch001",  # 제목 검색
                "searchKeyword": keyword,
            })
            for row in soup.select("table.board-list-table tbody tr"):
                link = row.select_one("td.subject a[href*='board_seq=']")
                if not link:
                    continue
                m = re.search(r"board_seq=(\d+)", link.get("href", ""))
                if not m:
                    continue
                date_el = row.select_one("td.date")
                # 상단 고정 공지는 검색 결과마다 중복으로 나오므로 글 번호로 덮어쓴다.
                candidates[m.group(1)] = {
                    "post_id": m.group(1),
                    "title": _clean(link.get_text()),
                    "date": _clean(date_el.get_text()) if date_el else "",
                }
        return candidates

    def fetch_detail(self, post_id: str) -> dict:
        soup = _get(self.base_url, {
            "mCode": self.mcode,
            "mode": "view",
            "mgr_seq": self.mgr_seq,
            "board_seq": post_id,
        })

        title_el = soup.select_one("h4.vtitle")
        category_el = title_el.select_one("span.cate") if title_el else None
        category = _clean(category_el.get_text()) if category_el else ""
        if category_el:
            category_el.extract()  # 제목에서 [일반] 같은 분류 표시를 뗀다

        info = soup.select("div.vtitle-winfo span.txt")
        attachments = [
            _clean(a.get_text()) for a in soup.select("ul.board-view-filelist li a")
        ]

        return {
            "title": _clean(title_el.get_text()) if title_el else "",
            "category": category,
            "writer": _clean(info[0].get_text()) if info else "",
            "date": _clean(info[1].get_text()) if len(info) > 1 else "",
            "content": _body_text(soup.select_one("#boardContents")),
            "attachments": attachments,
            "url": self.post_url(post_id),
        }


class DeptBoard:
    """
    학과 홈페이지 게시판(ict.ulsan.ac.kr 계열, ?action=view&no=...).

    제목 검색이 GET으로 안 열려서 최근 pages_to_check 페이지를 훑는다.
    같은 CMS를 쓰는 다른 학부 사이트는 board_url만 바꾸면 그대로 붙는다.
    """

    def __init__(
        self, board_id: str, name: str, tag: str, board_url: str, pages_to_check: int = 2
    ):
        self.board_id = board_id
        self.name = name
        self.tag = tag
        self.board_url = board_url.rstrip("/")
        self.pages_to_check = pages_to_check

    def post_url(self, post_id: str) -> str:
        return f"{self.board_url}?action=view&no={post_id}"

    def fetch_candidates(self, keywords: list[str]) -> dict[str, dict]:
        candidates: dict[str, dict] = {}
        for page in range(1, self.pages_to_check + 1):
            soup = _get(self.board_url, {"pageIndex": page})
            for row in soup.select("table.a_brdList tbody tr"):
                link = row.select_one("td.bdlTitle a[href*='no=']")
                if not link:
                    continue
                m = re.search(r"no=(\d+)", link.get("href", ""))
                if not m:
                    continue
                date_el = row.select_one("td.bdlDate")
                # 상단 고정 공지(tr.noti)는 모든 페이지에 나오므로 글 번호로 덮어쓴다.
                candidates[m.group(1)] = {
                    "post_id": m.group(1),
                    "title": _clean(link.get_text()),
                    "date": _clean(date_el.get_text()) if date_el else "",
                }
        return candidates

    def fetch_detail(self, post_id: str) -> dict:
        soup = _get(self.board_url, {"action": "view", "no": post_id})

        title_el = soup.select_one("td.bdvTitle")

        # 작성자·작성일·조회수는 제목 바로 아랫줄에 th/td 쌍으로 들어 있다.
        info: dict[str, str] = {}
        info_row = title_el.find_parent("tr").find_next_sibling("tr") if title_el else None
        if info_row:
            cells = info_row.find_all(["th", "td"])
            for label, value in zip(cells[::2], cells[1::2]):
                info[_clean(label.get_text())] = _clean(value.get_text())

        attachments = [
            _clean(a.get_text())
            for a in soup.select("div.bdvfile ul li a[href*='boardDownload.do']")
        ]

        return {
            "title": _clean(title_el.get_text()) if title_el else "",
            "category": "",
            "writer": info.get("작성자", ""),
            "date": info.get("작성일", ""),
            "content": _body_text(soup.select_one("td.bdvEdit")),
            "attachments": attachments,
            "url": self.post_url(post_id),
        }


BOARDS = [
    UnivBoard(
        board_id="univ-notice",
        name="울산대학교 일반공지",
        tag="울산대 장학",
        mcode="MN113",
        mgr_seq="35",
    ),
    DeptBoard(
        board_id="ict-notice",
        name="ICT융합학부 공지사항",
        tag="ICT 장학",
        board_url="https://ict.ulsan.ac.kr/ict/5778",
    ),
]


def load_state() -> dict[str, set]:
    if not STATE_FILE.exists():
        return {}
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {board_id: set(ids) for board_id, ids in data.get("seen", {}).items()}


def save_state(state: dict[str, set]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seen": {board_id: sorted(ids) for board_id, ids in sorted(state.items())}}
    STATE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def matches_target(title: str) -> str | None:
    normalized = _normalize(title)
    if any(_normalize(word) in normalized for word in EXCLUDE_KEYWORDS):
        return None
    for keyword in TARGET_KEYWORDS:
        if _normalize(keyword) in normalized:
            return keyword
    return None


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
    email_to = os.environ.get("EMAIL_TO", email_user)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=TIMEOUT) as server:
        server.starttls()
        server.login(email_user, email_pass)

        for item in items:
            msg = MIMEText(format_body(item), "plain", "utf-8")
            msg["Subject"] = Header(f"[{item['board_tag']}] {item['title']}", "utf-8")
            msg["From"] = email_user
            msg["To"] = email_to
            server.sendmail(email_user, [email_to], msg.as_string())
            print(f"메일 발송 완료: {item['title']}")


def collect_new_items(board, seen: set, with_details: bool = True) -> tuple[list[dict], set]:
    """
    게시판에서 알림 보낼 글과, 이번에 확인한 전체 글 번호를 돌려준다.

    with_details=False면 목록만 읽고 상세 페이지는 건너뛴다. 최초 감시 때는
    어차피 메일을 안 보내므로 요청 수를 목록 몇 번으로 줄이려고 쓴다.
    """
    candidates = board.fetch_candidates(TARGET_KEYWORDS)
    if not with_details:
        return [], set(candidates)

    new_items = []
    for post_id, row in candidates.items():
        if post_id in seen:
            continue
        keyword = matches_target(row["title"])
        if not keyword:
            continue
        detail = board.fetch_detail(post_id)
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
    parser = argparse.ArgumentParser(description="울산대 장학 공지 감시")
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
            print(f"[{board.name}] 새로운 장학 공지가 없습니다.")
            continue

        print(f"[{board.name}] 새 장학 공지 {len(new_items)}건")
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
