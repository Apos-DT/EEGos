"""Dependency-light classification metrics for EEG experiments."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def confusion_matrix(y_true: Sequence[int], y_pred: Sequence[int], n_classes: int) -> np.ndarray:
    true = np.asarray(y_true, dtype=np.int64)
    pred = np.asarray(y_pred, dtype=np.int64)
    if len(true) != len(pred):
        raise ValueError("y_true 与 y_pred 长度不一致")
    matrix = np.zeros((n_classes, n_classes), dtype=np.int64)
    for t, p in zip(true, pred):
        if 0 <= t < n_classes and 0 <= p < n_classes:
            matrix[t, p] += 1
    return matrix


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def compute_metrics(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    n_classes: int,
    class_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compute accuracy, balanced accuracy, macro-F1, kappa and per-class stats."""

    true = np.asarray(y_true, dtype=np.int64)
    pred = np.asarray(y_pred, dtype=np.int64)
    matrix = confusion_matrix(true, pred, n_classes)
    total = int(matrix.sum())
    accuracy = _safe_div(np.trace(matrix), total)

    per_class = []
    recalls = []
    f1s = []
    for cls in range(n_classes):
        tp = float(matrix[cls, cls])
        support = float(matrix[cls, :].sum())
        predicted = float(matrix[:, cls].sum())
        precision = _safe_div(tp, predicted)
        recall = _safe_div(tp, support)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        recalls.append(recall if support else 0.0)
        f1s.append(f1)
        name = class_names[cls] if class_names is not None and cls < len(class_names) else str(cls)
        per_class.append(
            {
                "class_id": cls,
                "class_name": name,
                "support": int(support),
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
            }
        )

    observed = accuracy
    row_totals = matrix.sum(axis=1).astype(float)
    col_totals = matrix.sum(axis=0).astype(float)
    expected = _safe_div(float(np.dot(row_totals, col_totals)), float(total * total))
    kappa = _safe_div(observed - expected, 1.0 - expected) if expected < 1.0 else 0.0

    return {
        "n_samples": total,
        "accuracy": round(accuracy, 4),
        "balanced_accuracy": round(float(np.mean(recalls)), 4),
        "macro_f1": round(float(np.mean(f1s)), 4),
        "cohen_kappa": round(kappa, 4),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
    }


def bootstrap_accuracy_ci(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    n_bootstrap: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
    groups=None,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for accuracy."""

    true = np.asarray(y_true, dtype=np.int64)
    pred = np.asarray(y_pred, dtype=np.int64)
    if len(true) == 0:
        return (float("nan"), float("nan"))
    units = np.arange(len(true)) if groups is None else np.asarray(groups)
    if len(units) != len(true):
        raise ValueError("置信区间分组长度不一致")
    unique = np.unique(units)
    if len(unique) < 2:
        return (None, None)
    unit_scores = np.asarray([(true[units == unit] == pred[units == unit]).mean() for unit in unique])
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, len(unique), len(unique))
        values.append(float(unit_scores[idx].mean()))
    lower = float(np.quantile(values, alpha / 2))
    upper = float(np.quantile(values, 1 - alpha / 2))
    return round(lower, 4), round(upper, 4)
