"""
울산대학교 SW중심대학사업단 공지를 감시해서 대회·공모전 공고가 새로 올라오면
이메일로 알려주는 스크립트.

대표 홈페이지(www.ulsan.ac.kr)와 학부 홈페이지(ict.ulsan.ac.kr)도 감시해 봤지만,
학교 서버가 IP당 요청 수를 제한해서 GitHub Actions 러너에서 다섯 번째 요청부터
연결을 거절했다(ConnectTimeout / Connection refused). 해외 IP 차단은 아니고
요청 수 제한이다. 그래서 안정적으로 되는 곳만 남겼다.

SW중심대학사업단 사이트만 학교 전산망 밖에 있다. 화면은 CloudFront에서 오고
게시판 데이터는 외부 CMS(didisam)의 공개 JSON API로 나온다. 인증이 필요 없고
목록 한 번이면 제목·작성일·글번호가 전부 온다. HTML을 긁지 않으니 화면이 바뀌어도
잘 안 깨진다.

동작 방식:
1. 목록 API에서 최근 공지를 받아온다.
2. 제목이 TARGET_KEYWORDS에 걸리고 state/seen.json에 없는 글이면
   상세 API로 본문·첨부파일을 가져온다.
3. 이메일로 발송하고 글 번호를 state/seen.json에 기록한다.

최초 실행 때는 메일을 보내지 않고 지금 올라와 있는 글을 읽음 처리만 한다.
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

# 게시판 데이터가 나오는 곳. 사이트 화면은 https://sw.ulsan.ac.kr/site/swulsan/notices
API_BASE = "https://prd-community.didisam.com/api/v3/sampage/notice"
SITE_BASE = "https://sw.ulsan.ac.kr/site"
SITE_SLUG = "swulsan"  # 어느 사이트의 게시판인지는 요청 헤더의 slug로 가른다

STATE_FILE = Path(__file__).parent / "state" / "seen.json"
PAGE_SIZE = 30  # 한 번에 받아올 공지 수. 2시간 주기면 이 정도로 충분하다
TIMEOUT = (15, 30)  # (연결, 응답)
REQUEST_DELAY = 1.0

# 제목에 이 중 하나라도 들어 있으면 알림 대상. 띄어쓰기와 대소문자는 무시하고 비교한다.
TARGET_KEYWORDS = [
    "대회",
    "공모전",
    "해커톤",
    "경진",
    "챌린지",
    "challenge",
    "장학",  # 이 게시판에도 자격증 응시료 지원 같은 공고가 가끔 올라온다
]

# 위 키워드에 걸려도 이미 끝난 소식은 뺀다. 남의 수상 소식까지 받을 이유는 없다.
EXCLUDE_KEYWORDS = ["수상자", "명단", "최종 결과", "결과 안내"]

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


def _build_session() -> requests.Session:
    """연결을 재사용하고, 일시적인 오류는 간격을 늘려가며 재시도하는 세션."""
    session = requests.Session()
    session.headers.update({**HEADERS, "slug": SITE_SLUG})
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


def api_get(path: str = "", params: dict | None = None) -> dict:
    resp = SESSION.get(f"{API_BASE}{path}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return resp.json()["result"]


def post_url(post_id: str) -> str:
    return f"{SITE_BASE}/{SITE_SLUG}/notices/{post_id}"


def load_seen() -> set:
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("seen_ids", []))
    return set()


def save_seen(seen_ids: set) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({"seen_ids": sorted(seen_ids)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def matches_target(title: str) -> str | None:
    normalized = _normalize(title)
    if any(_normalize(word) in normalized for word in EXCLUDE_KEYWORDS):
        return None
    for keyword in TARGET_KEYWORDS:
        if _normalize(keyword) in normalized:
            return keyword
    return None


def fetch_list() -> dict[str, dict]:
    result = api_get("/community", {"page_size": PAGE_SIZE, "page": 1})

    rows: dict[str, dict] = {}
    for row in result.get("data", []):
        post_id = str(row["notice_id"])
        # 상단 고정 공지는 목록에 두 번 나오므로 글 번호로 덮어쓴다.
        rows[post_id] = {
            "post_id": post_id,
            "title": _clean(row.get("title", "")),
            "date": (row.get("insert_date") or "")[:10],
        }
    return rows


def fetch_detail(post_id: str) -> dict:
    row = api_get(f"/{post_id}")

    body = BeautifulSoup(row.get("contents") or "", "html.parser")
    content = re.sub(r"\n{3,}", "\n\n", body.get_text("\n", strip=True).replace("\xa0", " "))
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
        "url": post_url(post_id),
    }


def format_body(item: dict) -> str:
    lines = [
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
            msg["Subject"] = Header(f"[SW 공지] {item['title']}", "utf-8")
            msg["From"] = email_user
            msg["To"] = ", ".join(recipients)
            server.sendmail(email_user, recipients, msg.as_string())
            print(f"메일 발송 완료: {item['title']} → {', '.join(recipients)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="울산대 SW중심대학사업단 공지 감시")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="메일을 보내지 않고 무엇이 걸렸는지 화면에만 출력한다(state도 건드리지 않음).",
    )
    args = parser.parse_args()

    seen = load_seen()
    candidates = fetch_list()

    new_items = []
    for post_id, row in candidates.items():
        if post_id in seen:
            continue
        keyword = matches_target(row["title"])
        if not keyword:
            continue
        detail = fetch_detail(post_id)
        detail["keyword"] = keyword
        detail["post_id"] = post_id
        if not detail["title"]:
            detail["title"] = row["title"]
        new_items.append(detail)

    if args.dry_run:
        for item in new_items:
            print("=" * 60)
            print(format_body(item))
        print("=" * 60)
        print(f"dry-run: 메일 {len(new_items)}건을 보낼 차례였습니다. state는 그대로 둡니다.")
        return

    if not STATE_FILE.exists():
        save_seen(seen | set(candidates))
        print(f"최초 실행: 기존 글 {len(candidates)}건을 읽음 처리했습니다. (메일 발송 없음)")
        return

    if not new_items:
        print("새로운 공지가 없습니다.")
        return

    send_email(new_items)

    seen.update(item["post_id"] for item in new_items)
    save_seen(seen)


if __name__ == "__main__":
    main()
