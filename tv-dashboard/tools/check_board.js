// 2페이지 현황판 계산 결과를 콘솔로 확인:  node tools/check_board.js [YYYY-MM-DD]
const { execFileSync } = require("child_process");
const path = require("path");
const L = require("../static/schedule-logic.js");
const data = JSON.parse(execFileSync("python3", ["-c",
  "import json,server;print(json.dumps(server.get_schedule(server.load_config()),ensure_ascii=False))"], { cwd: path.join(__dirname, "..") }));
const cfg = require("../config.json");
const t = process.argv[2] ? L.parseDate(process.argv[2]) : new Date(new Date().toDateString());
const b = L.buildBoard(data.projects, cfg, t);
console.log("월:", b.months.map((m) => m.label).join(" | "));
console.log("부하:", b.load.map((l, k) => b.months[k].label + " " + l.people.map((p) => p.name + "(" + p.level + ")").join(",")).filter((x) => x.includes("(")).join(" / ") || "없음");
for (const r of b.rows) {
  console.log(`KR-${r.no} ${r.name.slice(0, 34).padEnd(34)} ${r.progress}%  ` +
    r.phases.filter((p) => p.visible).map((p) => `${p.label}[${p.from.toFixed(1)}~${p.to.toFixed(1)}]${p.load ? "!" + p.load : ""}`).join(" "));
}
