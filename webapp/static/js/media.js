(function () {
  "use strict";
  const search = document.getElementById("mediaSearch");
  const category = document.getElementById("mediaCategory");
  const selectedOnly = document.getElementById("mediaSelectedOnly");
  const table = document.getElementById("mediaTable");
  const count = document.getElementById("mediaCount");
  let modality = "all";
  if (!table) return;

  function apply() {
    const query = (search?.value || "").trim().toLowerCase();
    const cat = category?.value || "";
    const onlySelected = !!selectedOnly?.checked;
    let visible = 0;
    table.querySelectorAll("tbody tr").forEach((row) => {
      const matchText = !query || (row.dataset.search || "").toLowerCase().includes(query);
      const matchModality = modality === "all" || row.dataset.modality === modality;
      const matchCategory = !cat || row.dataset.category === cat;
      const matchSelected = !onlySelected || row.dataset.selected === "1";
      const show = matchText && matchModality && matchCategory && matchSelected;
      row.hidden = !show;
      if (show) visible += 1;
    });
    if (count) count.textContent = `${visible} 条`;
  }

  search?.addEventListener("input", apply);
  category?.addEventListener("change", apply);
  selectedOnly?.addEventListener("change", apply);
  document.querySelectorAll("#mediaModality .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#mediaModality .chip").forEach((item) => item.classList.remove("active"));
      chip.classList.add("active");
      modality = chip.dataset.filter || "all";
      apply();
    });
  });

  document.getElementById("mediaSync")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    EEG.setBusy(button, true, "同步中…");
    try {
      const response = await EEG.api("/api/media/sync", { method: "POST", body: "{}" });
      const job = response.job;
      EEG.renderJob(job, "mediaJob");
      EEG.pollJob(job.id, {
        consoleId: "mediaJob",
        onSuccess: () => {
          EEG.setBusy(button, false);
          EEG.toast("素材库已同步，正在刷新。", "success");
          setTimeout(() => window.location.reload(), 600);
        },
        onFail: () => EEG.setBusy(button, false),
      });
    } catch (error) {
      EEG.setBusy(button, false);
      EEG.toast(error.message, "error");
    }
  });
})();
