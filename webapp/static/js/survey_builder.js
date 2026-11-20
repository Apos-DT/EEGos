(function () {
  "use strict";
  const form = document.getElementById("surveyForm");
  const table = document.getElementById("builderTable");
  const search = document.getElementById("builderSearch");
  const category = document.getElementById("builderCategory");
  const selectedCount = document.getElementById("selectedCount");
  const visible = document.getElementById("builderVisible");
  const error = document.getElementById("builderError");
  let modality = "all";
  if (!form || !table) return;

  // ------------------------------------------------------------------
  // 题目设计器
  // ------------------------------------------------------------------
  const catalog = window.__QUESTIONNAIRE__ || { types: [], roles: [], templates: {} };
  let questions = JSON.parse(JSON.stringify(window.__SURVEY_SCHEMA__ || []));
  let kind = window.__SURVEY_KIND__ || "video";
  const qList = document.getElementById("questionList");
  const qCount = document.getElementById("questionCount");
  const schemaError = document.getElementById("schemaError");

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[ch]);
  }

  function optionsHtml(items, current, valueKey, labelKey) {
    return (items || []).map((item) => {
      const value = item[valueKey];
      return `<option value="${esc(value)}" ${String(value) === String(current || "") ? "selected" : ""}>${esc(item[labelKey])}</option>`;
    }).join("");
  }

  function applyDefaults(q) {
    if ((q.type === "single" || q.type === "multiple") && !(q.options || []).length) {
      q.options = ["选项 A", "选项 B"];
    }
    if (q.type === "rating") {
      if (q.min == null) q.min = 1;
      if (q.max == null) q.max = 9;
      if (q.min_label == null) q.min_label = "";
      if (q.max_label == null) q.max_label = "";
    }
  }

  function rowHtml(q, i) {
    const choice = q.type === "single" || q.type === "multiple";
    const rating = q.type === "rating";
    return `<div class="q-row" data-index="${i}">
      <div class="q-row-main">
        <span class="q-num">${i + 1}</span>
        <input class="q-title" data-field="title" value="${esc(q.title)}" placeholder="题干" aria-label="第 ${i + 1} 题题干">
        <select class="q-select" data-field="type" aria-label="题型">${optionsHtml(catalog.types, q.type, "value", "label")}</select>
        <select class="q-select q-role" data-field="role" aria-label="字段角色">${optionsHtml(catalog.roles, q.role, "value", "label")}</select>
        <label class="checkline q-required"><input type="checkbox" data-field="required" ${q.required === false ? "" : "checked"}> 必填</label>
        <div class="q-actions">
          <button class="q-btn" type="button" data-act="up" title="上移">↑</button>
          <button class="q-btn" type="button" data-act="down" title="下移">↓</button>
          <button class="q-btn q-del" type="button" data-act="del" title="删除">×</button>
        </div>
      </div>
      <div class="q-row-extra">
        ${choice ? `<label class="q-field q-wide">选项（每行一个）<textarea class="q-options" data-field="options" rows="2">${esc((q.options || []).join("\n"))}</textarea></label>` : ""}
        ${rating ? `<label class="q-field">最小值<input type="number" class="q-num-input" data-field="min" value="${esc(q.min)}"></label>
                    <label class="q-field">最大值<input type="number" class="q-num-input" data-field="max" value="${esc(q.max)}"></label>
                    <label class="q-field">左端标签<input class="q-label" data-field="min_label" value="${esc(q.min_label)}"></label>
                    <label class="q-field">右端标签<input class="q-label" data-field="max_label" value="${esc(q.max_label)}"></label>` : ""}
        <span class="q-id mono">${esc(q.id)} · ${esc(q.type)}</span>
      </div>
    </div>`;
  }

  function renderQuestions() {
    if (!qList) return;
    qList.innerHTML = questions.length
      ? questions.map(rowHtml).join("")
      : `<div class="empty" style="padding:22px"><p>还没有题目，请加载标准量表或手动添加。</p></div>`;
    if (qCount) qCount.textContent = `${questions.length} 题`;
  }

  function targetOf(node) {
    const row = node.closest(".q-row");
    return row ? { q: questions[Number(row.dataset.index)], index: Number(row.dataset.index) } : null;
  }

  qList?.addEventListener("input", (event) => {
    const field = event.target.dataset.field;
    const hit = targetOf(event.target);
    if (!field || !hit) return;
    const q = hit.q;
    if (field === "title") q.title = event.target.value;
    else if (field === "options") q.options = event.target.value.split("\n").map((s) => s.trim()).filter(Boolean);
    else if (field === "min" || field === "max") q[field] = Number(event.target.value) || (field === "max" ? 9 : 1);
    else if (field === "min_label" || field === "max_label") q[field] = event.target.value;
  });

  qList?.addEventListener("change", (event) => {
    const field = event.target.dataset.field;
    const hit = targetOf(event.target);
    if (!field || !hit) return;
    const q = hit.q;
    if (field === "type") {
      q.type = event.target.value;
      applyDefaults(q);
      renderQuestions();
    } else if (field === "role") q.role = event.target.value;
    else if (field === "required") q.required = event.target.checked;
  });

  qList?.addEventListener("click", (event) => {
    const act = event.target.dataset.act;
    if (!act) return;
    const hit = targetOf(event.target);
    if (!hit) return;
    const i = hit.index;
    if (act === "del") questions.splice(i, 1);
    else if (act === "up" && i > 0) [questions[i - 1], questions[i]] = [questions[i], questions[i - 1]];
    else if (act === "down" && i < questions.length - 1) [questions[i + 1], questions[i]] = [questions[i], questions[i + 1]];
    renderQuestions();
  });

  document.getElementById("templatePicker")?.addEventListener("change", (event) => {
    const key = event.target.value;
    if (!key) return;
    const tpl = catalog.templates[key];
    if (tpl) {
      questions = JSON.parse(JSON.stringify(tpl));
      kind = key;
      renderQuestions();
    }
    event.target.value = "";
  });

  document.getElementById("addQuestion")?.addEventListener("click", () => {
    questions.push({ id: "q" + Date.now().toString(36), type: "text", title: "新题目", required: true, role: "" });
    renderQuestions();
    qList?.lastElementChild?.querySelector(".q-title")?.focus();
  });

  renderQuestions();

  // ------------------------------------------------------------------
  // 素材选择（原有逻辑）
  // ------------------------------------------------------------------
  function picks() { return Array.from(document.querySelectorAll(".media-pick:checked")); }
  function updateCount() {
    const count = picks().length;
    if (selectedCount) selectedCount.textContent = `已选 ${count} 个`;
  }
  const materialRows=Array.from(table.querySelectorAll("tbody tr"));
  const materialQuery=new EEG.ListController({items:materialRows,searchText:r=>r.dataset.search,matches:(r,f)=>(f.modality==="all"||r.dataset.modality===f.modality)&&(!f.category||r.dataset.category===f.category)});
  function filterRows() {
    const query = (search?.value || "").trim().toLowerCase();
    const cat = category?.value || "";
    const result=materialQuery.update({query,filters:{modality,category:cat}});
    materialRows.forEach(row=>{row.hidden=true;});result.items.forEach(row=>{row.hidden=false;});
    const n=result.total;
    if (visible) visible.textContent = `${n} 条`;
  }

  document.querySelectorAll(".media-pick").forEach((input) => input.addEventListener("change", updateCount));
  search?.addEventListener("input", filterRows);
  category?.addEventListener("change", filterRows);
  document.querySelectorAll("#builderModality .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#builderModality .chip").forEach((item) => item.classList.remove("active"));
      chip.classList.add("active");
      modality = chip.dataset.filter || "all";
      filterRows();
    });
  });
  document.getElementById("clearSelection")?.addEventListener("click", () => {
    document.querySelectorAll(".media-pick:checked").forEach((input) => { input.checked = false; });
    updateCount();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    if (schemaError) schemaError.hidden = true;
    const ids = picks().map((input) => input.value);
    if (!ids.length) {
      error.textContent = "请选择至少一个素材。";
      error.hidden = false;
      return;
    }
    const title = document.getElementById("surveyTitle").value.trim();
    if (!title) {
      error.textContent = "请填写问卷标题。";
      error.hidden = false;
      return;
    }
    if (!questions.length || questions.some((q) => !String(q.title || "").trim())) {
      if (schemaError) {
        schemaError.textContent = "至少需要一道题，且每题都必须有题干。";
        schemaError.hidden = false;
      }
      return;
    }
    const payload = {
      title,
      description: document.getElementById("surveyDescription").value.trim(),
      material_ids: ids,
      require_code: document.getElementById("requireCode").checked,
      allow_multiple: document.getElementById("allowMultiple").checked,
      kind,
      schema: questions,
    };
    const surveyId = form.dataset.surveyId;
    // 页面顶部与底部各有一个 submit 按钮，必须一起禁用，否则请求期间可重复创建/更新问卷
    const submitButtons = Array.from(form.querySelectorAll('button[type="submit"]'));
    const setSubmitBusy = (busy) => submitButtons.forEach((btn) => EEG.setBusy(btn, busy, "保存中…"));
    setSubmitBusy(true);
    try {
      const url = surveyId ? `/api/surveys/${encodeURIComponent(surveyId)}` : "/api/surveys";
      await EEG.api(url, { method: surveyId ? "PUT" : "POST", body: JSON.stringify(payload) });
      EEG.toast("问卷已保存，分享链接已生成", "success");
      setTimeout(() => { window.location.href = "/surveys"; }, 500);
    } catch (err) {
      setSubmitBusy(false);
      error.textContent = err.message;
      error.hidden = false;
    }
  });

  updateCount();
  filterRows();
})();
