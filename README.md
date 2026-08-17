# 울산대 SW중심대학 공지 알리미

[SW중심대학사업단 공지](https://sw.ulsan.ac.kr/site/swulsan/notices)에 **해커톤·경진대회·공모전 공고가
새로 올라오면 이메일로** 보내줍니다. GitHub Actions가 2시간마다 돌기 때문에
컴퓨터를 켜둘 필요도, 서버를 띄울 필요도 없습니다.

## 왜 이 게시판만 보는가

대표 홈페이지(`www.ulsan.ac.kr`)와 학부 홈페이지(`ict.ulsan.ac.kr`)도 감시해 봤지만
GitHub Actions에서 계속 실패했습니다. 학교 서버가 **IP당 요청 수를 제한**해서
다섯 번째 요청부터 연결을 거절합니다(`ConnectTimeout`, `Connection refused`).

해외 IP 차단은 아닙니다. 미국에서도 첫 요청은 정상적으로 열립니다. 호스트마다 네 번까지는
되고 다섯 번째부터 막히는, 요청 수 제한에 가까운 동작입니다.

SW중심대학사업단 사이트만 **학교 전산망 밖**에 있습니다. 화면은 CloudFront에서 오고
게시판 데이터는 외부 CMS의 공개 JSON API로 나옵니다. 그래서 요청이 막히지 않고,
목록 한 번이면 제목·작성일·글번호가 전부 옵니다. HTML을 긁지 않으니 화면이 바뀌어도 잘 안 깨집니다.

**못 보는 것:** 국가장학금·학부 우수장학처럼 학교 게시판에만 올라오는 공고는 이 알리미로 안 옵니다.
그건 직접 확인해야 합니다.

## 동작 방식

1. GitHub Actions가 2시간마다 `watcher.py`를 실행합니다.
2. 목록 API에서 최근 공지 30건을 받아 제목이 `TARGET_KEYWORDS`에 걸리는 글을 고릅니다.
3. `state/seen.json`에 없는 글이면 상세 API로 **본문·작성일·첨부파일 목록·링크**를 담아 메일로 보냅니다.
4. 보낸 글 번호를 `state/seen.json`에 적고 리포지토리에 커밋합니다.

**최초 실행 때는 메일을 보내지 않고** 지금 올라와 있는 글을 읽음 처리만 합니다.

`수상자`·`명단`·`최종 결과`가 제목에 든 글은 뺍니다. 이미 끝난 소식이라
`EXCLUDE_KEYWORDS`에 넣어뒀습니다. 남의 수상 소식까지 받고 싶으면 그 목록을 비우면 됩니다.

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
`hongjeeee@mail.ulsan.ac.kr, 본인@gmail.com` 처럼 씁니다.

학교 메일(`mail.ulsan.ac.kr`)은 Microsoft 365라서 Gmail에서 보낸 메일이 잘 들어갑니다.
처음 한두 통이 정크 메일함으로 갈 수 있으니, 안 오면 거기부터 보고 보낸 사람을 안전한 발신자로 등록하세요.

보내는 계정은 Gmail 그대로 둡니다. 학교 계정으로 **보낼** 필요는 없고, 받기만 하면 됩니다.
Gmail이 아닌 계정으로 보내려면 워크플로에 `SMTP_HOST`, `SMTP_PORT`를 넣어 바꿀 수 있습니다.

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
- **cron은 정시에 안 맞습니다.** GitHub 부하에 따라 5~20분씩 밀리고, 아주 드물게 건너뛰기도 합니다.
- **60일 동안 리포지토리에 사람 활동이 없으면 스케줄이 자동으로 꺼집니다.** 봇 커밋은 활동으로 안 쳐줍니다. 꺼지기 전에 GitHub이 메일로 알려주고, `Actions` 탭에서 다시 켜면 됩니다.
- **실패한 작업을 "Re-run"하면 그때 그 커밋으로 다시 돕니다.** 코드를 고친 뒤에는 `Run workflow`로 새로 실행해야 고친 코드가 돕니다.
- 실행 기록과 로그는 `Actions` 탭에 남습니다. 메일이 안 오면 여기 로그부터 봅니다.

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
TARGET_KEYWORDS = ["대회", "공모전", "해커톤", "경진", "챌린지", "challenge", "장학"]
EXCLUDE_KEYWORDS = ["수상자", "명단", "최종 결과", "결과 안내"]
```

띄어쓰기와 대소문자는 무시하고 비교하므로 `AI 융합 해커톤`으로 적어도 같은 글이 걸립니다.
인턴십 공고까지 받고 싶으면 `"인턴"`을 넣으면 됩니다.

### 확인 주기

`.github/workflows/watch.yml`의 `cron: "0 */2 * * *"`를 고칩니다. UTC 기준입니다.

### 한 번에 확인하는 공지 수

`PAGE_SIZE`를 늘립니다. 기본값 30이면 2시간 주기로는 충분하고, 최대 77건까지 한 번에 옵니다.

## 파일

| 경로 | 하는 일 |
| --- | --- |
| `watcher.py` | 공지 수집·필터·메일 발송 전부 |
| `state/seen.json` | 알림 보낸 글 번호 |
| `.github/workflows/watch.yml` | 2시간마다 실행하고 state 커밋 |

`state/seen.json`은 이렇게 생겼습니다.

```json
{
  "seen_ids": ["4523", "4557", "4664"]
}
```

---

원본: https://github.com/wlstmd/kmu-scholarship-watcher
