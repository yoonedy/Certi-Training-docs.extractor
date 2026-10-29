# KR AUEN TV 대시보드

TV 한 화면에서 3페이지가 자동으로 돌아가는 사내 대시보드.

| 페이지 | 내용 | 데이터 |
|---|---|---|
| 1. 프로젝트 지도 | 현장별 핀·카드, 2주 내 임박(D-day), 현장 부하 경고, 해안선을 도는 ABB 차량 | 스케줄 엑셀 (`입력양식` 시트) |
| 2. 프로젝트 현황판 | 프로젝트별 월간 일정(ABB work · FAT · 납품 · 현장작업), 월별 엔지니어 부하(High / Extremly High), 진행률, 종료일 — 5건씩 `board_page_seconds`(15초)마다 다음 장 | 스케줄 엑셀 (`입력양식` 시트) |
| 3. 뉴스 & 생활 | 왼쪽: 사내 공지(전체공지 메일 모아보기) · ABB 코리아 소식 · 경제 주요 뉴스 / 오른쪽: 오늘(큰 날짜 · 음력 · 24절기 · 날씨 · 습도 · 미세먼지) · 주간 식단(오늘 열 하늘색) | 전체공지 메일(Power Automate) · new.abb.com/kr · SharePoint 식단 게시판 |
| 상단 우측 (1·2페이지) | 날짜·시각 · 기온 · 습도 · 미세먼지 등급 (3페이지는 '오늘' 칸이 대신) | Open-Meteo 날씨·대기질 |
| 하단 바 (공통) | 경제뉴스 헤드라인(8초마다 교체) · 주가 | 경제 RSS · Yahoo Finance |

## 실행

```bash
pip install -r requirements.txt
python server.py          # → http://localhost:8080
```

서버 없이 화면만 확인하려면 `python tools/build_preview.py` → `preview/tv-preview-all.html`을 브라우저로 연다
(TV 화면 자동 회전 + 3페이지 한눈에 보기, 지도는 지금 엑셀 데이터 · 나머지는 샘플).
`--live`를 붙이면 뉴스·ABB 소식·날씨·미세먼지·주가를 지금 실제로 받아서 넣는다 (사내 공지는 메일 연동 전이라 샘플).

TV PC(Windows)에서는 `start_tv.bat` 바로가기를 시작 프로그램에 넣으면 서버 + Edge 키오스크 전체화면으로 뜬다.
화면은 1920×1080 기준으로 그려지고 어떤 해상도든 비율 맞춰 확대/축소된다.

- `←` / `→` : 페이지 넘기기
- `?page=1` : 한 페이지에 고정 (설치·점검용)
- `?today=2026-10-19` : 기준일을 바꿔서 보기
- `?page=2&board=3` : 현황판 3장에 고정

## 엑셀 연동

`config.json`의 `excel_path`에 스케줄 파일 경로를 넣는다. 파일이 저장되면(수정시각 변경) 다음 새로고침(`refresh_minutes`, 기본 5분) 때 자동 반영되고, 상단 LAST UPDATE에 엑셀 저장 시각이 나온다.
SharePoint에 있는 파일이면 OneDrive로 그 라이브러리를 TV PC에 **동기화**한 뒤 로컬 경로를 적으면 된다.

- 헤더 이름으로 열을 찾으므로 열 순서가 바뀌어도 된다: `프로젝트 번호, 프로젝트 명, 담당자(쉼표구분), ABB Work 시작/종료, FAT 시작/종료, 납품 시작/종료, 시운전 시작/종료, 프로젝트 종료`
- 선택 열: `현장`(지도 위치를 직접 지정), `표시명`(카드에 보일 이름)
- 담당자 첫 번째 = PM, 나머지 = ENG
- `2026/11/31`처럼 없는 날짜는 그 달 말일로 보정 (서버 `/api/schedule`의 `warnings`에 표시)
- `.xlsb`, `.xlsx`, `.xlsm` 모두 가능

### 지도 규칙 (`static/schedule-logic.js`)

- 종료일이 지난 행은 제외. 같은 프로젝트 번호는 한 카드로 묶음 (예: 신인천 3CC · 1CC)
- 현장 위치: `현장` 열 → 없으면 `config.json`의 `sites[].keywords`로 프로젝트명에서 찾기
- 카드 이름: `표시명` 열 → `config.json`의 `aliases` → 프로젝트명에서 접두어(EX_, S-Oil/RTS_ …) 정리
- 색상 우선순위: **2주 내 임박**(다음 일정이 `imminent_days`일 이내) > **현장작업**(시운전 중/예정) > **FAT** > **ABB Work** > **연간 계약**(이름에 "연간계약")
- **현장 부하 경고**: ENG별로 "현장작업 중 + 진행 중 연간계약" 수가 `load_high`(2) 이상이면 HIGH, `load_extreme`(3) 이상이면 EXTREME
- 한 현장에 2건 이상이면 목록 패널(예: 울산 현장 7건), 1건이면 카드. 서쪽 현장은 왼쪽, 동쪽은 오른쪽에 배치하고 넘치면 자동으로 반대편 이동 → 목록 축소 → "외 N건"

