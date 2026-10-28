/* 스케줄 엑셀 행 → 지도용 모델.
 * 브라우저에서는 window.ScheduleLogic, Node에서는 require()로 쓴다 (tools/check_logic.js). */
(function (root) {
  "use strict";

  const PHASES = [
    { key: "abb", label: "ABB Work", s: "abbStart", e: "abbEnd" },
    { key: "fat", label: "FAT", s: "fatStart", e: "fatEnd" },
    { key: "del", label: "납품", s: "delStart", e: "delEnd" },
    { key: "site", label: "현장작업", s: "siteStart", e: "siteEnd" },
  ];

  // 낮을수록 우선 (핀 색, 정렬)
  const CATEGORY = {
    imminent: { order: 0, label: "2주 내 임박" },
    site: { order: 1, label: "현장작업" },
    fat: { order: 2, label: "FAT" },
    abb: { order: 3, label: "ABB Work" },
    annual: { order: 4, label: "연간 계약" },
  };

  const DAY = 86400000;

  function parseDate(s) {
    if (!s) return null;
    const [y, m, d] = s.split("-").map(Number);
    return new Date(y, m - 1, d);
  }

  function daysBetween(a, b) {
    return Math.round((b - a) / DAY);
  }

  const pad = (n) => String(n).padStart(2, "0");

  // 같은 해면 MM.DD, 아니면 YY.MM.DD
  function fmtDate(d, today) {
    const md = pad(d.getMonth() + 1) + "." + pad(d.getDate());
    return d.getFullYear() === today.getFullYear() ? md : String(d.getFullYear()).slice(2) + "." + md;
  }

  function findSite(p, sites) {
    if (p.site) {
      const named = sites.find((s) => s.name === p.site);
      if (named) return named;
    }
    const name = (p.name || "").toLowerCase();
    return sites.find((s) => (s.keywords || []).some((k) => name.includes(k.toLowerCase()))) || null;
  }

  function cleanName(name) {
    return name
      .replace(/^(EX|PJ|MT)_/, "")
      .replace(/^[^/]+\/(RTS_|Panel_|Overhaul_|연간계약,\s*)?(EPC\([^)]*\),?\s*)?/, "")
      .replace(/\s*:C\b.*$/, "")
      .trim();
  }

  function titleOf(p, aliases) {
    if (p.title) return p.title;
    const name = (p.name || "").toLowerCase();
    for (const key of Object.keys(aliases || {})) {
      if (name.includes(key.toLowerCase())) return aliases[key];
    }
    return cleanName(p.name || p.no);
  }

  // "(3CC)" 같은 호기 구분
  function unitOf(p) {
    const m = /\(([^)]*)\)\s*$/.exec(p.name || "");
    return m && /\d/.test(m[1]) && m[1].length <= 8 ? m[1] : "";
  }

  function evaluate(p, today, opts) {
    const annual = /연간\s*계약/.test(p.name || "");
    const dates = PHASES.flatMap((ph) => [p[ph.s], p[ph.e]]).concat(p.end).filter(Boolean).map(parseDate);
    if (!dates.length) return null;
    const end = parseDate(p.end) || new Date(Math.max(...dates));
    if (end < today) return null;

    let current = null;
    for (const ph of PHASES) {
      const s = parseDate(p[ph.s]);
      const e = parseDate(p[ph.e]) || s;
      if (s && e && s <= today && today <= e) current = ph; // 겹치면 뒤 단계 우선
    }

    const events = [];
    for (const ph of PHASES) {
      const s = parseDate(p[ph.s]);
      if (s && s >= today) events.push({ date: s, label: ph.label + " 시작", phase: ph.key });
    }
    const siteEnd = parseDate(p.siteEnd);
    if (siteEnd && siteEnd >= today) events.push({ date: siteEnd, label: "현장작업 종료", phase: "site" });
    events.sort((a, b) => a.date - b.date);
    const next = annual ? null : events[0] || null;
    const days = next ? daysBetween(today, next.date) : null;

    let category;
    if (annual) category = "annual";
    else if (next && days <= opts.imminentDays) category = "imminent";
    else if (current && (current.key === "site" || current.key === "fat")) category = current.key;
    else {
      const focus = next ? next.phase : current ? current.key : "abb";
      category = focus === "site" ? "site" : focus === "fat" ? "fat" : "abb";
    }

    let badge;
    if (category === "annual") badge = "연간 계약 · ~" + fmtDate(end, today);
    else if (category === "imminent") badge = (days === 0 ? "D-DAY" : "D-" + days) + " · " + fmtDate(next.date, today) + " " + next.label;
    else if (current && current.key === "site") badge = "현장작업 중 · ~" + fmtDate(siteEnd || end, today);
    else if (next) badge = fmtDate(next.date, today) + " " + next.label;
    else if (current) badge = current.label + " 진행 중 · ~" + fmtDate(parseDate(p[current.e]) || end, today);
    else badge = "~" + fmtDate(end, today) + " 종료";

    return {
      category, badge, annual, next, days, end,
      phase: current ? current.key : null,
      onSite: (current && current.key === "site") || (annual && parseDate(p.abbStart) <= today),
    };
  }

  /**
   * @param projects  /api/schedule 의 projects
   * @param cfg       { sites, aliases, imminent_days, load_high, load_extreme }
   * @param today     Date (자정 기준)
   */
  function buildModel(projects, cfg, today) {
    const opts = { imminentDays: cfg.imminent_days ?? 14 };
    const sites = cfg.sites || [];

    // 1) 행 평가 → 같은 프로젝트 번호 + 현장끼리 묶기
    const groups = new Map();
    let activeRows = 0;
    for (const p of projects) {
      const st = evaluate(p, today, opts);
      if (!st) continue;
      activeRows++;
      const site = findSite(p, sites);
      const key = (p.no || p.name) + "|" + (site ? site.name : "");
      const row = { ...p, st, unit: unitOf(p) };
      if (!groups.has(key)) groups.set(key, { key, no: p.no, site, rows: [] });
      groups.get(key).rows.push(row);
    }

    // 목록 순서: 임박 → 현장작업 중 → FAT 중 → 연간계약 → 그 밖의 예정 (각각 가까운 날짜 순)
    const rank = (st) => {
      const tier = st.category === "imminent" ? 0 : st.phase === "site" ? 1 : st.phase === "fat" ? 2 : st.annual ? 3 : 4;
      const d = st.next ? daysBetween(today, st.next.date) : daysBetween(today, st.end);
      return tier * 100000 + Math.min(d, 99999);
    };

    for (const g of groups.values()) {
      g.rows.sort((a, b) => rank(a.st) - rank(b.st));
      const lead = g.rows[0];
      g.st = lead.st;
      const units = g.rows.map((r) => r.unit).filter(Boolean);
      g.title = titleOf(lead, cfg.aliases) + (units.length ? " " + units.join(" · ") : "");
      g.pm = lead.members[0] || "";
      g.eng = lead.members.slice(1);
      g.rank = rank(lead.st);
      g.onSite = g.rows.some((r) => r.st.onSite);
    }

    // 2) 엔지니어 현장 부하: 현장작업 중 + 진행 중인 연간계약 수 (PM 제외)
    const load = new Map();
    for (const g of groups.values()) {
      if (!g.onSite) continue;
      const engs = g.eng.length ? g.eng : [g.pm];
      for (const name of engs) {
        if (!name) continue;
        if (!load.has(name)) load.set(name, []);
        load.get(name).push(g);
      }
    }
    const high = cfg.load_high ?? 2, extreme = cfg.load_extreme ?? 3;
    const overloaded = [...load.entries()]
      .filter(([, gs]) => gs.length >= high)
      .map(([name, gs]) => ({
        name, count: gs.length, level: gs.length >= extreme ? "EXTREME" : "HIGH",
        sites: [...new Set(gs.map((g) => (g.site ? g.site.name : "미지정")))],
      }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "ko"));
    const overName = new Set(overloaded.map((o) => o.name));
    for (const g of groups.values()) {
      g.highLoad = g.st.phase === "site" && g.eng.some((n) => overName.has(n));
    }

    // 3) 현장별 묶음
    const bySite = new Map();
    for (const g of groups.values()) {
      const name = g.site ? g.site.name : "위치 미지정";
      if (!bySite.has(name)) bySite.set(name, { name, site: g.site, groups: [] });
      bySite.get(name).groups.push(g);
    }
    const siteList = [...bySite.values()].map((s) => {
      s.groups.sort((a, b) => a.rank - b.rank);
      s.category = s.groups.map((g) => g.st.category).sort((a, b) => CATEGORY[a].order - CATEGORY[b].order)[0];
      s.highLoad = s.groups.some((g) => g.highLoad);
      return s;
    });

    return { activeRows, groups: [...groups.values()], sites: siteList, overloaded };
  }

  // ───────── 2페이지 현황판 (월별 간트) ─────────

  // 현황판 막대가 놓이는 줄: ABB work / FAT·납품 / 현장작업
  const BOARD_LANE = { abb: 0, fat: 1, del: 1, site: 2 };
  // 월별 부하: 지도 '현장 부하 경고'와 같은 기준 — 현장작업 + 진행 중인 연간계약 (ENG 기준)
  const countsForLoad = (r, ph) => ph.key === "site" || (r.st.annual && ph.key === "abb");

  /**
   * @param months  표시할 개월 수 (이번 달부터)
   * @returns { months:[{y,m,label}], rows:[...], load:[{month, people:[{name, level}]}] }
   */
  function buildBoard(projects, cfg, today, months = 12) {
    const start = new Date(today.getFullYear(), today.getMonth(), 1);
    const monthList = [];
    for (let k = 0; k < months; k++) {
      const d = new Date(start.getFullYear(), start.getMonth() + k, 1);
      monthList.push({ y: d.getFullYear(), m: d.getMonth() + 1, label: `${String(d.getFullYear()).slice(2)}. ${d.getMonth() + 1}월` });
    }
    const end = new Date(start.getFullYear(), start.getMonth() + months, 1);
    // 날짜 → 0~months (월 칸 기준, 달마다 일수가 달라도 칸 너비는 같게)
    const pos = (d) => {
      if (d < start) return 0;
      if (d >= end) return months;
      const k = (d.getFullYear() - start.getFullYear()) * 12 + d.getMonth() - start.getMonth();
      const dim = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
      return k + (d.getDate() - 1) / dim;
    };
    const opts = { imminentDays: cfg.imminent_days ?? 14 };
    const high = cfg.load_high ?? 2, extreme = cfg.load_extreme ?? 3;

    const rows = [];
    for (const p of projects) {
      const st = evaluate(p, today, opts);
      if (!st) continue; // 이미 끝난 행
      const phases = [];
      for (const ph of PHASES) {
        let s = parseDate(p[ph.s]), e = parseDate(p[ph.e]);
        if (!s && !e) continue;
        s = s || e; e = e || s;
        if (e < s) e = s; // 엑셀 입력 오류(종료 < 시작) 보정
        phases.push({ key: ph.key, label: ph.label, s, e, lane: BOARD_LANE[ph.key] });
      }
      const begin = parseDate(p.abbStart) || (phases[0] && phases[0].s);
      const total = begin ? st.end - begin : 0;
      const progress = total > 0 ? Math.max(0, Math.min(100, Math.round(((today - begin) / total) * 100))) : 0;
      rows.push({ ...p, st, phases, progress, pm: p.members[0] || "", eng: p.members.slice(1) });
    }

    // 월별 엔지니어 부하: 그 달에 현장작업·연간계약이 걸친 프로젝트 수
    const load = monthList.map((mo, k) => {
      const ms = new Date(mo.y, mo.m - 1, 1), me = new Date(mo.y, mo.m, 0);
      const count = new Map();
      for (const r of rows) {
        const busy = r.phases.some((ph) => countsForLoad(r, ph) && ph.s <= me && ph.e >= ms);
        if (!busy) continue;
        for (const name of r.eng.length ? r.eng : [r.pm]) count.set(name, (count.get(name) || 0) + 1);
      }
      const people = [...count.entries()]
        .filter(([, n]) => n >= high)
        .map(([name, n]) => ({ name, count: n, level: n >= extreme ? "extreme" : "high" }))
        .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "ko"));
      return { k, ms, me, people };
    });

    // 막대 위치 계산 + 그 기간에 담당 엔지니어가 부하 상태면 표시
    for (const r of rows) {
      for (const ph of r.phases) {
        ph.from = pos(ph.s);
        ph.to = Math.max(pos(ph.e) + 1 / 30, ph.from + 0.12); // 하루짜리도 보이게
        ph.visible = ph.e >= start && ph.s < end;
        let level = null;
        if (countsForLoad(r, ph)) {
          for (const L of load) {
            if (ph.s > L.me || ph.e < L.ms) continue;
            for (const who of L.people) {
              if (r.eng.includes(who.name) || (!r.eng.length && r.pm === who.name)) {
                if (who.level === "extreme") level = "extreme";
                else if (!level) level = "high";
              }
            }
          }
        }
        ph.load = level;
      }
    }

    return { months: monthList, rows, load, today: pos(today) };
  }

  const api = { buildModel, buildBoard, evaluate, parseDate, fmtDate, cleanName, titleOf, CATEGORY };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ScheduleLogic = api;
})(this);
