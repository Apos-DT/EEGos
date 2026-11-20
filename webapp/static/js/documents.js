(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  document.addEventListener("DOMContentLoaded", () => {
    const cards = $$(".doc-card");
    const controller=new EEG.ListController({items:cards,searchText:card=>card.dataset.search,matches:(card,f)=>f.active==="all" || card.dataset.group===f.active});
    const input = document.getElementById("docSearch");
    const count = document.getElementById("docCount");
    const empty = document.getElementById("docEmpty");
    const chips = $$(".chips .chip");
    let active = "all";
    const apply = () => {
      const query = (input && input.value ? input.value : "").trim().toLowerCase();
      const result=controller.update({query,filters:{active}});
      cards.forEach(card=>{card.hidden=true;});result.items.forEach(card=>{card.hidden=false;});
      const visible=result.total;
      if (count) count.textContent = `${visible} 份`;
      if (empty) empty.hidden = visible !== 0;
    };
    if (input) input.addEventListener("input", apply);
    chips.forEach((chip) => chip.addEventListener("click", () => {
      chips.forEach((item) => item.classList.toggle("active", item === chip));
      active = chip.dataset.filter || "all";
      apply();
    }));
    apply();
  });
})();
