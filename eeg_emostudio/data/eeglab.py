"""EEGLAB ``.set/.fdt`` import and a reproducible raw-EEG preprocessing recipe.

The importer intentionally supports the common continuous EEGLAB layout:
``EEG.data`` embedded in the ``.set`` file, or a companion ``.fdt`` binary.
It does not depend on MNE, so a clean Windows/Python environment can run it.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import scipy.io as sio
from scipy import signal

from .features import aggregate_windows, compute_de_features
from .manifest import write_feature_dataset
from .preprocess import PreprocessConfig, epoch_by_events, preprocess_array, reject_by_amplitude


@dataclass
class EEGLABData:
    data: np.ndarray  # (channels, samples), µV
    fs: float
    channel_names: list[str]
    events: list[dict[str, Any]]
    source: str
    subject: str = ""
    setname: str = ""


def _field(obj: Any, name: str, default: Any = None) -> Any:
    try:
        value = getattr(obj, name)
        return default if value is None else value
    except Exception:
        return default


def _scalar(value: Any) -> Any:
    array = np.asarray(value).reshape(-1)
    return array[0] if array.size else None


def _channel_names(eeg: Any, n_channels: int) -> list[str]:
    labels: list[str] = []
    chanlocs = _field(eeg, "chanlocs")
    if chanlocs is not None:
        items = np.asarray(chanlocs).reshape(-1)
        for item in items:
            label = _field(item, "labels", "")
            labels.append(str(label).strip() or f"CH{len(labels) + 1}")
    while len(labels) < n_channels:
        labels.append(f"CH{len(labels) + 1}")
    return labels[:n_channels]


def _events(eeg: Any) -> list[dict[str, Any]]:
    raw_events = _field(eeg, "event")
    if raw_events is None:
        return []
    events: list[dict[str, Any]] = []
    for item in np.asarray(raw_events).reshape(-1):
        latency = _field(item, "latency")
        if latency is None:
            continue
        try:
            sample = int(round(float(_scalar(latency))))
        except (TypeError, ValueError):
            continue
        event_type = _scalar(_field(item, "type", ""))
        code = str(event_type).strip()
        if code.endswith(".0"):
            code = code[:-2]
        events.append({"latency": sample, "type": code})
    return events


def load_eeglab_set(path: str | Path) -> EEGLABData:
    source = Path(path)
    if source.suffix.lower() != ".set":
        raise ValueError("EEGLAB 导入需要 .set 文件")
    mat = sio.loadmat(source, struct_as_record=False, squeeze_me=True)
    eeg = mat.get("EEG")
    if eeg is None:
        raise ValueError("MAT 文件中没有 EEG 结构")
    if isinstance(eeg, np.ndarray):
        eeg = eeg.reshape(-1)[0]
    n_channels = int(_scalar(_field(eeg, "nbchan", 0)) or 0)
    pnts = int(_scalar(_field(eeg, "pnts", 0)) or 0)
    fs = float(_scalar(_field(eeg, "srate", 0)) or 0)
    data_field = _field(eeg, "data")
    if isinstance(data_field, str):
        fdt = source.parent / data_field
        if not fdt.exists():
            fdt = source.with_suffix(".fdt")
        if not fdt.exists():
            raise FileNotFoundError(f"EEGLAB 数据文件不存在：{data_field}")
        flat = np.fromfile(fdt, dtype="<f4")
        if n_channels <= 0 or pnts <= 0:
            raise ValueError("EEGLAB 元数据缺少 nbchan/pnts")
        if flat.size < n_channels * pnts:
            raise ValueError("FDT 数据长度与 nbchan×pnts 不一致")
        data = flat[: n_channels * pnts].reshape((n_channels, pnts), order="F")
    else:
        data = np.asarray(data_field, dtype=np.float64)
        if data.ndim == 3:
            raise ValueError("当前只支持连续 EEG；检测到 epoched 三维数据，请先在 EEGLAB 中导出连续数据")
        if data.ndim != 2:
            raise ValueError(f"EEG.data 形状应为 channels×samples，实际 {data.shape}")
        n_channels, pnts = data.shape
    data = np.asarray(data, dtype=np.float64)
    if data.shape[0] > data.shape[1]:
        raise ValueError("EEG.data 疑似为 samples×channels；EEGLAB 连续数据应为 channels×samples")
    if fs <= 0:
        raise ValueError("EEGLAB 采样率 srate 无效")
    if not np.isfinite(data).all():
        raise ValueError("EEG 数据包含 NaN/Inf")
    return EEGLABData(
        data=data,
        fs=fs,
        channel_names=_channel_names(eeg, n_channels),
        events=_events(eeg),
        source=str(source),
        subject=str(_scalar(_field(eeg, "subject", "")) or ""),
        setname=str(_scalar(_field(eeg, "setname", "")) or ""),
    )


def safe_extract_zip(zip_path: str | Path, output_dir: str | Path) -> Path:
    """Extract an EEGLAB set/fdt ZIP and return the first ``.set`` path."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            name = member.filename.replace("\\", "/")
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("ZIP 包含非法路径")
            destination = (target / name).resolve()
            if root not in destination.parents and destination != root:
                raise ValueError("ZIP 路径越界")
            archive.extract(member, target)
    sets = sorted(target.rglob("*.set"))
    if not sets:
        raise FileNotFoundError("ZIP 中没有 .set 文件")
    return sets[0]


