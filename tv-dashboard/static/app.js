/* TV 대시보드: 페이지 회전 + 각 페이지 렌더링.
 * URL 옵션 — ?page=1|2|3 : 해당 페이지 고정(설치·점검용), ?today=2026-10-19 : 기준일 바꿔 보기 */
(function () {
  "use strict";

  const params = new URLSearchParams(location.search);
  const SVG_NS = "http://www.w3.org/2000/svg";
  const W = 1920, H = 1080;
  let CFG = null;

  // ───────────────────────── 공통

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pad = (n) => String(n).padStart(2, "0");
  const WEEK = ["일", "월", "화", "수", "목", "금", "토"];

  function today() {
    const t = params.get("today");
    if (t) return ScheduleLogic.parseDate(t);
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), n.getDate());
  }

  async function getJSON(url) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 15000);
    try {
      const r = await fetch(url, { cache: "no-store", signal: ctrl.signal });
      if (!r.ok) throw new Error(url + " → " + r.status);
      return await r.json();
    } finally {
      clearTimeout(timer);
    }
  }

  function svg(tag, attrs, parent) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(el);
    return el;
  }

  function fitStage() {
    const s = Math.min(innerWidth / W, innerHeight / H);
    $("stage").style.transform = `scale(${s}) translate(-50%, -50%)`;
  }

  function fmtUpdate(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return "—";
    const h = d.getHours();
    return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} · ${h < 12 ? "AM" : "PM"} ${pad(h % 12 || 12)}:${pad(d.getMinutes())}`;
  }

  // ───────────────────────── 페이지 회전

  const PAGES = [
    { id: "page-map", title: "KR AUEN PROJECT OVERVIEW" },
    { id: "page-legacy", title: "" },
    { id: "page-info", title: "KR AUEN NEWS & LIFE" },
  ];
  let pageIdx = 0, pageTimer = null;

  function showPage(i) {
    const enabled = PAGES.filter((p) => !p.disabled);
    pageIdx = (i + enabled.length) % enabled.length;
    const page = enabled[pageIdx];
    for (const p of PAGES) $(p.id).classList.toggle("active", p === page);
    if (page.title) $("page-title").textContent = page.title;
    $("dots").innerHTML = enabled.map((p, k) => `<i class="${k === pageIdx ? "on" : ""}"></i>`).join("");
    if (params.has("page")) return;
    clearTimeout(pageTimer);
    const secs = (CFG.rotation_seconds || [])[PAGES.indexOf(page)] || 40;
    pageTimer = setTimeout(() => showPage(pageIdx + 1), secs * 1000);
  }

  addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") showPage(pageIdx + 1);
    if (e.key === "ArrowLeft") showPage(pageIdx - 1);
  });

  // ───────────────────────── 1. 지도

  const M = window.KOREA_MAP;
  function project(lat, lon) {
    const p = M.projection;
    return { x: p.x0 + (lon - p.lonMin) * p.kx, y: p.y0 + (p.latMax - lat) * p.k };
  }

  const PROVINCE_FILL = {
    "11": "#efe5d8", "21": "#efe5d8", "22": "#efe5d8", "23": "#efe5d8", "24": "#efe5d8", "25": "#efe5d8",
    "26": "#efe5d8", "29": "#efe5d8",
    "31": "#dde9cc", "32": "#e5def2", "33": "#fbe6be", "34": "#d6e6f2", "35": "#f7dbe2",
    "36": "#d9e9d1", "37": "#dbe2f5", "38": "#f8dfc8",
  };
  const PROVINCE_LABELS = [
    ["경기", 37.93, 127.28], ["강원", 37.82, 128.35], ["충북", 36.78, 127.72], ["충남", 36.42, 126.93],
    ["전북", 35.66, 127.05], ["전남", 34.92, 126.9], ["경북", 36.8, 128.7], ["경남", 35.33, 128.2],
  ];
  const CITIES = [
    ["서울", 37.566, 126.978], ["강릉", 37.752, 128.876], ["대전", 36.35, 127.385], ["전주", 35.824, 127.148],
    ["대구", 35.871, 128.601], ["포항", 36.019, 129.343], ["부산", 35.18, 129.075], ["광주", 35.16, 126.853],
    ["여수", 34.76, 127.662],
  ];
  const WAVES = [[468, 180], [1270, 180], [620, 300], [1400, 330], [580, 560], [1330, 790], [620, 850]];

  let carPath = null, carEl = null, carLen = 0;

  function drawBaseMap() {
    const root = $("map-svg");
    root.innerHTML = "";
    const base = svg("g", {}, root);

    for (const [x, y] of WAVES) svg("path", { class: "wave", d: `M${x},${y} q10,-9 20,0 t20,0 t20,0` }, base);
    svg("text", { class: "sea-label", x: 545, y: 800 }, base).textContent = "서 해";
    svg("text", { class: "sea-label", x: 1326, y: 420 }, base).textContent = "동 해";
    svg("text", { class: "sea-label", x: 1250, y: 880 }, base).textContent = "남 해";

    for (const p of M.provinces) {
      svg("path", { class: "province", d: p.d, fill: PROVINCE_FILL[p.code] || "#eee" }, base);
    }
    // 울릉도·독도 인셋
    svg("rect", { class: "inset-box", x: 1287, y: 190, width: 132, height: 92, rx: 10 }, base);
    svg("circle", { cx: 1318, cy: 232, r: 11, fill: "#dbe2f5", stroke: "#8a9bb5", "stroke-width": 1.6 }, base);
    svg("circle", { cx: 1384, cy: 243, r: 6, fill: "#dbe2f5", stroke: "#8a9bb5", "stroke-width": 1.6 }, base);
    svg("text", { class: "inset-label", x: 1318, y: 263, "font-size": 14 }, base).textContent = "울릉도";
    svg("text", { class: "inset-label", x: 1384, y: 269 }, base).textContent = "독도";
    // 제주 인셋
    svg("rect", { class: "inset-box", x: 462, y: 905, width: 156, height: 141, rx: 12 }, base);
    svg("text", { class: "inset-label", x: 540, y: 934, "font-size": 18 }, base).textContent = "제주";
    svg("path", { class: "province", d: M.jeju, fill: "#d9e9d1" }, base);

    for (const [name, la, lo] of PROVINCE_LABELS) {
      const p = project(la, lo);
      svg("text", { class: "prov-label", x: p.x, y: p.y }, base).textContent = name;
    }

    // 자동차가 도는 해안 외곽 도로
    carPath = svg("path", { d: M.carRoute, fill: "none", stroke: "none" }, base);
    carLen = carPath.getTotalLength();
    // 화면에서 시계방향(서해안 북상 → 동해안 남하 → 남해안 서진)으로 돌도록 경로 방향 확인
    let area = 0, prev = carPath.getPointAtLength(0);
    for (let i = 1; i <= 200; i++) {
      const pt = carPath.getPointAtLength((carLen * i) / 200);
      area += prev.x * pt.y - pt.x * prev.y;
      prev = pt;
    }
    carDir = area > 0 ? 1 : -1; // SVG는 y가 아래로 커지므로 양수 = 시계방향

    svg("g", { id: "memo-line" }, root);
    svg("g", { id: "city-layer" }, root);
    svg("g", { id: "connector-layer" }, root);
    svg("g", { id: "pin-layer" }, root);
    carEl = buildCar(root);
  }

  function buildCar(parent) {
    // 오른쪽을 바라보는 ABB 오픈카 (바퀴 바닥이 y=0)
    const g = svg("g", { id: "car" }, parent);
    const body = svg("g", { transform: "translate(-34,-44)" }, g);
    body.innerHTML = `
      <rect x="19" y="13" width="5" height="12" rx="2" fill="#4a5160" stroke="#2a2f3b" stroke-width="1.6"/>
      <path d="M26,25 L26,17 Q26,13.5 30,13.5 L34,13.5 Q37.5,13.5 37.5,17 L37.5,25Z" fill="#2f6fe0" stroke="#2a2f3b" stroke-width="1.6"/>
      <path d="M37,18 L41,22" stroke="#2a2f3b" stroke-width="2.2" stroke-linecap="round"/>
      <circle cx="31.5" cy="8" r="5.5" fill="#f6d7b8" stroke="#2a2f3b" stroke-width="1.6"/>
      <path d="M25,6.5 Q25.5,-1 31.5,-1 Q37.5,-1 38,6.5 Z" fill="#f7c21b" stroke="#2a2f3b" stroke-width="1.6"/>
      <rect x="23.5" y="5.4" width="16.5" height="2.4" rx="1.2" fill="#f7c21b" stroke="#2a2f3b" stroke-width="1.2"/>
      <path d="M44,23.5 L40.5,13 L42.5,13 L47,23.5Z" fill="#cfe3f3" stroke="#2a2f3b" stroke-width="1.6" stroke-linejoin="round"/>
      <path d="M2,38 L2,30 Q2,25.5 8,25 L60,24.5 Q68,25.5 68,31 L68,38 Q68,40 66,40 L4,40 Q2,40 2,38Z" fill="#fff" stroke="#2a2f3b" stroke-width="2.4" stroke-linejoin="round"/>
      <image class="car-logo" href="abb-logo.png" x="23" y="27" width="24" height="${(24 * 66 / 174).toFixed(3)}" preserveAspectRatio="xMidYMid meet"/>
      <g class="wheel" transform="translate(16,40)"><circle r="6.5" fill="#2a2f3b"/><circle r="2.6" fill="#d6dbe4"/><path d="M0,-5.6V5.6M-5.6,0H5.6" stroke="#d6dbe4" stroke-width="1.4"/></g>
      <g class="wheel" transform="translate(54,40)"><circle r="6.5" fill="#2a2f3b"/><circle r="2.6" fill="#d6dbe4"/><path d="M0,-5.6V5.6M-5.6,0H5.6" stroke="#d6dbe4" stroke-width="1.4"/></g>
