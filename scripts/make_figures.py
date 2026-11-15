"""Generate the diagrams used by the thesis/documents.

Run from the project root::

    python scripts/make_figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

INK = "#1f2937"
MUTED = "#607086"
BLUE = "#dce9f7"
GREEN = "#dff0e6"
ORANGE = "#fbe7cf"
PURPLE = "#e9e2f5"
LINE = "#91a4b7"


def box(ax, x, y, w, h, text, color=BLUE, fontsize=10, weight="normal"):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.0,
        edgecolor=LINE,
        facecolor=color,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize,
            color=INK, weight=weight, linespacing=1.5)


def arrow(ax, start, end, color="#4b5f73"):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.1,
            color=color,
            shrinkA=3,
            shrinkB=3,
        )
    )


def architecture():
    fig, ax = plt.subplots(figsize=(11.2, 7.0), dpi=200)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.965, "EEG-EmoStudio 分层架构", ha="center", fontsize=16, weight="bold", color=INK)

    layers = [
        (0.80, "表现层", "CLI 命令（audit / select / features / train / demo） · HTML 报告 · DOCX/CSV 导出", ORANGE),
        (0.61, "应用服务层", "材料筛选服务 · 数据审计服务 · 特征构建服务 · 训练评估服务 · 报告服务", BLUE),
        (0.42, "领域层", "刺激/被试/会话/Trial · 标签与质量规则 · LOSO 划分 · 指标与统计", PURPLE),
        (0.23, "数据与基础设施层", "问卷 CSV · 质量排序 · 媒体文件 · NPZ 特征 · 模型检查点 · 运行清单", GREEN),
    ]
    for y, title, detail, color in layers:
        box(ax, 0.06, y, 0.88, 0.13, "", color=color)
        ax.text(0.09, y + 0.088, title, fontsize=11.5, weight="bold", color=INK, va="center")
        ax.text(0.09, y + 0.043, detail, fontsize=9.5, color=MUTED, va="center")
    for y1, y2 in [(0.36, 0.42), (0.55, 0.61), (0.74, 0.80)]:
        arrow(ax, (0.50, y1), (0.50, y2))
        arrow(ax, (0.54, y2), (0.54, y1))
    ax.text(0.56, 0.385, "调用 / 返回", fontsize=8, color=MUTED)
    box(ax, 0.06, 0.04, 0.40, 0.10, "科研用户：数据管理员、算法工程师\n导师/评审：查看报告与可复现证据", color="#f4f6f8", fontsize=8.8)
    box(ax, 0.54, 0.04, 0.40, 0.10, "外部数据：SEED / DEAP / MPED / FACED\n自采设备：62/32 导 EEG + 辅助生理信号", color="#f4f6f8", fontsize=8.8)
    arrow(ax, (0.26, 0.14), (0.26, 0.23))
    arrow(ax, (0.74, 0.14), (0.74, 0.23))
    fig.tight_layout()
    fig.savefig(OUT / "architecture.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def dataflow():
    fig, ax = plt.subplots(figsize=(12, 5.6), dpi=200)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.95, "从刺激材料到模型评估的数据流", ha="center", fontsize=16, weight="bold", color=INK)
    stages = [
        ("① 刺激库\n视频/音乐 240", 0.03, 0.58),
        ("② 问卷预评价\n效价/唤醒/离散", 0.155, 0.58),
        ("③ 清洗与质量分\nE/C/L/D/N + 门控", 0.28, 0.58),
        ("④ 平衡选材\n模态×四象限", 0.405, 0.58),
        ("⑤ EEG 采集\n事件与自评", 0.53, 0.58),
        ("⑥ 预处理\n滤波/重参考/分段", 0.655, 0.58),
        ("⑦ DE 特征\n通道×5 频带", 0.78, 0.58),
        ("⑧ 数据集\n清单/哈希/划分", 0.905, 0.58),
    ]
    for text, x, y in stages:
        box(ax, x, y, 0.095, 0.17, text, color=BLUE if x < 0.5 else GREEN, fontsize=8.4)
    for index in range(len(stages) - 1):
        arrow(ax, (stages[index][1] + 0.095, 0.665), (stages[index + 1][1], 0.665))

    box(ax, 0.18, 0.22, 0.20, 0.16, "训练与评估\nLOSO / 被试依赖\nDualView / DGCNN / MLP", color=ORANGE, fontsize=9)
    box(ax, 0.46, 0.22, 0.18, 0.16, "指标与统计\nACC / Macro-F1 / κ\n95% CI / 混淆矩阵", color=ORANGE, fontsize=9)
    box(ax, 0.72, 0.22, 0.20, 0.16, "证据与报告\n指标 JSON · 检查点\nHTML · 论文图表", color=ORANGE, fontsize=9)
    arrow(ax, (0.95, 0.58), (0.82, 0.38))
    arrow(ax, (0.38, 0.38), (0.46, 0.38))
    arrow(ax, (0.64, 0.38), (0.72, 0.38))
    ax.text(0.88, 0.47, "按被试留出", fontsize=8, color=MUTED)
    ax.text(0.5, 0.10, "反馈环：混淆类别 → 检查刺激/标签/通道 → 修订方案或补充数据", ha="center", fontsize=9, color=MUTED)
    arrow(ax, (0.82, 0.22), (0.32, 0.12), color="#b07a5a")
    fig.tight_layout()
    fig.savefig(OUT / "dataflow.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def gantt():
    tasks = [
        ("文献调研与选题", 1, 3),
        ("需求分析与数据审计", 2, 4),
        ("实验/采集方案与伦理", 4, 2),
        ("数据集制备与质量门控", 5, 4),
        ("预处理与特征流水线", 7, 2),
        ("模型与跨被试方法实现", 8, 4),
        ("对比实验与消融", 10, 3),
        ("系统测试与可用性", 12, 2),
        ("论文撰写与查重", 11, 5),
        ("答辩材料与演示", 15, 2),
    ]
    fig, ax = plt.subplots(figsize=(10.5, 5.2), dpi=200)
    colors = ["#9ecae1", "#a1d99b", "#fdd0a2", "#bcbddc", "#9ecae1", "#a1d99b", "#fdd0a2", "#bcbddc", "#fdd0a2", "#9ecae1"]
    for index, (name, start, duration) in enumerate(tasks):
        ax.barh(index, duration, left=start - 0.5, height=0.55, color=colors[index % len(colors)], edgecolor="white")
        ax.text(start - 0.55, index, f" {name}", ha="right", va="center", fontsize=9, color=INK)
    ax.set_yticks([])
    ax.set_xlim(0.5, 16.8)
    ax.set_xticks(range(1, 17))
    ax.set_xlabel("周次")
    ax.set_title("16 周毕业设计进度计划（可与实际采集窗口滚动调整）", fontsize=13, weight="bold", pad=12)
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "gantt.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def schema():
    fig, ax = plt.subplots(figsize=(11, 6.4), dpi=200)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.5, 0.96, "核心数据实体与关系（文件型数据仓库）", ha="center", fontsize=16, weight="bold", color=INK)
    entities = {
        "subject": (0.04, 0.66, 0.20, 0.18, "subject\nsubject_id (PK)\nage, sex, group\nconsent_id"),
        "session": (0.30, 0.66, 0.22, 0.18, "session\nsession_id (PK)\nsubject_id (FK)\ndate, device, fs"),
        "trial": (0.58, 0.66, 0.22, 0.18, "trial\ntrial_id (PK)\nsession_id (FK)\nstimulus_id (FK)\norder, start/end"),
        "stimulus": (0.04, 0.30, 0.22, 0.20, "stimulus\nstimulus_id (PK)\nmodality, category\nduration, source\nquality_score"),
        "rating": (0.32, 0.30, 0.22, 0.20, "rating\nrating_id (PK)\ntrial_id (FK)\nvalence, arousal\nemotion, quality"),
        "feature": (0.60, 0.30, 0.22, 0.20, "feature_set\nfeature_id (PK)\ntrial_id (FK)\nchannels × bands\nfile_uri, sha256"),
        "experiment": (0.60, 0.04, 0.28, 0.17, "experiment\nrun_id (PK)\nconfig_hash, seed\nmodel, split\nmetrics_uri"),
    }
    for name, (x, y, w, h, text) in entities.items():
        color = GREEN if name in {"subject", "session", "trial"} else BLUE if name in {"stimulus", "rating"} else PURPLE
        box(ax, x, y, w, h, text, color=color, fontsize=8.8)
    arrow(ax, (0.24, 0.75), (0.30, 0.75))
    arrow(ax, (0.52, 0.75), (0.58, 0.75))
    arrow(ax, (0.15, 0.66), (0.15, 0.50))
    arrow(ax, (0.69, 0.66), (0.69, 0.50))
    arrow(ax, (0.26, 0.40), (0.32, 0.40))
    arrow(ax, (0.54, 0.40), (0.60, 0.40))
    arrow(ax, (0.71, 0.30), (0.71, 0.21))
    ax.text(0.50, 0.12, "所有表通过稳定 ID 关联；原始文件与派生产物均登记 SHA-256，实验只引用清单版本。", ha="center", fontsize=8.8, color=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "schema.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def quality_figure():
    import pandas as pd

    root = Path(__file__).resolve().parent.parent
    rows = []
    for kind, path in [
        ("视频", root / "视频质量评分输出" / "视频质量排序.csv"),
        ("音乐", root / "音乐质量评分输出" / "音乐歌曲质量排序.csv"),
    ]:
        frame = pd.read_csv(path, encoding="utf-8-sig")
        for grade, count in frame["质量等级"].value_counts().items():
            rows.append((kind, grade, int(count)))
    frame = pd.DataFrame(rows, columns=["modality", "grade", "count"])
    pivot = frame.pivot(index="grade", columns="modality", values="count").reindex(list("SABCD")).fillna(0)
    fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=200)
    x = range(len(pivot))
    width = 0.35
    ax.bar([value - width / 2 for value in x], pivot["视频"], width, label="视频", color="#4C78A8")
    ax.bar([value + width / 2 for value in x], pivot["音乐"], width, label="音乐", color="#F58518")
    ax.set_xticks(list(x), [f"{grade} 级" for grade in pivot.index])
    ax.set_ylabel("素材数量")
    ax.set_title("240 条刺激材料的质量等级分布")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    for container in ax.containers:
        ax.bar_label(container, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "quality_grades.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    architecture()
    dataflow()
    gantt()
    schema()
    quality_figure()
    print(f"figures written to {OUT}")
