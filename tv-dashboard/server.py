"""ABB KR AUEN TV 대시보드 서버.

    python server.py            → http://localhost:8080 (TV 브라우저 전체화면으로 열기)

- /api/schedule : 스케줄 엑셀(.xlsb/.xlsx) → JSON. 파일이 바뀌면 자동으로 다시 읽음
- /api/memo     : 지도 하단 메모 (memo.file 텍스트 파일 → 없으면 config의 memo.text)
- /api/notices  : Power Automate가 notices_dir에 저장한 전체공지 JSON 목록
- /api/menu     : menu_weekly_dir 의 최신 주간 식단표 이미지 + 글자 인식 결과(text)
- /api/news     : ABB 소식 / 경제뉴스 RSS (15분 캐시)
- /api/weather  : Open-Meteo 현재 기온 (10분 캐시)
- /api/stocks   : Yahoo Finance 시세 (5분 캐시)

엑셀·공지·식단표 폴더는 SharePoint 문서 라이브러리를 OneDrive로 동기화한 로컬 경로를 지정하면
SharePoint에 올리는 즉시 TV에 반영된다.
"""
import calendar
import datetime as dt
import json
import mimetypes
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CONFIG_PATH = ROOT / "config.json"
EXCEL_EPOCH = dt.date(1899, 12, 30)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# 엑셀 헤더 → JSON 키. 열 순서가 바뀌어도 헤더 이름으로 찾는다.
COLUMNS = {
    "프로젝트 번호": "no",
    "프로젝트 명": "name",
    "담당자(쉼표구분)": "members",
    "ABB Work 시작": "abbStart",
    "ABB Work 종료": "abbEnd",
    "FAT 시작": "fatStart",
    "FAT 종료": "fatEnd",
    "납품 시작": "delStart",
    "납품 종료": "delEnd",
    "시운전 시작": "siteStart",
    "시운전 종료": "siteEnd",
    "프로젝트 종료": "end",
    # 선택 열: 있으면 config의 키워드 매칭보다 우선
    "현장": "site",
    "표시명": "title",
}


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def resolve(path_str):
    p = Path(path_str)
    return p if p.is_absolute() else ROOT / p


# ---------------------------------------------------------------- 엑셀

def to_date(v):
    """엑셀 일련번호 / 문자열 날짜 → 'YYYY-MM-DD'. '2026/11/31'처럼 없는 날짜는 그 달 말일로 보정."""
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, (int, float)):
        if v < 20000:  # 날짜가 아닌 숫자
            return None
        return (EXCEL_EPOCH + dt.timedelta(days=int(v))).isoformat()
    s = str(v).strip()
    m = re.match(r"^(\d{4})[./-](\d{1,2})[./-](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})", s)  # MM/DD/YYYY
        if not m:
            return None
        mo, d, y = map(int, m.groups())
    if not (1 <= mo <= 12):
        return None
    d = max(1, min(d, calendar.monthrange(y, mo)[1]))
    return dt.date(y, mo, d).isoformat()


def read_rows(path, sheet):
    if path.suffix.lower() == ".xlsb":
        from pyxlsb import open_workbook
        with open_workbook(str(path)) as wb:
            with wb.get_sheet(sheet) as sh:
                return [[c.v for c in row] for row in sh.rows()]
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    try:
        return [list(r) for r in wb[sheet].iter_rows(values_only=True)]
    finally:
        wb.close()


