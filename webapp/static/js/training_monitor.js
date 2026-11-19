/* Read-only, refresh-safe local training monitor. */
(function () {
  const $ = (id) => document.getElementById(id);
  const labels = {running: "训练进程运行中", queued: "排队中", success: "已完成", failed: "失败", interrupted: "进程已退出 · 无完成记录", unknown: "状态待确认"};
  let timer;
  let inFlight = false;
  function node(tag, text, cls) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
  function duration(seconds) {
    if (seconds == null) return "未记录";
    return `${Math.floor(seconds / 3600)}时 ${Math.floor(seconds % 3600 / 60)}分 ${Math.floor(seconds % 60)}秒`;
  }
  function usageGauge(label, value, detail, tone) {
    const gauge = node("div", undefined, `gpu-gauge gpu-gauge-${tone}`);
    const ring = node("div", value == null ? "—" : `${Math.round(value)}%`, "gpu-gauge-ring");
    if (value != null) {
      const percent = Math.max(0, Math.min(100, value));
      ring.setAttribute("role", "meter");
      ring.setAttribute("aria-label", label);
      ring.setAttribute("aria-valuemin", "0");
      ring.setAttribute("aria-valuemax", "100");
      ring.setAttribute("aria-valuenow", String(percent));
      ring.style.setProperty("--usage", `${percent}%`);
    }
    const caption = node("div", undefined, "gpu-gauge-caption");
    caption.append(node("span", label));
    if (detail) caption.append(node("span", detail, "gpu-gauge-detail"));
    gauge.append(ring, caption);
    return gauge;
  }
  function taskCard(task) {
    const card = node("article", undefined, "monitor-task");
    card.dataset.taskId = task.id;
    const header = node("div", undefined, "monitor-task-head");
    const state = task.status === "running" && !task.pid ? "任务执行中 · 等待进程状态" : labels[task.status] || task.status;
    header.append(node("strong", task.title), node("span", state, `badge badge-${task.status === "running" ? "blue" : task.status === "success" ? "green" : "neutral"}`));
    card.append(header, node("p", `${task.run_id || task.job_id || "等待创建运行目录"}`, "mono monitor-run-id"));
    const setting = {"cross-subject":"跨被试", "cross-session":"跨会话", loso:"跨被试 LOSO", "subject-dependent":"被试依赖"}[task.setting] || "待确认协议";
    card.append(node("p", `${task.dataset} · ${setting} · PID ${task.pid || "—"} · 运行时长 ${duration(task.elapsed_seconds)}`, "hint"));
    card.append(node("p", `开始：${task.started_at ? new Date(task.started_at).toLocaleString("zh-CN", {hour12:false}) : "未记录"}`, "hint"));
    const p = task.progress || {};
    if (p.fraction != null) {
      const bar = node("progress"); bar.max = 1; bar.value = p.fraction;
      bar.setAttribute("aria-label", "已记录训练进度");
      card.append(bar);
    }
    const parts = [];
    if (p.completed_folds != null) parts.push(`已完成 ${p.completed_folds}/${p.total_folds} 折`);
    if (p.current_fold != null && task.status === "running") parts.push(`当前第 ${p.current_fold} 折`);
    if (p.epoch != null) parts.push(`最近评估 epoch ${p.epoch}/${p.epochs || "—"}`);
    if (p.updated_at) parts.push(`进度更新 ${new Date(p.updated_at).toLocaleTimeString("zh-CN", {hour12:false})}`);
    card.append(node("p", parts.join(" · ") || p.note || "等待进度记录", "hint"));
    if (parts.length && p.note) card.append(node("p", p.note, "hint"));
    if (task.error) card.append(node("p", task.error, "monitor-error"));
    const details = node("details");
    details.dataset.detailId = task.id;
    details.append(node("summary", "查看最近日志与配置"));
    details.append(node("pre", task.logs?.length ? task.logs.join("\n") : "此进程暂未写出可读取日志。", "monitor-log"));
    details.append(node("pre", JSON.stringify(task.params, null, 2), "monitor-log"));
    card.append(details);
    if (task.report_url) {
      const link = node("a", "打开实验报告", "mini-link");
      link.href = task.report_url; link.target = "_blank"; link.rel = "noopener";
      card.append(link);
    }
    return card;
  }
  function render(data) {
    const open = new Set(Array.from(document.querySelectorAll("#backgroundTraining details[data-detail-id][open]")).map(el => el.dataset.detailId));
    const scroll = new Map(Array.from(document.querySelectorAll("#backgroundTraining article[data-task-id]")).map(el => {
      const log = el.querySelector("pre");
      return [el.dataset.taskId, {top: log.scrollTop, bottom: log.scrollHeight - log.scrollTop - log.clientHeight < 30}];
    }));
    $("monitorCount").textContent = `${data.active_count} 个活动任务`;
    $("monitorCount").className = `badge badge-${data.active_count ? "blue" : "neutral"}`;
    $("monitorStatus").textContent = data.errors?.length ? data.errors.join("；") : `最近采样：${new Date(data.sampled_at).toLocaleTimeString("zh-CN", {hour12:false})} · 刷新页面后自动恢复监控`;
    const gpu = $("monitorGPU"); gpu.replaceChildren();
    if (data.gpu.available) {
      for (const device of data.gpu.devices) {
        const info = node("div", undefined, "monitor-device");
        const header = node("div", undefined, "gpu-device-head");
        header.append(node("strong", device.name), node("span", device.temperature == null ? "温度未知" : `${device.temperature}°C`, "gpu-temperature"));
        info.append(header);
        const memoryGB = (n) => n == null ? "—" : (n / 1024).toFixed(1);
        const gauges = node("div", undefined, "gpu-gauges");
        const memoryPercent = device.memory_used_mb != null && device.memory_total_mb > 0
          ? 100 * device.memory_used_mb / device.memory_total_mb : null;
        gauges.append(
          usageGauge("GPU", device.utilization, "", "compute"),
          usageGauge("显存", memoryPercent, `${memoryGB(device.memory_used_mb)} / ${memoryGB(device.memory_total_mb)} GB`, "memory")
        );
        info.append(gauges);
        gpu.append(info);
      }
    } else gpu.append(node("p", data.gpu.message || "GPU 信息暂不可用", "hint"));
    const active = $("monitorTasks"), history = $("monitorHistory");
    active.replaceChildren(); history.replaceChildren();
    for (const task of data.tasks) {
      const card = taskCard(task);
      if (open.has(task.id)) card.querySelector("details").open = true;
      (["running", "queued", "unknown"].includes(task.status) ? active : history).append(card);
      const position = scroll.get(task.id);
      const log = card.querySelector("pre");
      if (position && open.has(task.id)) log.scrollTop = position.bottom ? log.scrollHeight : position.top;
    }
    if (!active.childElementCount) active.append(node("p", data.process_scan_ok ? "当前未发现本项目正在运行的训练进程。" : "无法确认当前是否存在训练进程。", "hint"));
    $("monitorRecent").hidden = !history.childElementCount;
  }
  async function refresh() {
    if (inFlight || document.hidden) return;
    inFlight = true;
    try { render(await EEG.api("/api/training/monitor")); }
    catch (error) {
      $("monitorStatus").textContent = `监控连接暂不可用：${error.message}。显示的数据可能已过期，将自动重试。`;
      $("monitorCount").textContent = "连接中断";
    } finally { inFlight = false; }
  }
  document.addEventListener("DOMContentLoaded", () => {
    refresh(); timer = setInterval(refresh, 5000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
    window.addEventListener("pagehide", () => clearInterval(timer));
    window.addEventListener("pageshow", (event) => { if (event.persisted) { timer = setInterval(refresh, 5000); refresh(); } });
  });
})();
