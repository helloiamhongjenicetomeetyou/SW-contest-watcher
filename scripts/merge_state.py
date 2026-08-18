"""
이번 실행에서 만든 state와 원격(origin/main)의 state를 합친다.

state를 리포지토리에 커밋하는 구조라, 커밋을 만드는 동안 다른 실행이나 사람이
먼저 푸시하면 푸시가 거절된다. 그때 원격 것을 그냥 덮어쓰면 이미 알림을 보낸 글이
'아직 안 본 글'로 되살아나서 같은 메일이 두 번 간다. 그래서 게시판별로 글 번호를
합집합으로 만든 뒤 원격 위에 새로 올린다.

게시판이 하나뿐이던 시절의 형식({"seen_ids": [...]})도 읽어서 새 형식으로 옮긴다.

사용법: python scripts/merge_state.py [내보낼 경로]
경로를 안 주면 state/seen.json에 그대로 쓴다.
"""

import json
import pathlib
import subprocess
import sys

STATE_FILE = pathlib.Path("state/seen.json")
REMOTE_REF = "origin/main:state/seen.json"
LEGACY_BOARD_ID = "sw-notice"  # 예전 seen_ids는 SW 게시판 기록이었다


def _parse(raw: str) -> dict[str, set]:
    data = json.loads(raw)
    if "seen_ids" in data:
        return {LEGACY_BOARD_ID: set(data["seen_ids"])}
    return {board_id: set(ids) for board_id, ids in data.get("seen", {}).items()}


def local_state() -> dict[str, set]:
    if not STATE_FILE.exists():
        return {}
    return _parse(STATE_FILE.read_text(encoding="utf-8"))


def remote_state() -> dict[str, set]:
    try:
        raw = subprocess.check_output(
            ["git", "show", REMOTE_REF], text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        return {}  # 원격에 아직 state가 없다(최초 실행)
    return _parse(raw)


def main() -> None:
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else STATE_FILE

    mine, theirs = local_state(), remote_state()
    merged = {
        board_id: mine.get(board_id, set()) | theirs.get(board_id, set())
        for board_id in set(mine) | set(theirs)
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"seen": {b: sorted(ids) for b, ids in sorted(merged.items())}},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = ", ".join(
        f"{b} {len(mine.get(b, ()))}+{len(theirs.get(b, ()))}→{len(ids)}"
        for b, ids in sorted(merged.items())
    )
    print(f"state 합침: {summary}")


if __name__ == "__main__":
    main()
