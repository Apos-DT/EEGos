(function () {
  "use strict";

  const state = { session: null, watchStartedAt: null, watchSeconds: 0, completed: false };

  const $ = (id) => document.getElementById(id);
  const setupPanel = $("setupPanel");
  const setupLayout = document.querySelector(".experiment-layout");
  const runner = $("runner");
  const runnerGrid = document.querySelector(".runner-grid");
  const setupForm = $("setupForm");
  const video = $("experimentVideo");
  const questionnaire = $("questionnaire");
  const completion = $("completion");
  const responseForm = $("responseForm");

  async function api(url, options) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let payload = null;
    try { payload = await response.json(); } catch (error) { payload = null; }
    if (!response.ok) {
      throw new Error(payload?.detail || `请求失败（${response.status}）`);
    }
    return payload;
  }

  function setError(element, message) {
    if (!element) return;
    element.textContent = message || "";
    element.hidden = !message;
  }

  function formatClock(seconds) {
    const value = Math.max(0, Math.floor(seconds || 0));
    return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
  }

  function setProgress(session) {
    const total = session.total || 0;
    const answered = session.answered || 0;
    $("progressText").textContent = `${answered} / ${total}`;
    $("progressBar").style.width = `${total ? Math.round((answered / total) * 100) : 0}%`;
  }

  function syncScale(key) {
    const input = $(key);
    if (!input) return;
    const scale = document.querySelector(`.rating-scale[data-scale="${key}"]`);
    if (!scale) return;
    scale.querySelectorAll("button").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.value) === Number(input.value));
    });
  }

  function resetQuestionnaire() {
    responseForm.reset();
    $("valence").value = "5";
    $("arousal").value = "5";
    $("valenceValue").textContent = "5";
    $("arousalValue").textContent = "5";
    $("intensity").value = "3";
    $("familiarity").value = "3";
    syncScale("valence");
    syncScale("arousal");
    questionnaire.hidden = true;
    setError($("responseError"), "");
    state.watchStartedAt = null;
    state.watchSeconds = 0;
    $("videoClock").textContent = "00:00";
  }

  function showSetup() {
    runner.hidden = true;
    if (setupLayout) setupLayout.hidden = false;
    setupPanel.hidden = false;
    $("recentSessionsPanel").hidden = false;
    questionnaire.hidden = true;
    completion.hidden = true;
  }

  function renderSession(session) {
    state.session = session;
    if (setupLayout) setupLayout.hidden = true;
    setupPanel.hidden = true;
    runner.hidden = false;
    runnerGrid?.classList.add("video-only");
    $("recentSessionsPanel").hidden = true;
    $("runnerParticipant").textContent = `被试 ${session.participant_code} · ${session.id}`;
    setProgress(session);

    if (session.status === "completed" || session.status === "aborted") {
      video.pause();
      video.removeAttribute("src");
      video.load();
      $("runnerTitle").textContent = session.status === "completed" ? "实验完成" : "实验已结束";
      $("runnerStatus").textContent = session.status === "completed" ? "已完成" : "已结束";
      $("questionnaire").hidden = true;
      $("completion").hidden = false;
      $("completion").querySelector("h3").textContent = session.status === "completed" ? "本轮实验完成" : "本轮已结束";
      $("completion").querySelector("p").textContent =
        session.status === "completed"
          ? `已保存 ${session.answered} 条问卷。可以导出 CSV，或开始下一名被试。`
          : `已保存 ${session.answered} 条问卷；未完成的会话可以在“问卷数据”中查看。`;
      localStorage.removeItem("eeg_active_session");
      return;
    }

    if (!session.current) {
      $("runnerTitle").textContent = "等待刺激";
      $("runnerStatus").textContent = "待开始";
      return;
    }

    $("runnerTitle").textContent = `刺激 ${session.current.index} / ${session.current.total}`;
    $("runnerStatus").textContent = "进行中";
    $("questionStimulus").textContent = `#${String(session.current.index).padStart(2, "0")} · ${session.current.stimulus_id}`;
    completion.hidden = true;
    resetQuestionnaire();
    video.src = session.current.video_url;
    video.load();
    localStorage.setItem("eeg_active_session", session.id);
  }

  async function fetchSession(id) {
    const payload = await api(`/api/experiment/sessions/${encodeURIComponent(id)}`);
    renderSession(payload.session);
  }

  async function loadInitial() {
    const params = new URLSearchParams(location.search);
    const id = params.get("session") || localStorage.getItem("eeg_active_session");
    if (!id) return;
    try {
      await fetchSession(id);
    } catch (error) {
      localStorage.removeItem("eeg_active_session");
      EEG.toast(error.message, "error");
    }
  }

  setupForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    setError($("setupError"), "");
    const button = $("startExperiment");
    button.disabled = true;
    try {
      const form = new FormData(setupForm);
      const payload = await api("/api/experiment/sessions", {
        method: "POST",
        body: JSON.stringify({
          participant_code: String(form.get("participant_code") || "").trim(),
          limit: Number(form.get("limit") || 8),
          age: form.get("age") ? Number(form.get("age")) : null,
          gender: String(form.get("gender") || ""),
          consent: $("consent").checked,
          note: String(form.get("note") || ""),
          sleep_hours: form.get("sleep_hours") ? Number(form.get("sleep_hours")) : null,
          fatigue: form.get("fatigue") ? Number(form.get("fatigue")) : null,
          mood: form.get("mood") ? Number(form.get("mood")) : null,
        }),
      });
      renderSession(payload.session);
      EEG.toast("实验已开始", "success");
    } catch (error) {
      setError($("setupError"), error.message);
    } finally {
      button.disabled = false;
    }
  });

  video?.addEventListener("play", () => {
    if (!state.watchStartedAt) state.watchStartedAt = Date.now();
  });
  video?.addEventListener("timeupdate", () => {
    if (state.watchStartedAt) {
      state.watchSeconds = Math.max(state.watchSeconds, Math.round((Date.now() - state.watchStartedAt) / 1000));
      $("videoClock").textContent = formatClock(state.watchSeconds);
    }
  });
  video?.addEventListener("ended", () => {
    $("showQuestionnaire").classList.add("pulse");
    EEG.toast("视频播放完毕，请填写问卷", "info");
  });

  $("showQuestionnaire")?.addEventListener("click", () => {
    video.pause();
    questionnaire.hidden = false;
    runnerGrid?.classList.remove("video-only");
    $("showQuestionnaire").classList.remove("pulse");
    questionnaire.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  ["valence", "arousal"].forEach((key) => {
    $(key)?.addEventListener("input", (event) => {
      $(`${key}Value`).textContent = event.target.value;
      syncScale(key);
    });
    document.querySelectorAll(`.rating-scale[data-scale="${key}"] button`).forEach((button) => {
      button.addEventListener("click", () => {
        const input = $(key);
        input.value = button.dataset.value;
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });
  });

  responseForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.session) return;
    setError($("responseError"), "");
    const button = $("submitResponse");
    button.disabled = true;
    try {
      const form = new FormData(responseForm);
      const payload = await api(`/api/experiment/sessions/${encodeURIComponent(state.session.id)}/responses`, {
        method: "POST",
        body: JSON.stringify({
          valence: Number(form.get("valence")),
          arousal: Number(form.get("arousal")),
          discrete: String(form.get("discrete") || ""),
          intensity: Number(form.get("intensity")),
          familiarity: Number(form.get("familiarity")),
          previous_viewed: $("previousViewed").checked,
          watch_seconds: state.watchSeconds,
          note: String(form.get("note") || ""),
        }),
      });
      renderSession(payload.session);
      EEG.toast("问卷已保存", "success");
    } catch (error) {
      setError($("responseError"), error.message);
    } finally {
      button.disabled = false;
    }
  });

  $("abortExperiment")?.addEventListener("click", async () => {
    if (!state.session) return;
    if (!confirm("结束本轮实验？已填写的问卷会保留。")) return;
    try {
      const payload = await api(`/api/experiment/sessions/${encodeURIComponent(state.session.id)}/abort`, { method: "POST" });
      renderSession(payload.session);
    } catch (error) {
      EEG.toast(error.message, "error");
    }
  });

  $("newSession")?.addEventListener("click", () => {
    localStorage.removeItem("eeg_active_session");
    state.session = null;
    showSetup();
    setupForm.reset();
    $("experimentLimit").value = "8";
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  document.querySelectorAll("[data-session]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      fetchSession(link.dataset.session).catch((error) => EEG.toast(error.message, "error"));
    });
  });

  loadInitial();
})();
