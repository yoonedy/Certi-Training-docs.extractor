# KR AUEN TV 대시보드

TV 한 화면에서 3페이지가 자동으로 돌아가는 사내 대시보드.

| 페이지 | 내용 | 데이터 |
|---|---|---|
| 1. 프로젝트 지도 | 현장별 핀·카드, 2주 내 임박(D-day), 현장 부하 경고, 해안선을 도는 ABB 차량 | 스케줄 엑셀 (`입력양식` 시트) |
| 2. 기존 화면 | 정해진 기존 디자인 | `static/page2.html` (또는 `page2_url`) |
| 3. 뉴스 & 생활 | 사내 공지(전체공지 메일 모아보기) · ABB 코리아 소식 / 오늘 식단 · 주간 식단 | 전체공지 메일(Power Automate) · new.abb.com/kr · SharePoint 식단 게시판 |
| 상단 우측 (공통) | 날짜·시각 · 기온 · 습도 · 미세먼지 등급 | Open-Meteo 날씨·대기질 |
| 하단 바 (공통) | 경제뉴스 헤드라인(8초마다 교체) · 주가 | 경제 RSS · Yahoo Finance |

## 실행

```bash
pip install -r requirements.txt
python server.py          # → http://localhost:8080
```

TV PC(Windows)에서는 `start_tv.bat` 바로가기를 시작 프로그램에 넣으면 서버 + Edge 키오스크 전체화면으로 뜬다.
화면은 1920×1080 기준으로 그려지고 어떤 해상도든 비율 맞춰 확대/축소된다.

- `←` / `→` : 페이지 넘기기
- `?page=1` : 한 페이지에 고정 (설치·점검용)
- `?today=2026-10-19` : 기준일을 바꿔서 보기

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

새 현장이 생기면 `config.json`의 `sites`에 이름·위도·경도·키워드만 추가하면 된다.

## 사내 전체공지 모아보기 (Power Automate 연동)

전체공지 메일이 올 때마다 Power Automate가 메일 내용을 SharePoint 폴더에 JSON 파일로 저장하고, TV는 그 폴더를 읽는다.
최근 공지를 모아 목록으로 보여주고, 8초마다 다음 공지를 크게 보여준다.

1. https://make.powerautomate.com → **만들기 → 자동화된 클라우드 흐름**
2. 트리거: **Office 365 Outlook – 새 메일이 도착하면 (V3)**
   - 공유 사서함/배포 목록으로 오면: **공유 사서함에 새 메일이 도착하는 경우 (V2)**
   - 고급 옵션 → 제목 필터: `[전체공지]` (실제 공지 메일 제목 규칙에 맞게), 또는 보낸 사람 필터
3. 동작: **SharePoint – 파일 만들기**
   - 사이트 주소: TV용 SharePoint 사이트, 폴더: `TV/notices`
   - 파일 이름: `@{formatDateTime(triggerBody()?['receivedDateTime'],'yyyyMMdd-HHmmss')}.json`
   - 파일 콘텐츠: `@{triggerBody()}`
4. TV 서버 PC에서 `TV/notices` 폴더를 OneDrive **동기화** → `config.json`의 `notices_dir`에 그 경로

서버는 `subject`, `from`, `receivedDateTime`, `body`(HTML은 글자만 남김)를 읽는다.

## 식단표 (SharePoint CanteenReservation)

식단 게시판: https://abb.sharepoint.com/sites/CanteenReservation

SharePoint는 로그인이 필요해서 TV 서버가 페이지를 직접 열 수 없다 (다른 사이트 안에 SharePoint 페이지를 끼워 넣는 것도 막혀 있음).
그래서 식단 **이미지 파일**을 TV 서버 PC의 폴더로 가져온다. 둘 중 편한 방법:

- **A. OneDrive 동기화**: CanteenReservation 사이트에서 식단 이미지가 들어 있는 문서 라이브러리(예: 문서, 사이트 자산)를 열고 **동기화** → 동기화된 폴더 경로를 `menu_daily_dir` / `menu_weekly_dir`에 지정. 하위 폴더까지 찾는다.
- **B. Power Automate 복사**: 트리거 **SharePoint – 파일을 만든 경우(속성만)** (CanteenReservation, 식단 이미지 폴더) → 동작 **SharePoint – 파일 복사**로 TV 사이트의 `TV/menu/daily`(또는 `weekly`)에 복사 → 그 폴더를 동기화

오늘 식단은 파일 이름에 오늘 날짜(`20261028`, `2026-10-28`, `2026.10.28`, `261028`)가 들어간 이미지를 먼저 고르고, 없으면 가장 최근 이미지를 쓴다. 주간 식단은 가장 최근 이미지.

## 날씨 · 미세먼지 · 뉴스 · 주가

TV 서버 PC에서 인터넷이 되어야 한다. 서버가 대신 받아서 캐시한다.

- 날씨·미세먼지: Open-Meteo (키 불필요) — `weather`에 위치. 미세먼지 등급은 환경부 기준
  (PM10 좋음 ≤30 · 보통 ≤80 · 나쁨 ≤150, PM2.5 좋음 ≤15 · 보통 ≤35 · 나쁨 ≤75) 중 나쁜 쪽을 표시
- ABB 코리아 소식: `news.abb` — new.abb.com/kr 페이지에서 주소에 `link_pattern`(`/news/detail/`)이 들어간 기사 링크 제목을 뽑는다.
  홈페이지 구조가 바뀌어 못 찾으면 `fallback_rss`(Google 뉴스 "ABB 코리아")로 대신 보여준다
- 경제뉴스: `news.economy` RSS (기본: 매일경제 경제)
- 주가: Yahoo Finance — `stocks`에 종목 코드 (`ABBN.SW`, `^KS11`, `^KQ11`, `KRW=X` …)

## 파일 구성

```
server.py               엑셀/공지/식단/외부데이터 API + 정적 파일 서버
config.json             경로·회전 시간·현장 좌표·별칭·피드 설정
static/index.html       3페이지 화면
static/app.js           페이지 회전, 지도 배치·자동차 애니메이션, 3페이지 렌더링
static/schedule-logic.js  엑셀 행 → 상태/색/D-day/부하 계산
static/korea-map.js     시·도 지도 path (tools/build_map.py로 생성)
static/page2.html       2페이지 기존 디자인 자리
tools/check_logic.js    node tools/check_logic.js 2026-10-19  → 콘솔로 결과 확인
```
