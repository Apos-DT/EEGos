(function () {
  "use strict";
  const form = document.getElementById("surveyForm");
  const table = document.getElementById("builderTable");
  const search = document.getElementById("builderSearch");
  const category = document.getElementById("builderCategory");
  const selectedCount = document.getElementById("selectedCount");
  const visible = document.getElementById("builderVisible");
  const error = document.getElementById("builderError");
  let modality = "all";
  if (!form || !table) return;

  function picks() { return Array.from(document.querySelectorAll(".media-pick:checked")); }
  function updateCount() {
    const count = picks().length;
    if (selectedCount) selectedCount.textContent = `已选 ${count} 个`;
  }
  function filterRows() {
    const query = (search?.value || "").trim().toLowerCase();
    const cat = category?.value || "";
    let n = 0;
    table.querySelectorAll("tbody tr").forEach((row) => {
      const show = (!query || (row.dataset.search || "").toLowerCase().includes(query))
        && (modality === "all" || row.dataset.modality === modality)
        && (!cat || row.dataset.category === cat);
      row.hidden = !show;
      if (show) n += 1;
    });
    if (visible) visible.textContent = `${n} 条`;
  }

  document.querySelectorAll(".media-pick").forEach((input) => input.addEventListener("change", updateCount));
  search?.addEventListener("input", filterRows);
  category?.addEventListener("change", filterRows);
  document.querySelectorAll("#builderModality .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#builderModality .chip").forEach((item) => item.classList.remove("active"));
      chip.classList.add("active");
      modality = chip.dataset.filter || "all";
      filterRows();
    });
  });
  document.getElementById("clearSelection")?.addEventListener("click", () => {
    document.querySelectorAll(".media-pick:checked").forEach((input) => { input.checked = false; });
    updateCount();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const ids = picks().map((input) => input.value);
    if (!ids.length) {
      error.textContent = "请选择至少一个素材。";
      error.hidden = false;
      return;
    }
    const title = document.getElementById("surveyTitle").value.trim();
    if (!title) {
      error.textContent = "请填写问卷标题。";
      error.hidden = false;
      return;
    }
    const payload = {
      title,
      description: document.getElementById("surveyDescription").value.trim(),
      material_ids: ids,
      require_code: document.getElementById("requireCode").checked,
      allow_multiple: document.getElementById("allowMultiple").checked,
    };
    const surveyId = form.dataset.surveyId;
    const button = document.getElementById("saveSurvey");
    EEG.setBusy(button, true, "保存中…");
    try {
      const url = surveyId ? `/api/surveys/${encodeURIComponent(surveyId)}` : "/api/surveys";
      await EEG.api(url, { method: surveyId ? "PUT" : "POST", body: JSON.stringify(payload) });
      EEG.toast("问卷已保存，分享链接已生成", "success");
      setTimeout(() => { window.location.href = "/surveys"; }, 500);
    } catch (err) {
      EEG.setBusy(button, false);
      error.textContent = err.message;
      error.hidden = false;
    }
  });

  updateCount();
  filterRows();
})();
