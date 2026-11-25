(function () {
  const list = document.getElementById("merQueueList");
  if (!list) return;
  const summary = document.getElementById("merQueueSummary");
  const dialog = document.getElementById("merJobDialog");
  const title = document.getElementById("merJobTitle");
  const status = document.getElementById("merJobStatus");
  const log = document.getElementById("merJobLogs");
  const selected = document.getElementById("merDataset")?.value || "";
  const path = `/api/dashboard/queue?dataset=${encodeURIComponent(selected)}`;
  const labels = {queued: "排队中", running: "运行中", cancelling: "终止中", cancelled: "已终止",
    success: "已完成", failed: "失败", interrupted: "已中断", unknown: "状态待确认"};
  let openTask = null;
  let refreshing = false;
  let rendered = "";
  const stopping = new Set();

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function updateLogs(taskStatus, lines) {
    status.textContent = labels[taskStatus] || taskStatus;
    const text = lines?.length ? lines.join("\n") : "暂无日志输出。";
    if (log.textContent === text) return;
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 32;
    log.textContent = text;
    if (atBottom) log.scrollTop = log.scrollHeight;
  }

  async function showLogs() {
    const task = openTask;
    if (!task || !dialog.open) return;
    try {
      const endpoint = task.job_id ? `/api/jobs/${encodeURIComponent(task.job_id)}`
        : `/api/dashboard/queue/log?task_id=${encodeURIComponent(task.id)}`;
      const job = await EEG.api(endpoint, {cache: "no-store"});
      if (openTask?.id === task.id && dialog.open) updateLogs(job.status, job.logs);
    } catch (error) {
      if (openTask?.id === task.id && dialog.open) log.textContent = `日志读取失败。${error.message}`;
    }
  }

  function viewLogs(task) {
    openTask = task;
    title.textContent = task.title;
    status.textContent = labels[task.status] || task.status;
    log.textContent = "正在读取日志…";
    dialog.showModal();
    void showLogs();
  }

  async function stopTask(task, button) {
    if (stopping.has(task.id) || !window.confirm(`终止「${task.title}」？已写出的日志会保留。`)) return;
    stopping.add(task.id);
    button.disabled = true;
    try {
      await EEG.api(`/api/dashboard/jobs/${encodeURIComponent(task.job_id)}/cancel`, {
        method: "POST", body: JSON.stringify({confirmed: true}),
      });
      EEG.toast("已提交终止请求", "success");
    } catch (error) {
      EEG.toast(error.message, "error");
    } finally {
      stopping.delete(task.id);
      rendered = "";
      await refresh();
    }
  }

  function row(task) {
    const entry = element("div", null, "mer-queue-row");
    entry.dataset.taskId = task.id;
    const name = element("div", null, "mer-queue-name");
    const jobTitle = element("strong", task.title, "mer-queue-title");
    jobTitle.title = task.title;
    name.append(jobTitle, element("span", labels[task.status] || task.status, `mer-queue-status ${task.status}`));
    const progress = element("div", null, "mer-queue-progress");
    const details = task.progress || {};
    if (Number.isFinite(details.fraction)) {
      const meter = element("progress");
      meter.max = 1;
      meter.value = Math.min(1, Math.max(0, details.fraction));
      meter.setAttribute("aria-label", `${task.title}进度`);
      const current = details.epoch && details.epochs ? `Epoch ${details.epoch} / ${details.epochs}` : "";
      progress.title = [current, details.note].filter(Boolean).join(" · ");
      progress.append(meter, element("span", `${Math.round(meter.value * 100)}%`));
    } else {
      progress.append(element("span", task.status === "queued" ? "待启动" : "进度未记录"));
    }
    const actions = element("div", null, "mer-queue-actions");
    const logsButton = element("button", "日志", "btn btn-soft btn-sm");
    logsButton.type = "button";
    logsButton.dataset.action = "logs";
    logsButton.addEventListener("click", () => viewLogs(task));
    const stopButton = element("button", "终止", "btn btn-soft btn-sm mer-queue-stop");
    stopButton.type = "button";
    stopButton.dataset.action = "stop";
    stopButton.disabled = !task.can_cancel || stopping.has(task.id);
    if (!task.can_cancel) stopButton.title = task.cancel_reason;
    stopButton.addEventListener("click", () => void stopTask(task, stopButton));
    actions.append(logsButton, stopButton);
    entry.append(name, progress, actions);
    return entry;
  }

  function render(data) {
    const {jobs, running_training_count: count, process_scan_ok: scanned} = data;
    document.querySelectorAll("[data-mer-training-count]").forEach(node => {
      node.textContent = count;
      node.hidden = false;
    });
    summary.textContent = jobs.length ? `${jobs.length} 项活动` : "";
    const key = JSON.stringify({jobs, scanned});
    if (key === rendered) return;
    rendered = key;
    const focused = document.activeElement;
    const focusedTask = focused?.closest(".mer-queue-row")?.dataset.taskId;
    const entries = jobs.map(row);
    const message = scanned ? "当前没有后台任务" : "当前未发现受管任务，外部进程状态暂不可用";
    list.replaceChildren(...(entries.length ? entries : [element("p", message, "mer-queue-message")]));
    if (focusedTask) entries.find(entry => entry.dataset.taskId === focusedTask)
      ?.querySelector(`[data-action="${focused.dataset.action}"]`)?.focus();
  }

  async function refresh() {
    if (refreshing || document.hidden) return;
    refreshing = true;
    try {
      const data = await EEG.api(path, {cache: "no-store"});
      render(data);
      if (openTask) {
        openTask = data.jobs.find(task => task.id === openTask.id) || openTask;
        await showLogs();
      }
    } catch (_) {
      rendered = "";
      summary.textContent = "";
      list.replaceChildren(element("p", "后台任务暂不可用，稍后会自动刷新。", "mer-queue-message"));
      document.querySelectorAll("[data-mer-training-count]").forEach(node => { node.hidden = true; });
    } finally {
      refreshing = false;
    }
  }

  dialog.addEventListener("close", () => { openTask = null; });
  document.addEventListener("visibilitychange", refresh);
  void refresh();
  window.setInterval(refresh, 5000);
})();
