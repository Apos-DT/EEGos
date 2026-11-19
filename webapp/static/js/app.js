/* Shared UI behaviour: API client, toasts, job polling, table filters. */
(function () {
  const EEG = {};
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  EEG.$ = $;
  EEG.$$ = $$;

  EEG.api = async function (path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (_) { data = { detail: text }; }
    if (!response.ok) {
      const detail = data && data.detail;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || response.statusText));
    }
    return data;
  };

  EEG.toast = function (message, type = "info", timeout = 4200) {
    const stack = $("#toastStack");
    if (!stack) return;
    const el = document.createElement("div");
    el.className = `toast ${type === "error" ? "error" : type === "success" ? "success" : ""}`;
    el.innerHTML = `<span class="toast-mark">${type === "success" ? "✓" : type === "error" ? "!" : "i"}</span><span>${escapeHtml(message)}</span>`;
    stack.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateY(6px)";
      setTimeout(() => el.remove(), 220);
    }, timeout);
  };

  EEG.setBusy = function (button, busy, label) {
    if (!button) return;
    if (busy) {
      button.dataset.original = button.innerHTML;
      button.disabled = true;
      button.innerHTML = `<span class="spinner"></span>${escapeHtml(label || "处理中…")}`;
    } else {
      button.disabled = false;
      if (button.dataset.original) button.innerHTML = button.dataset.original;
    }
  };

  EEG.statusText = function (status) {
    return {
      queued: "排队中",
      running: "运行中",
      success: "已完成",
      failed: "失败",
    }[status] || status;
  };

  EEG.renderJob = function (job, consoleId) {
    const panel = document.getElementById(consoleId);
    if (!panel) return;
    panel.hidden = false;
    panel.classList.remove("idle", "running", "success", "failed");
    panel.classList.add(job.status || "running");
    const title = document.getElementById(`${consoleId}-title`);
    const status = document.getElementById(`${consoleId}-status`);
    const log = document.getElementById(`${consoleId}-log`);
    if (title) title.textContent = job.title || "任务输出";
    if (status) status.textContent = `${EEG.statusText(job.status)}${job.started_at ? " · " + shortTime(job.started_at) : ""}`;
    if (log) {
      const lines = job.logs && job.logs.length ? job.logs.join("\n") : "等待任务开始…";
      const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
      log.textContent = lines;
      if (nearBottom) log.scrollTop = log.scrollHeight;
    }
  };

  EEG.pollJob = function (jobId, options = {}) {
    const { consoleId, onSuccess, onFail, interval = 1400, timeout = 45 * 60 * 1000 } = options;
    const started = Date.now();
    let timer = null;
    const tick = async () => {
      if (Date.now() - started > timeout) {
        clearInterval(timer);
        EEG.toast("任务等待超时，请到“系统状态”查看后台任务。", "error");
        if (onFail) onFail({ error: "任务状态等待超时，后台任务可能仍在运行。" });
        return;
      }
      try {
        const job = await EEG.api(`/api/jobs/${encodeURIComponent(jobId)}`);
        if (consoleId) EEG.renderJob(job, consoleId);
        if (job.status === "success") {
          clearInterval(timer);
          if (onSuccess) onSuccess(job);
        } else if (job.status === "failed") {
          clearInterval(timer);
          if (onFail) onFail(job);
          else EEG.toast(job.error || "任务失败", "error");
        }
      } catch (error) {
        clearInterval(timer);
        EEG.toast(error.message || "无法读取任务状态", "error");
        if (onFail) onFail({ error: error.message || "无法读取任务状态" });
      }
    };
    tick();
    timer = setInterval(tick, interval);
    return () => clearInterval(timer);
  };

  EEG.startJob = async function (url, payload, options = {}) {
    const { button, consoleId, onSuccess, onFail, successMessage } = options;
    EEG.setBusy(button, true, "提交中…");
    try {
      const response = await EEG.api(url, {
        method: "POST",
        body: JSON.stringify(payload || {}),
      });
      const job = response.job;
      if (consoleId) EEG.renderJob(job, consoleId);
      EEG.toast("任务已提交，正在后台运行。", "success", 2600);
      EEG.pollJob(job.id, {
        consoleId,
        timeout: options.pollTimeout,
        onSuccess: (finished) => {
          EEG.setBusy(button, false);
          if (successMessage) EEG.toast(successMessage, "success");
          if (onSuccess) onSuccess(finished);
        },
        onFail: (failed) => {
          EEG.setBusy(button, false);
          EEG.toast(failed.error || "任务失败，请查看日志。", "error", 6000);
          if (onFail) onFail(failed);
        },
      });
    } catch (error) {
      EEG.setBusy(button, false);
      EEG.toast(error.message || "提交失败", "error", 6000);
      if (onFail) onFail({ error: error.message || "提交失败" });
    }
  };

  EEG.filterTable = function (options) {
    const input = typeof options.input === "string" ? document.getElementById(options.input) : options.input;
    const table = typeof options.table === "string" ? document.getElementById(options.table) : options.table;
    if (!table) return;
    const rows = Array.from(table.querySelectorAll("tbody tr"));
    const count = options.count ? document.getElementById(options.count) : null;
    const chips = options.chips ? Array.from(document.querySelectorAll(options.chips)) : [];
    let activeChip = "all";
    const apply = () => {
      const query = (input && input.value ? input.value : "").trim().toLowerCase();
      let visible = 0;
      rows.forEach((row) => {
        const text = (row.dataset.search || row.textContent || "").toLowerCase();
        const chipMatch = activeChip === "all" || row.dataset.group === activeChip;
        const show = chipMatch && (!query || text.includes(query));
        row.style.display = show ? "" : "none";
        if (show) visible += 1;
      });
      if (count) count.textContent = `${visible} 条`;
    };
    if (input) input.addEventListener("input", apply);
    chips.forEach((chip) => {
      chip.addEventListener("click", () => {
        chips.forEach((item) => item.classList.remove("active"));
        chip.classList.add("active");
        activeChip = chip.dataset.filter || "all";
        apply();
      });
    });
    apply();
  };

  EEG.formatPct = function (value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return `${(Number(value) * 100).toFixed(digits)}%`;
  };

  EEG.formatNum = function (value, digits = 0) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
  };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (s) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[s]));
  }

  function shortTime(value) {
    if (!value) return "";
    const text = String(value);
    return text.length >= 16 ? text.slice(11, 16) : text;
  }

  // Sidebar for narrow screens
  document.addEventListener("DOMContentLoaded", () => {
    const sidebar = document.getElementById("sidebar");
    const scrim = document.getElementById("sidebarScrim");
    const toggle = document.getElementById("menuToggle");
    const close = () => {
      sidebar && sidebar.classList.remove("open");
      scrim && scrim.classList.remove("show");
      toggle && toggle.setAttribute("aria-expanded", "false");
    };
    if (toggle) toggle.addEventListener("click", () => {
      sidebar.classList.toggle("open");
      scrim.classList.toggle("show");
      toggle.setAttribute("aria-expanded", String(sidebar.classList.contains("open")));
    });
    if (scrim) scrim.addEventListener("click", close);
    document.addEventListener("keydown", (event) => { if (event.key === "Escape" && sidebar?.classList.contains("open")) { close(); toggle?.focus(); } });
    $$(".nav-item").forEach((item) => item.addEventListener("click", close));

    // Mark API availability without blocking the page.
    fetch("/api/health").then((r) => r.ok ? r.json() : Promise.reject()).then(() => {
      const pill = document.getElementById("apiPill");
      if (pill) pill.classList.add("api-ok");
    }).catch(() => {
      const pill = document.getElementById("apiPill");
      if (pill) {
        pill.classList.add("api-down");
        pill.innerHTML = '<span class="status-dot"></span><span>API 离线</span>';
      }
    });
  });

  window.EEG = EEG;
})();
