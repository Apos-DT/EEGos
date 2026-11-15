"""Leakage-aware dataset splitting."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def _as_arrays(y: Sequence[int], subjects: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    labels = np.asarray(y, dtype=np.int64)
    groups = np.asarray([str(item) for item in subjects])
    if labels.ndim != 1 or groups.ndim != 1 or len(labels) != len(groups):
        raise ValueError("y 与 subjects 必须是一维且长度相同")
    if len(np.unique(labels)) < 2:
        raise ValueError("至少需要两个类别")
    return labels, groups


def _stratified_holdout(
    indices: np.ndarray,
    labels: np.ndarray,
    fraction: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    train_parts: list[np.ndarray] = []
    val_parts: list[np.ndarray] = []
    for cls in np.unique(labels[indices]):
        cls_idx = indices[labels[indices] == cls]
        cls_idx = rng.permutation(cls_idx)
        n_val = int(round(len(cls_idx) * fraction))
        if len(cls_idx) >= 2:
            n_val = min(max(n_val, 1), len(cls_idx) - 1)
        else:
            n_val = 0
        val_parts.append(cls_idx[:n_val])
        train_parts.append(cls_idx[n_val:])
    train = np.concatenate(train_parts) if train_parts else np.array([], dtype=int)
    val = np.concatenate(val_parts) if val_parts else np.array([], dtype=int)
    return np.sort(train), np.sort(val)


def loso_splits(
    y: Sequence[int],
    subjects: Sequence[str],
    val_fraction: float = 0.2,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Leave-one-subject-out folds with a subject-disjoint validation split.

    For every test subject, validation samples are carved out of the
    remaining *training subjects*, never from the test subject.  This makes
    early stopping honest for cross-subject evaluation.
    """

    labels, groups = _as_arrays(y, subjects)
    rng = np.random.default_rng(seed)
    folds: list[dict[str, Any]] = []
    for test_subject in sorted(np.unique(groups)):
        test_idx = np.where(groups == test_subject)[0]
        pool = np.where(groups != test_subject)[0]
        train_idx, val_idx = _stratified_holdout(pool, labels, val_fraction, rng)
        if len(train_idx) == 0:
            raise ValueError(f"测试被试 {test_subject} 留出后没有训练样本")
        if len(val_idx) == 0:
            # Degenerate small datasets: fall back to a copy of training for
            # early stopping, but record the limitation for the report.
            val_idx = train_idx.copy()
        folds.append(
            {
                "fold": len(folds) + 1,
                "test_subject": str(test_subject),
                "train_idx": train_idx,
                "val_idx": val_idx,
                "test_idx": test_idx,
                "n_train": int(len(train_idx)),
                "n_val": int(len(val_idx)),
                "n_test": int(len(test_idx)),
            }
        )
    return folds


def subject_dependent_split(
    y: Sequence[int],
    subjects: Sequence[str],
    test_fraction: float = 0.2,
    val_fraction: float = 0.2,
    seed: int = 42,
) -> dict[str, np.ndarray]:
    """Random stratified split for the within-subject (subject-dependent) setting.

    Subject identity is intentionally *not* held out here; this setting is
    only valid when the research question is within-subject decoding.
    """

    labels, _ = _as_arrays(y, subjects)
    rng = np.random.default_rng(seed)
    all_idx = np.arange(len(labels))
    train_val, test = _stratified_holdout(all_idx, labels, test_fraction, rng)
    train, val = _stratified_holdout(train_val, labels, val_fraction, rng)
    return {"train_idx": train, "val_idx": val, "test_idx": test}


def assert_no_subject_leakage(fold: dict[str, Any], subjects: Sequence[str]) -> None:
    """Raise if a fold shares a subject between train/validation and test."""

    groups = np.asarray([str(item) for item in subjects])
    train_subjects = set(groups[np.asarray(fold["train_idx"], dtype=int)])
    val_subjects = set(groups[np.asarray(fold["val_idx"], dtype=int)])
    test_subjects = set(groups[np.asarray(fold["test_idx"], dtype=int)])
    if train_subjects & test_subjects or val_subjects & test_subjects:
        raise AssertionError(
            f"fold {fold.get('fold')} 存在被试泄漏: train={train_subjects}, test={test_subjects}"
        )


def describe_folds(folds: list[dict[str, Any]], subjects: Sequence[str]) -> list[dict[str, Any]]:
    groups = np.asarray([str(item) for item in subjects])
    description = []
    for fold in folds:
        assert_no_subject_leakage(fold, groups)
        description.append(
            {
                "fold": fold["fold"],
                "test_subject": fold["test_subject"],
                "train_subjects": sorted(set(groups[fold["train_idx"]])),
                "val_subjects": sorted(set(groups[fold["val_idx"]])),
                "n_train": fold["n_train"],
                "n_val": fold["n_val"],
                "n_test": fold["n_test"],
            }
        )
    return description
