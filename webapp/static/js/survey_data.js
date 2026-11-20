(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const TYPE_LABELS = {
    text: "单行填空", rating: "量表评分", single: "单选",
    multiple: "多选", textarea: "多行文本",
  };
  const params = new URLSearchParams(window.location.search);
  const state = {
    surveyId: "",
    metadata: null,
    quality: null,
    responses: [],
    responseTotal: 0,
    batches: window.__IMPORT_BATCHES__ || [],
    stagingId: "",
    preview: null,
    deepResponseId: params.get("response_id") || "",
    sessionFilter: params.get("session_id") || "",
    detailRecord: null,
    detailId: "",
  };
  const TABS = ["overview", "responses", "quality", "imports", "import"];

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[ch]);
  }
  function fmt(value) { return value == null || value === "" ? "—" : esc(String(value)); }
  function fmtValue(value) {
    if (value == null || value === "") return "—";
    if (Array.isArray(value)) return value.length ? value.join("、") : "—";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }
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
  function switchTab(key) {
    document.querySelectorAll("#dataTabs .tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === key));
    TABS.forEach((name) => { $("tab-" + name).hidden = name !== key; });
  }
  function setUrl(updates, removals = []) {
    const url = new URL(window.location.href);
    Object.entries(updates).forEach(([k, v]) => url.searchParams.set(k, v));
    removals.forEach((k) => url.searchParams.delete(k));
    history.replaceState({}, "", url);
  }

  // ------------------------------------------------------------------
  // 数据加载
  // ------------------------------------------------------------------
  async function loadAll() {
    const id = $("surveySelect").value;
    state.surveyId = id;
    state.detailRecord = null;
    state.detailId = "";
    $("responseDetail").hidden = true;
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
      state.responseTotal = rp.total || state.responses.length;
      state.batches = im.imports || [];
      renderStats();
      renderOverview();
      renderResponses();
      renderQuality();
      renderImports();
      applyDeepLink();
    } catch (error) {
      setError("pageError", error.message);
    }
  }

  function applyDeepLink() {
    if (params.get("tab") === "responses") switchTab("responses");
    if (state.deepResponseId) {
      switchTab("responses");
      openDetail(state.deepResponseId, false);
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

  // ------------------------------------------------------------------
  // 答卷明细：筛选 + 逐题详情
  // ------------------------------------------------------------------
  function filteredResponses() {
    const query = ($("responseSearch")?.value || "").trim().toLowerCase();
    const validity = $("responseValidFilter")?.value || "";
    const controller=new EEG.ListController({items:state.responses,searchText:r=>[r.rater,r.stimulus_id,r.response_id,r.session_id,r.batch_id,r.source,r.display_name].join(" "),matches:(r)=>{
      if (state.sessionFilter && r.session_id !== state.sessionFilter) return false;
      if (validity === "valid" && !r.valid) return false;
      if (validity === "flagged" && r.valid) return false;
      return true;
    }});
    return controller.update({query}).items;
  }

  function renderResponses() {
    const rows = filteredResponses().map((r) => [
      fmt(r.submitted_at), fmt(r.rater), fmt(r.stimulus_id), fmt(r.source),
      fmt(r.batch_id || "—"), fmt(r.raw_row ?? "—"),
      r.valid ? badge("有效", "green") : badge("已标记", "amber"),
      fmt((r.flags || []).join("; ") || "—"),
      `<button class="btn btn-soft btn-sm view-response" type="button" data-id="${esc(r.response_id)}">查看答卷</button><button class="btn btn-soft btn-sm manage-response" type="button" data-id="${esc(r.response_id)}">管理</button>`,
    ]);
    const shown = rows.length;
    $("responseCount").textContent = state.sessionFilter
      ? `本轮 ${shown} 条`
      : `显示 ${shown} / 共 ${state.responseTotal} 条（最多载入 200）`;
    $("responsesBody").innerHTML = table(
      ["提交时间", "评分者", "素材", "来源", "批次", "原始行", "状态", "标记", "操作"], rows
    );
    if (state.sessionFilter) {
      $("sessionFilterHint").textContent = `仅显示会话 ${state.sessionFilter} 提交的答卷`;
      $("sessionFilterHint").hidden = false;
      $("clearResponseFilter").hidden = false;
    }
  }

  $("responsesBody")?.addEventListener("click",event=>{const b=event.target.closest(".manage-response");if(b)EEG.records.edit("responses",b.dataset.id);});

  function answerRows(record, schema) {
    const answers = record.answers || {};
    const normalized = record.normalized || {};
    const seen = new Set();
    const rows = (schema || []).map((q, index) => {
      seen.add(q.id);
      return [
        String(index + 1), esc(q.title || q.id),
        esc(TYPE_LABELS[q.type] || q.type || "—"), esc(q.role || "自定义"),
        `<span class="answer-raw">${esc(fmtValue(answers[q.id]))}</span>`,
        `<span class="answer-norm">${esc(fmtValue(normalized[q.id]))}</span>`,
      ];
    });
    Object.keys(answers).filter((key) => !seen.has(key)).forEach((key) => {
      rows.push([
        String(rows.length + 1), esc(key), "历史字段", "—",
        `<span class="answer-raw">${esc(fmtValue(answers[key]))}</span>`,
        `<span class="answer-norm">${esc(fmtValue(normalized[key]))}</span>`,
      ]);
    });
    return rows;
  }

  function renderDetail(record, schema) {
    const meta = [
      ["答卷 ID", record.response_id], ["会话 ID", record.session_id || "—"],
      ["评分者", record.rater || record.participant_code || "—"],
      ["素材", record.stimulus_id || record.stimulus_raw || "—"],
      ["提交时间", record.submitted_at],
      ["答卷用时", record.duration_s == null ? "—" : `${record.duration_s} 秒`],
      ["观看时长", `${record.watch_seconds ?? 0} 秒`],
      ["来源", record.source], ["来源详情", record.source_detail],
      ["IP 地区", record.ip_region || "—"], ["IP 哈希", record.ip_hash || "—"],
      ["导入批次", record.batch_id || "—"], ["原始行号", record.raw_row ?? "—"],
      ["量表版本", `v${record.schema_version ?? "—"}`], ["量表指纹", record.schema_hash],
      ["答卷来源", record.origin], ["平台序号", record.serial_no ?? "—"],
      ["平台总分", record.total_score ?? "—"],
      ["质量标记", (record.flags || []).join("；") || "无"],
    ];
    const kv = `<div class="kv-grid">${meta.map(([k, v]) =>
      `<div><span>${esc(k)}</span><strong>${esc(fmtValue(v))}</strong></div>`).join("")}</div>`;
    const rows = answerRows(record, schema);
    $("responseDetail").innerHTML = `
      <div class="response-detail-head">
        <div>
          <h3>答卷详情 · ${esc(record.rater || record.participant_code || "匿名")} × ${esc(record.stimulus_id || "—")}</h3>
          <p>${esc(record.response_id)} · ${esc(record.submitted_at || "")} · 量表 v${esc(record.schema_version ?? "—")}</p>
        </div>
        <div class="detail-actions">
          ${record.valid ? badge("有效", "green") : badge("已标记", "amber")}
          <button class="btn btn-soft btn-sm" type="button" id="downloadResponse">下载 JSON</button>
          <button class="btn btn-soft btn-sm" type="button" id="closeResponseDetail">关闭</button>
        </div>
      </div>
      <div class="response-detail-body">
        <h3 class="section-title">答卷元数据</h3>${kv}
        <h3 class="section-title">逐题作答（${rows.length} 题）</h3>
        <div class="table-scroll">${table(["#", "题干", "题型", "字段角色", "原始作答", "归一化值"], rows)}</div>
        <p class="hint" style="padding:10px 0 0">归一化值由字段角色自动生成，供质量评分与分析宽表使用；原始作答保留被试填写或问卷星导出的原样。</p>
      </div>`;
  }

  async function openDetail(id, scroll = true) {
    if (!state.surveyId || !id) return;
    const box = $("responseDetail");
    box.hidden = false;
    box.innerHTML = `<div class="empty" style="padding:22px"><p>正在读取答卷…</p></div>`;
    state.detailId = id;
    try {
      const data = await EEG.api(
        `/api/surveys/${encodeURIComponent(state.surveyId)}/responses/${encodeURIComponent(id)}`
      );
      state.detailRecord = data.response;
      renderDetail(data.response, data.schema);
      setUrl({ tab: "responses", response_id: id });
      if (scroll) box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (error) {
      box.innerHTML = `<div class="form-error" style="margin:16px">${esc(error.message)}</div>`;
    }
  }

  function clearFilters() {
    $("responseSearch").value = "";
    $("responseValidFilter").value = "";
    state.sessionFilter = "";
    state.deepResponseId = "";
    state.detailId = "";
    state.detailRecord = null;
    $("sessionFilterHint").hidden = true;
    $("clearResponseFilter").hidden = true;
    $("responseDetail").hidden = true;
    setUrl({ tab: "responses" }, ["response_id", "session_id"]);
    renderResponses();
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
      `<a class="btn btn-soft btn-sm" href="/api/surveys/imports/${encodeURIComponent(b.batch_id)}/source.csv">原始 CSV</a><button class="btn btn-soft btn-sm manage-import" type="button" data-id="${esc(b.batch_id)}">管理</button>`,
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
      switchTab(button.dataset.tab);
      setUrl({ tab: button.dataset.tab });
    });
  });
  $("surveySelect").addEventListener("change", loadAll);
  $("responseSearch")?.addEventListener("input", renderResponses);
  $("responseValidFilter")?.addEventListener("change", renderResponses);
  $("clearResponseFilter")?.addEventListener("click", clearFilters);

  $("responsesBody")?.addEventListener("click", (event) => {
    const button = event.target.closest(".view-response");
    if (button) openDetail(button.dataset.id);
  });

  $("responseDetail")?.addEventListener("click", (event) => {
    if (event.target.closest("#closeResponseDetail")) {
      $("responseDetail").hidden = true;
      state.detailId = "";
      state.deepResponseId = "";
      setUrl({ tab: "responses" }, ["response_id"]);
    }
    if (event.target.closest("#downloadResponse") && state.detailRecord) {
      const blob = new Blob([JSON.stringify(state.detailRecord, null, 2)], { type: "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${state.detailRecord.response_id || "response"}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(link.href);
    }
  });

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

  $("importsBody")?.addEventListener("click",event=>{const b=event.target.closest(".manage-import");if(b)EEG.records.edit("imports",b.dataset.id);});
  renderImports();
  if (TABS.includes(params.get("tab"))) switchTab(params.get("tab"));
  if ($("surveySelect").value) loadAll();
})();
