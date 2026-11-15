(function () {
  const $ = (s, r = document) => r.querySelector(s);

  function collect() {
    const dataset = document.getElementById("datasetSelect");
    const model = $("input[name='model']:checked");
    const setting = $("input[name='setting']:checked");
    return {
      dataset_id: dataset ? dataset.value : "",
      model: model ? model.value : "dualview",
      setting: setting ? setting.value : "loso",
      epochs: Number(document.getElementById("epochs").value || 40),
      batch_size: Number(document.getElementById("batchSize").value || 32),
      lr: Number(document.getElementById("learningRate").value || 0.001),
      seed: Number(document.getElementById("seed").value || 42),
      hidden: Number(document.getElementById("hidden").value || 32),
      dropout: Number(document.getElementById("dropout").value || 0.25),
      prototypes: Number(document.getElementById("prototypes").value || 2),
      proto_weight: Number(document.getElementById("protoWeight").value || 0.1),
    };
  }

  function setState(text, tone) {
    const state = document.getElementById("runState");
    if (state) {
      state.textContent = text;
      state.className = `badge badge-${tone || "neutral"}`;
    }
    const hint = document.getElementById("runHint");
    if (hint && text !== "IDLE") hint.textContent = "任务日志实时写入下方控制台";
  }

  function renderResult(job) {
    const result = job.result || {};
    const metrics = result.metrics || {};
    const overall = metrics.overall || {};
    if (!overall.accuracy && overall.accuracy !== 0) {
      EEG.toast("任务完成，但未找到 metrics.json。", "error");
      return;
    }
    document.getElementById("trainingIdle").style.display = "none";
    document.getElementById("trainingResult").classList.add("show");
    document.getElementById("metricAcc").textContent = EEG.formatPct(overall.accuracy);
    document.getElementById("metricBal").textContent = EEG.formatPct(overall.balanced_accuracy);
    document.getElementById("metricF1").textContent = EEG.formatPct(overall.macro_f1);
    document.getElementById("metricKappa").textContent = Number(overall.cohen_kappa || 0).toFixed(3);
    document.getElementById("metricSetting").textContent = metrics.setting === "subject-dependent" ? "被试依赖" : "跨被试 LOSO";
    document.getElementById("metricModel").textContent = String(metrics.model || "").toUpperCase();
    document.getElementById("metricSamples").textContent = `${metrics.n_samples || 0} 样本 · ${metrics.n_subjects || 0} 被试`;
    const ci = overall.accuracy_ci95 || [];
    document.getElementById("metricCI").textContent = ci.length === 2 && ci[0] !== null
      ? `95% CI ${(ci[0] * 100).toFixed(1)}–${(ci[1] * 100).toFixed(1)}%`
      : "95% CI —";
    const runId = result.run_id;
    if (runId) {
      document.getElementById("openReport").href = `/api/experiments/${runId}/report`;
      document.getElementById("metricsLink").href = `/api/experiments/${runId}`;
      document.getElementById("confusionImage").src = `/api/experiments/${runId}/figure/confusion_matrix.png?v=${Date.now()}`;
      document.getElementById("subjectImage").src = `/api/experiments/${runId}/figure/per_subject_accuracy.png?v=${Date.now()}`;
    }
    document.getElementById("resultNote").textContent = runId && runId === "demo"
      ? "合成数据只用于软件验收"
      : `run_id: ${runId || "—"}`;
    document.getElementById("trainingResult").scrollIntoView({ behavior: "smooth", block: "start" });
    setState("DONE", "green");
  }


  function tuneForDataset() {
    const select = document.getElementById("datasetSelect");
    if (!select) return;
    const option = select.selectedOptions[0];
    const samples = Number(option?.dataset?.samples || 0);
    const hint = document.getElementById("datasetHint");
    if (samples > 10000) {
      document.getElementById("epochs").value = "15";
      document.getElementById("batchSize").value = "128";
      if (hint) hint.textContent = "大数据集：已建议 15 epochs / batch 128；完整 15 折 LOSO 可能较久，可先用 MLP 跑基线。";
    } else {
      if (hint) hint.textContent = "小数据集：默认 40 epochs / batch 32；DualView 可直接跑 8 折演示。";
    }
  }

  function submit(event) {
    if (event) event.preventDefault();
    const payload = collect();
    if (!payload.dataset_id) {
      EEG.toast("请选择一个特征数据集。", "error");
      return;
    }
    const button = document.getElementById("trainSubmit");
    setState("RUNNING", "blue");
    EEG.startJob("/api/train/run", payload, {
      button,
      consoleId: "trainingConsole",
      successMessage: "训练完成，指标已加载。",
      onSuccess: (job) => renderResult(job),
      onFail: () => setState("FAILED", "red"),
    });
  }

  function quickDemo() {
    const select = document.getElementById("datasetSelect");
    if (!select) return;
    const demo = Array.from(select.options).find((option) => option.text.includes("合成"));
    if (!demo) {
      EEG.toast("当前没有合成数据集；请先在“数据集”页生成。", "error");
      select.focus();
      return;
    }
    select.value = demo.value;
    document.getElementById("epochs").value = "20";
    document.querySelector("input[name='model'][value='dualview']").checked = true;
    document.querySelector("input[name='setting'][value='loso']").checked = true;
    document.getElementById("trainingForm").requestSubmit();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("trainingForm");
    if (form) form.addEventListener("submit", submit);
    const datasetSelect = document.getElementById("datasetSelect");
    if (datasetSelect) {
      datasetSelect.addEventListener("change", tuneForDataset);
      tuneForDataset();
    }
    const quick = document.getElementById("quickDemo");
    if (quick) quick.addEventListener("click", quickDemo);
    const top = document.getElementById("topTrain");
    if (top) top.addEventListener("click", () => {
      const form = document.getElementById("trainingForm");
      if (form) form.requestSubmit();
    });
  });
})();
