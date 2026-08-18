# 울산대 대회·공모전 알리미

울산대학교 공지에 **대회·공모전·해커톤 공고가 새로 올라오면 이메일로** 보내줍니다.
GitHub Actions가 2시간마다 돌기 때문에 컴퓨터를 켜둘 필요도, 서버를 띄울 필요도 없습니다.

| 감시 대상 | 여기에 올라오는 것 | 수집 방식 |
| --- | --- | --- |
| [대표 홈페이지 일반공지](https://www.ulsan.ac.kr/kor/CMS/Board/Board.do?mCode=MN113) | 교외 AI·SW 해커톤과 공모전. 학교가 받아서 올려줍니다 | 목록 2페이지를 받아 제목을 거름 |
| [SW중심대학사업단 공지](https://sw.ulsan.ac.kr/site/swulsan/notices) | 학내 SW 대회 (캡스톤디자인, 프로그래밍 경진대회, AI 해커톤) | 공개 JSON API 한 번 |

메일 제목 앞에 `[울산대 SW대회]` / `[SW 대회]`가 붙어서 어디서 온 건지 바로 구분됩니다.

## 대표 홈페이지는 SW 대회만 거릅니다

이 게시판에는 교외 기관 공고가 그대로 올라옵니다. 대회 단어만으로 거르면
`한우 곤포 나르기 대회`, `가마레이스`, `안보토론대회`, `그림 공모전`까지 전부 딸려옵니다.

그래서 이 게시판만 **대회 계열 단어에 더해 `SW_KEYWORDS` 중 하나가 제목에 있어야** 알림을 보냅니다.
실제 공고 42건으로 맞춰본 결과입니다.

| | 예 |
| --- | --- |
| 통과 | `ESG × AI 챌린지 해커톤`, `공공데이터·AI 활용 대학생 경진대회`, `NHN GAME X AI 해커톤`, `자율주행 해커톤 경진대회` |
| 차단 | `한우 곤포 나르기 대회`, `수원 가마레이스`, `청년 안보 스피치 대회`, `장단삼백요리 경연대회` |

SW중심대학사업단 게시판은 전부 SW 대회라 이 조건을 안 겁니다.

`AI`처럼 영문·숫자로만 된 키워드는 **단어 단위로** 찾습니다. 그냥 부분 문자열로 찾으면
`it`이 `digital`에, `ar`이 `start`에 걸려서 엉뚱한 글이 딸려옵니다.

## 요청 수를 아끼는 이유

학교 서버(`www.ulsan.ac.kr`)는 **IP당 요청 수를 제한**합니다. 러너에서 다섯 번째 요청부터
연결을 거절한 적이 있습니다(`ConnectTimeout`, `Connection refused`). 해외 IP 차단은 아니고
요청 수 제한에 가까운 동작입니다.

그래서 대표 홈페이지는 **키워드마다 검색하지 않고 목록 두 페이지만** 받아 제목을 직접 거릅니다.
키워드를 아무리 늘려도 요청 수는 그대로입니다. 목록 2페이지면 나흘치라 2시간 주기에 넉넉합니다.

평소 한 회차에 나가는 요청은 **목록 3번 + 새 글 상세 몇 번**입니다.
그래도 본문을 못 읽으면 **제목·작성일·링크만 넣어서 메일을 보냅니다.** 본문이 빠지더라도
"새 공고가 떴다"는 알림 자체는 놓치지 않는 쪽을 택했습니다.

SW중심대학사업단 사이트만 학교 전산망 밖(CloudFront + 외부 CMS)이라 요청 제한이 없습니다.

## 동작 방식

1. GitHub Actions가 2시간마다 `watcher.py`를 실행합니다.
2. 두 게시판에서 후보 글을 모아 제목이 `TARGET_KEYWORDS`에 걸리는 글을 고릅니다.
3. `state/seen.json`에 없는 글이면 상세 페이지를 읽어 **본문·작성일·첨부파일 목록·링크**를 담아 메일로 보냅니다.
4. 보낸 글 번호를 `state/seen.json`에 적고 리포지토리에 커밋합니다.

게시판을 **처음 감시할 때는 메일을 보내지 않고 읽음 처리만** 합니다.
게시판별로 따로 판단하므로, 나중에 게시판을 하나 더 붙여도 그 게시판의 과거 글이 쏟아지지 않습니다.

`수상자`·`명단`·`최종 결과`·`개최 취소`가 제목에 든 글은 뺍니다. 이미 끝난 소식이라
`EXCLUDE_KEYWORDS`에 넣어뒀습니다.

한쪽 게시판이 죽어도 나머지는 정상적으로 확인하고, 대신 실행이 실패 처리돼서
GitHub이 알림 메일을 보내줍니다.

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

`EMAIL_TO`는 **쉼표로 여러 개**를 적을 수 있습니다. 학교 메일과 개인 메일로 같이 받으려면
`본인@mail.ulsan.ac.kr, 본인@gmail.com` 처럼 씁니다.

학교 메일(`mail.ulsan.ac.kr`)은 Microsoft 365라서 Gmail에서 보낸 메일이 잘 들어갑니다.
처음 한두 통이 정크 메일함으로 갈 수 있으니, 안 오면 거기부터 보세요.

### 3. 첫 실행

`Actions > SW Contest Watcher > Run workflow`로 한 번 수동 실행합니다.
이때는 메일이 오지 않고 현재 글만 읽음 처리됩니다. 그 다음부터 새 공고에 메일이 옵니다.

## GitHub Actions에 대해

[`.github/workflows/watch.yml`](.github/workflows/watch.yml)이 알리미 본체입니다.

```yaml
on:
  schedule:
    - cron: "0 */2 * * *"   # 2시간마다 (UTC)
  workflow_dispatch: {}     # 손으로 실행하는 버튼
```

- **state를 리포지토리에 커밋해서** 무엇을 이미 보냈는지 기억합니다. 그래서 워크플로에 `permissions: contents: write`가 들어 있습니다. 푸시 단계에서 403이 나면 `Settings > Actions > General > Workflow permissions`를 `Read and write`로 바꾸면 됩니다.
- **cron은 정시에 안 맞습니다.** GitHub 부하에 따라 5~20분씩 밀리고, 아주 드물게 건너뛰기도 합니다.
- **60일 동안 리포지토리에 사람 활동이 없으면 스케줄이 자동으로 꺼집니다.** 봇 커밋은 활동으로 안 쳐줍니다. 꺼지기 전에 GitHub이 메일로 알려주고, `Actions` 탭에서 다시 켜면 됩니다.
- **실패한 작업을 "Re-run"하면 그때 그 커밋으로 다시 돕니다.** 코드를 고친 뒤에는 `Run workflow`로 새로 실행해야 고친 코드가 돕니다.
- **작업이 도는 동안 누가 먼저 푸시하면** state 커밋이 밀립니다(`! [rejected] main -> main`). 그때는 원격 state와 이번 state를 **합쳐서** 다시 올립니다(최대 3번). 덮어쓰지 않는 이유는, 이미 알림을 보낸 글이 되살아나면 같은 메일이 두 번 가기 때문입니다.
- 실행 기록과 로그는 `Actions` 탭에 남습니다. 메일이 안 오면 여기 로그부터 봅니다.

### 학교 서버가 또 막히면

[`Probe Ulsan`](.github/workflows/probe.yml) 워크플로를 수동 실행하면 러너에서 학교 서버로
요청을 순서대로 던져 **몇 번째에서 깨지는지** 알려줍니다. 재시도를 꺼서 깨지는 지점을 그대로 봅니다.

- 전부 성공 → 그때 실패는 일시적인 문제
- 중간부터 실패 → 요청 수 제한. `PAGES_TO_CHECK`를 줄이거나 `REQUEST_DELAY`를 늘립니다
- 처음부터 실패 → IP 차단

## 로컬에서 확인하기

```bash
pip install -r requirements.txt
python watcher.py --dry-run
```

`--dry-run`은 **메일을 보내지 않고** 무엇이 걸렸는지 화면에만 출력하고 `state/seen.json`도 건드리지 않습니다.
키워드를 바꿔놓고 뭐가 걸리는지 볼 때 씁니다.

## 고치고 싶을 때

### 받고 싶은 것만 받기

`watcher.py`의 `TARGET_KEYWORDS`를 바꿉니다.

```python
TARGET_KEYWORDS = [
    "대회", "공모전", "공모", "해커톤", "hackathon", "경진",
    "경연", "챌린지", "challenge", "아이디어톤", "콘테스트", "contest",
]
EXCLUDE_KEYWORDS = ["수상자", "명단", "최종 결과", "결과 안내", "개최 취소"]
```

대표 홈페이지에 걸리는 SW 조건은 `SW_KEYWORDS`입니다. 여기를 비우면 모든 대회가 옵니다.
반대로 좁히려면 `"콘텐츠"` 같은 느슨한 말을 빼면 됩니다.

띄어쓰기와 대소문자는 무시하고 비교하므로 `AI 융합 해커톤`으로 적어도 같은 글이 걸립니다.
목록을 받아놓고 거르는 방식이라 **키워드를 늘려도 요청 수는 그대로**입니다.
장학 공고까지 받고 싶으면 `"장학"`을, 인턴십까지 받고 싶으면 `"인턴"`을 넣으면 됩니다.

### 확인 주기

`.github/workflows/watch.yml`의 `cron: "0 */2 * * *"`를 고칩니다. UTC 기준입니다.

### 얼마나 거슬러 올라가서 볼지

대표 홈페이지는 `UnivBoard(..., pages_to_check=2)`, SW사업단은 `SwBoard(..., page_size=30)`입니다.
대표 홈페이지는 하루 4~5건 올라와서 2페이지면 나흘치입니다.

## 파일

| 경로 | 하는 일 |
| --- | --- |
| `watcher.py` | 공지 수집·필터·메일 발송 전부 |
| `state/seen.json` | 알림 보낸 글 번호. 게시판별로 나눠 저장 |
| `scripts/merge_state.py` | 푸시가 밀렸을 때 원격 state와 합치기 |
| `scripts/probe_ulsan.py` | 학교 서버가 러너에서 되는지 재보는 진단용 |
| `.github/workflows/watch.yml` | 2시간마다 실행하고 state 커밋 |
| `.github/workflows/probe.yml` | 진단용. 손으로 실행할 때만 돔 |

`state/seen.json`은 이렇게 생겼습니다.

```json
{
  "seen": {
    "sw-notice": ["4523", "4557"],
    "univ-notice": ["90892", "90895"]
  }
}
```

---

원본: https://github.com/wlstmd/kmu-scholarship-watcher
