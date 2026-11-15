"""SEED-IV adapter: official precomputed DE/PSD features and raw trials.

Dataset reference
-----------------
SEED-IV (SJTU) contains 15 subjects × 3 sessions × 24 trials, 62-channel EEG.
Labels per session are distributed with the dataset (ReadMe.txt):

    session1 = [1,2,3,0,2,0,0,1,0,1,2,1,1,1,2,3,2,2,3,3,0,3,0,3]
    session2 = [2,1,3,0,0,2,0,2,3,3,2,3,2,0,1,1,2,1,0,3,0,1,3,1]
    session3 = [1,2,2,1,3,3,3,1,1,2,1,0,2,3,3,0,2,3,0,0,2,0,1,0]

0=neutral, 1=sad, 2=fear, 3=happy.

The files under ``eeg_feature_smooth`` have one variable per trial, e.g.
``de_LDS1`` with shape ``(62, T, 5)`` where T is the number of 4-second
windows.  This adapter turns each trial into ``T`` samples of shape
``(channels, bands)`` and attaches subject/session/trial identifiers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import numpy as np
import scipy.io as sio

from .manifest import write_feature_dataset

SEED_IV_ROOT = Path(__file__).resolve().parents[2] / "data" / "SEED_IV"

SESSION_LABELS: dict[int, list[int]] = {
    1: [1, 2, 3, 0, 2, 0, 0, 1, 0, 1, 2, 1, 1, 1, 2, 3, 2, 2, 3, 3, 0, 3, 0, 3],
    2: [2, 1, 3, 0, 0, 2, 0, 2, 3, 3, 2, 3, 2, 0, 1, 1, 2, 1, 0, 3, 0, 1, 3, 1],
    3: [1, 2, 2, 1, 3, 3, 3, 1, 1, 2, 1, 0, 2, 3, 3, 0, 2, 3, 0, 0, 2, 0, 1, 0],
}
CLASS_NAMES = ["neutral", "sad", "fear", "happy"]
CLASS_NAMES_ZH = ["平静", "悲伤", "恐惧", "快乐"]
CLASS_COLORS = ["#6B7C93", "#4C78A8", "#C45A5A", "#2E9B7A"]
FEATURE_KEYS = ("de_LDS", "de_movingAve", "psd_LDS", "psd_movingAve")
CHANNELS = [
    "FP1", "FPZ", "FP2", "AF3", "AF4", "F7", "F5", "F3", "F1", "FZ", "F2", "F4",
    "F6", "F8", "FT7", "FC5", "FC3", "FC1", "FCZ", "FC2", "FC4", "FC6", "FT8",
    "T7", "C5", "C3", "C1", "CZ", "C2", "C4", "C6", "T8", "TP7", "CP5", "CP3",
    "CP1", "CPZ", "CP2", "CP4", "CP6", "TP8", "P7", "P5", "P3", "P1", "PZ",
    "P2", "P4", "P6", "P8", "PO7", "PO5", "PO3", "POZ", "PO4", "PO6", "PO8",
    "CB1", "O1", "OZ", "O2", "CB2",
]
BANDS = ["delta", "theta", "alpha", "beta", "gamma"]


@dataclass
class SeedTrial:
    x: np.ndarray  # (T, 62, 5)
    label: int
    subject: str
    session: str
    trial: int
    source: str


def subject_file(root: Path, session: int, subject: int) -> Path:
    directory = root / "eeg_feature_smooth" / str(session)
    matches = sorted(directory.glob(f"{subject}_*.mat"))
    if not matches:
        raise FileNotFoundError(f"SEED-IV 找不到 s{session} subject {subject} 的特征文件")
    if len(matches) > 1:
        raise ValueError(f"SEED-IV s{session} subject {subject} 有多个特征文件：{matches}")
    return matches[0]


def _trial_array(mat: dict, feature_key: str, trial: int) -> np.ndarray:
    key = f"{feature_key}{trial}"
    if key not in mat:
        raise KeyError(f"MAT 文件缺少变量 {key}")
    array = np.asarray(mat[key], dtype=np.float32)
    if array.ndim != 3:
        raise ValueError(f"{key} 形状应为 (channels, windows, bands)，实际 {array.shape}")
    if array.shape[0] != 62 or array.shape[2] != 5:
        raise ValueError(f"{key} 期望 62 通道 × 5 频带，实际 {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{key} 含 NaN/Inf")
    return array


def iter_feature_trials(
    root: str | Path = SEED_IV_ROOT,
    feature_key: str = "de_LDS",
    sessions: Sequence[int] = (1, 2, 3),
    subjects: Sequence[int] | None = None,
) -> Iterator[SeedTrial]:
    root = Path(root)
    if feature_key not in FEATURE_KEYS:
        raise ValueError(f"feature_key 必须为 {FEATURE_KEYS}")
    subject_ids = list(subjects) if subjects is not None else list(range(1, 16))
    for session in sessions:
        if session not in SESSION_LABELS:
            raise ValueError(f"未知 session {session}")
        labels = SESSION_LABELS[session]
        for subject in subject_ids:
            path = subject_file(root, session, subject)
            mat = sio.loadmat(path, struct_as_record=False, squeeze_me=True)
            for trial in range(1, 25):
                array = _trial_array(mat, feature_key, trial)
                # (channels, windows, bands) -> (windows, channels, bands)
                yield SeedTrial(
                    x=np.ascontiguousarray(array.transpose(1, 0, 2)),
                    label=int(labels[trial - 1]),
                    subject=f"S{subject:02d}",
                    session=f"session{session}",
                    trial=trial,
                    source=str(path),
                )


def audit_seed_iv(
    root: str | Path = SEED_IV_ROOT,
    feature_key: str = "de_LDS",
    sessions: Sequence[int] = (1, 2, 3),
    subjects: Sequence[int] | None = None,
) -> dict:
    """Inspect every feature trial without retaining arrays."""

    root = Path(root)
    wanted_subjects = set(subjects) if subjects is not None else None
    subjects_found: set[int] = set()
    session_files: dict[str, int] = {}
    class_counts = {name: 0 for name in CLASS_NAMES}
    shapes: list[tuple[int, int]] = []
    total_windows = 0
    per_subject: dict[str, int] = {}
    for session in sessions:
        files = sorted((root / "eeg_feature_smooth" / str(session)).glob("*.mat"))
        included = 0
        session_files[f"session{session}"] = 0
        for path in files:
            subject = int(path.name.split("_")[0])
            if wanted_subjects is not None and subject not in wanted_subjects:
                continue
            subjects_found.add(subject)
            included += 1
            mat = sio.loadmat(path, struct_as_record=False, squeeze_me=True)
            per_subject[f"S{subject:02d}"] = per_subject.get(f"S{subject:02d}", 0) + 24
            for trial in range(1, 25):
                array = _trial_array(mat, feature_key, trial)
                shapes.append((array.shape[0], array.shape[1]))
                total_windows += array.shape[1]
                class_counts[CLASS_NAMES[SESSION_LABELS[session][trial - 1]]] += 1
        session_files[f"session{session}"] = included
    channels = sorted({shape[0] for shape in shapes})
    windows = sorted({shape[1] for shape in shapes})
    return {
        "dataset": "SEED-IV",
        "root": str(root),
        "feature_key": feature_key,
        "subjects": [f"S{subject:02d}" for subject in sorted(subjects_found)],
        "n_subjects": len(subjects_found),
        "sessions": {key: value for key, value in session_files.items()},
        "n_sessions": len(session_files),
        "n_trials": int(sum(per_subject.values())),
        "n_windows": int(total_windows),
        "channels": channels,
        "n_channels": channels[0] if len(channels) == 1 else None,
        "bands": BANDS,
        "n_bands": 5,
        "window_range": [min(windows), max(windows)] if windows else [0, 0],
        "class_names": CLASS_NAMES,
        "class_names_zh": CLASS_NAMES_ZH,
        "class_counts_trials": class_counts,
        "per_subject_trials": per_subject,
        "subject_files_complete": all(
            len(list((root / "eeg_feature_smooth" / str(session)).glob(f"{subject}_*.mat"))) == 1
            for session in sessions
            for subject in subjects_found
        ),
        "units": "SEED-IV official DE/PSD features; 4-second windows; 5 bands",
    }


def build_seed_iv(
    root: str | Path = SEED_IV_ROOT,
    output: str | Path = "data/processed/seed_iv_de_LDS.npz",
    feature_key: str = "de_LDS",
    sessions: Sequence[int] = (1, 2, 3),
    subjects: Sequence[int] | None = None,
    aggregate: str = "window",
) -> dict:
    """Build a model-ready feature dataset from official SEED-IV features."""

    root = Path(root)
    output = Path(output)
    if aggregate not in {"window", "trial"}:
        raise ValueError("aggregate 必须为 window 或 trial")
    pieces: list[np.ndarray] = []
    labels: list[int] = []
    subject_ids: list[str] = []
    session_ids: list[str] = []
    trial_ids: list[str] = []
    sources: dict[str, str] = {}
    for trial in iter_feature_trials(root, feature_key=feature_key, sessions=sessions, subjects=subjects):
        trial_id = f"{trial.subject}_{trial.session}_T{trial.trial:02d}"
        if aggregate == "trial":
            pieces.append(trial.x.mean(axis=0, keepdims=True))
            count = 1
        else:
            pieces.append(trial.x)
            count = trial.x.shape[0]
        labels.extend([trial.label] * count)
        subject_ids.extend([trial.subject] * count)
        session_ids.extend([trial.session] * count)
        trial_ids.extend([trial_id] * count)
        sources[trial_id] = Path(trial.source).name
    if not pieces:
        raise ValueError("没有可构建的 SEED-IV trial")
    x = np.concatenate(pieces, axis=0)
    y = np.asarray(labels, dtype=np.int64)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_feature_dataset(
        output,
        x,
        y,
        subject_ids,
        sessions=session_ids,
        class_names=CLASS_NAMES_ZH,
        feature_names=BANDS,
        trial_ids=trial_ids,
        metadata={
            "source": "SEED-IV",
            "root": str(root),
            "feature_key": feature_key,
            "window_seconds": 4,
            "sessions": list(sessions),
            "subjects": sorted(set(subject_ids)),
            "n_trials": len(sources),
            "aggregation": "mean_over_windows" if aggregate == "trial" else "window",
            "classes": {"0": "neutral/平静", "1": "sad/悲伤", "2": "fear/恐惧", "3": "happy/快乐"},
            "channels": CHANNELS,
            "license": "SEED-IV data agreement; do not redistribute raw data",
            "note": "Official de_LDS/de_movingAve features; 62 channels × 5 bands; T windows per trial.",
        },
    )
    summary = audit_seed_iv(root, feature_key=feature_key, sessions=sessions, subjects=subjects)
    summary["aggregation"] = "mean_over_windows" if aggregate == "trial" else "window"
    summary["output"] = str(output)
    summary["n_samples"] = int(len(y))
    summary["n_features"] = int(x.shape[2])
    summary["class_counts_windows"] = {
        CLASS_NAMES[index]: int((y == index).sum()) for index in range(4)
    }
    manifest_path = output.with_suffix(".manifest.json")
    summary["manifest"] = str(manifest_path)
    output.with_suffix(".seed_iv_audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
