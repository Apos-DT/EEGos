(function () {
  "use strict";
  const search = document.getElementById("stimuliSearch");
  const category = document.getElementById("stimuliCategory");
  const table = document.getElementById("stimuliTable");
  const count = document.getElementById("stimuliCount");
  let modality = "all";
  if (!table) return;
  const rows=Array.from(table.querySelectorAll("tbody tr"));
  const controller=new EEG.ListController({items:rows,searchText:r=>r.dataset.search,matches:(r,f)=>(f.modality==="all"||r.dataset.modality===f.modality)&&(!f.category||r.dataset.category===f.category)});

  function apply() {
    const query = (search?.value || "").trim().toLowerCase();
    const cat = category?.value || "";
    const result=controller.update({query,filters:{modality,category:cat}});
    rows.forEach(row=>{row.hidden=true;});result.items.forEach(row=>{row.hidden=false;});
    const visible=result.total;
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
