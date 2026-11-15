"""Self-contained HTML experiment report."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any, Sequence


def _image_data_uri(path: str | Path) -> str:
    source = Path(path)
    mime = "image/png" if source.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    head = "".join(f"<th>{html.escape(str(item))}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(item))}</td>" for item in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_loso_report(
    result: dict[str, Any],
    output_path: str | Path,
    figure_paths: Sequence[str | Path] = (),
    title: str = "EEG 情绪识别模型训练报告",
) -> Path:
    overall = result["overall"]
    config = result.get("config", {})
    metrics_rows = [
        ["Accuracy", f"{overall['accuracy']:.4f}"],
        ["Balanced accuracy", f"{overall['balanced_accuracy']:.4f}"],
        ["Macro F1", f"{overall['macro_f1']:.4f}"],
        ["Cohen's κ", f"{overall['cohen_kappa']:.4f}"],
        [
            "Accuracy 95% CI",
            f"{overall.get('accuracy_ci95', ('—', '—'))[0]:.4f} – "
            f"{overall.get('accuracy_ci95', ('—', '—'))[1]:.4f}",
        ],
    ]
    per_class_rows = [
        [item["class_name"], item["support"], item["precision"], item["recall"], item["f1"]]
        for item in overall["per_class"]
    ]
    per_subject_rows = [
        [item["subject"], item["n"], item["accuracy"], item["macro_f1"]]
        for item in result["per_subject"]
    ]
    fold_rows = [
        [
            item["fold"],
            item["test_subject"],
            item["n_test"],
            item["accuracy"],
            item["macro_f1"],
            item["cohen_kappa"],
        ]
        for item in result["folds"]
    ]
    images = "".join(
        f'<figure><img src="{_image_data_uri(path)}" alt="figure"><figcaption>{html.escape(Path(path).name)}</figcaption></figure>'
        for path in figure_paths
        if Path(path).exists()
    )
    config_json = html.escape(json.dumps(config, ensure_ascii=False, indent=2))
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --ink:#17212b; --muted:#5b6b7c; --line:#d9e2ec; --accent:#1f6feb; --bg:#f6f8fb; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:14px/1.65 "Microsoft YaHei", "Segoe UI", sans-serif; }}
main {{ max-width:1040px; margin:0 auto; padding:36px 28px 72px; }}
h1 {{ font-size:28px; margin:0 0 6px; }}
h2 {{ font-size:19px; margin:32px 0 10px; border-left:4px solid var(--accent); padding-left:10px; }}
.sub {{ color:var(--muted); margin:0 0 28px; }}
.cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
.card {{ background:white; border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
.card .k {{ color:var(--muted); font-size:12px; }}
.card .v {{ font-size:24px; font-weight:700; }}
table {{ width:100%; border-collapse:collapse; background:white; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
th,td {{ border-bottom:1px solid var(--line); padding:8px 10px; text-align:left; }}
th {{ background:#eef3f9; font-weight:600; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
figure {{ margin:0; background:white; border:1px solid var(--line); border-radius:10px; padding:10px; }}
figure img {{ width:100%; height:auto; display:block; }}
figcaption {{ color:var(--muted); font-size:12px; padding-top:6px; }}
pre {{ background:#0f1720; color:#dce6f2; padding:16px; border-radius:8px; overflow:auto; font-size:12px; }}
.note {{ background:#fff8e6; border:1px solid #f0d48a; padding:12px 14px; border-radius:8px; color:#6b4e00; }}
@media (max-width:760px) {{ .cards,.grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body><main>
<h1>{html.escape(title)}</h1>
<p class="sub">设置：{html.escape(result['setting'])}　模型：{html.escape(result['model'])}　
样本：{result['n_samples']}　被试：{result['n_subjects']}　类别：{result['n_classes']}</p>
<div class="cards">
  <div class="card"><div class="k">Accuracy</div><div class="v">{overall['accuracy']:.2%}</div></div>
  <div class="card"><div class="k">Balanced accuracy</div><div class="v">{overall['balanced_accuracy']:.2%}</div></div>
  <div class="card"><div class="k">Macro F1</div><div class="v">{overall['macro_f1']:.3f}</div></div>
  <div class="card"><div class="k">Cohen's κ</div><div class="v">{overall['cohen_kappa']:.3f}</div></div>
</div>
<h2>总体指标</h2>
{_table(["指标", "取值"], metrics_rows)}
<h2>混淆矩阵与分被试结果</h2>
<div class="grid">{images}</div>
<h2>分类别指标</h2>
{_table(["类别", "支持数", "Precision", "Recall", "F1"], per_class_rows)}
<h2>逐折结果</h2>
{_table(["Fold", "测试被试", "测试样本", "Accuracy", "Macro F1", "Kappa"], fold_rows)}
<h2>分被试汇总</h2>
{_table(["被试", "样本数", "Accuracy", "Macro F1"], per_subject_rows)}
<h2>运行配置</h2>
<pre>{config_json}</pre>
<p class="note">注意：若本报告由 <code>demo</code> 命令生成，其数据为合成特征，只用于验证软件流水线，不能作为 EEG 情绪识别的科研结论。正式实验请使用 <code>features</code>/<code>train</code> 命令并保留数据哈希与划分清单。</p>
</main></body></html>
"""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    return target