### 현황판 규칙 (2페이지, `buildBoard`)

- 이번 달부터 12개월. 종료일이 지나지 않은 행을 엑셀 순서대로 5건씩 보여주고 `board_page_seconds`(15초)마다 다음 장
- 막대 줄: 맨 위 ABB work · 가운데 FAT/납품(🚚, 붙어 있으면 한 막대) · 아래 현장작업(🚩). 빨간 세로선 = 오늘
- 맨 위 줄 이름: 그 달에 현장작업 + 연간계약이 2건↑이면 **High**(주황), 3건↑이면 **Extremly High**(분홍) — 지도의 '현장 부하 경고'와 같은 기준 (ENG 기준, `load_high` / `load_extreme`)
- 막대 왼쪽 위 `!` = 그 기간에 담당 엔지니어가 High / Extremly High
- 파란 글씨 = 다음 일정, 진행률 = ABB Work 시작 ~ 프로젝트 종료 사이 경과율

새 현장이 생기면 `config.json`의 `sites`에 이름·위도·경도·키워드만 추가하면 된다.

## 사내 전체공지 모아보기 (현황판 전용 메일 + Power Automate)

현황판 전용 메일함(예: `auen-board@…`)으로 들어온 메일을 Power Automate가 SharePoint 폴더에 JSON 파일로 저장하고,
TV는 그 폴더를 `notices_refresh_hours`(기본 6시간)마다 읽는다. 최근 공지를 모아 목록으로 보여주고 8초마다 다음 공지를 크게 보여준다.

```
전체공지 메일 ──(배포 목록에 현황판 메일 추가 / 전달 규칙)──▶ 현황판 전용 메일함
   ──(Power Automate: 새 메일 → 파일 만들기)──▶ SharePoint TV/notices/*.json
   ──(OneDrive 동기화)──▶ TV 서버 PC 폴더 ──(6시간마다)──▶ TV 3페이지 '사내 공지'
```

**1. 전용 메일함에 공지가 들어오게 하기** (IT 또는 메일 관리자)
- 전체공지 배포 목록(예: 전 직원 그룹)의 **구성원으로 현황판 메일을 추가** → 전 직원에게 가는 공지가 자동으로 들어옴
- 또는 공지를 받는 사람이 Outlook **규칙**으로 현황판 메일에 자동 전달
- 전용 메일함이 **공유 사서함**이면 라이선스 없이 만들 수 있고, 흐름을 만드는 사람에게 그 사서함 권한만 주면 됨

