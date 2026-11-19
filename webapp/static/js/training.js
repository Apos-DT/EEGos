(function () {
  const $ = (s, r = document) => r.querySelector(s);
  let busy = false;
  const method = () => $("input[name='model']:checked").value;
  const isDDA = () => method() === "dda";

  function syncConfig() {
    const dda = isDDA();
    $("#standardConfig").hidden = dda;
    $("#standardConfig").disabled = dda;
    $("#ddaConfig").hidden = !dda;
    $("#ddaConfig").disabled = !dda;
    const crossSession = $("#ddaSetting").value === "cross-session";
    $("#ddaSubject").disabled = crossSession;
    if (crossSession) $("#ddaSubject").value = "";
    $("#ddaLabeledTrials").disabled = $("#ddaAlgorithm").value !== "SDDA";
    const sessions = $("#ddaSession").value ? 1 : 3;
    const subjects = $("#ddaSubject").value ? 1 : 15;
    const folds = crossSession ? sessions : sessions * subjects;
    const limit = Number($("#ddaMaxFolds").value);
    $("#ddaFoldHint").textContent = `当前配置运行 ${limit > 0 ? Math.min(limit, folds) : folds} 折，每折 ${$("#ddaEpochs").value} 轮。完整跨被试为 45 折，跨会话为 3 折。`;
    $("#quickDemo").hidden = dda;
    const semi = $("#ddaAlgorithm").value === "SDDA";
    $("#ddaLabelField").hidden = !semi;
    $("#ddaAlgorithmHint").textContent = semi ? "部分目标 trial 标签参与训练，其余目标数据无标签适配。" : "目标标签仅用于评估，不参与梯度更新。";
    document.querySelectorAll("[data-dualview]").forEach((field) => {
      field.hidden = method() !== "dualview";
      field.querySelector("input").disabled = method() !== "dualview";
    });
    $("#methodHint").textContent = dda ? "DDA 使用论文 MLP 骨干进行域适配；在下方选择适配变体与目标域。" : "所选模型使用特征数据集训练；验证与测试划分由评估协议决定。";
    const modelLabel = {dda: "DDA", mlp: "MLP", dgcnn: "DGCNN", dualview: "DualView"}[method()];
    $("#experimentSummary").textContent = dda
      ? `${modelLabel} / ${$("#ddaAlgorithm").value} · SEED-IV · ${crossSession ? "跨会话" : "跨被试"} · ${limit > 0 ? Math.min(limit, folds) : folds} 折 × ${$("#ddaEpochs").value} 轮 · 种子 ${$("#ddaSeed").value}`
      : `${modelLabel} · ${$("#datasetSelect").selectedOptions[0]?.textContent || "请选择数据集"} · ${$("#standardSetting").selectedOptions[0].textContent} · 最多 ${$("#epochs").value} 轮`;
    $("#standardPipeline").hidden = dda;
    $("#ddaIdle").hidden = !dda;
    const unavailable = !dda && !$("#datasetSelect").value;
    $("#trainSubmit").disabled = busy || unavailable;
    $("#topTrain").disabled = busy || unavailable;
    $("#quickDemo").disabled = busy || unavailable;
  }

  function collectDDA() {
    return {
      setting: $("#ddaSetting").value,
      algorithm: $("#ddaAlgorithm").value,
      epochs: Number($("#ddaEpochs").value),
      seed: Number($("#ddaSeed").value),
      max_folds: Number($("#ddaMaxFolds").value),
      target_subject: $("#ddaSetting").value === "cross-session" ? null : ($("#ddaSubject").value || null),
      target_session: $("#ddaSession").value || null,
      batch_size: Number($("#ddaBatchSize").value),
      lr: Number($("#ddaLearningRate").value),
      beta: Number($("#ddaBeta").value),
      pseudo_threshold: Number($("#ddaThreshold").value),
      eval_interval: Number($("#ddaEvalInterval").value),
      target_labeled_trials: $("#ddaAlgorithm").value === "SDDA" ? Number($("#ddaLabeledTrials").value) : 0,
    };
  }

  function collect() {
    const dataset = document.getElementById("datasetSelect");
    const model = $("input[name='model']:checked");
    return {
      dataset_id: dataset ? dataset.value : "",
      model: model ? model.value : "dualview",
      setting: $("#standardSetting").value,
      epochs: Number(document.getElementById("epochs").value || 40),
      batch_size: Number(document.getElementById("batchSize").value || 32),
      lr: Number(document.getElementById("learningRate").value || 0.001),
      seed: Number(document.getElementById("seed").value),
      hidden: Number(document.getElementById("hidden").value || 32),
      dropout: Number(document.getElementById("dropout").value),
      prototypes: Number(document.getElementById("prototypes").value || 2),
      proto_weight: Number(document.getElementById("protoWeight").value),
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
    document.getElementById("metricSetting").textContent = metrics.setting === "cross-session" ? "跨会话" : metrics.setting === "subject-dependent" ? "被试依赖" : "跨被试 LOSO";
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
      const external = result.kind === "external_reproduction";
      $("#confusionImage").closest(".figure-grid").hidden = external;
      if (!external) {
        document.getElementById("confusionImage").src = `/api/experiments/${runId}/figure/confusion_matrix.png?v=${Date.now()}`;
        document.getElementById("subjectImage").src = `/api/experiments/${runId}/figure/per_subject_accuracy.png?v=${Date.now()}`;
      }
    }
    document.getElementById("resultNote").textContent = runId && runId === "demo"
      ? "合成数据只用于软件验收"
      : `run_id: ${runId || "—"}`;
    if (result.kind === "external_reproduction") {
      $("#resultNote").textContent += ` · 目标测试峰值 ${EEG.formatPct(overall.paper_protocol_peak_accuracy)}（用于选取训练峰值，可能偏乐观）`;
    }
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
      if (hint) hint.textContent = "大数据集：建议先用 15 epochs / batch 128；完整 15 折 LOSO 可能较久，可先用 MLP 跑基线。";
    } else {
      if (hint) hint.textContent = "数据量较小，可先使用默认参数检查训练流程。";
    }
  }

  function submit(event) {
    if (event) event.preventDefault();
    if (busy) return;
    const dda = isDDA();
    const payload = dda ? collectDDA() : collect();
    if (!dda && !payload.dataset_id) {
      EEG.toast("请选择一个特征数据集。", "error");
      return;
    }
    const button = document.getElementById("trainSubmit");
    busy = true;
    syncConfig();
    $("#trainingResult").classList.remove("show");
    setState("RUNNING", "blue");
    EEG.startJob(dda ? "/api/integrations/dda/run" : "/api/train/run", payload, {
      button,
      consoleId: "trainingConsole",
      pollTimeout: dda ? 7 * 24 * 60 * 60 * 1000 : undefined,
      successMessage: "训练完成，指标已加载。",
      onSuccess: (job) => { busy = false; syncConfig(); renderResult(job); },
      onFail: () => { busy = false; syncConfig(); setState("FAILED", "red"); },
    });
  }

  function quickDemo() {
    document.querySelector("input[name='model'][value='dualview']").checked = true;
    syncConfig();
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
    $("#standardSetting").value = "loso";
    document.getElementById("trainingForm").requestSubmit();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("trainingForm");
    if (form) {
      form.addEventListener("submit", submit);
      form.addEventListener("invalid", (event) => {
        const details = event.target.closest("details");
        if (details) details.open = true;
      }, true);
    }
    const datasetSelect = document.getElementById("datasetSelect");
    if (datasetSelect) {
      datasetSelect.addEventListener("change", () => { tuneForDataset(); syncConfig(); });
      tuneForDataset();
    }
    ["ddaAlgorithm", "ddaSetting", "ddaSubject", "ddaSession", "ddaMaxFolds", "ddaEpochs"].forEach((id) => {
      document.getElementById(id).addEventListener("change", syncConfig);
    });
    document.querySelectorAll("input[name='model']").forEach((input) => input.addEventListener("change", syncConfig));
    form.addEventListener("input", syncConfig);
    form.addEventListener("change", syncConfig);
    syncConfig();
    const quick = document.getElementById("quickDemo");
    if (quick) quick.addEventListener("click", quickDemo);
    const top = document.getElementById("topTrain");
    if (top) top.addEventListener("click", () => {
      const form = document.getElementById("trainingForm");
      if (form) form.requestSubmit();
    });
  });
})();
