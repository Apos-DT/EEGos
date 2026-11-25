(() => {
  const dataset = document.getElementById("merDataset");
  dataset?.addEventListener("change", () => dataset.form.requestSubmit());

  for (const name of ["Import", "Fusion"]) {
    const dialog = document.getElementById(`mer${name}Dialog`);
    document.getElementById(`mer${name}Open`)?.addEventListener("click", () => dialog.showModal());
  }
})();
