(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  function initTabs() {
    $$(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        const name = tab.dataset.tab;
        $$(".tab").forEach((item) => item.classList.toggle("active", item === tab));
        $$(".tab-panel").forEach((panel) => { panel.hidden = panel.dataset.panel !== name; });
      });
    });
  }

  function bindFilter(inputId, tableId, countId, chipsSelector) {
    EEG.filterTable({input:inputId,table:tableId,count:countId,chips:chipsSelector});
  }

  function chart() {
    const payload = JSON.parse(document.getElementById("auditChartData").textContent);
    const labels = ["S 级", "A 级", "B 级", "C 级", "D 级"];
    const grades = ["S", "A", "B", "C", "D"];
    EESCharts.barChart(document.getElementById("auditQualityChart"), {
      labels,
      series: [
        { name: "视频", color: "#0c7368", values: grades.map((g) => Number(payload.video[g] || 0)) },
        { name: "音乐", color: "#6ea8fe", values: grades.map((g) => Number(payload.audio[g] || 0)) },
      ],
    }, { title: "质量等级分布" });
  }

  function runAudit(button) {
    const probe = document.getElementById("probeMedia");
    const target = button || document.getElementById("runAudit") || document.getElementById("runAuditEmpty");
    EEG.startJob("/api/audit/run", { probe_media: !!(probe && probe.checked) }, {
      button: target,
      consoleId: "auditConsole",
      successMessage: "审计完成，正在刷新数据。",
      onSuccess: () => setTimeout(() => window.location.reload(), 700),
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const run = document.getElementById("runAudit");
    if (run) run.addEventListener("click", () => runAudit(run));
    const empty = document.getElementById("runAuditEmpty");
    if (empty) empty.addEventListener("click", () => runAudit(empty));
    if (!document.getElementById("auditQualityChart")) return;
    initTabs();
    chart();
    bindFilter("raterSearch", "raterTable", "raterCount", "[data-panel='raters'] .chip");
    bindFilter("issueSearch", "issueTable", "issueCount", "[data-panel='issues'] .chip");
    bindFilter("qualitySearch", "qualityTable", "qualityCount", "[data-panel='quality'] .chip");
  });
})();
