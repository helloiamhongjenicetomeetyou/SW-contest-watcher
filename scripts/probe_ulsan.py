"""
학교 서버(www.ulsan.ac.kr, ict.ulsan.ac.kr)에 몇 번째 요청까지 되는지 재본다.

GitHub Actions 러너에서 다섯 번째 요청부터 연결이 거절돼서 학교 게시판을 뺐는데,
그게 정말 요청 수 제한인지 그때 GitHub 장애 때문이었는지 확인하려고 만들었다.

일부러 재시도를 끄고 요청을 순서대로 던진다. 몇 번째에서 무슨 오류로 깨지는지가
알고 싶은 값이라, 재시도가 붙으면 그게 가려진다.

사용법: python scripts/probe_ulsan.py [요청간격초]
"""

import sys
import time

import requests

DELAY = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"}

UNIV = "https://www.ulsan.ac.kr/kor/CMS/Board/Board.do"
ICT = "https://ict.ulsan.ac.kr/ict/5778"

PLAN = [
    ("www 목록(공모전 검색)", UNIV, {"mCode": "MN113", "mode": "list", "mgr_seq": "35",
                                    "searchID": "sch001", "searchKeyword": "공모전"}),
    ("www 목록(대회 검색)", UNIV, {"mCode": "MN113", "mode": "list", "mgr_seq": "35",
                                  "searchID": "sch001", "searchKeyword": "대회"}),
    ("www 목록(1페이지)", UNIV, {"mCode": "MN113", "page": 1}),
    ("www 목록(2페이지)", UNIV, {"mCode": "MN113", "page": 2}),
    ("www 상세 1", UNIV, {"mCode": "MN113", "mode": "view", "mgr_seq": "35", "board_seq": "90892"}),
    ("www 상세 2", UNIV, {"mCode": "MN113", "mode": "view", "mgr_seq": "35", "board_seq": "90856"}),
    ("www 상세 3", UNIV, {"mCode": "MN113", "mode": "view", "mgr_seq": "35", "board_seq": "90840"}),
    ("www 상세 4", UNIV, {"mCode": "MN113", "mode": "view", "mgr_seq": "35", "board_seq": "90834"}),
    ("www 상세 5", UNIV, {"mCode": "MN113", "mode": "view", "mgr_seq": "35", "board_seq": "90816"}),
    ("www 상세 6", UNIV, {"mCode": "MN113", "mode": "view", "mgr_seq": "35", "board_seq": "90769"}),
    ("ict 목록(1페이지)", ICT, {"pageIndex": 1}),
    ("ict 목록(2페이지)", ICT, {"pageIndex": 2}),
    ("ict 상세 1", ICT, {"action": "view", "no": "279063"}),
    ("ict 상세 2", ICT, {"action": "view", "no": "278269"}),
    ("ict 상세 3", ICT, {"action": "view", "no": "277510"}),
    ("ict 상세 4", ICT, {"action": "view", "no": "275189"}),
]


def outbound_ip() -> str:
    try:
        return requests.get("https://api.ipify.org", timeout=10).text.strip()
    except requests.RequestException as exc:
        return f"(확인 실패: {type(exc).__name__})"


def main() -> None:
    print(f"러너 바깥 IP: {outbound_ip()}")
    print(f"요청 간격: {DELAY}초 / 재시도 없음\n")

    session = requests.Session()  # 연결 재사용은 실제 코드와 같게 켜 둔다
    session.headers.update(HEADERS)

    results = []
    for i, (label, url, params) in enumerate(PLAN, start=1):
        started = time.monotonic()
        try:
            resp = session.get(url, params=params, timeout=(15, 30))
            elapsed = time.monotonic() - started
            ok = resp.status_code == 200
            print(f"{i:2}. {label:22} {resp.status_code}  {elapsed:5.1f}초  {len(resp.content):>7,}바이트")
            results.append((i, label, ok, str(resp.status_code)))
        except requests.RequestException as exc:
            elapsed = time.monotonic() - started
            print(f"{i:2}. {label:22} 실패  {elapsed:5.1f}초  {type(exc).__name__}")
            results.append((i, label, False, type(exc).__name__))
        time.sleep(DELAY)

    ok_count = sum(1 for *_, ok, _ in results if ok)
    print(f"\n성공 {ok_count}/{len(results)}")

    failed = [r for r in results if not r[2]]
    if not failed:
        print("전부 성공했습니다. 학교 게시판을 다시 붙여도 됩니다.")
        return

    first = failed[0]
    print(f"처음 막힌 지점: {first[0]}번째 요청({first[1]}) — {first[3]}")
    print("성공하다가 중간부터 막혔다면 요청 수 제한, 처음부터 막혔다면 IP 차단 쪽입니다.")
    sys.exit(1)


if __name__ == "__main__":
    main()