**2. Power Automate 흐름** (https://make.powerautomate.com → 만들기 → 자동화된 클라우드 흐름)
- 트리거
  - 공유 사서함이면: **Office 365 Outlook – 공유 사서함에 새 메일이 도착하는 경우 (V2)** → 원래 사서함 주소에 현황판 메일
  - 일반 계정이면: 그 계정으로 로그인해서 **새 메일이 도착하면 (V3)**
  - 고급 옵션(선택): 제목 필터 `[전체공지]`, 첨부 파일 포함 = 아니요
- 동작: **SharePoint – 파일 만들기**
  - 사이트 주소: TV용 SharePoint 사이트(또는 팀 사이트), 폴더 경로: `TV/notices`
  - 파일 이름: `@{formatDateTime(triggerBody()?['receivedDateTime'],'yyyyMMdd-HHmmss')}.json`
  - 파일 콘텐츠: `@{triggerBody()}` (메일 JSON 그대로)
- 저장 → 현황판 메일로 테스트 메일을 보내 `TV/notices`에 파일이 생기는지 확인

**3. TV 서버 PC**
- SharePoint `TV/notices` 폴더를 열고 **동기화** (OneDrive) → `config.json`의 `notices_dir`에 동기화된 경로
  (예: `C:/Users/계정/ABB/TV - Documents/notices`)
- 새 공지가 TV에 나오기까지 최대 `notices_refresh_hours`(6시간). 바로 보고 싶으면 브라우저 새로고침(F5)

서버는 `subject`(제목), `from`(보낸 사람), `receivedDateTime`(받은 시각), `body`(본문, HTML은 글자만 남김)를 읽고 최근 8건을 보여준다.

**이미 메일을 엑셀에 쌓고 있다면** (Power Automate '표에 행 추가'): `config.json`의 `notices_excel.path`에 그 엑셀(OneDrive 동기화 경로)을 적으면
JSON 폴더 대신/함께 읽는다. 머리글(`receivedDateTime`·`subject`·`from`·`toRecipients`·`ccRecipients`·`body` 또는 받은날짜·제목·보낸사람·받는사람·참조·본문, 띄어쓰기 무시)로 열을 찾고,
날짜가 아닌 줄(흐름을 처음 만들 때 생긴 빈 줄, 'Received Time' 같은 시험 줄)은 건너뛰며,
머리글이 없으면 A=받은 시간, B=제목, C=보낸 사람, D=받는 사람, E=참조, F=본문으로 본다.

### 진짜 전체공지만 고르기 (`notices_filter`)

1. **`min_recipients` — 받는 사람 + 참조가 15명 이상 (기본 15)**: 여러 명에게 한꺼번에 보낸 메일만 공지로 본다.
   주소는 중복 없이 센다. 받는 사람 열이 없는 옛 행에는 적용하지 않는다.
   ⚠️ 전 직원 **배포 목록 주소 하나**로 보낸 공지는 1명으로 세어지므로 그 주소를 `require_to`에 같이 넣어 둔다 (둘 중 하나만 맞으면 통과).
   **숨은 참조(BCC)**로 보낸 공지는 받는 사람이 안 보여서 인원 조건으로는 못 고른다 → 이때는 보낸 사람·제목 규칙만 쓴다
2. **`require_to` — 가장 정확**: 전 직원 배포 목록 주소(예: `KR-All-Employees@abb.com`)를 넣으면 **받는 사람·참조에 그 주소가 있는 메일만** 공지로 본다.
   테스트 메일, 개인에게 온 알림, 회신은 배포 목록으로 가지 않으므로 제목과 상관없이 빠진다.
   → 흐름/엑셀에 **받는 사람(`toRecipients`)·참조(`ccRecipients`)** 열을 추가해야 한다 (동적 콘텐츠 '받는 사람', '참조')
3. **`exclude_from` / `exclude_subject` — 기본으로 켜져 있음**: no-reply·office365·Digest 같은 자동 발신자, "sent a message"·Reminder·Action required·RE:/FW:·test·테스트 제목은 뺀다
4. **`include_subject`** (선택): 예를 들어 `["공지", "안내", "^\\["]`처럼 넣으면 그중 하나가 제목에 있어야 공지로 본다
5. 같은 제목으로 두 번 보낸 공지는 최신 것 하나만

규칙은 모두 대소문자 무시 정규식. 실제 메일 24건(Teams 알림·Digest·회신·테스트 섞임)으로 시험해 진짜 공지 9건만 남는 것을 확인함.
공지 파일은 계속 쌓이므로 가끔 오래된 파일을 지우거나, 흐름에 '30일 지난 파일 삭제' 예약 흐름을 하나 더 두면 된다.

## 식단표 (SharePoint CanteenReservation)

식단 게시판: https://abb.sharepoint.com/sites/CanteenReservation

SharePoint는 로그인이 필요해서 TV 서버가 페이지를 직접 열 수 없다 (다른 사이트 안에 SharePoint 페이지를 끼워 넣는 것도 막혀 있음).
그래서 식단 **이미지 파일**을 TV 서버 PC의 폴더로 가져온다. 둘 중 편한 방법:

- **A. OneDrive 동기화**: CanteenReservation 사이트에서 식단 이미지가 들어 있는 문서 라이브러리(예: 문서, 사이트 자산)를 열고 **동기화** → 동기화된 폴더 경로를 `menu_weekly_dir`에 지정. 하위 폴더까지 찾는다.
- **B. Power Automate 복사**: 트리거 **SharePoint – 파일을 만든 경우(속성만)** (CanteenReservation, 식단 이미지 폴더) → 동작 **SharePoint – 파일 복사**로 TV 사이트의 `TV/menu/weekly`에 복사 → 그 폴더를 동기화

- 주간 식단: `menu_weekly_dir`의 가장 최근 이미지 (아래 글자 읽기가 되면 요일별 표로, 오늘 열 강조)

### 식단표 글자 읽기 (OCR)

주간 식단표 이미지의 글자를 읽어 **텍스트로** 요일별 표에 보여준다 (오늘 열 강조).
글자를 못 읽으면(Tesseract 없음, 양식이 다름) 식단표 이미지를 그대로 보여준다.

- 새 식단표 이미지가 보이면 서버가 뒤에서 한 번 읽고(몇 초) 결과를 기억해 둔다
- 표 칸은 색으로 찾는다: 초록 = 날짜 줄, 노랑 = 사이드 줄, 머리줄의 밝은 틈 = 요일 경계 (`menu_ocr.py`)
- 날짜는 머리줄의 "10월26일"을 읽어 그 주 월요일을 정한다 (못 읽으면 이번 주)
- 읽은 글자는 메뉴 사전과 비교해 가장 가까운 메뉴로 고친다 (`menu_ocr.cutoff`, 기본 0.68)
  - 기본 사전: `tools/menu_words.txt`, 우리 식당 메뉴 추가: `data/menu/menu_words.txt` (한 줄에 하나)
  - **사전에 없는 새 메뉴는 읽은 그대로 나오므로 가끔 글자가 틀릴 수 있다** → 틀린 메뉴를 사전 파일에 적어 두면 다음부터 맞게 나온다
- 점검: `python menu_ocr.py 식단표.png` → 읽은 결과 출력

**TV 서버 PC(Windows) 설치**: https://github.com/UB-Mannheim/tesseract/wiki 에서 Tesseract 설치 프로그램을 받아 설치할 때
"Additional language data"에서 **Korean**을 체크 → `config.json`의 `menu_ocr.tesseract_cmd`를
`C:/Program Files/Tesseract-OCR/tesseract.exe`로 지정. `pip install -r requirements.txt`로 Pillow도 설치.

## 음력 · 24절기 (3페이지 '오늘' 칸)

- 음력: `korean_lunar_calendar` (한국천문연구원 데이터 기준, 윤달 포함) — `pip install -r requirements.txt`로 설치
- 24절기: 태양 황경이 15°씩 지나는 날을 계산 (`calendar_kr.py`, 인터넷 불필요). 2024~2026 역서 날짜와 대조해 일치 확인
- 절기 당일엔 "오늘은 ○○", 아니면 "절기 ○○ · 다음 ○○ 월.일 (D-n)"

## 날씨 · 미세먼지 · 뉴스 · 주가

TV 서버 PC에서 인터넷이 되어야 한다. 서버가 대신 받아서 캐시한다.

- 날씨·미세먼지: Open-Meteo (키 불필요) — `weather`에 위치. 미세먼지 등급은 환경부 기준
  (PM10 좋음 ≤30 · 보통 ≤80 · 나쁨 ≤150, PM2.5 좋음 ≤15 · 보통 ≤35 · 나쁨 ≤75) 중 나쁜 쪽을 표시
- ABB 코리아 소식: `news.abb` — new.abb.com/kr 페이지에서 주소에 `link_pattern`(`/news/detail/`)이 들어간 기사 링크 제목을 뽑는다.
  홈페이지를 못 읽으면(구조 변경, 접속 거부) `fallback_rss`로 대신 보여준다 — Google 뉴스에서 **ABB 공식 뉴스룸(new.abb.com/news) 기사만**,
  최근 1년, 최신순. 일반 언론 검색은 회사에 불리한 기사까지 섞여 나와서 쓰지 않는다
- 경제뉴스: **매일경제 경제 페이지(www.mk.co.kr/news/economy) 위쪽 기사부터** — 3페이지 '경제 주요 뉴스'에 6건, 하단 바에 8초마다 한 줄씩.
  주소가 `/news/economy/숫자`인 기사 링크의 제목을 뽑는다(`link_regex`). 페이지를 못 읽으면 `fallback_rss`(매일경제 경제 RSS)로 자동 전환. 15분에 한 번만 가져온다
  - 네이버 경제 헤드라인(news.naver.com/section/101)으로 바꾸려면 `config.json`의 `economy_naver` 블록 이름을 `economy`로 바꾼다 (기존 `economy`는 지우거나 다른 이름으로)
- 뉴스 출처 점검: `python server.py --check-news` → 출처마다 실제로 읽히는지, 대비용 RSS로 넘어갔는지 출력
- 주가: Yahoo Finance — `stocks`에 종목 코드 (`ABBN.SW`, `^KS11`, `^KQ11`, `KRW=X` …)

## 파일 구성

```
server.py               엑셀/공지/식단/외부데이터 API + 정적 파일 서버
config.json             경로·회전 시간·현장 좌표·별칭·피드 설정
static/index.html       3페이지 화면
static/app.js           페이지 회전, 지도 배치·자동차 애니메이션, 3페이지 렌더링
static/schedule-logic.js  엑셀 행 → 상태/색/D-day/부하 계산
static/korea-map.js     시·도 지도 path (tools/build_map.py로 생성)
tools/check_logic.js    node tools/check_logic.js 2026-10-19  → 콘솔로 결과 확인
```
