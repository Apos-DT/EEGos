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


def trial_groups(subjects, sessions=None, trial_ids=None):
    if trial_ids is None:
        return None
    sessions = sessions if sessions is not None else [""] * len(subjects)
    if len(trial_ids) != len(subjects) or len(sessions) != len(subjects) or any(not str(t) for t in trial_ids):
        raise ValueError("试次分组信息不完整")
    return np.asarray([str((str(a), str(b), str(c))) for a, b, c in zip(subjects, sessions, trial_ids)])


def _group_holdout(indices, labels, groups, fraction, rng):
    unique = np.unique(groups[indices])
    group_labels = []
    for group in unique:
        values = np.unique(labels[indices[groups[indices] == group]])
        if len(values) != 1:
            raise ValueError("同一试次包含多个情绪标签")
        group_labels.append(values[0])
    train, val = _stratified_holdout(np.arange(len(unique)), np.asarray(group_labels), fraction, rng)
    return indices[np.isin(groups[indices], unique[train])], indices[np.isin(groups[indices], unique[val])]


def loso_splits(
    y: Sequence[int],
    subjects: Sequence[str],
    val_fraction: float = 0.2,
    seed: int = 42,
    trial_ids=None, sessions=None,
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
        source_subjects = rng.permutation(np.unique(groups[pool]))
        if len(source_subjects) > 1:
            n_val = min(len(source_subjects) - 1, max(1, round(len(source_subjects) * val_fraction)))
            val_idx = pool[np.isin(groups[pool], source_subjects[:n_val])]
            train_idx = pool[~np.isin(groups[pool], source_subjects[:n_val])]
        else:
            trials = trial_groups(groups, sessions, trial_ids)
            if trials is None:
                train_idx, val_idx = _stratified_holdout(pool, labels, val_fraction, rng)
            else:
                train_idx, val_idx = _group_holdout(pool, labels, trials, val_fraction, rng)
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
    trial_ids=None, sessions=None,
) -> dict[str, np.ndarray]:
    """Random stratified split for the within-subject (subject-dependent) setting.

    Subject identity is intentionally *not* held out here; this setting is
    only valid when the research question is within-subject decoding.
    """

    labels, identities = _as_arrays(y, subjects)
    rng = np.random.default_rng(seed)
    trials = trial_groups(identities, sessions, trial_ids)
    parts = {key: [] for key in ("train_idx", "val_idx", "test_idx")}
    for subject in np.unique(identities):
        indices = np.where(identities == subject)[0]
        if trials is None:
            train_val, test = _stratified_holdout(indices, labels, test_fraction, rng)
            train, val = _stratified_holdout(train_val, labels, val_fraction, rng)
        else:
            train_val, test = _group_holdout(indices, labels, trials, test_fraction, rng)
            train, val = _group_holdout(train_val, labels, trials, val_fraction, rng)
        for key, value in zip(parts, (train, val, test)):
            parts[key].extend(value.tolist())
    result = {key: np.sort(np.asarray(value, dtype=int)) for key, value in parts.items()}
    if any(len(value) == 0 for value in result.values()):
        raise ValueError("独立试次不足以划分训练、验证和测试集")
    return result


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
