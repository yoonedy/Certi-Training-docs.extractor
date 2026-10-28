"""서버 없이 열리는 미리보기 파일 만들기.

    python tools/build_preview.py            → preview/tv-preview-all.html (TV 화면 + 3페이지 한눈에)

지도는 지금 엑셀(config.json의 excel_path)로 그리고, 공지·뉴스·날씨·주가·식단은 샘플 데이터를 넣는다.
"""
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def sample_menu(server, cfg):
    """식단 폴더에 이미지가 있으면 미리보기에 그대로 넣음 (없으면 빈칸)"""
    menu = server.get_menu({**cfg, "menu_ocr": {"enabled": False}})  # 서버식 백그라운드 인식은 끄고 아래에서 바로 읽음
    for key, folder in (("weekly", "menu_weekly_dir"),):
        img = menu.get(key)
        if img:
            f = server.resolve(cfg[folder]) / img["rel"]
            mime = "image/png" if f.suffix.lower() == ".png" else "image/jpeg"
            img["url"] = f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()
    if menu.get("weekly") and not menu.get("text"):  # 서버는 뒤에서 읽지만 미리보기는 여기서 바로 읽음
        try:
            import menu_ocr
            opts = cfg.get("menu_ocr", {})
            menu["text"] = menu_ocr.read_menu(server.resolve(cfg["menu_weekly_dir"]) / menu["weekly"]["rel"],
                                              opts.get("tesseract_cmd", "tesseract"), opts.get("cutoff", 0.68))
        except Exception as e:
            print("식단 글자 인식 생략:", e)
    return menu


def build_tv(server):
    root = server.ROOT
    cfg = server.load_config()
    sched = server.get_schedule(cfg)
    keys = ("rotation_seconds","board_page_seconds","refresh_minutes","imminent_days","load_high","load_extreme","sites","aliases","weather")
    c = {k: cfg.get(k) for k in keys}
    api = {
      "/api/config": c, "/api/schedule": sched, "/api/memo": {k: v for k, v in (cfg.get("memo") or {}).items() if k != "file"},
      "/api/notices": {"items": [
        {"subject": "[전체공지] 미리보기용 샘플 공지 %d" % i, "from": "샘플 부서", "received": "2026-10-%02dT%02d:30:00" % (27 - i, 9 + i),
         "body": "실제 화면에서는 Power Automate가 저장한 전체공지 메일 본문 앞부분이 여기에 표시됩니다."} for i in range(1, 6)]},
      "/api/menu": sample_menu(server, cfg),
      "/api/news?feed=abb": {"items": [{"title": f"미리보기용 샘플 ABB 코리아 소식 {i}", "source": "ABB 코리아"} for i in range(1, 7)]},
      "/api/news?feed=economy": {"items": [{"title": f"미리보기용 샘플 경제 헤드라인 {i} — 실제로는 경제 RSS 주요 기사 제목이 표시됩니다", "source": "샘플",
                                            "date": f"Wed, 28 Oct 2026 0{i}:{10 * i}:00 +0900"} for i in range(1, 9)]},
      "/api/weather": {"name": "서울", "temp": 15, "humidity": 55, "code": 2, "text": "구름 조금", "max": 19, "min": 9,
                       "pm10": 42, "pm25": 18, "pm10_grade": "보통", "pm25_grade": "보통", "air_grade": "보통"},
      "/api/stocks": {"items": [{"name": "ABB (SIX)", "price": 52.34, "change": 0.62, "pct": 1.2}, {"name": "KOSPI", "price": 2934.12, "change": -12.3, "pct": -0.42},
                                {"name": "KOSDAQ", "price": 865.4, "change": 0, "pct": 0}, {"name": "USD/KRW", "price": 1382.5, "change": 3.1, "pct": 0.22}]},
    }
    st = root / "static"
    page = (st / "index.html").read_text(encoding="utf-8")
    shim = "<script>const PREVIEW_API=" + json.dumps(api, ensure_ascii=False) + ";window.fetch=async(u)=>{const d=PREVIEW_API[u];return{ok:!!d,status:d?200:404,json:async()=>d}};</script>"
    page = page.replace('<link rel="stylesheet" href="styles.css">', "<style>" + (st / "styles.css").read_text(encoding="utf-8") + "</style>")
    page = page.replace('<script src="korea-map.js"></script>', shim + "<script>" + (st / "korea-map.js").read_text(encoding="utf-8") + "</script>")
    for f in ("schedule-logic.js", "app.js"):
        page = page.replace(f'<script src="{f}"></script>', "<script>" + (st / f).read_text(encoding="utf-8") + "</script>")
    page = page.replace("<title>KR AUEN TV</title>", "<title>KR AUEN TV 미리보기</title>")
    logo = "data:image/png;base64," + base64.b64encode((st / "abb-logo.png").read_bytes()).decode()
    page = page.replace("abb-logo.png", logo)
    return page