`;
    return g;
  }

  // 차는 해안선을 따라 시계방향으로 돈다. 왼쪽으로 달릴 땐 좌우 반전해서 앞을 보게 하고(로고는 다시 뒤집어 바르게),
  // 차체는 기울이지 않고 화면에서 늘 수평을 유지한다 (해안선 굴곡과 상관없이).
  // 북쪽 끝은 상단 바(높이 64)에 가려지므로 그 아래 선을 따라 달리게 함
  const CAR_MIN_Y = 112;
  function carPoint(len) {
    const pt = carPath.getPointAtLength(len);
    return { x: pt.x, y: Math.max(pt.y, CAR_MIN_Y) };
  }
  let carStart = performance.now(), carDir = 1, carFace = 1, carScaleX = 1, lastNow = 0, lastAt = 0, spin = 0;
  function animateCar(now) {
    if (carPath && carLen && $("page-map").classList.contains("active")) {
      const speed = 45; // px/s
      const run = (((now - carStart) / 1000) * speed) % carLen;
      const at = carDir > 0 ? run : carLen - run;
      const p = carPoint(at);
      // 앞뒤 80px 지점으로 진행 방향을 잡아 해안 굴곡에 흔들리지 않게 함
      const ahead = carPoint((at + 80 * carDir + carLen) % carLen);
      const behind = carPoint((at - 80 * carDir + carLen) % carLen);
      const dx = ahead.x - behind.x, dy = ahead.y - behind.y, dist = Math.hypot(dx, dy) || 1;
      // 확실히 왼쪽으로 갈 때만 왼쪽을 봄 (남북 구간은 오른쪽), 경계에서 깜빡이지 않게 여유를 둠
      if (carFace > 0 && dx < -0.55 * dist) carFace = -1;
      else if (carFace < 0 && dx > -0.2 * dist) carFace = 1;
      const dt = lastNow ? Math.min((now - lastNow) / 1000, 0.1) : 1;
      lastNow = now;
      // 방향 전환은 0.3초 동안 좌우로 돌아서듯이
      carScaleX += Math.max(-dt / 0.15, Math.min(dt / 0.15, carFace - carScaleX));
      const sx = Math.abs(carScaleX) < 0.05 ? 0.05 * Math.sign(carFace) : carScaleX;
      const bounce = Math.sin(now / 110) * 0.7;
      carEl.setAttribute("transform", `translate(${p.x.toFixed(1)},${p.y.toFixed(1)}) scale(${sx.toFixed(3)},1) translate(0,${bounce.toFixed(2)}) scale(.95)`);
      carEl.querySelector(".car-logo").setAttribute("transform", sx < 0 ? "matrix(-1,0,0,1,70,0)" : "");
      // 차가 늘 앞으로 가므로 바퀴도 늘 앞으로 굴림
      const step = (run - lastAt + carLen) % carLen;
      lastAt = run;
      spin = (spin + (step / 6.5) * 180 / Math.PI) % 360;
      carEl.querySelectorAll(".wheel").forEach((w, i) => w.setAttribute("transform", `translate(${i ? 54 : 16},40) rotate(${spin.toFixed(1)})`));
    }
    requestAnimationFrame(animateCar);
  }

  function pinPath(color) {
    return `<path class="pin-body" d="M0,0 C-5,-12 -19,-22 -19,-37 A19,19 0 1 1 19,-37 C19,-22 5,-12 0,0Z" fill="${color}" stroke="#2a2f3b" stroke-width="2.6" stroke-linejoin="round"/>`;
  }
  const COLOR = { imminent: "#e3263b", site: "#2f6fe0", fat: "#7a55f0", abb: "#4a5160", annual: "#16a06b" };

  const COL = {
    left: { x: 62, w: 383, top: 166, bottom: 1046 },
    right: { x: 1440, w: 420, top: 140, bottom: 1046 },
  };
  const GAP = 26;

  function peopleHTML(g) {
    return `PM <b>${esc(g.pm)}</b>${g.eng.length ? " ENG <b>" + esc(g.eng.join(", ")) + "</b>" : ""}`;
  }

  function cardHTML(site) {
    const g = site.groups[0];
    const cat = g.st.category;
    return `<div class="card ${cat === "imminent" ? "imminent" : ""}">
      <div class="row1"><span class="badge ${cat}">${esc(g.st.badge)}</span><span class="kr-no">KR-${esc(g.no)}</span></div>
      <div class="title">${esc(g.title)}</div>
      <div class="people">${peopleHTML(g)}</div></div>`;
  }

  function clusterHTML(site, limit) {
    const shown = site.groups.slice(0, limit);
    const rest = site.groups.length - shown.length;
    const sub = (site.site && site.site.subtitle) || "";
    return `<div class="card cluster">
      <div class="c-head"><h4>${esc(site.name)} 현장</h4><span class="count">${site.groups.length}건</span></div>
      <div class="c-sub">${esc(sub) || "&nbsp;"}</div>
      <ul>${shown.map((g) => `<li>
        <div class="l1"><span class="nm"><i class="c-${g.st.category}"></i>${esc(g.title)}</span>${g.highLoad ? '<span class="hl">HIGH LOAD</span>' : ""}</div>
        <div class="l2"><span>${peopleHTML(g).replace(/<\/?b>/g, "")}</span><span class="st ${g.st.category}">${esc(g.st.badge)}</span></div>
      </li>`).join("")}</ul>${rest > 0 ? `<div class="more">외 ${rest}건</div>` : ""}</div>`;
  }

  function warnHTML(over, month) {
    const sites = [...new Set(over.flatMap((o) => o.sites))];
    const where = sites.length === 1 ? `모두 ${sites[0]} 현장` : sites.join(" · ");
    const byLevel = ["EXTREME", "HIGH"].map((lv) => [lv, over.filter((o) => o.level === lv)]).filter(([, a]) => a.length);
    return `<div class="card warn">
      <div class="head">${month}월 현장 부하 경고</div>
      ${byLevel.map(([lv, a], i) => `<div class="row"><span class="level ${lv}">${lv}</span><span class="who">${a.map((o) => esc(o.name)).join(" · ")}</span>${i === 0 ? `<span class="where">${esc(where)}</span>` : ""}</div>`).join("")}
    </div>`;
  }

  function placeEl(html, col) {
    const wrap = document.createElement("div");
    wrap.innerHTML = html.trim();
    const el = wrap.firstChild;
    el.style.left = col.x + "px";
    el.style.width = col.w + "px";
    el.style.top = "0px";
    $("map-cards").appendChild(el);
    return el;
  }

  function renderMap(data) {
    const t = today();
    const model = ScheduleLogic.buildModel(data.projects || [], CFG, t);
    $("map-cards").innerHTML = "";
    $("connector-layer").innerHTML = "";
    $("pin-layer").innerHTML = "";
    $("city-layer").innerHTML = "";

    // 핀 좌표
    const items = model.sites.map((s) => ({
      s, pin: s.site ? project(s.site.lat, s.site.lon) : null,
      kind: s.groups.length > 1 ? "cluster" : "card", limit: s.groups.length,
    }));

    // 도시 표시 (핀이 있는 도시는 생략)
    const pinned = new Set(items.filter((i) => i.pin).map((i) => i.s.name));
    for (const [name, la, lo] of CITIES) {
      if (pinned.has(name)) continue;
      const p = project(la, lo);
      svg("circle", { class: "city-dot", cx: p.x, cy: p.y, r: 5.5 }, $("city-layer"));
      svg("text", { class: "city-label", x: p.x + 11, y: p.y + 6 }, $("city-layer")).textContent = name;
    }

    // 부하 경고 카드 (오른쪽 맨 위, 핀 없음)
    const fixed = { left: [], right: [] };
    if (model.overloaded.length) {
      const el = placeEl(warnHTML(model.overloaded, t.getMonth() + 1), COL.right);
      fixed.right.push({ el, h: el.offsetHeight });
    }

    for (const it of items) it.side = !it.pin || it.pin.x >= 960 ? "right" : "left";
    const build = (it) => {
      if (it.el) it.el.remove();
      it.el = placeEl(it.kind === "cluster" ? clusterHTML(it.s, it.limit) : cardHTML(it.s), COL[it.side]);
      it.h = it.el.offsetHeight;
    };
    items.forEach(build);

    const used = (side) => [...fixed[side], ...items.filter((i) => i.side === side && !i.dropped)]
      .reduce((a, i) => a + i.h + GAP, -GAP);
    const avail = (side) => COL[side].bottom - COL[side].top;

    // 넘치면 반대편으로 옮기기 → 목록 줄이기 → 우선순위 낮은 카드 숨기기
    for (const [from, to] of [["left", "right"], ["right", "left"]]) {
      while (used(from) > avail(from)) {
        const cand = items.filter((i) => i.side === from && i.pin)
          .sort((a, b) => (from === "left" ? b.pin.x - a.pin.x : a.pin.x - b.pin.x))
          .find((i) => used(to) + i.h + GAP <= avail(to) + 1);
        if (!cand) break;
        cand.side = to;
        build(cand);
      }
    }
    for (const side of ["left", "right"]) {
      let guard = 50;
      while (used(side) > avail(side) && guard--) {
        const big = items.filter((i) => i.side === side && i.kind === "cluster" && i.limit > 3).sort((a, b) => b.h - a.h)[0];
        if (big) { big.limit--; build(big); continue; }
        const low = items.filter((i) => i.side === side && !i.dropped).sort((a, b) => b.s.groups[0].rank - a.s.groups[0].rank)[0];
        if (!low) break;
        low.dropped = true;
        low.el.remove();
      }
    }

    // 세로 배치: 핀 높이에 맞추되 겹치지 않게
    for (const side of ["left", "right"]) {
      const col = COL[side];
      const list = items.filter((i) => i.side === side && !i.dropped).sort((a, b) => (a.pin ? a.pin.y : 9999) - (b.pin ? b.pin.y : 9999));
      let y = col.top;
      for (const f of fixed[side]) { f.top = y; y += f.h + GAP; }
      for (const it of list) {
        const ideal = it.pin ? it.pin.y - 38 - Math.min(it.h / 2, 70) : y;
        it.top = Math.max(y, ideal);
        y = it.top + it.h + GAP;
      }
      let limit = col.bottom;
      for (let k = list.length - 1; k >= 0; k--) {
        list[k].top = Math.min(list[k].top, limit - list[k].h);
        limit = list[k].top - GAP;
      }
      for (const f of fixed[side]) f.el.style.top = f.top + "px";
      for (const it of list) it.el.style.top = it.top + "px";
    }

    // 연결선 + 핀
    for (const it of items) {
      if (!it.pin) continue;
      const head = { x: it.pin.x, y: it.pin.y - 37 };
      if (!it.dropped) {
        const left = it.side === "left";
        const a = { x: left ? COL.left.x + COL.left.w : COL.right.x, y: it.top + Math.min(it.h / 2, 64) };
        const dx = (head.x - a.x) * 0.5;
        svg("path", { class: "connector", d: `M${a.x},${a.y} C${a.x + dx},${a.y} ${head.x - dx},${head.y} ${head.x},${head.y}` }, $("connector-layer"));
      }
      const g = svg("g", { class: "pin" + (it.s.category === "imminent" ? " pulse" : ""), transform: `translate(${it.pin.x},${it.pin.y})` }, $("pin-layer"));
      if (it.s.highLoad) svg("circle", { class: "pin-halo", cx: 0, cy: 0, r: 30 }, g);
      g.insertAdjacentHTML("beforeend", pinPath(COLOR[it.s.category]) + '<circle cx="0" cy="-37" r="7" fill="#fff" stroke="#2a2f3b" stroke-width="2"/>');
      const labelLeft = it.pin.x > 1000;
      svg("text", { class: "pin-label", x: labelLeft ? -26 : 26, y: -26, "text-anchor": labelLeft ? "end" : "start" }, g).textContent = it.s.name;
    }

    const dropped = items.filter((i) => i.dropped).reduce((a, i) => a + i.s.groups.length, 0);
    $("map-sub").textContent = `진행 중이거나 예정된 프로젝트 ${model.activeRows}건 · 현장 위치 기준` + (dropped ? ` · 화면 공간 부족으로 ${dropped}건 생략` : "");
  }

  // ───────────────────────── 하단 메모 (여수 쪽)

  async function loadMemo() {
    const m = await getJSON("/api/memo").catch(() => ({}));
    $("memo-tag").textContent = m.tag || "메모";
    $("memo-text").textContent = m.text || "새 프로젝트가 등록되면 여기에 표시돼요";
    $("map-memo").classList.toggle("empty-memo", !m.text);
    const layer = $("memo-line");
    layer.innerHTML = "";
    const city = CITIES.find((c) => c[0] === m.site);
    if (city) {
      const p = project(city[1], city[2]);
      svg("path", { class: "memo-connector", d: `M${p.x},${p.y + 8} L${p.x},905` }, layer);
    }
  }

  async function loadSchedule() {
    try {
      const data = await getJSON("/api/schedule");
      if (data.error) throw new Error(data.error);
      renderMap(data);
      $("last-update").textContent = "LAST UPDATE · " + fmtUpdate(data.updated);
      $("map-error").hidden = !data.stale;
      if (data.stale) $("map-error").textContent = "엑셀을 읽지 못해 이전 데이터를 표시 중: " + data.stale;
    } catch (e) {
      $("map-error").hidden = false;
      $("map-error").textContent = "스케줄을 불러오지 못했습니다 · " + e.message;
    }
  }

  // ───────────────────────── 3. 사내소식 · 식단

  function fmtWhen(s) {
    const d = new Date(s);
    if (isNaN(d)) return "";
    return `${pad(d.getMonth() + 1)}.${pad(d.getDate())} (${WEEK[d.getDay()]}) ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function emptyHTML(tag, text) {
    return `<div class="empty"><b>${esc(tag)}</b><br>${esc(text)}</div>`;
  }

  async function loadNotices() {
    const el = $("notice-body");
    try {
      const d = await getJSON("/api/notices");
      const [first, ...rest] = d.items || [];
      if (!first) { el.innerHTML = emptyHTML("전체공지", "새 전체공지 메일이 오면 여기에 표시돼요"); return; }
      el.innerHTML = `<div class="notice-main"><div class="subj">${esc(first.subject)}</div>
        <div class="meta">${esc(first.from)} · ${fmtWhen(first.received)}</div>
        <div class="text">${esc(first.body)}</div></div>
        <ul class="notice-list">${rest.slice(0, 4).map((n) => `<li><span>${esc(n.subject)}</span><span class="d">${fmtWhen(n.received)}</span></li>`).join("")}</ul>`;
    } catch (e) {
      el.innerHTML = emptyHTML("연결 오류", e.message);
    }
  }

  async function loadNews(feed, id, max) {
    const el = $(id);
    try {
      const d = await getJSON("/api/news?feed=" + feed);
      if (d.error) throw new Error(d.error);
      el.innerHTML = (d.items || []).slice(0, max).map((n) => `<li><span class="t">${esc(n.title)}</span><span class="s">${esc(n.source)}</span></li>`).join("")
        || `<li>${emptyHTML("뉴스", "표시할 기사가 없어요")}</li>`;
    } catch (e) {
      el.innerHTML = `<li>${emptyHTML("뉴스 연결 오류", e.message)}</li>`;
    }
  }

  async function loadStocks() {
    const el = $("stocks");
    try {
      const d = await getJSON("/api/stocks");
      if (d.error) throw new Error(d.error);
      el.innerHTML = (d.items || []).map((s) => {
        if (s.error || s.price == null) return `<div class="stock"><div class="n">${esc(s.name)}</div><div class="p flat">—</div></div>`;
        const cls = s.change > 0 ? "up" : s.change < 0 ? "down" : "flat";
        const arrow = s.change > 0 ? "▲" : s.change < 0 ? "▼" : "–";
        const digits = s.price >= 1000 ? 2 : 2;
        return `<div class="stock"><div class="n">${esc(s.name)}</div>
          <div class="p">${s.price.toLocaleString("ko-KR", { maximumFractionDigits: digits })}</div>
          <div class="c ${cls}">${arrow} ${Math.abs(s.change).toLocaleString("ko-KR", { maximumFractionDigits: 2 })} (${s.pct >= 0 ? "+" : ""}${s.pct.toFixed(2)}%)</div></div>`;
      }).join("");
      const n = new Date();
      $("stock-time").textContent = `${pad(n.getHours())}:${pad(n.getMinutes())} 기준`;
    } catch (e) {
      el.innerHTML = emptyHTML("시세 연결 오류", e.message);
    }
  }

  function weatherIcon(code) {
    const sun = '<circle cx="40" cy="38" r="15" fill="#f7c21b"/><g stroke="#f7c21b" stroke-width="4" stroke-linecap="round"><path d="M40 12v-6M40 70v-6M14 38H8M72 38h-6M21 19l-4-4M63 61l-4-4M21 57l-4 4M63 15l-4 4"/></g>';
    const cloud = (x, c) => `<path transform="translate(${x},0)" d="M24 66h36a14 14 0 0 0 0-28 20 20 0 0 0-38-4 13 13 0 0 0 2 32z" fill="${c}" stroke="#2a2f3b" stroke-width="2.4"/>`;
    const drops = '<g stroke="#2f6fe0" stroke-width="4" stroke-linecap="round"><path d="M34 74l-3 8M48 74l-3 8M62 74l-3 8"/></g>';
    const flakes = '<g fill="#8fb4cf"><circle cx="34" cy="78" r="3.5"/><circle cx="48" cy="82" r="3.5"/><circle cx="62" cy="78" r="3.5"/></g>';
    const bolt = '<path d="M48 66l-8 14h8l-4 10 12-16h-8l4-8z" fill="#f7c21b" stroke="#2a2f3b" stroke-width="1.5"/>';
    let body;
    if (code <= 1) body = sun;
    else if (code === 2) body = sun + cloud(4, "#fff");
    else if (code <= 48) body = cloud(0, "#eef1f6");
    else if (code <= 67 || (code >= 80 && code <= 82)) body = cloud(0, "#eef1f6") + drops;
    else if (code <= 86) body = cloud(0, "#fff") + flakes;
    else body = cloud(0, "#dfe3ea") + bolt;
    return `<svg viewBox="0 0 92 92">${body}</svg>`;
  }

  async function loadWeather() {
    const el = $("weather");
    try {
      const w = await getJSON("/api/weather");
      if (w.error) throw new Error(w.error);
      el.innerHTML = `${weatherIcon(w.code)}<div class="temp">${Math.round(w.temp)}°</div>
        <div><div class="desc">${esc(w.text)} · 습도 ${w.humidity}%</div><div class="range">최고 ${Math.round(w.max)}° / 최저 ${Math.round(w.min)}°</div></div>
        <div class="place">${esc(w.name)}</div>`;
    } catch (e) {
      el.innerHTML = emptyHTML("날씨 연결 오류", e.message);
    }
  }

  async function loadMenu() {
    try {
      const d = await getJSON("/api/menu");
      const put = (id, img, dateId, label) => {
        $(id).innerHTML = img
          ? `<img src="${img.url}?v=${encodeURIComponent(img.updated)}" alt="${label}">`
          : emptyHTML("SharePoint", `식단표 폴더에 ${label} 이미지를 올리면 표시돼요`);
        $(dateId).textContent = img ? img.updated.replace("T", " ") + " 업로드" : "";
      };
      put("menu-daily", d.daily, "menu-daily-date", "오늘 식단");
      put("menu-weekly", d.weekly, "menu-weekly-date", "주간 식단");
    } catch (e) {
      $("menu-daily").innerHTML = emptyHTML("연결 오류", e.message);
    }
  }

  function tickClock() {
    const n = new Date();
    $("date-big").innerHTML = `<small>${n.getFullYear()}년</small>${n.getMonth() + 1}월 ${n.getDate()}일 ${WEEK[n.getDay()]}요일`;
    $("time-big").textContent = `${pad(n.getHours())}:${pad(n.getMinutes())}`;
  }

  // ───────────────────────── 시작

  async function init() {
    addEventListener("resize", fitStage);
    fitStage();
    CFG = await getJSON("/api/config");

    if (CFG.page2_url) $("legacy-frame").src = CFG.page2_url;
    else PAGES[1].disabled = true;

    drawBaseMap();
    requestAnimationFrame(animateCar);
    tickClock();
    setInterval(tickClock, 10000);

    const refresh = () => {
      loadSchedule(); loadMemo(); loadNotices(); loadMenu(); loadWeather(); loadStocks();
      loadNews("abb", "abb-news", 4); loadNews("economy", "econ-news", 4);
    };
    refresh();
    setInterval(refresh, (CFG.refresh_minutes || 5) * 60000);

    // 매일 새벽 4시 전체 새로고침 (코드·설정 변경 반영, 메모리 정리)
    setInterval(() => { if (new Date().getHours() === 4 && performance.now() > 3600000) location.reload(); }, 600000);

    const fixedPage = parseInt(params.get("page"), 10);
    showPage(fixedPage ? fixedPage - 1 : 0);
  }

  init().catch((e) => {
    document.body.insertAdjacentHTML("beforeend", `<div class="error-banner" style="position:fixed">시작 실패: ${esc(e.message)}</div>`);
  });
})();
