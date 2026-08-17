# 울산대 장학 공지 알리미

| 감시 대상 | 여기에만 올라오는 것 | 수집 방식 |
| --- | --- | --- |
| [대표 홈페이지 일반공지](https://www.ulsan.ac.kr/kor/CMS/Board/Board.do?mCode=MN113) | 국가장학금·국가근로장학, 손태희·세종이도 같은 교외 재단장학 | 게시판 **제목 검색**이 GET으로 열려서 키워드로 바로 질의 |
| [ICT융합학부 공지사항](https://ict.ulsan.ac.kr/ict/5778) | 학부 우수장학, 봉사장학(트랙), 역량개발·빛냄장학 | 검색이 없어서 최근 2페이지를 훑어 제목 매칭 |

둘은 서로 겹치지 않습니다. `ICT융합학부 우수장학 서류 제출 안내`는 대표 홈페이지에 안 올라오고,
`국가근로장학금 신청기간 안내`는 학부 공지에 안 올라오는 식입니다. 그래서 둘 다 봅니다.
메일 제목 앞에 `[울산대 장학]` / `[ICT 장학]`이 붙어서 어느 게시판에서 온 건지 바로 구분됩니다.

**못 보는 것:** UWINS(`uwin.ulsan.ac.kr`) 학사공지는 로그인이 필요해서 이 스크립트로는 안 됩니다.
교내장학 중 UWINS에만 뜨는 공고는 여전히 직접 확인해야 합니다.

## 동작 방식

1. GitHub Actions가 2시간마다 `watcher.py`를 실행합니다.
2. 두 게시판에서 후보 글을 모아 제목에 `TARGET_KEYWORDS`(기본값 `장학`)가 들어간 글을 고릅니다.
3. `state/seen.json`에 없는 글이면 상세 페이지를 읽어 **본문 전체·작성일·첨부파일 목록·링크**를 담아 메일로 보냅니다.
4. 보낸 글 번호를 `state/seen.json`에 적고 리포지토리에 커밋합니다.

게시판을 **처음 감시할 때는 메일을 보내지 않고 읽음 처리만** 합니다.
이때는 목록만 읽고 상세 페이지는 건너뛰어서 요청이 세 번으로 끝납니다.
게시판별로 따로 판단하므로, 나중에 학부 게시판을 하나 더 붙여도 그 게시판의 과거 글이 쏟아지지 않습니다.

학교 서버가 짧은 시간에 몰아치는 요청을 막기 때문에, 연결을 재사용하고
요청 사이를 1초 띄우며 실패하면 3초·6초·12초 간격으로 세 번까지 다시 시도합니다.

한쪽 게시판이 죽어도(사이트 개편·점검 등) 나머지 한쪽은 정상적으로 확인하고,
대신 실행이 실패 처리돼서 GitHub이 알림 메일을 보내줍니다.

## 준비

### 1. Gmail 앱 비밀번호

2단계 인증을 켠 계정에서 [앱 비밀번호](https://myaccount.google.com/apppasswords)를 발급합니다.
평소 쓰는 구글 비밀번호로는 SMTP 로그인이 안 됩니다.

### 2. GitHub Secrets

리포지토리 `Settings > Secrets and variables > Actions > New repository secret`.

| 이름 | 값 |
| --- | --- |
| `EMAIL_USER` | 보내는 Gmail 주소 |
| `EMAIL_PASS` | 위에서 발급한 앱 비밀번호 (16자리, 공백 없이) |
| `EMAIL_TO` | 받을 주소 (생략하면 `EMAIL_USER`로 보냄) |

Gmail이 아니면 워크플로에 `SMTP_HOST`, `SMTP_PORT`를 넣어 바꿀 수 있습니다.

### 3. 첫 실행

`Actions > UOU Scholarship Watcher > Run workflow`로 한 번 수동 실행합니다.
이때는 메일이 오지 않고 현재 글만 읽음 처리됩니다. 그 다음부터 새 공고에 메일이 옵니다.

## GitHub Actions에 대해

[`.github/workflows/watch.yml`](.github/workflows/watch.yml)이 전부입니다.

```yaml
on:
  schedule:
    - cron: "0 */2 * * *"   # 2시간마다 (UTC)
  workflow_dispatch: {}     # 손으로 실행하는 버튼
```

- **state를 리포지토리에 커밋해서** 무엇을 이미 보냈는지 기억합니다. 그래서 워크플로에 `permissions: contents: write`가 들어 있습니다. 푸시 단계에서 403이 나면 `Settings > Actions > General > Workflow permissions`를 `Read and write`로 바꾸면 됩니다.
- **cron은 정시에 안 맞습니다.** GitHub 부하에 따라 5~20분씩 밀리고, 아주 드물게 건너뛰기도 합니다. 공고 마감이 촉박한 게 아니라면 문제되지 않습니다.
- **60일 동안 리포지토리에 사람 활동이 없으면 스케줄이 자동으로 꺼집니다.** 봇 커밋은 활동으로 안 쳐줍니다. 꺼지기 전에 GitHub이 메일로 알려주고, `Actions` 탭에서 다시 켜면 됩니다.
- **`ConnectTimeout`으로 실패하는 경우가 있습니다.** 러너는 미국에 있어서 국내 서버가 연결을 늦게 받거나 거절할 때가 있습니다. 재시도로 대부분 넘어가지만 그래도 실패하면 그 회차만 건너뛰고 2시간 뒤에 다시 시도합니다. 실패한 회차의 글은 state에 기록되지 않으므로 다음 실행 때 그대로 잡힙니다.
- 실행 기록과 로그는 `Actions` 탭에 남습니다. 메일이 안 오면 여기 로그부터 봅니다.

## 로컬에서 확인하기

```bash
pip install -r requirements.txt
python watcher.py --dry-run
```

`--dry-run`은 **메일을 보내지 않고** 무엇이 걸렸는지 화면에만 출력하고 `state/seen.json`도 건드리지 않습니다.
키워드를 바꿔놓고 뭐가 걸리는지 볼 때 씁니다.

## 고치고 싶을 때

### 받고 싶은 장학금만 받기

`watcher.py`의 `TARGET_KEYWORDS`를 바꿉니다. 기본값은 `장학` 하나라 장학이 들어간 공고가 전부 옵니다.

```python
TARGET_KEYWORDS = ["ICT융합학부 우수장학", "국가근로장학", "봉사장학"]
```

띄어쓰기는 무시하고 비교하므로 `국가 근로 장학`으로 적어도 같은 글이 걸립니다.

반대로 특정 글만 빼고 싶으면 `EXCLUDE_KEYWORDS`에 넣습니다.
`[한국장학재단] 공공데이터 개방 목록 안내`처럼 장학은 들어갔지만 신청과 무관한 공지가 자꾸 올 때 씁니다.

### 다른 학부 게시판 추가하기

학과 홈페이지는 대부분 같은 CMS(`?action=view&no=`)를 씁니다. `BOARDS`에 한 줄 더 넣으면 됩니다.

```python
DeptBoard(
    board_id="ce-notice",
    name="건설환경공학부 공지사항",
    tag="건설환경 장학",
    board_url="https://ce.ulsan.ac.kr/ce/2209",
),
```

`board_id`는 `state/seen.json`의 키라서 게시판마다 겹치지 않게 정합니다.
추가한 게시판은 다음 실행 때 읽음 처리만 되고, 그 다음 새 글부터 메일이 옵니다.

### 확인 주기

`.github/workflows/watch.yml`의 `cron: "0 */2 * * *"`를 고칩니다. UTC 기준입니다.

### 학부 게시판을 더 깊이 훑기

`DeptBoard(..., pages_to_check=4)` 로 늘립니다. 기본값 2페이지면 2시간 주기로는 충분합니다.
대표 홈페이지는 페이지를 훑는 대신 제목 검색을 쓰므로 이 값의 영향을 받지 않습니다.

## 파일

| 경로 | 하는 일 |
| --- | --- |
| `watcher.py` | 게시판 수집·필터·메일 발송 전부 |
| `state/seen.json` | 알림 보낸 글 번호. 게시판별로 나눠 저장 |
| `.github/workflows/watch.yml` | 2시간마다 실행하고 state 커밋 |

`state/seen.json`은 이렇게 생겼습니다.

```json
{
  "seen": {
    "ict-notice": ["279063", "278269"],
    "univ-notice": ["90892", "90840"]
  }
}
```

---

원본: https://github.com/wlstmd/kmu-scholarship-watcher
