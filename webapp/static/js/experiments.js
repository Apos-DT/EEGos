(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  function chart() {
    const payload = document.getElementById("experimentData");
    if (!payload) return;
    const experiments = JSON.parse(payload.textContent);
    const rows = experiments
      .filter((item) => item.accuracy !== null && item.accuracy !== undefined)
      .sort((a, b) => b.accuracy - a.accuracy)
      .slice(0, 8)
      .map((item) => ({
        label: item.label.length > 22 ? `${item.label.slice(0, 22)}…` : item.label,
        value: Number(item.accuracy) * 100,
        display: `${(Number(item.accuracy) * 100).toFixed(1)}%`,
        color: item.is_demo ? "#d08a24" : "#0c7368",
      }));
    EESCharts.horizontalBars(document.getElementById("experimentChart"), rows, {
      title: "实验 Accuracy 对比",
      rowH: 34,
    });
  }

  function filter() {
    const table = document.getElementById("expTable");
    if (!table) return;
    const rows = Array.from(table.querySelectorAll("tbody tr"));
    const input = document.getElementById("expSearch");
    const count = document.getElementById("expCount");
    const chips = $$(".chips .chip");
    let active = "all";
    const apply = () => {
      const query = (input && input.value ? input.value : "").trim().toLowerCase();
      let visible = 0;
      rows.forEach((row) => {
        const show = (active === "all" || row.dataset.group === active) &&
          (!query || (row.dataset.search || "").toLowerCase().includes(query));
        row.style.display = show ? "" : "none";
        if (show) visible += 1;
      });
      if (count) count.textContent = `${visible} 次`;
    };
    if (input) input.addEventListener("input", apply);
    chips.forEach((chip) => chip.addEventListener("click", () => {
      chips.forEach((item) => item.classList.toggle("active", item === chip));
      active = chip.dataset.filter;
      apply();
    }));
    apply();
  }

  document.addEventListener("DOMContentLoaded", () => {
    chart();
    filter();
  });
})();