def parse_schedule(path, sheet):
    rows = read_rows(path, sheet)
    header_idx, colmap = None, {}
    for i, row in enumerate(rows[:10]):
        names = [str(c).strip() if c is not None else "" for c in row]
        if "프로젝트 번호" in names:
            header_idx = i
            colmap = {j: COLUMNS[n] for j, n in enumerate(names) if n in COLUMNS}
            break
    if header_idx is None:
        raise ValueError(f"'{sheet}' 시트에서 '프로젝트 번호' 헤더를 찾지 못했습니다")

    projects, warnings = [], []
    for r, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        rec = {}
        for j, key in colmap.items():
            v = row[j] if j < len(row) else None
            if key in ("no", "name", "members", "site", "title"):
                rec[key] = str(v).strip() if v not in (None, "") else ""
            else:
                rec[key] = to_date(v)
                if v not in (None, "") and rec[key] is None:
                    warnings.append(f"{r}행 '{key}' 날짜 해석 실패: {v!r}")
                elif isinstance(v, str) and rec[key]:
                    warnings.append(f"{r}행 '{key}' 문자열 날짜 {v!r} → {rec[key]}")
        if not rec.get("no") and not rec.get("name"):
            continue
        rec["members"] = [m.strip() for m in rec.get("members", "").split(",") if m.strip()]
        rec["row"] = r
        projects.append(rec)
    return projects, warnings


_schedule_cache = {"mtime": None, "data": None}
_schedule_lock = threading.Lock()


def get_schedule(cfg):
    path = resolve(cfg["excel_path"])
    if not path.exists():
        return {"error": f"엑셀 파일 없음: {path}", "projects": []}
    mtime = path.stat().st_mtime
    with _schedule_lock:
        if _schedule_cache["mtime"] != mtime:
            try:
                projects, warnings = parse_schedule(path, cfg.get("excel_sheet", "입력양식"))
            except Exception as e:  # 저장 중(잠김)이면 이전 데이터를 유지
                if _schedule_cache["data"]:
                    return {**_schedule_cache["data"], "stale": str(e)}
                return {"error": str(e), "projects": []}
            _schedule_cache["mtime"] = mtime
            _schedule_cache["data"] = {
                "file": path.name,
                "updated": dt.datetime.fromtimestamp(mtime).isoformat(timespec="minutes"),
                "projects": projects,
                "warnings": warnings,
            }
        return _schedule_cache["data"]


# ---------------------------------------------------------------- 공지 / 식단표

def get_notices(cfg, limit=8):
    folder = resolve(cfg["notices_dir"])
    items = []
    for f in folder.glob("*.json") if folder.exists() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        for n in d if isinstance(d, list) else [d]:
            items.append({
                "subject": n.get("subject") or n.get("Subject") or f.stem,
                "from": n.get("from") or n.get("From") or "",
                "received": n.get("received") or n.get("receivedDateTime") or
                            dt.datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "body": strip_html(n.get("body") or n.get("bodyPreview") or n.get("Body") or "")[:400],
            })
    items.sort(key=lambda n: n["received"], reverse=True)
    return {"items": items[:limit]}


