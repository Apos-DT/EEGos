(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  function upload(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".npz")) {
      EEG.toast("请选择 .npz 文件。", "error");
      return;
    }
    const zone = document.getElementById("dropzone");
    const progress = document.getElementById("uploadProgress");
    const bar = progress ? progress.querySelector("span") : null;
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/raw/upload?filename=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    if (progress) progress.classList.add("show");
    if (zone) zone.classList.add("dragover");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && bar) bar.style.width = `${Math.round((event.loaded / event.total) * 100)}%`;
    };
    xhr.onload = () => {
      if (zone) zone.classList.remove("dragover");
      if (xhr.status >= 200 && xhr.status < 300) {
        if (bar) bar.style.width = "100%";
        EEG.toast("上传成功，正在刷新数据列表。", "success");
        setTimeout(() => window.location.reload(), 650);
      } else {
        let message = "上传失败";
        try { message = JSON.parse(xhr.responseText).detail || message; } catch (_) {}
        if (progress) progress.classList.remove("show");
        if (bar) bar.style.width = "0";
        EEG.toast(message, "error", 6000);
      }
    };
    xhr.onerror = () => {
      if (zone) zone.classList.remove("dragover");
      EEG.toast("网络错误，上传失败。", "error");
    };
    xhr.send(file);
  }

  function submitFeatures(event) {
    event.preventDefault();
    const button = document.getElementById("featureSubmit");
    const rawId = document.getElementById("rawSelect").value;
    if (!rawId) {
      EEG.toast("请先选择一个 raw.npz。", "error");
      return;
    }
    const sourceFs = document.getElementById("sourceFs").value.trim();
    const targetFs = document.getElementById("targetFs").value.trim();
    const payload = {
      raw_id: rawId,
      fs: sourceFs ? Number(sourceFs) : null,
      target_fs: targetFs ? Number(targetFs) : null,
      window: Number(document.getElementById("windowSize").value || 1),
      step: Number(document.getElementById("stepSize").value || 1),
      aggregate: document.getElementById("aggregate").value,
      notch: document.getElementById("notch").value.trim() ? Number(document.getElementById("notch").value) : null,
    };
    EEG.startJob("/api/features/run", payload, {
      button,
      consoleId: "featureConsole",
      successMessage: "特征构建完成，正在刷新数据集。",
      onSuccess: () => setTimeout(() => window.location.reload(), 700),
    });
  }

  function selectedDatasetIds() {
    return $$(".dataset-check:checked").map((input) => input.dataset.id);
  }

  function updateMergeState() {
    const ids = selectedDatasetIds();
    const count = document.getElementById("mergeCount");
    const button = document.getElementById("mergeDatasets");
    if (count) count.textContent = `已选 ${ids.length} 个`;
    if (button) button.disabled = ids.length < 2;
  }

  async function mergeDatasets() {
    const ids = selectedDatasetIds();
    if (ids.length < 2) return;
    const button = document.getElementById("mergeDatasets");
    EEG.setBusy(button, true, "合并中…");
    try {
      await EEG.api("/api/datasets/merge", {
        method: "POST",
        body: JSON.stringify({ dataset_ids: ids }),
      });
      EEG.toast("特征集已合并，正在刷新。", "success");
      setTimeout(() => window.location.reload(), 650);
    } catch (error) {
      EEG.setBusy(button, false);
      EEG.toast(error.message, "error", 6000);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const zone = document.getElementById("dropzone");
    const input = document.getElementById("fileInput");
    if (zone && input) {
      zone.addEventListener("click", () => input.click());
      zone.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") input.click();
      });
      input.addEventListener("change", () => upload(input.files[0]));
      ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => {
        event.preventDefault();
        zone.classList.add("dragover");
      }));
      ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => {
        event.preventDefault();
        zone.classList.remove("dragover");
      }));
      zone.addEventListener("drop", (event) => upload(event.dataTransfer.files[0]));
    }
    $$(".use-raw").forEach((button) => button.addEventListener("click", () => {
      const select = document.getElementById("rawSelect");
      if (select) {
        select.value = button.dataset.raw;
        select.scrollIntoView({ behavior: "smooth", block: "center" });
        select.focus();
      }
    }));
    const form = document.getElementById("featureForm");
    if (form) form.addEventListener("submit", submitFeatures);
    $$(".dataset-check").forEach((input) => input.addEventListener("change", updateMergeState));
    updateMergeState();
    const mergeButton = document.getElementById("mergeDatasets");
    if (mergeButton) mergeButton.addEventListener("click", mergeDatasets);
  });
})();
