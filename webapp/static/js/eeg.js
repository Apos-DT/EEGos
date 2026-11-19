(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const dropzone = $("eegDropzone");
  const fileInput = $("eegFile");
  const summary = $("eegUploadSummary");
  const configPanel = $("eegConfigPanel");
  let currentUpload = null;

  function setError(message) {
    const box = $("eegUploadError");
    if (!box) return;
    box.textContent = message || "";
    box.hidden = !message;
  }

  function renderUpload(upload) {
    currentUpload = upload;
    $("eegUploadId").value = upload.upload_id;
    $("eegSummaryName").textContent = upload.filename;
    $("eegSummaryStats").innerHTML = [
      `<div><small>CHANNELS</small><strong>${upload.n_channels}</strong></div>`,
      `<div><small>FS</small><strong>${upload.fs} Hz</strong></div>`,
      `<div><small>DURATION</small><strong>${Number(upload.duration_s).toFixed(1)} s</strong></div>`,
      `<div><small>EVENTS</small><strong>${upload.n_events}</strong></div>`,
    ].join("");
    $("eegSummaryEvents").textContent = upload.n_events
      ? `事件码：${(upload.event_types || []).join("、") || "—"}；将按事件映射切 trial。`
      : "未检测到事件：仍会输出清洗后的连续数据，但不会生成训练集。";
    summary.hidden = false;
    configPanel.hidden = false;
    $("eegSubject").value = upload.subject || "";
    $("eegConfigHint").textContent = `${upload.filename} · ${upload.n_channels} ch · ${upload.fs} Hz · 设置参数后开始清洗。`;
    $("eegResult").hidden = true;
    $("eegUploadError").hidden = true;
    summary.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function uploadFile(file) {
    if (!file) return;
    if (!/\.(set|zip)$/i.test(file.name)) {
      setError("请选择 .set 或包含 .set/.fdt 的 .zip 文件。");
      return;
    }
    setError("");
    const progress = $("eegUploadProgress");
    progress.hidden = false;
    progress.querySelector("span").style.width = "18%";
    $("eegUploadTitle").textContent = `正在上传 ${file.name}…`;
    try {
      const response = await fetch(`/api/eeg/upload?filename=${encodeURIComponent(file.name)}`, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      });
      progress.querySelector("span").style.width = "75%";
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "上传失败");
      progress.querySelector("span").style.width = "100%";
      $("eegUploadTitle").textContent = "文件已读取";
      renderUpload(payload.upload);
      EEG.toast("EEG 文件已读取", "success");
    } catch (error) {
      setError(error.message);
      $("eegUploadTitle").textContent = "拖入 .set 或 .zip，或点击选择文件";
    } finally {
      setTimeout(() => { progress.hidden = true; }, 500);
    }
  }

  $("eegPick")?.addEventListener("click", () => fileInput.click());
  dropzone?.addEventListener("click", (event) => {
    if (event.target.closest("button")) return;
    fileInput.click();
  });
  fileInput?.addEventListener("change", () => uploadFile(fileInput.files[0]));
  ["dragenter", "dragover"].forEach((name) => dropzone?.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((name) => dropzone?.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
  }));
  dropzone?.addEventListener("drop", (event) => uploadFile(event.dataTransfer.files[0]));

  $("eegReset")?.addEventListener("click", () => {
    currentUpload = null;
    summary.hidden = true;
    configPanel.hidden = true;
    $("eegResult").hidden = true;
    $("eegUploadTitle").textContent = "拖入 .set 或 .zip，或点击选择文件";
    fileInput.value = "";
  });

  function renderResult(uploadId, report) {
    const result = report || {};
    $("eegResult").hidden = false;
    $("eegResultTitle").textContent = `${result.setname || "EEGLAB"} · ${result.n_channels || "—"} ch · ${result.duration_s || "—"} s`;
    const preview = `/files/eeg/${encodeURIComponent(uploadId)}/eeg_preview.png?t=${Date.now()}`;
    $("eegPreview").innerHTML = `<img src="${preview}" alt="EEG before/after"><div class="hint">前 4 通道：灰线为滤波前，青线为滤波后（前 20 s）。</div>`;
    const before = result.before || {};
    const after = result.after || {};
    $("eegMetrics").innerHTML = `
      <div class="eeg-metric"><small>输入采样率</small><strong>${result.input_fs} Hz</strong></div>
      <div class="eeg-metric"><small>输出采样率</small><strong>${result.output_fs} Hz</strong></div>
      <div class="eeg-metric"><small>事件数</small><strong>${result.n_events}</strong></div>
      <div class="eeg-metric"><small>峰值幅度</small><strong>${after.peak_abs_uv ?? "—"} µV</strong></div>
      <div class="eeg-metric"><small>平直通道</small><strong>${after.flat_channels ?? "—"}</strong></div>
      <div class="eeg-metric"><small>训练 trial</small><strong>${result.training?.n_trials ?? 0}</strong></div>`;
    const links = [
      ["eeg_clean.npz", "清洗后的连续 EEG"],
      ["eeg_report.json", "完整 JSON 报告"],
    ];
    if (result.files?.raw) links.push(["raw.npz", "按事件切分的 trial"]);
    if (result.files?.features) links.push(["features.npz", "DE 特征（可训练）"]);
    if (result.files?.preview) links.push(["eeg_preview.png", "前后对比图"]);
    $("eegFiles").innerHTML = links.map(([name, label]) =>
      `<a class="file-pill" href="/files/eeg/${encodeURIComponent(uploadId)}/${name}" target="_blank">${iconText(name)}<span>${label}</span></a>`
    ).join("") + (result.training
      ? `<a class="btn btn-primary btn-sm" href="/training">去训练 →</a><span class="hint">单个 .set = 单个被试；LOSO 需多名被试的特征集。</span>`
      : `<span class="hint">未产生有效训练片段；请检查事件映射、边界与质量阈值。</span>`);
    $("eegResult").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function iconText(name) {
    return `<span class="mono">${name}</span>`;
  }

  $("eegForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!currentUpload) {
      setError("请先上传 EEGLAB 文件。");
      return;
    }
    const payload = {
      upload_id: currentUpload.upload_id,
      subject: $("eegSubject").value.trim(),
      bandpass_low: Number($("eegLow").value),
      bandpass_high: Number($("eegHigh").value),
      notch: Number($("eegNotch").value),
      target_fs: Number($("eegTargetFs").value),
      reref: $("eegReref").value,
      epoch_start: Number($("eegEpochStart").value),
      epoch_end: Number($("eegEpochEnd").value),
      reject: Number($("eegReject").value),
      event_map: $("eegEventMap").value.trim(),
      window: Number($("eegWindow").value),
      ica: $("eegIca").checked,
    };
    const button = $("eegRun");
    EEG.setBusy(button, true, "提交中…");
    try {
      const response = await EEG.api("/api/eeg/process", { method: "POST", body: JSON.stringify(payload) });
      const job = response.job;
      EEG.renderJob(job, "eegJob");
      EEG.toast("EEG 清洗任务已提交", "success");
      EEG.pollJob(job.id, {
        consoleId: "eegJob",
        onSuccess: (finished) => {
          EEG.setBusy(button, false);
          EEG.toast("EEG 清洗完成", "success");
          renderResult(payload.upload_id, finished.result?.report || {});
        },
        onFail: () => EEG.setBusy(button, false),
      });
    } catch (error) {
      EEG.setBusy(button, false);
      setError(error.message);
    }
  });

  document.querySelectorAll("[data-resume-eeg]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const response = await EEG.api(`/api/eeg/report/${encodeURIComponent(button.dataset.resumeEeg)}`);
        renderUpload(response.upload);
        if (response.report && Object.keys(response.report).length) {
          renderResult(response.upload.upload_id, response.report);
        }
      } catch (error) {
        EEG.toast(error.message, "error");
      }
    });
  });
})();