def latest_image(folder):
    if not folder.exists():
        return None
    files = [f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXT]
    if not files:
        return None
    f = max(files, key=lambda p: p.stat().st_mtime)
    return {"name": f.name, "rel": f.relative_to(folder).as_posix(), "updated": dt.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes")}


def get_menu(cfg):
    weekly = latest_image(resolve(cfg["menu_weekly_dir"]))
    if weekly:
        weekly["url"] = "/files/menu-weekly/" + urllib.parse.quote(weekly["rel"])
    out = {"weekly": weekly}
    if weekly and cfg.get("menu_ocr", {}).get("enabled", True):
        out["text"] = menu_text(cfg, resolve(cfg["menu_weekly_dir"]) / weekly["rel"])
    return out


# 주간 식단표 글자 읽기는 몇 초 걸리므로 새 이미지가 보이면 뒤에서 한 번만 돌리고 결과를 기억해 둠
_ocr = {"key": None, "result": None, "running": False}
_ocr_lock = threading.Lock()


def menu_text(cfg, path):
    key = (str(path), path.stat().st_mtime)
    with _ocr_lock:
        if _ocr["key"] == key:
            return _ocr["result"]
        if _ocr["running"]:
            return None
        _ocr["running"] = True
    opts = cfg.get("menu_ocr", {})

    def work():
        try:
            import menu_ocr
            result = menu_ocr.read_menu(path, opts.get("tesseract_cmd", "tesseract"), opts.get("cutoff", 0.68))
        except Exception as e:  # Tesseract가 없거나 양식이 달라도 화면은 이미지로 계속 보여줌
            result = {"error": str(e)}
        with _ocr_lock:
            _ocr.update(key=key, result=result, running=False)

    threading.Thread(target=work, daemon=True).start()
    return None


# ---------------------------------------------------------------- 외부 데이터 (캐시)

_cache = {}


def cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    try:
        val = fn()
        _cache[key] = (time.time(), val)
        return val
    except Exception as e:
        if hit:
            return {**hit[1], "stale": str(e)}
        return {"error": str(e)}


def http_get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (TV dashboard)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\s+", " ", s).strip()


def fetch_rss(url, limit=6):
    root = ET.fromstring(http_get(url))
    items = []
    for it in root.iter("item"):
        title = strip_html(it.findtext("title") or "")
        source = it.findtext("source") or ""
        if source and title.endswith(" - " + source):  # Google News 제목 꼬리 제거
            title = title[: -len(source) - 3]
        items.append({"title": title, "source": source, "date": it.findtext("pubDate") or ""})
        if len(items) >= limit:
            break
    return {"items": items}


def fetch_headlines(src, limit=6):
    """ABB 코리아 홈페이지(new.abb.com/kr)에서 뉴스 기사 링크 제목을 뽑는다.
    링크 주소에 link_pattern(기본 '/news/detail/')이 들어간 <a>만 기사로 본다."""
    url = src["url"]
    pattern = src.get("link_pattern", "/news/detail/")
    page = http_get(url).decode("utf-8", "replace")
    items, seen = [], set()
    for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.S | re.I):
        href, inner = m.group(1), m.group(2)
        if pattern not in href:
            continue
        title = strip_html(inner)
        if len(title) < 8:  # '자세히 보기' 같은 버튼 글자는 제외
            alt = re.search(r'(?:title|aria-label)="([^"]{8,})"', m.group(0))
            title = strip_html(alt.group(1)) if alt else ""
        link = urllib.parse.urljoin(url, href)
        if not title or link in seen:
            continue
        seen.add(link)
        items.append({"title": title, "source": "ABB 코리아", "date": "", "link": link})
        if len(items) >= limit:
            break
    if not items:
        raise ValueError("기사 링크를 찾지 못함 (link_pattern 확인)")
    return {"items": items}


def fetch_news(src):
    """src: RSS 주소 문자열, 또는 {"type": "html", "url", "link_pattern", "fallback_rss"}"""
    if isinstance(src, str):
        return fetch_rss(src)
    try:
        return fetch_headlines(src)
    except Exception:
        if src.get("fallback_rss"):
            return fetch_rss(src["fallback_rss"])
        raise


WEATHER_CODES = {0: "맑음", 1: "대체로 맑음", 2: "구름 조금", 3: "흐림", 45: "안개", 48: "안개",
                 51: "이슬비", 53: "이슬비", 55: "이슬비", 61: "비", 63: "비", 65: "강한 비",
                 71: "눈", 73: "눈", 75: "강한 눈", 80: "소나기", 81: "소나기", 82: "강한 소나기",
                 95: "뇌우", 96: "뇌우", 99: "뇌우"}


def fetch_weather(w):
    q = urllib.parse.urlencode({
        "latitude": w["lat"], "longitude": w["lon"], "timezone": "Asia/Seoul",
        "current": "temperature_2m,weather_code,relative_humidity_2m",
        "daily": "temperature_2m_max,temperature_2m_min", "forecast_days": 1,
    })
    d = json.loads(http_get("https://api.open-meteo.com/v1/forecast?" + q))
    code = d["current"]["weather_code"]
    out = {
        "name": w.get("name", ""),
        "temp": d["current"]["temperature_2m"],
        "humidity": d["current"]["relative_humidity_2m"],
        "code": code,
        "text": WEATHER_CODES.get(code, ""),
        "max": d["daily"]["temperature_2m_max"][0],
        "min": d["daily"]["temperature_2m_min"][0],
    }
    try:  # 미세먼지는 실패해도 날씨는 그대로 보여줌
        out.update(fetch_air(w))
    except Exception as e:
        out["air_error"] = str(e)
    return out


