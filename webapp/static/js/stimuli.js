(function () {
  "use strict";
  const search = document.getElementById("stimuliSearch");
  const category = document.getElementById("stimuliCategory");
  const table = document.getElementById("stimuliTable");
  const count = document.getElementById("stimuliCount");
  let modality = "all";
  if (!table) return;

  function apply() {
    const query = (search?.value || "").trim().toLowerCase();
    const cat = category?.value || "";
    let visible = 0;
    table.querySelectorAll("tbody tr").forEach((row) => {
      const matchText = !query || (row.dataset.search || "").toLowerCase().includes(query);
      const matchModality = modality === "all" || row.dataset.modality === modality;
      const matchCategory = !cat || row.dataset.category === cat;
      const show = matchText && matchModality && matchCategory;
      row.hidden = !show;
      if (show) visible += 1;
    });
    if (count) count.textContent = `${visible} 条`;
  }

  search?.addEventListener("input", apply);
  category?.addEventListener("change", apply);
  document.querySelectorAll("#stimuliModality .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#stimuliModality .chip").forEach((item) => item.classList.remove("active"));
      chip.classList.add("active");
      modality = chip.dataset.filter || "all";
      apply();
    });
  });
})();
