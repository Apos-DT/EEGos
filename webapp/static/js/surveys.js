(function () {
  "use strict";
  let status = "all";
  const cards=Array.from(document.querySelectorAll(".survey-tile"));
  const controller=new EEG.ListController({items:cards,searchText:r=>r.dataset.search,
    matches:(r,f)=>f.status==="all" || r.dataset.status===f.status,
    compare:(a,b,mode)=>mode==="responses" ? Number(b.dataset.responses)-Number(a.dataset.responses) : mode==="title" ? a.dataset.title.localeCompare(b.dataset.title,"zh-CN",{numeric:true}) : (b.dataset.updated||"").localeCompare(a.dataset.updated||"")});
  function closeMenus(except) {
    document.querySelectorAll(".survey-more[open]").forEach(menu => {
      if (menu !== except) menu.open = false;
    });
  }
  function sortSurveys() {
    filterSurveys();
  }
  function filterSurveys() {
    closeMenus();
    const query = (document.getElementById("surveySearch")?.value || "").trim().toLocaleLowerCase();
    const result=controller.update({query,filters:{status},sort:document.getElementById("surveySort").value});
    cards.forEach(card=>{card.hidden=true;});result.items.forEach(card=>{card.hidden=false;});
    document.getElementById("surveyGrid").append(...result.items);
    const count=result.total;
    document.getElementById("surveyVisible").textContent = `${count} 个问卷`;
    document.getElementById("surveyEmpty").hidden = count > 0;
  }
  document.getElementById("surveySearch")?.addEventListener("input", filterSurveys);
  document.getElementById("surveySort")?.addEventListener("change", sortSurveys);
  sortSurveys();
  document.querySelectorAll(".survey-more").forEach(menu => {
    menu.addEventListener("toggle", () => { if (menu.open) closeMenus(menu); });
  });
  document.addEventListener("click", event => {
    if (!event.target.closest(".survey-more")) closeMenus();
  });
  document.addEventListener("focusin", event => {
    closeMenus(event.target.closest(".survey-more"));
  });
  document.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    const menu = document.querySelector(".survey-more[open]");
    if (menu) { closeMenus(); menu.querySelector("summary").focus(); event.preventDefault(); }
  });
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
