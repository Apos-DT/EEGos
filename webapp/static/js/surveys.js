(function () {
  "use strict";
  let status = "all";
  function filterSurveys() {
    const query = (document.getElementById("surveySearch")?.value || "").trim().toLocaleLowerCase();
    let count = 0;
    document.querySelectorAll(".survey-tile").forEach((card) => {
      card.hidden = !((status === "all" || card.dataset.status === status) && card.dataset.search.toLocaleLowerCase().includes(query));
      if (!card.hidden) count++;
    });
    document.getElementById("surveyVisible").textContent = `${count} 个问卷`;
    document.getElementById("surveyEmpty").hidden = count > 0;
  }
  document.getElementById("surveySearch")?.addEventListener("input", filterSurveys);
  document.querySelectorAll("[data-survey-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      status = button.dataset.surveyFilter;
      document.querySelectorAll("[data-survey-filter]").forEach((item) => {
        item.classList.toggle("active", item === button);
        item.setAttribute("aria-pressed", String(item === button));
      });
      filterSurveys();
    });
  });
  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); EEG.toast("分享链接已复制", "success"); }
    catch (_) { prompt("复制分享链接", text); }
  }
  document.querySelectorAll(".copy-link").forEach((button) => {
    button.addEventListener("click", () => copyText(`${button.dataset.base || location.origin}${button.dataset.path}`));
  });
  document.querySelectorAll(".toggle-survey").forEach((button) => {
    button.addEventListener("click", async () => {
      EEG.setBusy(button, true, "处理中…");
      try {
        await EEG.api(`/api/surveys/${button.dataset.id}/toggle`, { method: "POST", body: "{}" });
        EEG.toast("问卷状态已更新", "success");
        setTimeout(() => window.location.reload(), 400);
      } catch (error) {
        EEG.setBusy(button, false);
        EEG.toast(error.message, "error");
      }
    });
  });
})();
