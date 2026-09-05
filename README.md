# 울산대 대회·장학 알리미

울산대학교 공지에 **대회·공모전·해커톤이나 장학 공고가 새로 올라오면 이메일로** 보내줍니다.
GitHub Actions가 2시간마다 돌기 때문에 컴퓨터를 켜둘 필요도, 서버를 띄울 필요도 없습니다.

메일 제목 앞에 `[울산대 SW대회]` `[울산대 장학]` `[SW 대회]` `[SW 장학]` `[U-STEP 대회]`가 붙어서
어디서 온 무슨 공고인지 바로 구분됩니다.
내 학년이 나갈 수 없는 공고는 오지 않습니다(기본값 1학년, `MY_GRADE`로 바꿉니다).

## 어디서 가져오나

| 사이트 | 여기에 올라오는 것 | 가져오는 분야 | 방식 |
| --- | --- | --- | --- |
| [대표 홈페이지 일반공지](https://www.ulsan.ac.kr/kor/CMS/Board/Board.do?mCode=MN113) | 교외 AI·SW 해커톤과 공모전, 교내외 장학 공고. 학교가 받아서 올려줍니다 | 대회, 장학 | 목록 2페이지를 받아 제목을 거름 |
| [SW중심대학사업단 공지](https://sw.ulsan.ac.kr/site/swulsan/notices) | 학내 SW 대회(캡스톤디자인, 프로그래밍 경진대회, AI 해커톤)와 SW 장학 | 대회, 장학 | 공개 JSON API 한 번 |
| [U-STEP 비교과프로그램](https://ustep.ulsan.ac.kr/home/sub/prog-list) | 마일리지가 붙는 교내 공모전·해커톤. 공지 게시판에는 안 올라오는 것도 있습니다 | 대회 | 화면을 그리는 AJAX를 그대로 호출 |

U-STEP은 게시판이 아니라 비교과 프로그램 목록이라 장학 공고가 올라오지 않습니다. 그래서 대회만 봅니다.

찾는 말은 이렇습니다.

| 분야 | 걸리는 말 |
| --- | --- |
| 대회 | `대회` `공모전` `해커톤` `경진` `경연` `챌린지` `아이디어톤` `콘테스트` |
| 장학 | `장학` `학자금` `국가근로` `등록금 지원` `학비 지원` `생활비 지원` |

대표 홈페이지와 U-STEP의 **대회**는 교외 공고가 그대로 올라와서(`한우 곤포 나르기 대회`)
`SW_KEYWORDS`(`AI` `소프트웨어` `데이터` 등) 중 하나가 제목에 더 있어야 보냅니다.
장학은 SW 장학만 받을 이유가 없어서 이 조건 없이 다 받습니다.

## 쓰는 방법

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

`EMAIL_TO`는 쉼표로 여러 개를 적을 수 있습니다.
학교 메일과 개인 메일로 같이 받으려면 `본인@mail.ulsan.ac.kr, 본인@gmail.com` 처럼 씁니다.
처음 한두 통이 정크 메일함으로 갈 수 있으니, 안 오면 거기부터 보세요.

### 3. 첫 실행

`Actions > SW Contest Watcher > Run workflow`로 한 번 수동 실행합니다.
게시판을 처음 감시할 때는 메일이 오지 않고 현재 글만 읽음 처리됩니다. 그다음부터 새 공고에 메일이 옵니다.
(U-STEP만 예외로 처음부터 보냅니다. 지금 신청할 수 있는 것만 목록에 남아서 안 보내면 놓칩니다.)

### 4. 학년 바꾸기

[`.github/workflows/watch.yml`](.github/workflows/watch.yml)의 `MY_GRADE`를 올립니다. 2학년이 되면 `"2"`.
`0`으로 두면 학년을 아예 안 거릅니다.

```yaml
env:
  MY_GRADE: "2"
```

### 5. 확인 주기 바꾸기

같은 파일의 `cron: "0 */2 * * *"`를 고칩니다. UTC 기준입니다.

## 로컬에서 확인하기

```bash
pip install -r requirements.txt
python watcher.py --dry-run
```

`--dry-run`은 메일을 보내지 않고 무엇이 걸렸는지 화면에만 출력하고 `state/seen.json`도 건드리지 않습니다.

```bash
python watcher.py --dry-run --only scholarship   # 장학만
python watcher.py --dry-run --only contest       # 대회만
python watcher.py --dry-run --grade 3            # 3학년이면 뭐가 더 오는지
python watcher.py --dry-run --grade 0            # 학년을 안 거르면 뭐가 더 오는지
```

## 고치고 싶을 때

전부 [`watcher.py`](watcher.py) 한 파일에 있습니다.

| 바꾸고 싶은 것 | 볼 곳 |
| --- | --- |
| 대회로 칠 말 | `CONTEST_KEYWORDS` / `CONTEST_EXCLUDE` |
| 장학으로 칠 말 | `SCHOLARSHIP_KEYWORDS` / `SCHOLARSHIP_EXCLUDE` |
| SW 대회로 좁히는 조건 | `SW_KEYWORDS` (비우면 모든 대회가 옴) |
| 어느 사이트에서 어느 분야를 볼지 | `BOARDS`의 `watches` |
| 분야를 하나 더 늘리기 | `Category`를 만들어 `CATEGORIES`와 `watches`에 넣기 |
| 얼마나 거슬러 올라가서 볼지 | `UnivBoard(pages_to_check=2)`, `SwBoard(page_size=30)` |

띄어쓰기와 대소문자는 무시하고 비교하므로 `AI 융합 해커톤`으로 적어도 같은 글이 걸립니다.
목록을 받아놓고 거르는 방식이라 키워드를 늘려도 요청 수는 그대로입니다.

## 파일

| 경로 | 하는 일 |
| --- | --- |
| `watcher.py` | 공지 수집·필터·메일 발송 전부 |
| `state/seen.json` | 알림 보낸 글 번호. 게시판별로 나눠 저장 |
| `scripts/merge_state.py` | 푸시가 밀렸을 때 원격 state와 합치기 |
| `scripts/probe_ulsan.py` | 학교 서버가 러너에서 되는지 재보는 진단용 |
| `.github/workflows/watch.yml` | 2시간마다 실행하고 state 커밋 |
| `.github/workflows/probe.yml` | 진단용. 손으로 실행할 때만 돔 |

## 참고 링크

**가져오는 곳**

- [울산대 대표 홈페이지 일반공지](https://www.ulsan.ac.kr/kor/CMS/Board/Board.do?mCode=MN113)
- [SW중심대학사업단 공지](https://sw.ulsan.ac.kr/site/swulsan/notices)
- [U-STEP 비교과통합관리시스템](https://ustep.ulsan.ac.kr/home/sub/prog-list)

**설정에 필요한 곳**

- [Google 앱 비밀번호 발급](https://myaccount.google.com/apppasswords)
- [Gmail SMTP 설정 안내](https://support.google.com/mail/answer/7126229)
- [GitHub Actions 스케줄(cron) 문법](https://docs.github.com/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Actions 시크릿 설정](https://docs.github.com/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
- [crontab.guru — cron 식 확인](https://crontab.guru/)
