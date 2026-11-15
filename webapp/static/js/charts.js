/* Lightweight SVG charts — no external chart library. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(tooltip));

  function esc(value) {
    return String(value).replace(/[&<>"']/g, (s) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[s]));
  }

  function niceMax(value) {
    if (!value || value <= 0) return 5;
    const step = value <= 10 ? 2 : value <= 50 ? 10 : 20;
    return Math.ceil(value / step) * step;
  }

  function barChart(el, data, options = {}) {
    if (!el) return;
    const width = 780;
    const height = options.height || 260;
    const pad = { top: 18, right: 16, bottom: 34, left: 38 };
    const labels = data.labels || [];
    const series = data.series || [];
    const values = series.flatMap((s) => s.values || []).map(Number).filter((v) => Number.isFinite(v));
    const max = niceMax(Math.max(...values, 1));
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const groupW = innerW / Math.max(labels.length, 1);
    const barW = Math.min(28, (groupW * 0.64) / Math.max(series.length, 1));
    const gap = 4;
    const y = (v) => pad.top + innerH - (Number(v) / max) * innerH;
    const parts = [];
    parts.push(`<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(options.title || "柱状图")}">`);
    for (let i = 0; i <= 4; i++) {
      const value = (max / 4) * i;
      const yy = y(value);
      parts.push(`<g class="chart-grid"><line x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}"/></g>`);
      parts.push(`<text class="chart-axis" x="${pad.left - 9}" y="${yy + 3}" text-anchor="end">${value}</text>`);
    }
    labels.forEach((label, li) => {
      const cx = pad.left + groupW * li + groupW / 2;
      const totalW = series.length * barW + (series.length - 1) * gap;
      series.forEach((s, si) => {
        const value = Number((s.values || [])[li] || 0);
        const xx = cx - totalW / 2 + si * (barW + gap);
        const yy = y(value);
        const h = Math.max(pad.top + innerH - yy, value > 0 ? 2 : 0);
        parts.push(
          `<rect class="chart-bar" x="${xx}" y="${yy}" width="${barW}" height="${h}" rx="4" fill="${esc(s.color || "#0c7368")}" data-label="${esc(label)}" data-series="${esc(s.name || "")}" data-value="${value}"></rect>`
        );
      });
      parts.push(`<text class="chart-axis" x="${cx}" y="${height - 13}" text-anchor="middle">${esc(label)}</text>`);
    });
    parts.push("</svg>");
    el.innerHTML = parts.join("");
    el.querySelectorAll(".chart-bar").forEach((bar) => {
      bar.addEventListener("mousemove", (event) => {
        tooltip.textContent = `${bar.dataset.series} · ${bar.dataset.label}: ${bar.dataset.value}`;
        tooltip.style.left = `${event.clientX}px`;
        tooltip.style.top = `${event.clientY}px`;
        tooltip.classList.add("show");
      });
      bar.addEventListener("mouseleave", () => tooltip.classList.remove("show"));
    });
  }

  function horizontalBars(el, rows, options = {}) {
    if (!el) return;
    if (!rows || !rows.length) {
      el.innerHTML = `<div class="table-empty">暂无数据</div>`;
      return;
    }
    const width = 780;
    const rowH = options.rowH || 34;
    const pad = { top: 12, right: 56, bottom: 12, left: 150 };
    const height = pad.top + pad.bottom + rows.length * rowH;
    const max = Math.max(...rows.map((r) => Number(r.value) || 0), 0.01);
    const innerW = width - pad.left - pad.right;
    const parts = [`<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(options.title || "对比图")}">`];
    rows.forEach((row, index) => {
      const y = pad.top + index * rowH;
      const value = Number(row.value) || 0;
      const w = Math.max((value / max) * innerW, 2);
      parts.push(`<text class="chart-axis" x="${pad.left - 10}" y="${y + 15}" text-anchor="end">${esc(row.label)}</text>`);
      parts.push(`<rect x="${pad.left}" y="${y + 3}" width="${innerW}" height="15" rx="7" fill="#edf2f8"></rect>`);
      parts.push(`<rect x="${pad.left}" y="${y + 3}" width="${w}" height="15" rx="7" fill="${esc(row.color || "#0c7368")}"></rect>`);
      parts.push(`<text class="chart-axis" x="${pad.left + innerW + 8}" y="${y + 15}" text-anchor="start">${esc(row.display || value)}</text>`);
    });
    parts.push("</svg>");
    el.innerHTML = parts.join("");
  }

  function sparkline(el, values, options = {}) {
    if (!el) return;
    const width = options.width || 150;
    const height = options.height || 42;
    const nums = (values || []).map(Number).filter((v) => Number.isFinite(v));
    if (!nums.length) { el.innerHTML = ""; return; }
    const min = Math.min(...nums);
    const max = Math.max(...nums);
    const span = max - min || 1;
    const points = nums.map((v, i) => {
      const x = 2 + (i / Math.max(nums.length - 1, 1)) * (width - 4);
      const y = height - 3 - ((v - min) / span) * (height - 8);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" aria-hidden="true"><polyline points="${points.join(" ")}" fill="none" stroke="${options.color || "#58e0c8"}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  }

  window.EESCharts = { barChart, horizontalBars, sparkline };
})();
