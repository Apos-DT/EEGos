"""Raw-array to feature-dataset pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .data.features import aggregate_windows, compute_de_features
from .data.manifest import validate_feature_arrays, write_feature_dataset
from .data.preprocess import PreprocessConfig, preprocess_array


def build_features_from_raw(
    raw_path: str | Path,
    output_path: str | Path,
    fs: float | None = None,
    bandpass: tuple[float, float] = (0.1, 70.0),
    notch_hz: float | None = 50.0,
    target_fs: float | None = None,
    window_s: float = 1.0,
    step_s: float | None = None,
    aggregate: str = "mean",
) -> dict[str, Any]:
    """Read ``raw.npz``, filter/epoch-level features and write ``features.npz``.

    Expected raw keys: ``x`` ``(trials, channels, samples)``, ``y``, and
    ``subjects``; ``fs`` may be stored in the file.  The function does not
    perform event locking because the synthetic/standardised NPZ contract
    already supplies fixed trials.  EDF/BDF adapters should produce this NPZ
    first (MNE optional dependency).
    """

    source = Path(raw_path)
    with np.load(source, allow_pickle=False) as raw:
        required = {"x", "y", "subjects"}
        missing = required - set(raw.files)
        if missing:
            raise ValueError(f"原始数组缺少字段：{sorted(missing)}")
        x = np.asarray(raw["x"], dtype=np.float64)
        y = np.asarray(raw["y"], dtype=np.int64)
        subjects = np.asarray(raw["subjects"]).astype(str)
        file_fs = float(raw["fs"]) if "fs" in raw.files else None
        class_names = (
            np.asarray(raw["class_names"]).astype(str).tolist() if "class_names" in raw.files else None
        )
    effective_fs = float(fs if fs is not None else file_fs) if (fs is not None or file_fs) else None
    if not effective_fs:
        raise ValueError("未提供采样率：请在 NPZ 中写入 fs 或通过参数传入")
    if x.ndim != 3:
        raise ValueError(f"x 应为 (trials, channels, samples)，实际 {x.shape}")
    if len(x) != len(y) or len(x) != len(subjects):
        raise ValueError("x/y/subjects 数量不一致")

    config = PreprocessConfig(
        fs=effective_fs,
        bandpass=bandpass,
        notch_hz=notch_hz,
        target_fs=target_fs,
    )
    processed = preprocess_array(x, config)
    de, window_starts = compute_de_features(
        processed,
        fs=target_fs or effective_fs,
        window_s=window_s,
        step_s=step_s,
    )
    features = aggregate_windows(de, method=aggregate)
    validate_feature_arrays(features, y, subjects)
    output = write_feature_dataset(
        output_path,
        features,
        y,
        subjects,
        class_names=class_names,
        metadata={
            "source": str(source),
            "fs": target_fs or effective_fs,
            "bandpass": list(bandpass),
            "notch_hz": notch_hz,
            "window_s": window_s,
            "step_s": step_s if step_s is not None else window_s,
            "aggregate": aggregate,
            "n_windows": int(de.shape[1]),
            "window_starts_s": window_starts.tolist(),
            "feature": "differential_entropy",
            "bands": ["delta", "theta", "alpha", "beta", "gamma"],
        },
    )
    summary = {
        "raw": str(source),
        "features": str(output),
        "n_samples": int(features.shape[0]),
        "n_channels": int(features.shape[1]),
        "n_bands": int(features.shape[2]),
        "fs": target_fs or effective_fs,
    }
    Path(output).with_suffix(".build.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
