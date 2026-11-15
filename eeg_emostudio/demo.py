"""Synthetic-data demo used to verify the whole software pipeline.

The demo is deliberately labelled as synthetic everywhere it surfaces.  It
exists to test shapes, leakage checks, training, metrics and reporting before
real EEG arrives; it is not a scientific result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .data.manifest import write_feature_dataset
from .data.splits import loso_splits
from .reporting.figures import plot_confusion_matrix, plot_subject_accuracy
from .reporting.html import render_loso_report
from .training.trainer import TrainConfig, run_loso


def make_synthetic_features(
    n_subjects: int = 8,
    n_per_class: int = 30,
    n_channels: int = 8,
    n_bands: int = 5,
    n_classes: int = 4,
    seed: int = 42,
    subject_shift: float = 0.9,
    noise: float = 1.0,
) -> dict[str, Any]:
    """Generate class-separable features with a subject-specific distribution shift."""

    if n_subjects < 3:
        raise ValueError("LOSO 演示至少需要 3 名被试")
    rng = np.random.default_rng(seed)
    centers = rng.normal(0.0, 1.1, size=(n_channels, n_bands, n_classes))
    # Make the first two spatial patterns more distinct to avoid a degenerate
    # demo where all classes collapse.
    for cls in range(n_classes):
        centers[:, 0, cls] += cls * 0.45
    subject_offsets = rng.normal(0.0, subject_shift, size=(n_subjects, n_channels, n_bands))
    subject_gain = rng.uniform(0.85, 1.15, size=(n_subjects, 1, 1))

    features = []
    labels = []
    subjects = []
    for subject in range(n_subjects):
        for cls in range(n_classes):
            pattern = centers[..., cls] + subject_offsets[subject]
            samples = pattern[None, ...] + rng.normal(
                0.0, noise, size=(n_per_class, n_channels, n_bands)
            )
            samples *= subject_gain[subject]
            features.append(samples.astype(np.float32))
            labels.extend([cls] * n_per_class)
            subjects.extend([f"S{subject + 1:02d}"] * n_per_class)

    x = np.concatenate(features, axis=0)
    y = np.asarray(labels, dtype=np.int64)
    subjects_array = np.asarray(subjects)
    order = rng.permutation(len(y))
    return {
        "x": x[order],
        "y": y[order],
        "subjects": subjects_array[order],
        "class_names": [f"class_{index}" for index in range(n_classes)],
        "n_channels": n_channels,
        "n_bands": n_bands,
    }


def make_synthetic_raw(
    n_subjects: int = 3,
    n_per_class: int = 4,
    n_channels: int = 8,
    n_classes: int = 4,
    fs: int = 200,
    seconds: float = 6.0,
    seed: int = 7,
) -> dict[str, Any]:
    """Generate band-limited oscillatory EEG-like trials for pipeline tests."""

    rng = np.random.default_rng(seed)
    n_samples = int(fs * seconds)
    time = np.arange(n_samples) / fs
    frequencies = np.array([2.0, 6.0, 10.0, 20.0, 36.0])
    trials = []
    labels = []
    subjects = []
    for subject in range(n_subjects):
        gains = rng.uniform(0.6, 1.4, size=(n_channels, len(frequencies)))
        for cls in range(n_classes):
            for _ in range(n_per_class):
                signal = np.zeros((n_channels, n_samples), dtype=np.float64)
                for band_index, frequency in enumerate(frequencies):
                    amplitude = gains[:, band_index] * (1.0 + 0.25 * ((cls + band_index) % 4))
                    phase = rng.uniform(0, 2 * np.pi, size=(n_channels, 1))
                    signal += amplitude[:, None] * np.sin(
                        2 * np.pi * frequency * time[None, :] + phase
                    )
                signal += rng.normal(0.0, 0.35, size=signal.shape)
                trials.append(signal.astype(np.float32))
                labels.append(cls)
                subjects.append(f"S{subject + 1:02d}")
    x = np.stack(trials)
    order = rng.permutation(len(labels))
    return {
        "x": x[order],
        "y": np.asarray(labels, dtype=np.int64)[order],
        "subjects": np.asarray(subjects)[order],
        "fs": fs,
        "class_names": [f"class_{index}" for index in range(n_classes)],
    }


def run_demo(
    output_dir: str | Path,
    epochs: int = 40,
    model: str = "dualview",
    n_subjects: int = 8,
    n_per_class: int = 30,
    seed: int = 42,
) -> dict[str, Any]:
    """Generate synthetic features, run LOSO, and write a self-contained report."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    data = make_synthetic_features(
        n_subjects=n_subjects,
        n_per_class=n_per_class,
        seed=seed,
    )
    feature_path = write_feature_dataset(
        target / "features.npz",
        data["x"],
        data["y"],
        data["subjects"],
        class_names=data["class_names"],
        metadata={
            "source": "synthetic",
            "generator": "eeg_emostudio.demo.make_synthetic_features",
            "note": "仅用于软件流水线验证，不能作为科研结论。",
        },
    )
    folds = loso_splits(data["y"], data["subjects"], seed=seed)
    (target / "folds.json").write_text(
        json.dumps(
            [
                {
                    "fold": fold["fold"],
                    "test_subject": fold["test_subject"],
                    "n_train": fold["n_train"],
                    "n_val": fold["n_val"],
                    "n_test": fold["n_test"],
                }
                for fold in folds
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    config = TrainConfig(
        epochs=epochs,
        batch_size=32,
        lr=1e-3,
        patience=10,
        seed=seed,
        hidden=24,
        dropout=0.2,
        n_prototypes=2,
        proto_weight=0.05,
    )
    result = run_loso(
        data["x"],
        data["y"],
        data["subjects"],
        model_name=model,
        config=config,
        class_names=data["class_names"],
        output_dir=target,
    )
    matrix_path = plot_confusion_matrix(
        result["overall"]["confusion_matrix"],
        data["class_names"],
        target / "figures" / "confusion_matrix.png",
        title=f"Synthetic demo · {model} · LOSO",
    )
    subject_path = plot_subject_accuracy(
        result["per_subject"],
        target / "figures" / "per_subject_accuracy.png",
        chance=1.0 / len(data["class_names"]),
    )
    report_path = render_loso_report(
        result,
        target / "report.html",
        [matrix_path, subject_path],
        title="EEG-EmoStudio 合成数据流水线验证报告",
    )
    summary = {
        "demo": True,
        "feature_file": str(feature_path),
        "report": str(report_path),
        "overall_accuracy": result["overall"]["accuracy"],
        "overall_macro_f1": result["overall"]["macro_f1"],
        "note": "合成数据只用于验证软件流水线，不能作为 EEG 情绪识别科研结论。",
    }
    (target / "demo_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
