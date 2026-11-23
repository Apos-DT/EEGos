(() => {
  const byId = (id) => document.getElementById(id);
  const rows = Array.from(byId("catalogRows").rows);
  const search = byId("catalogSearch");
  const modality = byId("catalogModality");
  const dialog = byId("catalogDialog");
  const prev = byId("catalogPrev");
  const next = byId("catalogNext");
  const list = new EEG.ListController({
    items: rows,
    searchText: (row) => Array.from(row.cells).slice(0, 3).map((cell) => cell.textContent).join(" "),
    matches: (row, filters) => !filters.modality || row.dataset.modalities.split("|").includes(filters.modality),
    render: ({items, total, pages, page}) => {
      const visible = new Set(items);
      rows.forEach((row) => { row.hidden = !visible.has(row); });
      byId("catalogCount").textContent = `${total} / ${rows.length} 项`;
      byId("catalogEmpty").hidden = total !== 0;
      byId("catalogPager").hidden = pages <= 1;
      byId("catalogPage").textContent = `${page} / ${pages} 页`;
      prev.disabled = page <= 1;
      next.disabled = page >= pages;
    },
  });
  function applyFilters() {
    list.update({query: search.value, filters: {modality: modality.value}, page: 1, pageSize: 10});
  }
  search.addEventListener("input", applyFilters);
  modality.addEventListener("change", applyFilters);
  prev.addEventListener("click", () => list.update({page: list.state.page - 1}));
  next.addEventListener("click", () => list.update({page: list.state.page + 1}));
  byId("catalogRows").addEventListener("click", (event) => {
    const button = event.target.closest("[data-catalog-detail]");
    if (!button) return;
    const template = byId(`catalogDetail-${button.dataset.catalogDetail}`);
    byId("catalogTitle").textContent = button.closest("tr").cells[0].textContent.trim();
    byId("catalogDetail").replaceChildren(template.content.cloneNode(true));
    dialog.showModal();
  });
  applyFilters();
})();
