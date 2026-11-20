(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", () => {
    const $ = id => document.getElementById(id);
    const table = $("expTable");
    if (!table) return;
    const rows = Array.from(table.querySelectorAll("tbody tr"));
    const controller=new EEG.ListController({items:rows,searchText:r=>r.dataset.search,
      matches:(r,f)=>(!f.model || r.dataset.model===f.model) && (!f.protocol || r.dataset.group===f.protocol) && (!f.hideDemo || r.dataset.demo!=="1"),
      compare:(a,b,mode)=>(mode==="accuracy" || mode==="f1") ? Number(b.dataset[mode])-Number(a.dataset[mode]) : b.dataset.created.localeCompare(a.dataset.created)});
    const models = Array.from(new Set(rows.map(row => row.dataset.model).filter(Boolean))).sort();
    for (const model of models) {
      const option = document.createElement("option");
      option.value = model; option.textContent = model; $("expModel").append(option);
    }
    function apply() {
      const query = $("expSearch").value.trim().toLocaleLowerCase();
      const model = $("expModel").value;
      const protocol = $("expProtocol").value;
      const mode = $("expSort").value;
      const result=controller.update({query,filters:{model,protocol,hideDemo:$("expHideDemo").checked},sort:mode});
      rows.forEach(row=>{row.hidden=true;});result.items.forEach(row=>{row.hidden=false;});
      const visible=result.total;
      table.querySelector("tbody").append(...result.items);
      $("expCount").textContent = `${visible} / ${rows.length} 条记录`;
      $("expEmpty").hidden = visible > 0;
      $("experimentList").scrollTop = 0;
    }
    $("expSearch").addEventListener("input", apply);
    ["expModel", "expProtocol", "expSort", "expHideDemo"].forEach(id => $(id).addEventListener("change", apply));
    $("expReset")?.addEventListener("click", () => {
      $("expSearch").value = ""; $("expModel").value = ""; $("expProtocol").value = "";
      $("expSort").value = "recent"; $("expHideDemo").checked = false; apply();
    });
    apply();
  });
})();
