"""Feature dataset container and reproducibility manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np


def sha256_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_feature_arrays(
    x: np.ndarray,
    y: np.ndarray,
    subjects: Sequence[str],
    sessions: Sequence[str] | None = None,
) -> None:
    """Validate the shape/value contract of a feature dataset."""

    features = np.asarray(x)
    labels = np.asarray(y)
    groups = np.asarray([str(item) for item in subjects])
    if features.ndim != 3:
        raise ValueError(f"特征 x 应为 (samples, channels, bands)，实际 {features.shape}")
    if labels.ndim != 1 or groups.ndim != 1:
        raise ValueError("y 和 subjects 必须是一维")
    if not (len(features) == len(labels) == len(groups)):
        raise ValueError("x/y/subjects 样本数不一致")
    if len(features) == 0:
        raise ValueError("数据集为空")
    if not np.issubdtype(labels.dtype, np.integer):
        if not np.allclose(labels, np.round(labels)):
            raise ValueError("y 必须为整数类别编码")
    if np.isnan(features).any() or np.isinf(features).any():
        raise ValueError("特征包含 NaN/Inf")
    if sessions is not None and len(sessions) != len(features):
        raise ValueError("sessions 长度与样本数不一致")


def write_feature_dataset(
    path: str | Path,
    x: np.ndarray,
    y: np.ndarray,
    subjects: Sequence[str],
    sessions: Sequence[str] | None = None,
    class_names: Sequence[str] | None = None,
    feature_names: Sequence[str] | None = None,
    metadata: dict[str, Any] | None = None,
    trial_ids: Sequence[str] | None = None,
) -> Path:
    """Persist a feature dataset as a compressed NPZ with JSON metadata."""

    features = np.asarray(x, dtype=np.float32)
    labels = np.asarray(y, dtype=np.int64)
    groups = np.asarray([str(item) for item in subjects])
    session_array = (
        np.asarray([str(item) for item in sessions]) if sessions is not None else np.array([""] * len(labels))
    )
    validate_feature_arrays(features, labels, groups, session_array if sessions is not None else None)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "x": features,
        "y": labels,
        "subjects": groups,
        "sessions": session_array,
    }
    if class_names is not None:
        payload["class_names"] = np.asarray([str(item) for item in class_names])
    if feature_names is not None:
        payload["feature_names"] = np.asarray([str(item) for item in feature_names])
    if trial_ids is not None:
        if len(trial_ids) != len(labels):
            raise ValueError("trial_ids 长度与样本数不一致")
        payload["trial_ids"] = np.asarray([str(item) for item in trial_ids])
    np.savez_compressed(target, **payload)
    if metadata:
        manifest = build_manifest(
            target,
            x=features,
            y=labels,
            subjects=groups,
            sessions=session_array if sessions is not None else None,
            class_names=class_names,
            extra=metadata,
        )
        manifest_path = target.with_suffix(".manifest.json")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_features(path: str | Path) -> dict[str, Any]:
    """Load a feature NPZ and return a normalised dictionary."""

    source = Path(path)
    with np.load(source, allow_pickle=False) as data:
        required = {"x", "y", "subjects"}
        missing = required - set(data.files)
        if missing:
            raise ValueError(f"特征文件缺少数组：{sorted(missing)}")
        result: dict[str, Any] = {
            "x": np.asarray(data["x"], dtype=np.float32),
            "y": np.asarray(data["y"], dtype=np.int64),
            "subjects": np.asarray(data["subjects"]).astype(str),
            "sessions": np.asarray(data["sessions"]).astype(str)
            if "sessions" in data.files
            else np.array([""] * len(data["y"])),
            "class_names": np.asarray(data["class_names"]).astype(str)
            if "class_names" in data.files
            else None,
            "feature_names": np.asarray(data["feature_names"]).astype(str)
            if "feature_names" in data.files
            else None,
            "trial_ids": np.asarray(data["trial_ids"]).astype(str)
            if "trial_ids" in data.files
            else None,
            "path": str(source),
            "sha256": sha256_file(source),
        }
    validate_feature_arrays(
        result["x"],
        result["y"],
        result["subjects"],
        result["sessions"] if np.any(result["sessions"] != "") else None,
    )
    return result


def build_manifest(
    feature_path: str | Path,
    x: np.ndarray,
    y: np.ndarray,
    subjects: Sequence[str],
    sessions: Sequence[str] | None = None,
    class_names: Sequence[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact, thesis-appendix-friendly dataset manifest."""

    path = Path(feature_path)
    labels = np.asarray(y, dtype=np.int64)
    groups = np.asarray([str(item) for item in subjects])
    unique_labels, counts = np.unique(labels, return_counts=True)
    class_map = {
        int(label): int(count) for label, count in zip(unique_labels.tolist(), counts.tolist())
    }
    subject_counts = {
        str(subject): int((groups == subject).sum()) for subject in sorted(set(groups.tolist()))
    }
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "feature_file": str(path),
        "sha256": sha256_file(path) if path.exists() else None,
        "n_samples": int(len(labels)),
        "n_channels": int(np.asarray(x).shape[1]),
        "n_features": int(np.asarray(x).shape[2]),
        "n_subjects": int(len(subject_counts)),
        "n_classes": int(len(unique_labels)),
        "class_names": list(class_names) if class_names is not None else [str(v) for v in unique_labels],
        "class_counts": class_map,
        "subject_counts": subject_counts,
        "sessions": sorted(set(str(v) for v in sessions)) if sessions is not None else [],
        "generated_at": np.datetime64("now", "s").astype(str),
    }
    if extra:
        manifest["extra"] = extra
    return manifest
