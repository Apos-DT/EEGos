"""Portable DDA experiment provenance and HTML report (no training imports)."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def esc(value):
    if value is None:
        return "未记录"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return html.escape(str(value))


def table(headers, rows):
    return '<div class="table-wrap"><table><thead><tr>' + ''.join(f"<th>{esc(h)}</th>" for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f"<td>{esc(v)}</td>" for v in row) + '</tr>' for row in rows) + '</tbody></table></div>'


LABELS = {
    "name":"数据集", "root":"数据根目录", "feature":"特征字段", "channels":"通道数", "bands":"频段数",
    "window_seconds":"窗口长度（秒）", "classes":"情绪类别", "subjects":"被试数", "sessions":"会话数",
    "trials_per_subject_session":"每被试每会话 trial 数", "loaded_windows":"加载的窗口总数", "loaded_files":"加载的文件数",
    "manifest":"数据清单", "manifest_sha256":"数据清单 SHA256", "data_root":"数据路径", "output_dir":"输出路径",
    "setting":"评估协议", "algorithm":"DDA 变体", "target_labeled_trials":"目标域标签 trial 数", "target_subject":"目标被试",
    "target_session":"目标会话", "max_folds":"折数上限（0 为全部）", "epochs":"训练轮数", "batch_size":"训练批量",
    "eval_interval":"评估间隔（epoch）", "lr":"学习率", "beta":"对齐损失权重 β", "pseudo_threshold":"伪标签阈值",
    "seed":"随机种子", "optimizer":"优化器", "weight_decay":"权重衰减", "momentum":"动量", "dropout":"Dropout",
    "eval_batch_size":"评估批量", "gaussian_kernels":"高斯核数量", "gaussian_mul":"高斯核倍数", "dynamic_alpha":"动态权重 α",
    "fold_seed":"逐折种子规则", "normalization":"标准化方式", "batch_pairing":"批次配对方式", "python":"Python 版本",
    "python_executable":"Python 路径", "platform":"操作系统", "torch":"PyTorch 版本", "numpy":"NumPy 版本", "scipy":"SciPy 版本",
    "cuda_runtime":"CUDA 运行时", "cuda_available":"CUDA 可用", "device":"训练设备", "gpu_memory_bytes":"显存容量（字节）",
    "data":"输入数据说明", "fold_protocol":"数据划分协议", "target_labels_used_for_gradient":"目标标签参与梯度",
    "target_label_trials":"目标标签 trial 数", "selection_uses_target_test_accuracy":"目标测试集参与峰值选择",
    "selection_note":"模型选择口径", "batch_sampling":"采样方式", "accuracy":"最终准确率（折均值）",
    "accuracy_std":"准确率折间标准差", "balanced_accuracy":"平衡准确率", "macro_f1":"Macro F1", "cohen_kappa":"Cohen κ",
    "accuracy_ci95":"最终准确率 95% CI", "paper_protocol_peak_accuracy":"目标测试峰值（折均值）", "paper_protocol_peak_std":"峰值折间标准差",
    "fold":"折编号", "session":"目标会话", "started_at":"训练开始", "finished_at":"训练结束", "elapsed_seconds":"耗时（秒）",
    "n_source":"源域样本数", "n_target":"目标测试样本数", "n_target_labeled":"目标有标签样本数", "n_samples":"评分样本数",
    "final_accuracy":"最终准确率", "peak_epoch":"峰值 epoch", "source_sessions":"源域会话", "source_subject_ids":"源域被试",
}
PERCENT_KEYS = {"accuracy", "accuracy_std", "balanced_accuracy", "macro_f1", "paper_protocol_peak_accuracy", "paper_protocol_peak_std", "final_accuracy"}


def mapping(data):
    rows = []
    for k, v in data.items():
        if k == "confusion_matrix":
            continue
        if k in PERCENT_KEYS and isinstance(v, (int, float)):
            v = f"{v:.2%}"
        elif k == "accuracy_ci95" and isinstance(v, list):
            v = " – ".join(f"{n:.2%}" if n is not None else "未知" for n in v)
        elif k in ("target_subject", "target_session") and v is None:
            v = "全部"
        rows.append([f"{LABELS.get(k, k)}" + (f" · {k}" if k in LABELS else ""), v])
    return table(["项目", "记录"], rows)


def write_report(output):
    output = Path(output)
    meta = read_json(output / "run_meta.json")
    metrics = read_json(output / "metrics.json")
    progress = read_json(output / "progress.json")
    folds = metrics.get("folds", progress.get("folds", []))
    protocol = metrics.get("protocol", {})
    generated = now()
    sections = []
    titles = []
    def section(title, body):
        titles.append(title)
        sections.append(f'<section id="section-{len(sections)}"><h2>{esc(title)}</h2>{body}</section>')
    section("运行概要", mapping({
        "运行 ID": meta.get("run_id", output.name), "状态": {"success":"已完成", "failed":"失败", "running":"运行中"}.get(meta.get("status"), "历史结果，未记录状态"),
        "模型": metrics.get("model", meta.get("algorithm")), "提交时间": meta.get("submitted_at"),
        "运行开始": meta.get("started_at"), "数据加载完成": meta.get("data_loaded_at"),
        "训练结束": meta.get("training_finished_at"), "运行结束": meta.get("finished_at"),
        "总耗时（秒）": meta.get("elapsed_seconds"), "报告生成时间": generated,
        "本次报告生成器 SHA256": digest(Path(__file__)),
        "时间口径": "Asia/Shanghai · ISO 8601（+08:00）；未记录表示原始任务没有保存，不能从文件时间推断。",
        "已完成折数": len(folds), "计划折数": meta.get("planned_folds"), "错误": meta.get("error", "无" if meta.get("status") == "success" else None),
    }))
    section("数据集与数据版本", mapping(meta.get("dataset_info", {
        "名称": meta.get("dataset", "SEED-IV"), "数据说明": protocol.get("data"),
        "数据清单与哈希": "历史任务未保存，无法确认当时文件版本。",
    })))
    section("训练参数（完整快照）", mapping(meta.get("parameters", protocol)))
    section("模型、协议与运行环境", mapping({
        **meta.get("environment", {}), "模型结构": meta.get("architecture"),
        "实现来源": meta.get("external_engine"), "上游提交": meta.get("external_engine_commit"),
        "论文 DOI": meta.get("paper_doi"), "本地实现 SHA256": meta.get("code_sha256"),
        "实现说明": meta.get("implementation_note"), **protocol,
    }))
    overall = metrics.get("overall", {})
    cards = '<div class="metrics">' + ''.join(f'<div><span>{esc(LABELS[k])}</span><strong>{overall[k]:.2%}</strong></div>' for k in ("accuracy", "balanced_accuracy", "macro_f1", "paper_protocol_peak_accuracy") if isinstance(overall.get(k), (int,float))) + '</div>'
    section("结果汇总", cards + '<p class="note">Accuracy 为最终模型测试准确率的折均值；训练峰值使用目标测试标签挑选，可能偏乐观。不同划分、数据与标签预算不能直接比较。单折区间不代表总体不确定性。</p>' + mapping(overall))
    section("逐折结果与时间", table(["折", "目标会话", "目标被试", "种子", "开始", "结束", "耗时/s", "源样本", "目标有标签", "测试样本", "最终 ACC", "峰值 ACC", "峰值 epoch", "Macro F1", "κ"], [
        [f.get(k) for k in ("fold", "session", "target_subject", "seed", "started_at", "finished_at", "elapsed_seconds", "n_source", "n_target_labeled", "n_target", "final_accuracy", "paper_protocol_peak_accuracy", "peak_epoch", "macro_f1", "cohen_kappa")] for f in folds]))
    matrix = overall.get("confusion_matrix", [])
    names = metrics.get("class_names", [])
    if matrix:
        section("混淆矩阵（计数，行是真实类别，列是预测类别）", table(["真实 / 预测"] + names, [[names[i] if i < len(names) else i] + row for i, row in enumerate(matrix)]))
    if metrics.get("per_subject"):
        section("分被试结果", table(["被试", "测试样本", "ACC", "Macro F1"], [[r.get(k) for k in ("subject", "n", "accuracy", "macro_f1")] for r in metrics["per_subject"]]))
    details = []
    for fold in folds:
        details.append(f'<details><summary>Fold {esc(fold.get("fold"))} · Session {esc(fold.get("session"))} · {esc(fold.get("target_subject"))}</summary>' + mapping({k:v for k,v in fold.items() if k not in ("history", "confusion_matrix", "per_class")}) + table(["类别", "样本", "Recall", "F1"], [[r.get(k) for k in ("class_name", "support", "recall", "f1")] for r in fold.get("per_class", [])]) + table(["Epoch", "评估时间", "耗时/s", "测试 ACC", "训练 Loss"], [[r.get(k) for k in ("epoch", "evaluated_at", "elapsed_seconds", "accuracy", "loss")] for r in fold.get("history", [])]) + '</details>')
    section("逐折评估明细", ''.join(details) or '<p>尚无完成的折。</p>')
    manifest = read_json(output / "dataset_manifest.json")
    section("数据文件清单", '<details><summary>展开数据文件与 SHA256</summary>' + table(["相对路径", "字节数", "SHA256"], [[r.get(k) for k in ("path", "size_bytes", "sha256")] for r in manifest.get("files", [])]) + "</details>" if manifest else '<p>原始任务未保存文件清单。</p>')
    events = []
    if (output / "timeline.jsonl").exists():
        events = [json.loads(line) for line in (output / "timeline.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    section("运行时间线", '<details><summary>展开全部事件（含逐次评估）</summary>' + table(["时间", "事件", "细节"], [[e.get("at"), e.get("event"), {k:v for k,v in e.items() if k not in ("at", "event")}] for e in events]) + "</details>" if events else '<p>历史任务未保存事件时间线。</p>')
    title = f'{metrics.get("model", "DDA")} · 实验报告'
    doc = '<!doctype html><html lang="zh-CN" data-dda-report-version="2"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + esc(title) + '</title><style>body{font:14px/1.7 system-ui,sans-serif;color:#20323e;background:#f4f7fa;margin:0}main{max-width:1280px;margin:auto;padding:32px 20px}header,section{background:white;border:1px solid #dce5ec;border-radius:12px;padding:22px;margin-bottom:18px}h1{margin:0;font-size:26px}h2{font-size:18px;margin-top:0}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{padding:10px;text-align:left;border-bottom:1px solid #e5ebef;vertical-align:top;overflow-wrap:anywhere;min-width:80px}th{background:#f1f7f8;color:#126c64}td:last-child{white-space:pre-wrap}details{margin:12px 0}summary{cursor:pointer;font-weight:600}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:15px 0}.metrics div{padding:16px;background:#f0f8f6;border-radius:10px}.metrics span{display:block;font-size:12px}.metrics strong{font-size:28px;color:#126c64}nav{display:flex;flex-wrap:wrap;gap:12px;margin-top:20px}a{color:#126c64}.note{background:#fff6df;padding:14px;border-radius:8px}@media print{body{background:white}section{break-inside:auto}details{display:block}}</style></head><body><main><header><h1>' + esc(title) + '</h1><p>' + esc(output.name) + '</p><nav>' + ''.join(f'<a href="#section-{i}">{esc(t)}</a>' for i,t in enumerate(titles)) + '</nav></header>' + ''.join(sections) + '</main></body></html>'
    (output / "report.html").write_text(doc, encoding="utf-8")
    return output / "report.html"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir")
    print(write_report(parser.parse_args().output_dir))
