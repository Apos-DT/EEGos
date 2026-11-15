(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  document.addEventListener("DOMContentLoaded", () => {
    const cards = $$(".doc-card");
    const input = document.getElementById("docSearch");
    const count = document.getElementById("docCount");
    const empty = document.getElementById("docEmpty");
    const chips = $$(".chips .chip");
    let active = "all";
    const apply = () => {
      const query = (input && input.value ? input.value : "").trim().toLowerCase();
      let visible = 0;
      cards.forEach((card) => {
        const show = (active === "all" || card.dataset.group === active) &&
          (!query || (card.dataset.search || "").toLowerCase().includes(query));
        card.hidden = !show;
        if (show) visible += 1;
      });
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
