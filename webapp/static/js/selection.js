(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  function bindTable() {
    EEG.filterTable({input:"selectionSearch",table:"selectionTable",count:"selectionCount",chips:".chips .chip"});
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