# 환경부 통합대기 기준 (㎍/㎥): 좋음 / 보통 / 나쁨 / 매우나쁨
PM_GRADES = {"pm10": (30, 80, 150), "pm25": (15, 35, 75)}
GRADE_NAMES = ("좋음", "보통", "나쁨", "매우나쁨")


def pm_grade(kind, value):
    if value is None:
        return None
    return GRADE_NAMES[sum(value > limit for limit in PM_GRADES[kind])]


def fetch_air(w):
    q = urllib.parse.urlencode({"latitude": w["lat"], "longitude": w["lon"], "timezone": "Asia/Seoul",
                                "current": "pm10,pm2_5"})
    cur = json.loads(http_get("https://air-quality-api.open-meteo.com/v1/air-quality?" + q))["current"]
    pm10, pm25 = cur.get("pm10"), cur.get("pm2_5")
    g10, g25 = pm_grade("pm10", pm10), pm_grade("pm25", pm25)
    # 둘 중 나쁜 쪽을 대표 등급으로
    worst = max((g for g in (g10, g25) if g), key=GRADE_NAMES.index, default=None)
    return {"pm10": pm10, "pm25": pm25, "pm10_grade": g10, "pm25_grade": g25, "air_grade": worst}


def fetch_stocks(stocks):
    out = []
    for s in stocks:
        try:
            url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(s["symbol"]) +
                   "?range=5d&interval=1d")
            meta = json.loads(http_get(url))["chart"]["result"][0]["meta"]
            price, prev = meta["regularMarketPrice"], meta.get("chartPreviousClose") or meta.get("previousClose")
            out.append({"name": s["name"], "symbol": s["symbol"], "price": price, "currency": meta.get("currency", ""),
                        "change": price - prev if prev else None,
                        "pct": (price - prev) / prev * 100 if prev else None})
        except Exception as e:
            out.append({"name": s["name"], "symbol": s["symbol"], "error": str(e)})
    return {"items": out}


# ---------------------------------------------------------------- HTTP

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def log_message(self, fmt, *args):
        pass

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        if not path.is_file():
            return self.send_error(404)
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        cfg = load_config()
        url = urllib.parse.urlparse(self.path)
        p = url.path
        if p == "/api/config":
            keys = ("rotation_seconds", "board_page_seconds", "refresh_minutes", "imminent_days", "load_high",
                    "load_extreme", "sites", "aliases", "weather")
            return self.send_json({k: cfg.get(k) for k in keys})
        if p == "/api/schedule":
            return self.send_json(get_schedule(cfg))
        if p == "/api/memo":
            memo = dict(cfg.get("memo") or {})
            f = resolve(memo.pop("file", "") or "data/memo.txt")
            if f.is_file():
                memo["text"] = f.read_text(encoding="utf-8-sig").strip()
            return self.send_json(memo)
        if p == "/api/notices":
            return self.send_json(get_notices(cfg))
        if p == "/api/menu":
            return self.send_json(get_menu(cfg))
        if p == "/api/news":
            feed = urllib.parse.parse_qs(url.query).get("feed", [""])[0]
            src = cfg.get("news", {}).get(feed)
            if not src:
                return self.send_json({"error": "unknown feed"}, 404)
            return self.send_json(cached("news:" + feed, 900, lambda: fetch_news(src)))
        if p == "/api/weather":
            return self.send_json(cached("weather", 600, lambda: fetch_weather(cfg["weather"])))
        if p == "/api/stocks":
            return self.send_json(cached("stocks", 300, lambda: fetch_stocks(cfg.get("stocks", []))))
        if p.startswith("/files/menu-weekly/"):
            folder = resolve(cfg["menu_weekly_dir"])
            rel = urllib.parse.unquote(p.split("/", 3)[3])
            target = (folder / rel).resolve()
            if folder.resolve() not in target.parents:  # 경로 이탈 방지
                return self.send_error(404)
            return self.send_file(target)
        return super().do_GET()


def main():
    cfg = load_config()
    port = int(cfg.get("port", 8080))
    print(f"TV 대시보드: http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
