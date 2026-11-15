(function () {
  "use strict";
  const search = document.getElementById("responseSearch");
  const filter = document.getElementById("responseFilter");
  const table = document.getElementById("responseTable");
  if (!table) return;

  function apply() {
    const query = (search?.value || "").trim().toLowerCase();
    const discrete = filter?.value || "";
    table.querySelectorAll("tbody tr").forEach((row) => {
      const haystack = (row.dataset.search || "").toLowerCase();
      const matchQuery = !query || haystack.includes(query);
      const matchDiscrete = !discrete || row.dataset.discrete === discrete;
      row.hidden = !(matchQuery && matchDiscrete);
    });
  }

  search?.addEventListener("input", apply);
  filter?.addEventListener("change", apply);
})();
