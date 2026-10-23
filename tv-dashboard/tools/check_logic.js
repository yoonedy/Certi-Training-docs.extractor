// 엑셀 → 모델 결과를 콘솔로 확인:  python -c "..." 대신  node tools/check_logic.js [YYYY-MM-DD]
const { execFileSync } = require("child_process");
const path = require("path");
const L = require("../static/schedule-logic.js");
const root = path.join(__dirname, "..");
const data = JSON.parse(execFileSync("python3", ["-c",
  "import json,server;print(json.dumps(server.get_schedule(server.load_config()),ensure_ascii=False))"], { cwd: root }));
const cfg = require("../config.json");
const t = process.argv[2] ? L.parseDate(process.argv[2]) : new Date(new Date().toDateString());
const m = L.buildModel(data.projects, cfg, t);
console.log("기준일", t.toDateString(), "· 진행/예정", m.activeRows, "건");
for (const s of m.sites) {
  console.log(`\n[${s.name}] ${s.category}${s.highLoad ? " HIGH" : ""}`);
  for (const g of s.groups) console.log(`  ${g.st.category.padEnd(8)} ${g.title} | ${g.st.badge} | PM ${g.pm} ENG ${g.eng.join(",")}${g.highLoad ? " [HIGH LOAD]" : ""}`);
}
console.log("\n부하 경고:", m.overloaded.map((o) => `${o.name}(${o.count}, ${o.level}, ${o.sites})`).join(" / "));
