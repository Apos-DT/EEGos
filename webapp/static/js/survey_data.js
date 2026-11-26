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
    responseTicket: 0, responsePage: 1, responsePages: 1, loadTicket: 0, detailTicket: 0, tab: "overview",
  };
  const TABS = ["overview", "responses", "quality", "imports", "import"];
  const KIND_LABELS = {video:"视频问卷", audio:"音乐问卷", mixed:"音视频问卷", custom:"自定义问卷"};
  const ROLE_LABELS = {rater:"评分者", stimulus:"素材编号", stimulus_id:"素材编号", valence:"效价", arousal:"唤醒", dominance:"支配感", intensity:"强度", familiarity:"熟悉度", issues:"播放问题", primary_emotion:"主导情绪", emotion:"情绪类别", clarity:"情绪明确性", coverage:"持续比例", stability:"情绪稳定性", comprehension:"内容理解", other:"其他反馈"};
  const originLabel = value => ({local:"在线采集", online:"在线采集", wjx_import:"问卷星导入"}[value] || value || "—");
  const dateLabel = value => value ? String(value).replace("T", " ").slice(0,16) : "—";
  let questionQuery, responseQuery;
  function setDataActions(enabled) {
    ["exportWjx", "exportClean", "openSchema"].forEach(id => {$(id).setAttribute("aria-disabled",String(!enabled));$(id).tabIndex=enabled ? 0 : -1;});
    document.querySelectorAll("[data-response-stat]").forEach(button=>{button.disabled=!enabled;});
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[ch]);
  }
  function fmt(value) { return value == null || value === "" ? "—" : esc(String(value)); }
  function fmtValue(value) {
    if (value == null || value === "") return "—";
    if (Array.isArray(value)) return value.length ? value.map(fmtValue).join("、") : "—";
    if (typeof value === "object") {
      if("severity" in value && "tags" in value)return `${fmtValue(value.tags)} · 问题分值 ${value.severity}${value.contradictory ? " · 选项存在冲突" : ""}`;
      if("tag" in value && "text" in value)return [value.tag,value.text].filter(Boolean).join("：")||"—";
      return Object.entries(value).map(([key,item])=>`${key}：${fmtValue(item)}`).join("；");
    }
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
    if(!TABS.includes(key))key="overview";
    state.tab=key;
    if (key === "responses" && state.surveyId) renderResponses();
    if (key === "quality" && state.surveyId) loadQuality();
    document.querySelectorAll("#dataTabs .tab").forEach(b=>{const selected=b.dataset.tab===key;b.classList.toggle("active",selected);b.setAttribute("aria-selected",String(selected));b.tabIndex=selected ? 0 : -1;});
    TABS.forEach(name=>{$("tab-"+name).hidden=name!==key;});
  }
  async function loadQuality() {
    const survey = state.surveyId, ticket = state.loadTicket;
    try {
      const data = await EEG.api(`/api/surveys/${encodeURIComponent(survey)}/quality`);
      if (survey !== state.surveyId || ticket !== state.loadTicket) return;
      state.quality = data.quality; renderQuality();
    } catch (error) {
      if (survey === state.surveyId && ticket === state.loadTicket) $("qualityBody").textContent=error.message;
    }
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
    const ticket=++state.loadTicket;
    const previous=state.surveyId, id=$("surveySelect").value;
    state.surveyId=id;state.metadata=null;state.quality=null;state.responses=[];state.responseTotal=0;state.responsePage=1;
    state.detailTicket++;state.detailRecord=null;state.detailId="";
    if($("responseDialog").open)$("responseDialog").close();
    $("responseDetail").hidden=true;
    if(previous && previous!==id) {state.deepResponseId="";state.sessionFilter="";$("responseSearch").value="";$("responseValidFilter").value="";}
    setError("pageError","");setDataActions(false);renderStats();
    $("reloadSurvey").disabled=true;
    const empty=`<div class="empty"><h3>选择一份问卷</h3><p>选择上方问卷查看数据，或通过“导入 CSV”接入历史答卷。</p><a class="btn btn-soft btn-sm" href="/surveys">管理问卷</a></div>`;
    if(!id) {
      $("overviewBody").innerHTML=empty;$("qualityBody").innerHTML=empty;renderResponses();renderImports();
      $("surveyDataStatus").textContent="尚未选择问卷";
      setUrl({},["survey_id","response_id","session_id"]);
      return;
    }
    const loading=`<div class="empty"><p>正在读取问卷数据…</p></div>`;
    $("overviewBody").innerHTML=loading;$("qualityBody").innerHTML=loading;$("responsesBody").innerHTML=loading;
    $("responsePagination").hidden=true;$("responseCount").textContent="读取中…";
    $("surveyDataStatus").textContent="读取中…";
    setUrl({survey_id:id},previous && previous!==id ? ["response_id","session_id"] : []);
    const base=`/api/surveys/${encodeURIComponent(id)}`;
    $("exportWjx").href=`${base}/responses.csv`;$("exportClean").href=`${base}/responses.clean.csv`;$("openSchema").href=`/surveys/${encodeURIComponent(id)}/edit`;
    try {
      const md = await EEG.api(`${base}/metadata`);
      if(ticket!==state.loadTicket)return;
      state.metadata=md.metadata;state.quality=null;state.responses=[];
      state.responseTotal=md.metadata.n_all_versions ?? md.metadata.n_responses;
      renderStats();renderOverview();renderImports();setDataActions(true);applyDeepLink();
      if (state.tab === "quality") loadQuality();
      if (state.tab === "responses") renderResponses();
      $("surveyDataStatus").textContent=`更新于 ${new Date().toLocaleTimeString("zh-CN",{hour12:false,hour:"2-digit",minute:"2-digit"})}`;
    } catch(error) {
      if(ticket!==state.loadTicket)return;
      setError("pageError",error.message);$("surveyDataStatus").textContent="读取失败，可点击刷新重试";
      const failed=`<div class="empty"><p>数据未能读取，请检查上方提示后重试。</p></div>`;
      $("overviewBody").innerHTML=failed;$("qualityBody").innerHTML=failed;renderResponses();
    } finally {if(ticket===state.loadTicket)$("reloadSurvey").disabled=!state.surveyId;}
  }

  function applyDeepLink() {
    if(state.deepResponseId){const id=state.deepResponseId;state.deepResponseId="";switchTab("responses");openDetail(id,false);}
  }

  function renderStats() {
    const md=state.metadata;
    const fields={statResponses:md?.n_responses,statValid:md?.n_valid,statFlagged:md?.n_invalid,statRaters:md?.n_raters,statStimuli:md?.n_stimuli};
    Object.entries(fields).forEach(([id,value])=>{$(id).textContent=value??"—";});
    $("statRatings").textContent=md ? (md.questions||[]).filter(q=>q.type==="rating").length : "—";
    $("statValidNote").textContent=md ? `当前 v${md.schema_version} · 有效答卷 ${md.n_valid} 份 · 有效率 ${md.n_responses ? Math.round(md.n_valid/md.n_responses*100) : 0}%` : "等待数据";
    $("statFlagNote").textContent=md ? (md.n_invalid ? "请在数据质控中核验" : "暂无已标记答卷") : "等待数据";
    $("statCoverageNote").textContent=md ? `单素材平均 ${md.n_stimuli ? (md.n_valid/md.n_stimuli).toFixed(1) : "0"} 份有效标定` : "等待数据";
    $("dataTab-responses").textContent=md ? `答卷明细 (${md.n_responses})` : "答卷明细";
    $("schemaVersionBadge").hidden=!md;
    $("schemaVersionBadge").textContent=md ? `v${md.schema_version} · ${md.n_questions} 道题目 · ${md.n_stimuli} 个已覆盖素材` : "";
  }

  function renderQuestionStats() {
    if(!questionQuery)return;
    const result=questionQuery.update({query:$("questionSearch").value});
    result.items=result.items.filter(q=>!$("questionType").value||q.type===$("questionType").value);
    const rows=result.items.map(q=>{
      let stat="—";
      if(q.type==="rating")stat=q.mean==null ? "—" : `<div class="survey-rating"><strong>均值 ${esc(q.mean)}</strong><meter min="${Number(q.min ?? 1)}" max="${Number(q.max ?? 9)}" value="${Number(q.mean)}"></meter><small>${Number(q.min ?? 1)} — ${Number(q.max ?? 9)} 分</small></div>`;
      else if(q.distribution){
        const total=q.distribution.reduce((sum,item)=>sum+Number(item[1]),0);
        const colors=["#158068","#689e91","#a7c7be","#d0dfdb","#e4ece9"];
        stat=`<div class="survey-distribution" title="${esc(q.distribution.map(([k,v])=>k+" "+v).join(" · "))}">${q.distribution.map(([k,v],i)=>`<span style="width:${total ? v/total*100 : 0}%;background:${colors[Math.min(i,4)]}"></span>`).join("")}</div><small>${q.distribution.slice(0,3).map(([k,v])=>esc(k)+" "+(total?Math.round(v/total*100):0)+"% ("+v+")").join(" · ")}</small>`;
      } else stat=`已收集 ${Number(q.answered)||0} 条记录 <button class="btn btn-soft btn-sm" type="button" data-question-details>查看明细 →</button>`;
      return [String((state.metadata.questions||[]).indexOf(q)+1),esc(q.title||q.id),esc(TYPE_LABELS[q.type]||q.type),`${q.answer_rate??0}%`,stat];
    });
    $("questionStatsTable").innerHTML=table(["序号","题目名称","题型","作答率","统计分布"],rows);
    $("questionScroll").scrollTop=0;
    $("questionStatsTable").querySelectorAll("[data-question-details]").forEach(button=>button.addEventListener("click",()=>switchTab("responses")));
    $("questionCount").textContent=`${result.total} 道题目`;
  }

  function renderOverview() {
    const md=state.metadata;if(!md)return;const sv=md.survey||{};
    const origins=Object.entries(md.by_origin||{}).map(([k,v])=>`${originLabel(k)} ${v} 份`).join("、")||"暂无答卷";
    const trace=[["问卷编号",sv.id],["量表版本",`v${md.schema_version}`],["量表指纹",md.schema_hash],["历史版本",`${(md.schema_history||[]).length} 个`],["答卷来源",origins],["导入批次",Object.keys(md.by_batch||{}).length],["提交时间范围",`${dateLabel(md.first_submitted_at)} 至 ${dateLabel(md.last_submitted_at)}`]];
    $("overviewBody").innerHTML=`<div class="survey-overview-heading"><div><h2>${esc(sv.title||"问卷")}</h2>${sv.description ? `<p>${esc(sv.description)}</p>` : ""}</div>${badge(sv.status_label||"—",sv.status==="open" ? "green" : "gray")}</div>
      <div class="survey-overview-facts"><span>${esc(KIND_LABELS[md.kind]||md.kind)}</span><span>${md.n_questions} 道题目</span><span>${esc(md.origin?.type==="wjx_import" ? "问卷星导入" : "在线采集")}</span><span>最近提交 ${md.last_submitted_at ? esc(dateLabel(md.last_submitted_at)) : "暂无"}</span></div>
      <div class="survey-question-head"><h3>题目统计 <small id="questionCount"></small></h3><input class="input" id="questionSearch" type="search" placeholder="搜索题目…" aria-label="搜索题目统计"><select class="select" id="questionType" aria-label="筛选题型"><option value="">全部题型</option><option value="rating">量表评分</option><option value="single">单选</option><option value="multiple">多选</option><option value="text">填空</option><option value="textarea">多行文本</option></select></div>
      <div id="questionScroll" class="survey-data-scroll survey-question-scroll" tabindex="0" role="region" aria-label="题目统计表与数据溯源">
        <div id="questionStatsTable" class="survey-question-table"></div>
        <details class="survey-tech-details"><summary>版本与数据溯源 <small>问卷编号、量表指纹和来源</small></summary><dl>${trace.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${fmt(v)}</dd>`).join("")}</dl></details>
      </div>`;
    questionQuery=new EEG.ListController({items:md.questions||[],searchText:q=>[q.title,q.id,TYPE_LABELS[q.type],ROLE_LABELS[q.role]].join(" ")});
    $("questionSearch").addEventListener("input",renderQuestionStats);$("questionType").addEventListener("change",renderQuestionStats);renderQuestionStats();
  }

  // ------------------------------------------------------------------
  // 答卷明细：筛选 + 逐题详情
  // ------------------------------------------------------------------
  function filteredResponses() {
    return state.responseResult;
  }

  async function renderResponses(resetPage=true) {
    if (!state.surveyId) return;
    if(resetPage)state.responsePage=1;
    const ticket = ++state.responseTicket;
    const survey = state.surveyId;
    const pageSize = Number($("responsePageSize").value);
    const params = new URLSearchParams({page: state.responsePage, page_size: pageSize,
      q: $("responseSearch").value, validity: $("responseValidFilter").value, session_id: state.sessionFilter});
    try {
      const data = await EEG.api(`/api/surveys/${encodeURIComponent(survey)}/responses?${params}`);
      if(ticket !== state.responseTicket || survey !== state.surveyId) return;
      state.responses = data.responses;
      state.responseTotal = data.all_total;
      const result = {items: data.responses, total: data.total, page: data.page, pages: data.pages,
        start: (data.page-1)*pageSize};
      state.responsePage = result.page; state.responsePages = result.pages;
    const rows=result.items.map(r=>[fmt(dateLabel(r.submitted_at)),fmt(r.rater||r.participant_code||"匿名"),fmt(r.stimulus_id||r.stimulus_raw),r.valid ? badge("有效","green") : badge("已标记","amber"),fmt((r.flags||[]).join("；")||"—"),`<div class="survey-response-actions"><button class="btn btn-soft btn-sm view-response" type="button" data-id="${esc(r.response_id)}">查看答卷</button><button class="btn btn-soft btn-sm manage-response" type="button" data-id="${esc(r.response_id)}">管理</button></div>`]);
    $("responsesBody").innerHTML=rows.length ? table(["提交时间","评分者","素材","状态","标记","操作"],rows) : `<div class="empty"><h3>${state.responseTotal ? "没有匹配的答卷" : "暂无答卷"}</h3><p>${state.responseTotal ? "调整搜索或筛选条件后重试。" : "选择问卷后可查看已收集或导入的答卷。"}</p>${state.responseTotal ? '<button type="button" class="btn btn-soft btn-sm" data-clear-responses>重置筛选</button>' : ""}</div>`;
    $("responseCount").textContent=`${result.total} / ${state.responseTotal} 份`;
    $("responsePageInfo").textContent=`${result.total ? result.start+1 : 0}–${Math.min(result.start+result.items.length,result.total)} / ${result.total} 份 · ${result.page} / ${result.pages} 页`;
    $("responsePrev").disabled=result.page<=1;$("responseNext").disabled=result.page>=result.pages;
    $("responsePagination").hidden=!result.total;
    $("responseLoadNote").hidden=true;
    $("responseLoadNote").textContent=`当前载入 ${state.responses.length} / ${state.responseTotal} 份；筛选针对已载入答卷，完整数据请导出 CSV。`;
    $("sessionFilterHint").hidden=!state.sessionFilter;$("clearResponseFilter").hidden=!state.sessionFilter;
    $("sessionFilterHint").textContent=state.sessionFilter ? `会话 ${state.sessionFilter}` : "";
    $("responsesBody").scrollTop=0;
    } catch (error) {
      if(ticket === state.responseTicket) $("responsesBody").textContent = error.message;
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
        esc(TYPE_LABELS[q.type] || q.type || "—"), esc(ROLE_LABELS[q.role] || q.role || "自定义"),
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
    const kv = `<dl>${meta.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(fmtValue(v))}</dd>`).join("")}</dl>`;
    const rows = answerRows(record, schema);
    $("responseDetail").innerHTML = `
      <div class="response-detail-head">
        <div>
          <h3>答卷详情 · ${esc(record.rater || record.participant_code || "匿名")} × ${esc(record.stimulus_id || "—")}</h3>
          <p>${esc(dateLabel(record.submitted_at))} · 量表 v${esc(record.schema_version ?? "—")}</p>
        </div>
        <div class="detail-actions">
          ${record.valid ? badge("有效", "green") : badge("已标记", "amber")}
          <button class="btn btn-soft btn-sm" type="button" id="downloadResponse">下载 JSON</button>
          <button class="btn btn-soft btn-sm" type="button" id="closeResponseDetail">关闭</button>
        </div>
      </div>
      <div class="response-detail-body">
        <h3 class="section-title">逐题作答 <small>${rows.length} 题</small></h3>
        <div class="table-scroll">${table(["#", "题干", "题型", "字段角色", "原始作答", "归一化值"], rows)}</div>
        <p class="hint">分析值按字段角色归一化，原始作答保持原样。</p><details class="survey-tech-details"><summary>答卷元数据 <small>编号、来源、版本与质量标记</small></summary>${kv}</details>
      </div>`;
  }

  async function openDetail(id) {
    if(!state.surveyId||!id)return;
    const ticket=++state.detailTicket, survey=state.surveyId, box=$("responseDetail");
    state.detailId=id;box.hidden=false;box.innerHTML=`<div class="empty"><p>正在读取答卷…</p></div>`;
    if(!$("responseDialog").open)$("responseDialog").showModal();
    try {
      const data=await EEG.api(`/api/surveys/${encodeURIComponent(survey)}/responses/${encodeURIComponent(id)}`);
      if(ticket!==state.detailTicket||survey!==state.surveyId||!$("responseDialog").open)return;
      state.detailRecord=data.response;renderDetail(data.response,data.schema);setUrl({tab:"responses",response_id:id});
    } catch(error) {if(ticket===state.detailTicket)box.innerHTML=`<div class="form-error">${esc(error.message)}</div><button type="button" class="btn btn-soft btn-sm" id="closeResponseDetail">关闭</button>`;}
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

  function qualityCharts(quality) {
    const map = quality.affect_map;
    const points = map?.points || [];
    const coverage = [...(quality.stimulus_coverage || [])].sort((a, b) => a.n_raters - b.n_raters);
    const maximum = coverage.reduce((max, row) => Math.max(max, row.n_raters), 1);
    function position(value, axis) {
      return axis.max > axis.min ? (value - axis.min) / (axis.max - axis.min) * 100 : 50;
    }
    const plot = points.length ? `
      <label class="quality-chart-select">定位素材 <select class="select" id="affectStimulus">
        ${points.map((point, index) => `<option value="${index}">${esc(point.stimulus_id)}</option>`).join("")}
      </select></label>
      <div class="quality-affect-axis">唤醒度 ${map.arousal.min}–${map.arousal.max}</div>
      <div class="quality-affect-plot" aria-hidden="true">
        ${points.map((point, index) => `<span class="quality-affect-point" data-point="${index}"
          style="left:${position(point.valence, map.valence)}%;bottom:${position(point.arousal, map.arousal)}%"
          title="${esc(point.stimulus_id)}"></span>`).join("")}
      </div>
      <div class="quality-affect-axis">效价 ${map.valence.min}–${map.valence.max}</div>
      <p id="affectCoordinates" class="quality-chart-note" aria-live="polite"></p>` :
      '<p class="quality-chart-note">当前量表版本暂无可配对的有效效价与唤醒评分。</p>';
    const bars = coverage.slice(0, 8).map(row => `
      <li><span title="${esc(row.stimulus_id)}">${esc(row.stimulus_id)}</span>
      <meter min="0" max="${maximum}" value="${row.n_raters}" aria-label="${esc(row.stimulus_id)}的评分人数"></meter>
      <strong>${row.n_raters} 人</strong></li>`).join("");
    return `<div class="survey-quality-charts">
      <section><h3>素材效价与唤醒分布</h3>
        <p class="quality-chart-note">每个点代表一个素材，使用当前量表版本中同一份有效答卷的两项评分计算均值。</p>
        ${plot}
      </section>
      <section><h3>素材评分覆盖</h3>
        <p class="quality-chart-note">按评分人数从少到多展示前 ${Math.min(coverage.length, 8)} 个素材，含已标记答卷。</p>
        ${bars ? `<ul class="quality-coverage-bars">${bars}</ul>` : '<p class="quality-chart-note">暂无素材评分记录。</p>'}
      </section>
    </div>`;
  }

  function renderQuality() {
    const q=state.quality;if(!q)return;
    const summary=[["重复提交",q.n_duplicates],["直线作答提示",q.n_straightline_raters],["无效评分",q.invalid_ratings]];
    const raters=(q.rater_table||[]).map(r=>[fmt(r.rater),fmt(r.n_ratings),fmt(r.valence_sd),fmt(r.arousal_sd),r.straightline_suspect ? badge("需复核","amber") : badge("未触发","gray")]);
    const coverage=(q.stimulus_coverage||[]).map(r=>[fmt(r.stimulus_id),fmt(r.n_raters),fmt(r.valence_mean),fmt(r.arousal_mean),r.problem_rate==null ? "—" : EEG.formatPct(r.problem_rate)]);
    $("qualityBody").innerHTML=`<div class="survey-data-section-head"><h2>质量检查 <small>规则提示需结合原始答卷复核</small></h2></div><div class="survey-quality-summary">${summary.map(([k,v])=>`<span>${esc(k)} <strong>${fmt(v)}</strong></span>`).join("")}</div>${qualityCharts(q)}<div class="survey-quality-grid"><section><h3>评分者 <small>效价与唤醒离散程度</small></h3><div class="survey-inner-table">${table(["评分者","评分数","效价 SD","唤醒 SD","判定"],raters)}</div></section><section><h3>素材覆盖 <small>各素材的评分情况</small></h3><div class="survey-inner-table">${table(["素材","评分人数","效价均值","唤醒均值","问题率"],coverage)}</div></section></div><details class="survey-tech-details"><summary>检查口径</summary><p>同一评分者与素材的重复提交单独标记；效价与唤醒标准差均低于 1.0 时提示直线作答。这里展示规则检查结果，不等同于人工确认的答卷有效性。</p></details>`;
    const select = $("affectStimulus");
    if (select) {
      const markers = $("qualityBody").querySelectorAll("[data-point]");
      const update = () => {
        const index = Number(select.value);
        const point = q.affect_map.points[index];
        markers.forEach((marker, i) => marker.classList.toggle("active", i === index));
        $("affectCoordinates").textContent = `效价 ${point.valence.toFixed(2)} · 唤醒度 ${point.arousal.toFixed(2)} · ${point.n} 份配对评分`;
      };
      select.addEventListener("change", update);
      update();
    }
  }

  function renderImports() {
    const batches=state.batches.filter(b=>$("importScope").value==="all"||!state.surveyId||b.survey_id===state.surveyId);
    const rows=batches.map(b=>[`<strong>${fmt(b.filename)}</strong><small class="survey-row-secondary">${fmt(b.batch_id)}</small>`,fmt(KIND_LABELS[b.kind]||b.kind),fmt(b.n_rows),fmt(b.n_valid),fmt(b.n_duplicates),fmt(dateLabel(b.created_at)),`<div class="survey-response-actions"><a class="btn btn-soft btn-sm" href="/api/surveys/imports/${encodeURIComponent(b.batch_id)}/source.csv">原始 CSV</a><button class="btn btn-soft btn-sm manage-import" type="button" data-id="${esc(b.batch_id)}">管理</button></div>`]);
    $("importsBody").innerHTML=rows.length ? table(["源文件 / 批次","类型","行数","有效","重复","导入时间","操作"],rows) : `<div class="empty"><h3>暂无导入批次</h3><p>${state.surveyId&&$("importScope").value!=="all" ? "当前问卷没有导入记录，可切换到全部问卷。" : "导入历史问卷后，可以在这里回查源文件。"}</p><button class="btn btn-soft btn-sm" type="button" data-open-import>导入 CSV</button></div>`;
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
  $("reloadSurvey").addEventListener("click",()=>loadAll());
  $("importScope").addEventListener("change",renderImports);
  $("responsePrev").addEventListener("click",()=>{state.responsePage--;renderResponses(false);});
  $("responseNext").addEventListener("click",()=>{state.responsePage++;renderResponses(false);});
  $("responsePageSize").addEventListener("change",()=>renderResponses());
  document.querySelectorAll("[data-response-stat]").forEach(button=>button.addEventListener("click",()=>{
    state.sessionFilter="";state.deepResponseId="";$("responseSearch").value="";$("responseValidFilter").value=button.dataset.responseStat==="all" ? "" : button.dataset.responseStat;
    switchTab("responses");setUrl({tab:"responses"},["response_id","session_id"]);renderResponses();
  }));
  document.querySelector(".survey-data-workspace").addEventListener("click",event=>{if(event.target.closest("[data-open-import]")){switchTab("import");setUrl({tab:"import"});}});
  const tabs=Array.from(document.querySelectorAll("#dataTabs .tab"));
  tabs.forEach((tab,index)=>tab.addEventListener("keydown",event=>{
    if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;
    const next=event.key==="Home" ? 0 : event.key==="End" ? tabs.length-1 : (index+(event.key==="ArrowRight" ? 1 : -1)+tabs.length)%tabs.length;
    tabs[next].click();tabs[next].focus({preventScroll:true});tabs[next].scrollIntoView({block:"nearest",inline:"nearest"});event.preventDefault();
  }));
  document.querySelectorAll(".survey-data-actions a").forEach(link=>link.addEventListener("click",event=>{if(link.getAttribute("aria-disabled")==="true")event.preventDefault();else document.querySelector(".survey-export").open=false;}));
  document.addEventListener("click",event=>{if(!event.target.closest(".survey-export"))document.querySelector(".survey-export").open=false;});
  document.addEventListener("keydown",event=>{if(event.key==="Escape"&&document.querySelector(".survey-export").open){document.querySelector(".survey-export").open=false;}});
  $("responseDialog").addEventListener("close",()=>{state.detailTicket++;state.detailId="";state.detailRecord=null;$("responseDetail").hidden=true;setUrl({},["response_id"]);});
  $("responseDialog").addEventListener("click",event=>{if(event.target!==$("responseDialog"))return;const r=$("responseDialog").getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)$("responseDialog").close();});
  $("responseSearch")?.addEventListener("input", renderResponses);
  $("responseValidFilter")?.addEventListener("change", renderResponses);
  $("clearResponseFilter")?.addEventListener("click", clearFilters);

  $("responsesBody")?.addEventListener("click", (event) => {
    if(event.target.closest("[data-clear-responses]")){clearFilters();return;}
    const button = event.target.closest(".view-response");
    if (button) openDetail(button.dataset.id);
  });

  $("responseDetail")?.addEventListener("click", (event) => {
    if (event.target.closest("#closeResponseDetail")) {
      $("responseDialog").close();
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
    setError("importPreviewError", "");
    const input = $("importFile");
    const file = input.files && input.files[0];
    if (!file) { setError("importPreviewError", "请先选择问卷星导出的 CSV 文件。"); return; }
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
        <td>${q.index}</td><td class="mono">${fmt(q.source_column)}</td><td>${fmt(TYPE_LABELS[q.type] || q.type)}</td>
        <td>${fmt(ROLE_LABELS[q.role] || q.role || "自定义")}</td><td>${q.options ? q.options.length : "—"}</td>
        <td>${fmt((q.samples || []).join(" / ").slice(0, 80))}</td></tr>`).join("");
      if (!$("importTitle").value) $("importTitle").value = file.name.replace(/\.csv$/i, "");
      $("importPreviewBox").hidden = false;
      EEG.toast("字段映射已生成，请确认后导入", "success");
    } catch (error) {
      setError("importPreviewError", error.message);
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
  ["importFile","importKind"].forEach(id=>$(id).addEventListener("change",()=>{state.stagingId="";state.preview=null;$("importPreviewBox").hidden=true;setError("importPreviewError","");}));
  renderImports();switchTab(TABS.includes(params.get("tab")) ? params.get("tab") : "overview");
  if(!$("surveySelect").value && $("surveySelect").options.length>1 && !params.get("survey_id"))$("surveySelect").selectedIndex=1;
  loadAll().then(()=>{if(params.get("survey_id")&&!$("surveySelect").value)setError("pageError","该问卷不存在或已移入回收站，请重新选择。");});
})();