def build_hub(page):
    page = page.replace("const params = new URLSearchParams(location.search);",
                        "const params = new URLSearchParams(window.PREVIEW_QUERY || location.search);")
    embedded = json.dumps(page, ensure_ascii=False).replace("</", "<\\/")
    hub = """<!doctype html>
    <html lang="ko">
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>KR AUEN TV 미리보기</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
    <style>
      :root { --bg: #eef1f5; --card: #fff; --ink: #1d2230; --ink-2: #5b6273; --line: #dfe4ec; --red: #e30613; }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { background: var(--bg); color: var(--ink); font-family: "Pretendard Variable", Pretendard, "Malgun Gothic", sans-serif; padding: 28px 32px 40px; }
      .wrap { max-width: 1480px; margin: 0 auto; }
      header { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 18px; }
      h1 { font-size: 26px; font-weight: 800; letter-spacing: -.3px; }
      h1 small { display: block; font-size: 14px; font-weight: 600; color: var(--ink-2); margin-top: 6px; letter-spacing: 0; }
      .note { font-size: 13px; color: var(--ink-2); background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 8px 12px; line-height: 1.5; }
      .main { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 14px; box-shadow: 0 8px 24px rgba(30,35,50,.06); }
      .bar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
      .bar b { font-size: 16px; }
      .bar .mode { font-size: 13px; color: var(--ink-2); }
      .bar button { margin-left: auto; font: inherit; font-size: 14px; font-weight: 700; border: 1px solid var(--line); background: #fff; border-radius: 8px; padding: 7px 14px; cursor: pointer; }
      .bar button:hover { border-color: var(--ink-2); }
      .screen { position: relative; width: 100%; aspect-ratio: 16 / 9; border-radius: 10px; overflow: hidden; background: #0d1016; }
      .screen iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
      h2 { font-size: 17px; font-weight: 800; margin: 26px 0 12px; }
      .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
      .thumb { background: var(--card); border: 1.5px solid var(--line); border-radius: 14px; padding: 10px; cursor: pointer; text-align: left; font: inherit; color: inherit; transition: border-color .2s, box-shadow .2s; }
      .thumb:hover { border-color: #b8c0cc; }
      .thumb.on { border-color: var(--red); box-shadow: 0 0 0 3px rgba(227,6,19,.12); }
      .thumb .screen { pointer-events: none; }
      .thumb .cap { display: flex; justify-content: space-between; align-items: baseline; padding: 10px 4px 2px; }
      .thumb .cap b { font-size: 15px; }
      .thumb .cap span { font-size: 12px; color: var(--ink-2); }
      @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } body { padding: 16px; } }
    </style>
    </head>
    <body>
    <div class="wrap">
      <header>
        <h1>KR AUEN TV 미리보기<small>TV 화면 그대로 · 아래 페이지를 누르면 크게 보여요</small></h1>
        <div class="note">지도는 실제 스케줄 엑셀 데이터 · 공지/뉴스/날씨/주가/식단은 샘플</div>
      </header>

      <section class="main">
        <div class="bar"><b id="main-title">TV 화면</b><span class="mode" id="main-mode">자동 회전 중 (지도 → 현황판 → 사내 공지·식단)</span>
          <button id="auto" hidden>자동 회전으로 보기</button></div>
        <div class="screen"><iframe id="main" title="TV 화면"></iframe></div>
      </section>

      <h2>전체 페이지</h2>
      <div class="grid">
        <button class="thumb" data-page="1"><div class="screen"><iframe title="1페이지" tabindex="-1"></iframe></div><div class="cap"><b>1. 프로젝트 지도</b><span>스케줄 엑셀 연동</span></div></button>
        <button class="thumb" data-page="2"><div class="screen"><iframe title="2페이지" tabindex="-1"></iframe></div><div class="cap"><b>2. 프로젝트 현황판</b><span>월별 일정 · 15초마다 다음 장</span></div></button>
        <button class="thumb" data-page="3"><div class="screen"><iframe title="3페이지" tabindex="-1"></iframe></div><div class="cap"><b>3. 사내 공지 · 식단</b><span>공지 · ABB 소식 · 식단</span></div></button>
      </div>
    </div>
    <script>
    const TV = __TV__;
    const make = (q) => TV.replace("<head>", "<head><script>window.PREVIEW_QUERY=" + JSON.stringify(q) + "<\\/script>");
    const NAMES = { 1: "1. 프로젝트 지도", 2: "2. 프로젝트 현황판", 3: "3. 사내 공지 · 식단" };
    const main = document.getElementById("main"), auto = document.getElementById("auto");
    function show(page) {
      main.srcdoc = make(page ? "?page=" + page : "");
      document.getElementById("main-title").textContent = page ? NAMES[page] : "TV 화면";
      document.getElementById("main-mode").textContent = page ? "이 페이지에 고정" : "자동 회전 중 (지도 → 현황판 → 사내 공지·식단)";
      auto.hidden = !page;
      document.querySelectorAll(".thumb").forEach((t) => t.classList.toggle("on", t.dataset.page === String(page)));
    }
    document.querySelectorAll(".thumb").forEach((t) => {
      t.querySelector("iframe").srcdoc = make("?page=" + t.dataset.page);
      t.addEventListener("click", () => { show(+t.dataset.page); main.scrollIntoView({ behavior: "smooth", block: "center" }); });
    });
    auto.addEventListener("click", () => show(0));
    show(0);
    </script>
    </body>
    </html>
    """.replace("__TV__", embedded)
    return hub


def main():
    import server
    out = ROOT / "preview" / "tv-preview-all.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(build_hub(build_tv(server)), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
