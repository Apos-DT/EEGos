"""Thesis-ready figures."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def _configure_font() -> None:
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
            matplotlib.rcParams["axes.unicode_minus"] = False
            break


def plot_confusion_matrix(
    matrix: Sequence[Sequence[int]],
    labels: Sequence[str],
    output_path: str | Path,
    title: str = "Confusion matrix",
) -> Path:
    _configure_font()
    array = np.asarray(matrix, dtype=float)
    row_sums = array.sum(axis=1, keepdims=True)
    normalised = np.divide(array, row_sums, out=np.zeros_like(array), where=row_sums > 0)
    fig, ax = plt.subplots(figsize=(6.2, 5.2), dpi=180)
    image = ax.imshow(normalised, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)), labels=labels, rotation=35, ha="right")
    ax.set_yticks(range(len(labels)), labels=labels)
    ax.set_xlabel("Predicted label")
    ax.set_ylabel("True label")
    ax.set_title(title)
    for i in range(array.shape[0]):
        for j in range(array.shape[1]):
            value = normalised[i, j]
            ax.text(
                j,
                i,
                f"{int(array[i, j])}\n{value:.0%}",
                ha="center",
                va="center",
                color="white" if value > 0.55 else "#222222",
                fontsize=8,
            )
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label="Row-normalised rate")
    fig.tight_layout()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, bbox_inches="tight")
    plt.close(fig)
    return target


def plot_subject_accuracy(
    per_subject: Sequence[dict],
    output_path: str | Path,
    chance: float = 0.25,
) -> Path:
    _configure_font()
    subjects = [str(item["subject"]) for item in per_subject]
    accuracy = [float(item["accuracy"]) for item in per_subject]
    fig, ax = plt.subplots(figsize=(7.4, 3.8), dpi=180)
    ax.bar(subjects, accuracy, color="#4C78A8", width=0.6)
    ax.axhline(chance, color="#D1495B", linestyle="--", linewidth=1.2, label=f"Chance = {chance:.2f}")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Accuracy")
    ax.set_xlabel("Held-out subject")
    ax.set_title("Per-subject cross-subject accuracy")
    ax.legend(frameon=False, loc="lower right")
    ax.grid(axis="y", alpha=0.25)
    for index, value in enumerate(accuracy):
        ax.text(index, value + 0.02, f"{value:.2f}", ha="center", fontsize=8)
    fig.tight_layout()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, bbox_inches="tight")
    plt.close(fig)
    return target