def parse_event_map(value: str) -> dict[str, int]:
    """Parse ``1=0,2=1,3=2,4=3`` into a string-keyed mapping."""

    mapping: dict[str, int] = {}
    for part in (value or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError("事件映射格式应为 事件码=类别，例如 1=0,2=1")
        key, label = part.split("=", 1)
        key = key.strip()
        label = label.strip()
        if not key or not re.fullmatch(r"\d+", label):
            raise ValueError("事件映射类别必须是非负整数")
        mapping[key] = int(label)
    if not mapping:
        mapping = {"1": 0, "2": 1, "3": 2, "4": 3}
    return mapping


def _quality(data: np.ndarray, fs: float) -> dict[str, Any]:
    channel_std = np.std(data, axis=-1)
    flat = int(np.sum(channel_std < 1e-6))
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    return {
        "channels": int(data.shape[0]),
        "samples": int(data.shape[1]),
        "duration_s": round(data.shape[1] / fs, 2) if fs else 0,
        "flat_channels": flat,
        "peak_abs_uv": round(peak, 3),
        "std_uv": round(float(np.mean(channel_std)), 4),
    }


def _save_preview(before: np.ndarray, after: np.ndarray, fs_before: float, fs_after: float, path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        n = min(4, before.shape[0])
        seconds = min(20.0, before.shape[1] / fs_before, after.shape[1] / fs_after)
        n_before = max(2, int(seconds * fs_before))
        n_after = max(2, int(seconds * fs_after))
        t_before = np.arange(n_before) / fs_before
        t_after = np.arange(n_after) / fs_after
        fig, axes = plt.subplots(n, 1, figsize=(9, 1.7 * n), sharex=True)
        if n == 1:
            axes = [axes]
        for index, axis in enumerate(axes):
            axis.plot(t_before, before[index, :n_before], color="#93a8bb", linewidth=0.7, label="before")
            axis.plot(t_after, after[index, :n_after], color="#0c7368", linewidth=0.8, label="after")
            axis.set_ylabel(f"CH{index + 1}", fontsize=8)
            axis.tick_params(labelsize=7)
            axis.grid(alpha=0.15)
        axes[0].legend(loc="upper right", fontsize=7, frameon=False)
        axes[-1].set_xlabel("seconds", fontsize=8)
        fig.suptitle("Raw EEG · before / after filtering", fontsize=10)
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)
    except Exception:
        pass


def process_eeglab_set(
    set_path: str | Path,
    output_dir: str | Path,
    subject: str = "",
    bandpass: tuple[float, float] = (0.1, 70.0),
    notch_hz: float | None = 50.0,
    target_fs: float | None = 200.0,
    rereference: str = "car",
    epoch_start: float = -0.2,
    epoch_end: float = 4.0,
    reject_uv: float = 150.0,
    event_map_text: str = "1=0,2=1,3=2,4=3",
    window_s: float = 1.0,
    run_ica: bool = False,
) -> dict[str, Any]:
    """Clean one EEGLAB recording and optionally build training artifacts."""

    source = Path(set_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw = load_eeglab_set(source)
    event_map = parse_event_map(event_map_text)
    before_quality = _quality(raw.data, raw.fs)
    config = PreprocessConfig(
        fs=raw.fs,
        bandpass=bandpass,
        notch_hz=notch_hz,
        target_fs=target_fs,
        rereference=rereference,
    )
    clean = preprocess_array(raw.data, config)
    clean_fs = float(target_fs or raw.fs)
    after_quality = _quality(clean, clean_fs)
    after_quality["fs"] = clean_fs

    # Optional ICA is saved for inspection; it does not auto-delete components.
    ica_info = None
    if run_ica:
        try:
            from sklearn.decomposition import FastICA

            n_components = min(15, clean.shape[0], clean.shape[1])
            ica = FastICA(
                n_components=n_components,
                random_state=42,
                max_iter=600,
                whiten="unit-variance",
            )
            sources = ica.fit_transform(clean.T)
            np.savez_compressed(
                out / "ica_components.npz",
                mixing=ica.mixing_,
                unmixing=ica.components_,
                mean=ica.mean_,
                sources=sources.astype(np.float32),
            )
            ica_info = {
                "n_components": int(n_components),
                "explained_variance": round(float(np.mean(np.var(sources, axis=0))), 4),
                "note": "仅保存 ICA 分解，未自动剔除成分；请在 EEGLAB/审阅后人工判断。",
                "file": "ica_components.npz",
            }
        except Exception as exc:
            ica_info = {"error": str(exc), "note": "ICA 失败，但清洗数据已保存。"}

    np.savez_compressed(
        out / "eeg_clean.npz",
        data=clean.astype(np.float32),
        fs=float(clean_fs),
        channel_names=np.asarray(raw.channel_names),
        events=np.asarray([item["type"] for item in raw.events]),
        event_latencies=np.asarray([item["latency"] for item in raw.events], dtype=np.int64),
        source=str(source),
    )
    _save_preview(raw.data, clean, raw.fs, clean_fs, out / "eeg_preview.png")

    result: dict[str, Any] = {
        "source": str(source),
        "setname": raw.setname,
        "subject": subject or raw.subject or "unknown",
        "input_fs": raw.fs,
        "output_fs": clean_fs,
        "n_channels": int(raw.data.shape[0]),
        "duration_s": round(raw.data.shape[1] / raw.fs, 2),
        "n_events": len(raw.events),
        "event_types": sorted({item["type"] for item in raw.events}),
        "before": before_quality,
        "after": after_quality,
        "config": {
            "bandpass": list(bandpass),
            "notch_hz": notch_hz,
            "target_fs": target_fs,
            "rereference": rereference,
            "epoch": [epoch_start, epoch_end],
            "reject_uv": reject_uv,
            "event_map": event_map,
            "window_s": window_s,
        },
        "ica": ica_info,
        "files": {
            "clean": "eeg_clean.npz",
            "preview": "eeg_preview.png" if (out / "eeg_preview.png").exists() else "",
        },
        "training": None,
    }

    mapped_events: list[tuple[int, int]] = []
    for item in raw.events:
        label = event_map.get(item["type"])
        if label is None:
            continue
        sample = int(round(item["latency"] * clean_fs / raw.fs)) - 1
        if sample >= 0:
            mapped_events.append((sample, label))
    if mapped_events:
        events = [sample for sample, _ in mapped_events]
        labels = [label for _, label in mapped_events]
        epochs = epoch_by_events(clean, events, epoch_start, epoch_end, clean_fs)
        n_epochs_before = int(epochs.shape[0])
        if epochs.shape[0]:
            keep = reject_by_amplitude(epochs, reject_uv)
            epochs = epochs[keep]
            labels = [label for label, ok in zip(labels, keep) if ok]
        if epochs.shape[0]:
            n_classes = max(labels) + 1
            class_names = ["平静", "悲伤", "恐惧", "快乐"][:n_classes]
            raw_path = out / "raw.npz"
            np.savez_compressed(
                raw_path,
                x=epochs.astype(np.float32),
                y=np.asarray(labels, dtype=np.int64),
                subjects=np.asarray([subject or raw.subject or "unknown"] * len(labels)),
                fs=float(clean_fs),
                class_names=np.asarray(class_names),
                channel_names=np.asarray(raw.channel_names),
            )
            de, _ = compute_de_features(epochs, fs=clean_fs, window_s=window_s, step_s=window_s)
            features = aggregate_windows(de, method="mean")
            feature_path = out / "features.npz"
            write_feature_dataset(
                feature_path,
                features,
                np.asarray(labels, dtype=np.int64),
                [subject or raw.subject or "unknown"] * len(labels),
                class_names=class_names,
                feature_names=["delta", "theta", "alpha", "beta", "gamma"],
                metadata={
                    "source": "EEGLAB",
                    "set_file": str(source),
                    "fs": clean_fs,
                    "window_s": window_s,
                    "epoch": [epoch_start, epoch_end],
                    "reject_uv": reject_uv,
                    "event_map": event_map,
                    "channels": raw.channel_names,
                    "note": "由原始 EEG 清洗后按事件切分并提取 DE 特征。",
                },
            )
            result["training"] = {
                "raw": str(raw_path),
                "features": str(feature_path),
                "n_trials": int(epochs.shape[0]),
                "n_rejected": int(n_epochs_before - epochs.shape[0]),
                "class_counts": {str(index): int(np.sum(np.asarray(labels) == index)) for index in range(n_classes)},
            }
            result["files"]["raw"] = "raw.npz"
            result["files"]["features"] = "features.npz"
    (out / "eeg_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
