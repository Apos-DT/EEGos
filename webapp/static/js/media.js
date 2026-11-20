(function () {
  "use strict";
  const search = document.getElementById("mediaSearch");
  const category = document.getElementById("mediaCategory");
  const selectedOnly = document.getElementById("mediaSelectedOnly");
  const availability = document.getElementById("mediaAvailability");
  const table = document.getElementById("mediaTable");
  const count = document.getElementById("mediaCount");
  const listViewport = document.getElementById("mediaListViewport");
  let modality = "all";
  if (!table) return;
  const rows = Array.from(table.querySelectorAll("tbody tr"));
  const pageSize = document.getElementById("mediaPageSize");
  const pageButtons = document.getElementById("mediaPages");
  const prev = document.getElementById("mediaPrev");
  const next = document.getElementById("mediaNext");
  let page = 1;
  let totalPages = 1;
  const queryController = new EEG.ListController({items:rows, searchText:row=>row.dataset.search,
    matches:(row,f)=>(f.modality==="all" || row.dataset.modality===f.modality) && (!f.category || row.dataset.category===f.category) && (!f.selected || row.dataset.selected==="1") && (!f.availability || row.dataset.available===(f.availability==="available" ? "1" : "0"))});

  function renderPagination(total, start, size) {
    document.getElementById("mediaPagination").hidden = total === 0;
    document.getElementById("mediaPageRange").textContent = `${total ? start + 1 : 0}–${Math.min(start + size, total)} / ${total} 条`;
    prev.disabled = page <= 1;
    next.disabled = page >= totalPages;
    const focusedPage = pageButtons.contains(document.activeElement) ? document.activeElement.dataset.page : null;
    pageButtons.replaceChildren();
    let last = 0;
    for (let n = 1; n <= totalPages; n++) {
      if (n !== 1 && n !== totalPages && Math.abs(n - page) > 1) continue;
      if (last && n - last > 1) {
        const dots = document.createElement("span"); dots.textContent = "…"; dots.setAttribute("aria-hidden", "true"); pageButtons.append(dots);
      }
      const button = document.createElement("button");
      button.type = "button"; button.className = "media-page-number";
      button.textContent = n; button.dataset.page = n;
      button.setAttribute("aria-label", `第 ${n} 页`);
      if (n === page) button.setAttribute("aria-current", "page");
      pageButtons.append(button);
      last = n;
    }
    if (focusedPage) pageButtons.querySelector(`[data-page="${page}"]`)?.focus({preventScroll:true});
  }

  function apply(resetPage = true) {
    if (resetPage) page = 1;
    const size = Number(pageSize.value);
    const result=queryController.update({query:search.value,filters:{modality,category:category.value,selected:selectedOnly.checked,availability:availability.value},page,pageSize:size});
    const {matches,start}=result; totalPages=result.pages; page=result.page;
    rows.forEach(row => { row.hidden = true; });
    result.items.forEach(row => { row.hidden = false; });
    if (count) count.textContent = `${matches.length} 条`;
    document.getElementById("mediaEmpty").hidden = matches.length > 0;
    renderPagination(matches.length, start, size);
    listViewport.scrollTop = 0;
  }

  function goToPage(target) {
    page = Math.max(1, Math.min(target, totalPages));
    apply(false);
  }
  prev.addEventListener("click", () => goToPage(page - 1));
  next.addEventListener("click", () => goToPage(page + 1));
  pageButtons.addEventListener("click", event => {
    const button = event.target.closest("button[data-page]");
    if (button) goToPage(Number(button.dataset.page));
  });
  pageSize.addEventListener("change", () => apply());

  function resetFilters(view = "all") {
    search.value = "";
    category.value = "";
    modality = "all";
    selectedOnly.checked = view === "selected";
    availability.value = view === "missing" ? "missing" : "";
    document.querySelectorAll("#mediaModality .chip").forEach(chip => chip.classList.toggle("active", chip.dataset.filter === "all"));
    apply();
  }
  document.querySelectorAll("[data-media-view]").forEach(button => button.addEventListener("click", () => resetFilters(button.dataset.mediaView)));
  document.getElementById("mediaReset")?.addEventListener("click", () => resetFilters());

  search?.addEventListener("input", apply);
  category?.addEventListener("change", apply);
  selectedOnly?.addEventListener("change", apply);
  availability?.addEventListener("change", apply);
  apply();
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
