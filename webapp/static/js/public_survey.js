(function () {
  "use strict";
  const token = window.__SURVEY_TOKEN__;
  const state = { session: null, watchStartedAt: null, watchSeconds: 0 };
  const $ = (id) => document.getElementById(id);
  const welcome = $("publicWelcome");
  const runner = $("publicRunner");
  const video = $("publicVideo");
  const audio = $("publicAudio");
  const question = $("publicQuestion");
  const complete = $("publicComplete");
  const responseForm = $("publicResponseForm");
  const schema = window.__SURVEY_SCHEMA__ || [];
  const schemaForm = $("schemaResponseForm");
  const useSchema = schema.length > 0;

  const startForm = $("publicStartForm");
  if (startForm && startForm.dataset.requireCode === "0") {
    const codeInput = $("participantCode");
    if (codeInput) codeInput.required = false;
  }

  async function api(url, options) {
    const response = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
    let payload = null;
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(payload?.detail || `请求失败（${response.status}）`);
    return payload;
  }

  function setError(id, message) {
    const node = $(id);
    if (!node) return;
    node.textContent = message || "";
    node.hidden = !message;
  }

  function clock(value) {
    const s = Math.max(0, Math.floor(value || 0));
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }

  function syncScale(input, valueNode, scaleName) {
    const node = $(input);
    if ($(valueNode)) $(valueNode).textContent = node.value;
    document.querySelectorAll(`.rating-scale[data-scale="${scaleName}"] button`).forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.value) === Number(node.value));
    });
  }

  function resetForm() {
    responseForm.reset();
    if (schemaForm) {
      schemaForm.reset();
      schemaForm.querySelectorAll("input[data-rating]").forEach((input) => {
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    }
    $("publicValence").value = "5";
    $("publicArousal").value = "5";
    $("publicIntensity").value = "3";
    $("publicFamiliarity").value = "3";
    syncScale("publicValence", "publicValenceValue", "publicValence");
    syncScale("publicArousal", "publicArousalValue", "publicArousal");
    question.hidden = true;
    state.watchStartedAt = null;
    state.watchSeconds = 0;
    $("publicClock").textContent = "00:00";
  }

  function mediaVisible(kind) {
    video.hidden = kind !== "video";
    audio.hidden = kind !== "audio";
  }

  function renderSession(session) {
    state.session = session;
    welcome.hidden = true;
    runner.hidden = false;
    const total = session.total || 1;
    $("publicProgressText").textContent = `${session.answered} / ${total}`;
    $("publicProgressBar").style.width = `${Math.round((session.answered / total) * 100)}%`;
    if (session.status === "completed" || session.status === "aborted") {
      video.pause(); audio.pause();
      video.removeAttribute("src"); audio.removeAttribute("src");
      video.load(); audio.load();
      mediaVisible("none");
      $("publicStage").hidden = true;
      question.hidden = true;
      complete.hidden = false;
      return;
    }
    if (!session.current) return;
    resetForm();
    complete.hidden = true;
    $("publicStage").hidden = false;
    mediaVisible(session.current.media_type);
    const player = session.current.media_type === "audio" ? audio : video;
    player.src = `/q/${encodeURIComponent(token)}/media/${encodeURIComponent(session.id)}?v=${session.current.index}`;
    player.load();
    $("publicStimulus").textContent = `#${session.current.index} / ${total}`;
    $("publicMediaHint").textContent = session.current.media_type === "audio" ? "请完整收听音频后填写问卷" : "请完整观看视频后填写问卷";
  }

  $("publicStartForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    setError("publicError", "");
    const button = $("publicStart");
    button.disabled = true;
    const form = new FormData(event.currentTarget);
    try {
      const payload = await api(`/api/public/surveys/${encodeURIComponent(token)}/sessions`, {
        method: "POST",
        body: JSON.stringify({
          participant_code: String(form.get("participant_code") || "").trim(),
          age: form.get("age") ? Number(form.get("age")) : null,
          gender: String(form.get("gender") || ""),
          sleep_hours: form.get("sleep_hours") ? Number(form.get("sleep_hours")) : null,
          fatigue: form.get("fatigue") ? Number(form.get("fatigue")) : null,
          mood: form.get("mood") ? Number(form.get("mood")) : null,
          consent: $("publicConsent").checked,
        }),
      });
      renderSession(payload.session);
    } catch (error) {
      setError("publicError", error.message);
    } finally {
      button.disabled = false;
    }
  });

  [video, audio].forEach((player) => {
    player?.addEventListener("play", () => { if (!state.watchStartedAt) state.watchStartedAt = Date.now(); });
    player?.addEventListener("timeupdate", () => {
      if (state.watchStartedAt) {
        state.watchSeconds = Math.max(state.watchSeconds, Math.round((Date.now() - state.watchStartedAt) / 1000));
        $("publicClock").textContent = clock(state.watchSeconds);
      }
    });
    player?.addEventListener("ended", () => EEG.toast("播放完毕，请填写问卷", "info"));
  });

  $("publicDone")?.addEventListener("click", () => {
    video.pause(); audio.pause();
    question.hidden = false;
    question.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  $("publicValence")?.addEventListener("input", () => syncScale("publicValence", "publicValenceValue", "publicValence"));
  $("publicArousal")?.addEventListener("input", () => syncScale("publicArousal", "publicArousalValue", "publicArousal"));
  document.querySelectorAll('.rating-scale[data-scale="publicValence"] button').forEach((button) => button.addEventListener("click", () => {
    $("publicValence").value = button.dataset.value;
    $("publicValence").dispatchEvent(new Event("input", { bubbles: true }));
  }));
  document.querySelectorAll('.rating-scale[data-scale="publicArousal"] button').forEach((button) => button.addEventListener("click", () => {
    $("publicArousal").value = button.dataset.value;
    $("publicArousal").dispatchEvent(new Event("input", { bubbles: true }));
  }));

  responseForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.session) return;
    setError("publicResponseError", "");
    const button = $("publicSubmit");
    button.disabled = true;
    const form = new FormData(responseForm);
    try {
      const payload = await api(`/api/public/surveys/${encodeURIComponent(token)}/sessions/${encodeURIComponent(state.session.id)}/responses`, {
        method: "POST",
        body: JSON.stringify({
          valence: Number(form.get("valence")),
          arousal: Number(form.get("arousal")),
          discrete: String(form.get("discrete") || ""),
          intensity: Number(form.get("intensity")),
          familiarity: Number(form.get("familiarity")),
          previous_viewed: $("publicPrevious").checked,
          watch_seconds: state.watchSeconds,
          note: "",
        }),
      });
      renderSession(payload.session);
      EEG.toast("问卷已保存", "success");
    } catch (error) {
      setError("publicResponseError", error.message);
    } finally {
      button.disabled = false;
    }
  });

  // ------------------------------------------------------------------
  // 自定义量表：按 schema 动态渲染（旧版问卷走上面的固定表单）
  // ------------------------------------------------------------------
  const AUTO_ROLES = ["rater", "stimulus"];
  function escHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[ch]);
  }

  function questionHtml(q, i) {
    const id = escHtml(q.id);
    const need = q.required === false ? "" : "required";
    let body;
    if (q.type === "text") {
      body = `<div class="field"><input name="${id}" maxlength="200" ${need} placeholder="请填写"></div>`;
    } else if (q.type === "textarea") {
      body = `<div class="field"><textarea name="${id}" rows="3" ${need} placeholder="请填写"></textarea></div>`;
    } else if (q.type === "rating") {
      const low = Number(q.min ?? 1), high = Number(q.max ?? 9);
      const mid = Math.round((low + high) / 2);
      const buttons = Array.from({ length: high - low + 1 }, (_, k) =>
        `<button type="button" data-value="${low + k}">${low + k}</button>`).join("");
      body = `<div class="rating-block">
        <div class="rating-label"><span>${escHtml(q.min_label || "最低")}</span><strong data-rating-value="${id}">${mid}</strong><span>${escHtml(q.max_label || "最高")}</span></div>
        <input type="range" name="${id}" min="${low}" max="${high}" step="1" value="${mid}" data-rating="${id}" aria-label="${escHtml(q.title)}">
        <div class="rating-scale" data-scale="${id}" role="group">${buttons}</div>
      </div>`;
    } else if (q.type === "single") {
      body = `<div class="emotion-grid">${(q.options || []).map((opt, k) =>
        `<label class="emotion-option"><input type="radio" name="${id}" value="${escHtml(opt)}" ${need && k === 0 ? "required" : ""}><span>${escHtml(opt)}</span></label>`).join("")}</div>`;
    } else {
      body = `<div class="emotion-grid">${(q.options || []).map((opt) =>
        `<label class="emotion-option"><input type="checkbox" name="${id}" value="${escHtml(opt)}"><span>${escHtml(opt)}</span></label>`).join("")}</div>`;
    }
    return `<div class="dynamic-question">
      <div class="question-head"><div><span class="badge badge-blue">第 ${i + 1} 题</span><h3>${escHtml(q.title)}</h3></div><span class="hint">${q.required === false ? "选答" : "必答"}</span></div>
      ${body}
    </div>`;
  }

  if (useSchema && schemaForm) {
    const visible = schema.filter((q) => !AUTO_ROLES.includes(q.role));
    responseForm.hidden = true;
    schemaForm.hidden = false;
    schemaForm.innerHTML = visible.map(questionHtml).join("") +
      `<p class="hint">素材编号与评分者由系统自动记录，无需填写。</p>
       <button class="btn btn-primary btn-block" type="submit" id="schemaSubmit">提交并继续</button>
       <div class="form-error" id="schemaResponseError" hidden></div>`;

    schemaForm.addEventListener("click", (event) => {
      const button = event.target.closest(".rating-scale button");
      if (!button) return;
      const scale = button.closest(".rating-scale");
      const input = schemaForm.querySelector(`input[data-rating="${scale.dataset.scale}"]`);
      if (input) {
        input.value = button.dataset.value;
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });

    schemaForm.addEventListener("input", (event) => {
      const input = event.target.closest("input[data-rating]");
      if (!input) return;
      const id = input.dataset.rating;
      const valueNode = schemaForm.querySelector(`[data-rating-value="${id}"]`);
      if (valueNode) valueNode.textContent = input.value;
      schemaForm.querySelectorAll(`.rating-scale[data-scale="${id}"] button`).forEach((b) => {
        b.classList.toggle("active", b.dataset.value === input.value);
      });
    });

    schemaForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!state.session) return;
      setError("schemaResponseError", "");
      const button = $("schemaSubmit");
      button.disabled = true;
      const data = new FormData(schemaForm);
      const answers = {};
      visible.forEach((q) => {
        const all = data.getAll(q.id);
        answers[q.id] = q.type === "multiple" ? all : (all[0] ?? "");
      });
      try {
        const payload = await api(`/api/public/surveys/${encodeURIComponent(token)}/sessions/${encodeURIComponent(state.session.id)}/answers`, {
          method: "POST",
          body: JSON.stringify({ answers, watch_seconds: state.watchSeconds }),
        });
        renderSession(payload.session);
        EEG.toast("问卷已保存", "success");
      } catch (err) {
        setError("schemaResponseError", err.message);
      } finally {
        button.disabled = false;
      }
    });
  }
})();
