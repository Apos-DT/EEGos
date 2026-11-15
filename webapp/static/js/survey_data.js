(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = {
    surveyId: "",
    metadata: null,
    quality: null,
    responses: [],
    batches: window.__IMPORT_BATCHES__ || [],
    stagingId: "",
    preview: null,
  };
  const TABS = ["overview", "responses", "quality", "imports", "import"];

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[ch]);
  }
  function fmt(value) { return value == null || value === "" ? "—" : esc(String(value)); }
  function setError(id, message) {
    const node = $(id);
    if (!node) return;
    node.textContent = message || "";
    node.hidden = !message;
  }
  function table(headers, rows) {
    const head = `<thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>`;
    const body = `<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody>`;
    return rows.length ? `<table class="data">${head}${body}</table>` : `<div class="empty" style="padding:26px"><p>暂无数据</p></div>`;
  }
  function badge(text, tone) { return `<span class="badge ${tone === "green" ? "badge-green" : tone === "amber" ? "badge-amber" : "badge-gray"}">${esc(text)}</span>`; }

  // ------------------------------------------------------------------
  // 数据加载
  // ------------------------------------------------------------------
  async function loadAll() {
    const id = $("surveySelect").value;
    state.surveyId = id;
    setError("pageError", "");
    if (!id) {
      $("overviewBody").innerHTML = `<div class="empty" style="padding:30px"><p>请先选择一份问卷。</p></div>`;
      return;
    }
    const base = `/api/surveys/${encodeURIComponent(id)}`;
    $("exportWjx").href = `${base}/responses.csv`;
    $("exportClean").href = `${base}/responses.clean.csv`;
    $("openSchema").href = `/surveys/${encodeURIComponent(id)}/edit`;
    try {
      const [md, qr, rp, im] = await Promise.all([
        EEG.api(`${base}/metadata`),
        EEG.api(`${base}/quality`),
        EEG.api(`${base}/responses?limit=200`),
        EEG.api("/api/surveys/imports"),
      ]);
      state.metadata = md.metadata;
      state.quality = qr.quality;
      state.responses = rp.responses || [];
      state.batches = im.imports || [];
      renderStats();
      renderOverview();
      renderResponses();
      renderQuality();
      renderImports();
    } catch (error) {
      setError("pageError", error.message);
    }
  }

  function renderStats() {
    const md = state.metadata;
    if (!md) return;
    $("statResponses").textContent = md.n_responses;
    $("statValid").textContent = md.n_valid;
    $("statCoverage").textContent = `${md.n_raters} / ${md.n_stimuli}`;
    $("statVersion").textContent = `v${md.schema_version}`;
    $("statHash").textContent = md.schema_hash || "—";
    $("schemaVersionBadge").textContent = `量表 v${md.schema_version} · ${md.n_questions} 题 · ${md.kind}`;
  }

  function renderOverview() {
    const md = state.metadata;
    if (!md) return;
    const sv = md.survey || {};
    const origins = Object.entries(md.by_origin || {}).map(([k, v]) => `${k}: ${v}`).join("、") || "—";
    const info = [
      ["问卷 ID", sv.id], ["状态", sv.status_label], ["素材类型", md.kind],
      ["量表版本", `v${md.schema_version}`], ["量表指纹", md.schema_hash],
      ["历史版本", `${(md.schema_history || []).length} 个`], ["题目数", md.n_questions],
      ["答卷 / 有效 / 无效", `${md.n_responses} / ${md.n_valid} / ${md.n_invalid}`],
      ["评分者 / 素材", `${md.n_raters} / ${md.n_stimuli}`],
      ["提交时间窗", `${md.first_submitted_at || "—"} ~ ${md.last_submitted_at || "—"}`],
      ["答卷来源", origins],
      ["数据来源", (md.origin && md.origin.type) === "wjx_import" ? `问卷星导入 · ${md.origin.filename || ""}` : "本地系统采集"],
      ["导入批次", Object.keys(md.by_batch || {}).length],
    ];
    const infoHtml = `<div class="kv-grid">${info.map(([k, v]) => `<div><span>${esc(k)}</span><strong>${fmt(v)}</strong></div>`).join("")}</div>`;
    const questionRows = (md.questions || []).map((q) => {
      let stat = "—";
      if (q.type === "rating") stat = q.mean == null ? "—" : `${q.mean}${q.sd == null ? "" : ` ± ${q.sd}`}`;
      else if (q.distribution) stat = q.distribution.slice(0, 4).map(([k, v]) => `${k}(${v})`).join("、");
      return [fmt(q.id), fmt(q.title), fmt(q.type), fmt(q.role || "自定义"), `${q.answer_rate}%`, fmt(stat)];
    });
    $("overviewBody").innerHTML = `
      <div class="panel-head"><div><h2>${esc(sv.title || "问卷")}</h2><p>${esc(sv.description || "无说明")}</p></div></div>
      <h3 class="section-title">问卷元数据</h3>${infoHtml}
      <h3 class="section-title">题目级作答率与分布</h3>
      ${table(["ID", "题干", "题型", "字段角色", "作答率", "统计"], questionRows)}`;
  }

  function renderResponses() {
    const rows = state.responses.map((r) => [
      fmt(r.submitted_at), fmt(r.rater), fmt(r.stimulus_id), fmt(r.source),
      fmt(r.batch_id || "—"), fmt(r.raw_row ?? "—"),
      r.valid ? badge("有效", "green") : badge("已标记", "amber"),
      fmt((r.flags || []).join("; ") || "—"),
    ]);
    $("responseCount").textContent = `${state.responses.length} 条（最多显示 200）`;
    $("responsesBody").innerHTML = table(
      ["提交时间", "评分者", "素材", "来源", "批次", "原始行", "状态", "标记"], rows
    );
  }

  function renderQuality() {
    const q = state.quality;
    if (!q) return;
    const summary = [
      ["答卷 / 有效", `${q.n_responses} / ${q.n_valid}`],
      ["重复提交", q.n_duplicates], ["直线作答评分者", q.n_straightline_raters],
      ["无效评分", q.invalid_ratings], ["已覆盖素材", q.n_stimuli_covered],
      ["效价 / 唤醒均值", `${q.mean_valence ?? "—"} / ${q.mean_arousal ?? "—"}`],
    ];
    const raterRows = (q.rater_table || []).map((r) => [
      fmt(r.rater), fmt(r.n_ratings), fmt(r.valence_sd), fmt(r.arousal_sd),
      r.straightline_suspect ? badge("可疑", "amber") : badge("正常", "green"),
    ]);
    const coverageRows = (q.stimulus_coverage || []).slice(0, 120).map((r) => [
      fmt(r.stimulus_id), fmt(r.n_raters), fmt(r.valence_mean), fmt(r.arousal_mean), fmt(r.problem_rate),
    ]);
    $("qualityBody").innerHTML = `
      <div class="panel-head"><div><h2>质量诊断</h2><p>与数据审计口径一致：同评分者 × 素材保留首次；效价与唤醒 SD 均 &lt; 1.0 判为直线作答。异常只标记不删除。</p></div></div>
      <div class="kv-grid">${summary.map(([k, v]) => `<div><span>${esc(k)}</span><strong>${fmt(v)}</strong></div>`).join("")}</div>
      <h3 class="section-title">评分者诊断</h3>
      ${table(["评分者", "评分数", "效价 SD", "唤醒 SD", "判定"], raterRows)}
      <h3 class="section-title">逐素材覆盖（前 120）</h3>
      ${table(["素材", "评分人数", "效价均值", "唤醒均值", "问题率"], coverageRows)}`;
  }

  function renderImports() {
    const rows = state.batches.map((b) => [
      fmt(b.batch_id), fmt(b.filename), fmt(b.kind), fmt(b.n_rows),
      fmt(b.n_valid), fmt(b.n_duplicates), fmt(b.created_at),
      `<a class="btn btn-soft btn-sm" href="/api/surveys/imports/${encodeURIComponent(b.batch_id)}/source.csv">原始 CSV</a>`,
    ]);
    $("importsBody").innerHTML = table(
      ["批次", "源文件", "类型", "行数", "有效", "重复", "导入时间", "溯源"], rows
    );
  }

  // ------------------------------------------------------------------
  // 交互
  // ------------------------------------------------------------------
  document.querySelectorAll("#dataTabs .tab").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.tab;
      document.querySelectorAll("#dataTabs .tab").forEach((b) => b.classList.toggle("active", b === button));
      TABS.forEach((name) => { $("tab-" + name).hidden = name !== key; });
    });
  });
  $("surveySelect").addEventListener("change", loadAll);

  async function rawPost(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body,
    });
    const text = await response.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { detail: text }; }
    if (!response.ok) {
      const detail = data && data.detail;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || response.statusText));
    }
    return data;
  }

  $("importPreviewBtn")?.addEventListener("click", async () => {
    setError("importError", "");
    const input = $("importFile");
    const file = input.files && input.files[0];
    if (!file) { setError("importError", "请先选择问卷星导出的 CSV 文件。"); return; }
    const button = $("importPreviewBtn");
    EEG.setBusy(button, true, "解析中…");
    try {
      const kind = $("importKind").value;
      const url = `/api/surveys/import/preview?filename=${encodeURIComponent(file.name)}&kind=${encodeURIComponent(kind)}`;
      const data = await rawPost(url, file);
      state.preview = data.preview;
      state.stagingId = data.preview.staging_id;
      $("importSummary").textContent = `${data.preview.filename} · ${data.preview.n_rows} 行 · ${data.preview.n_columns} 列 · ${data.preview.encoding} · 推断 ${data.preview.questions.length} 题 · 素材类型 ${data.preview.kind} · SHA256 ${data.preview.sha256.slice(0, 12)}`;
      $("importMapTable").querySelector("tbody").innerHTML = data.preview.questions.map((q) => `<tr>
        <td>${q.index}</td><td class="mono">${fmt(q.source_column)}</td><td>${fmt(q.type)}</td>
        <td>${fmt(q.role || "自定义")}</td><td>${q.options ? q.options.length : "—"}</td>
        <td>${fmt((q.samples || []).join(" / ").slice(0, 80))}</td></tr>`).join("");
      if (!$("importTitle").value) $("importTitle").value = file.name.replace(/\.csv$/i, "");
      $("importPreviewBox").hidden = false;
      EEG.toast("字段映射已生成，请确认后导入", "success");
    } catch (error) {
      setError("importError", error.message);
    } finally {
      EEG.setBusy(button, false);
    }
  });

  $("importCommitBtn")?.addEventListener("click", async () => {
    if (!state.stagingId) { setError("importError", "请先解析预览。"); return; }
    setError("importError", "");
    const button = $("importCommitBtn");
    EEG.setBusy(button, true, "导入中…");
    try {
      const result = await EEG.api("/api/surveys/import/commit", {
        method: "POST",
        body: JSON.stringify({
          staging_id: state.stagingId,
          survey_id: $("importTarget").value,
          title: $("importTitle").value.trim(),
          description: "",
          mark_duplicates: $("importDedup").checked,
        }),
      });
      const b = result.batch;
      $("importResult").innerHTML = `<div class="callout"><strong>导入完成</strong><p>批次 ${esc(b.batch_id)}：写入 ${b.n_written} 行，有效 ${b.n_valid} 行，重复标记 ${b.n_duplicates} 行。原始 CSV 已保存，可按原始行号回查。</p></div>`;
      EEG.toast("历史问卷已导入", "success");
      setTimeout(() => { window.location.href = `/survey-data?survey_id=${encodeURIComponent(b.survey_id)}`; }, 900);
    } catch (error) {
      setError("importError", error.message);
    } finally {
      EEG.setBusy(button, false);
    }
  });

  renderImports();
  if ($("surveySelect").value) loadAll();
})();
