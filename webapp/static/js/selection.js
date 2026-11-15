(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  function bindTable() {
    const table = document.getElementById("selectionTable");
    if (!table) return;
    const rows = Array.from(table.querySelectorAll("tbody tr"));
    const input = document.getElementById("selectionSearch");
    const count = document.getElementById("selectionCount");
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
      if (count) count.textContent = `${visible} 条`;
    };
    if (input) input.addEventListener("input", apply);
    chips.forEach((chip) => chip.addEventListener("click", () => {
      chips.forEach((item) => item.classList.toggle("active", item === chip));
      active = chip.dataset.filter || "all";
      apply();
    }));
    apply();
  }

  function submit(event) {
    event.preventDefault();
    const button = document.getElementById("selectionSubmit");
    const perClass = Number(document.getElementById("perClass").value || 10);
    const minGrade = ($("input[name='min_grade']:checked") || {}).value || "D";
    const modalities = $$("input[name='modality']:checked").map((item) => item.value);
    if (!modalities.length) {
      EEG.toast("至少选择一个模态。", "error");
      return;
    }
    EEG.startJob("/api/selection/run", {
      per_class: perClass,
      min_grade: minGrade,
      modalities,
    }, {
      button,
      consoleId: "selectionConsole",
      successMessage: "选材完成，正在刷新结果。",
      onSuccess: () => setTimeout(() => window.location.reload(), 700),
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindTable();
    const form = document.getElementById("selectionForm");
    if (form) form.addEventListener("submit", submit);
    const top = document.getElementById("runSelection");
    if (top) top.addEventListener("click", () => {
      const form = document.getElementById("selectionForm");
      if (form) form.requestSubmit();
    });
  });
})();
