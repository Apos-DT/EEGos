"""Read-only domain services used by the pages and JSON API.

The web console does not invent a second data model.  It reads the same
artefacts that the CLI produces (JSON/CSV/NPZ) and presents them.  Write
operations are limited to explicit jobs in :mod:`webapp.tasks`.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from typing import Any, Iterable

import numpy as np

from eeg_emostudio.data.manifest import load_features, write_feature_dataset

from .config import (
    ARTIFACTS,
    AUDIT_DIR,
    AUDIT_PROBE_DIR,
    AUDIO_DIR,
    DATA_DIR,
    DELIVERABLES_DIR,
    EXPERIMENTS_DIR,
    OUTPUT_DIR,
    PROCESSED_DIR,
    QUALITY,
    RAW_DIR,
    ROOT,
    SELECTION_DIR,
    UPLOAD_DIR,
    VIDEO_DIR,
    WEB_JOBS_DIR,
    cache_by,
    cache_stats,
)
from .content import APP_VERSION, DOCS, MODELS
from .record_store import managed
from . import record_store


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError:
        return []


def _number(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    number = _number(value)
    return int(number) if number is not None else default


def _clean(value: Any) -> Any:
    """Convert numpy/pandas scalars and non-finite floats to JSON-safe values."""

    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, np.ndarray):
        return [_clean(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return value


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _id_for(path: Path) -> str:
    return hashlib.sha1(_rel(path).encode("utf-8")).hexdigest()[:12]


def _mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return ""


def _size_mb(path: Path) -> float:
    try:
        return round(path.stat().st_size / 1024 / 1024, 2)
    except OSError:
        return 0.0


def _decode_names(array: np.ndarray) -> list[str]:
    return [str(item) for item in np.asarray(array).tolist()]


def _count_eeg_files() -> int:
    """Count raw EEG recordings without counting feature MAT files."""

    count = 0
    seed_raw = DATA_DIR / "SEED_IV" / "eeg_raw_data"
    if seed_raw.exists():
        count += sum(1 for path in seed_raw.rglob("*.mat") if path.is_file())
    if RAW_DIR.exists():
        count += sum(
            1
            for path in RAW_DIR.rglob("*")
            if path.suffix.lower() in {".edf", ".bdf", ".cnt", ".vhdr", ".eeg", ".mat", ".npz"}
        )
    return count


# ---------------------------------------------------------------------------
# Audit / quality / selection
# ---------------------------------------------------------------------------


@cache_by("audit_summary", lambda: AUDIT_DIR)
def audit_summary() -> dict[str, Any]:
    return _read_json(AUDIT_DIR / "audit_summary.json", {}) or {}


@cache_by("quality_rows", lambda: AUDIT_DIR)
def _quality_rows() -> list[dict[str, Any]]:
    rows = _read_csv(AUDIT_DIR / "quality_combined.csv")
    if rows:
        for row in rows:
            row["quality_score"] = _number(row.get("quality_score"))
            row["rank"] = _int(row.get("rank"))
            row["n_raters"] = _int(row.get("n_raters"))
            row["problem_rate"] = _number(row.get("problem_rate")) or 0.0
        return rows
    combined: list[dict[str, Any]] = []
    for kind, path in QUALITY.items():
        for row in _read_csv(path):
            combined.append(
                {
                    "modality": kind,
                    "stimulus_id": row.get("视频编号") or row.get("音乐歌曲编号") or row.get("编号", ""),
                    "quality_score": _number(row.get("质量总分")),
                    "grade": row.get("质量等级", ""),
                    "category": row.get("情感类别(四象限)", ""),
                    "rank": _int(row.get("排名")),
                    "n_raters": _int(row.get("有效评分人数")),
                    "problem_rate": _number(row.get("问题报告率")) or 0.0,
                    "main_issue": row.get("主要问题", ""),
                    "discrete_label": row.get("离散标签", ""),
                }
            )
    return combined


def _grade_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {grade: 0 for grade in "SABCD"}
    for row in rows:
        grade = str(row.get("grade", "")).upper()
        if grade in counts:
            counts[grade] += 1
    return counts


def _category_summary(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        key = (str(row.get("modality", "")), str(row.get("category", "")))
        score = row.get("quality_score")
        if score is not None:
            grouped.setdefault(key, []).append(float(score))
    result = []
    modality_order = {"video": 0, "audio": 1}
    for (modality, category), scores in sorted(
        grouped.items(), key=lambda item: (modality_order.get(item[0][0], 9), item[0][0], item[0][1])
    ):
        result.append(
            {
                "modality": modality,
                "category": category,
                "n": len(scores),
                "mean": round(sum(scores) / len(scores), 1),
                "min": round(min(scores), 1),
                "max": round(max(scores), 1),
            }
        )
    return result


@cache_by("issue_rows", lambda: AUDIT_DIR)
def _issue_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for kind, label in (("video", "视频"), ("audio", "音乐")):
        for row in _read_csv(AUDIT_DIR / f"{kind}_playback_issues.csv"):
            row["modality"] = label
            row["issue_severity"] = _number(row.get("issue_severity")) or 0.0
            for key in ("valence", "arousal", "row_id"):
                row[key] = _number(row.get(key), 0.0)
            rows.append(row)
    return rows


def audit_payload() -> dict[str, Any]:
    summary = audit_summary()
    quality = _quality_rows()
    issues = _issue_rows()
    video_raters = _read_csv(AUDIT_DIR / "video_rater_table.csv")
    audio_raters = _read_csv(AUDIT_DIR / "audio_rater_table.csv")
    for row in video_raters:
        row["modality"] = "视频"
    for row in audio_raters:
        row["modality"] = "音乐"
    for row in video_raters + audio_raters:
        row["n_ratings"] = _int(row.get("n_ratings"))
        for key in ("valence_mean", "arousal_mean", "valence_sd", "arousal_sd", "median_duration_s"):
            row[key] = _number(row.get(key), 0.0)
        row["straightline_suspect"] = str(row.get("straightline_suspect", "")).lower() == "true"
    downloads = [
        {"name": "audit_summary.json", "label": "审计摘要 JSON", "kind": "json"},
        {"name": "audit_report.md", "label": "审计报告 Markdown", "kind": "md"},
        {"name": "video_ratings_clean.csv", "label": "视频清洗评分", "kind": "csv"},
        {"name": "audio_ratings_clean.csv", "label": "音乐清洗评分", "kind": "csv"},
        {"name": "video_playback_issues.csv", "label": "视频问题清单", "kind": "csv"},
        {"name": "audio_playback_issues.csv", "label": "音乐问题清单", "kind": "csv"},
        {"name": "quality_combined.csv", "label": "240 条质量合并表", "kind": "csv"},
    ]
    available = bool(summary)
    return {
        "available": available,
        "summary": summary,
        "quality": _clean(quality),
        "issues": _clean(issues),
        "raters": _clean(video_raters + audio_raters),
        "grade_counts": _grade_counts(quality),
        "category_summary": _category_summary(quality),
        "problem_stimuli": len({row.get("stimulus_id") for row in issues if row.get("stimulus_id")}),
        "downloads": [item for item in downloads if (AUDIT_DIR / item["name"]).exists()],
        "generated_at": summary.get("generated_at", ""),
    }


@cache_by("selection_payload", lambda: SELECTION_DIR)
def selection_payload() -> dict[str, Any]:
    summary = _read_json(SELECTION_DIR / "selection_summary.json", {}) or {}
    rows = _read_csv(SELECTION_DIR / "selected_materials.csv")
    for row in rows:
        row["quality_score"] = _number(row.get("quality_score"))
        row["selection_rank"] = _int(row.get("selection_rank"))
        row["category_rank"] = _int(row.get("category_rank"))
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = f"{row.get('modality', '')}/{row.get('category', '')}"
        group = groups.setdefault(key, {"key": key, "n": 0, "scores": [], "grades": []})
        group["n"] += 1
        if row["quality_score"] is not None:
            group["scores"].append(row["quality_score"])
        group["grades"].append(row.get("grade", ""))
    group_rows = []
    for key, group in sorted(groups.items()):
        scores = group.pop("scores")
        group["mean"] = round(sum(scores) / len(scores), 1) if scores else None
        group["min_grade"] = max(group["grades"], key=lambda grade: "SABCD".find(grade) if grade in "SABCD" else 9)
        group["grade_text"] = " ".join(sorted(set(group["grades"])))
        group_rows.append(group)
    grade_counts = _grade_counts(rows)
    return {
        "available": bool(rows),
        "summary": summary,
        "rows": _clean(rows),
        "groups": group_rows,
        "grade_counts": grade_counts,
        "total": len(rows),
        "downloads": [
            {"name": "selected_materials.csv", "label": "80 条选材 CSV"},
            {"name": "selection_summary.json", "label": "选材摘要 JSON"},
            {"name": "selection_report.md", "label": "选材报告 Markdown"},
        ] if (SELECTION_DIR / "selected_materials.csv").exists() else [],
    }


@cache_by(
    "stimuli_payload",
    lambda: SELECTION_DIR,
    lambda: VIDEO_DIR,
    lambda: AUDIO_DIR,
)
def stimuli_payload() -> dict[str, Any]:
    """Lean stimulus library: selected materials plus local-file availability."""

    data = selection_payload()
    rows = data["rows"]
    for row in rows:
        modality = str(row.get("modality", ""))
        directory = VIDEO_DIR if modality == "video" else AUDIO_DIR
        path = directory / str(row.get("stimulus_id", ""))
        row["available"] = path.exists()
        row["preview_url"] = (
            f"/stimuli/preview/{modality}/{quote(str(row.get('stimulus_id', '')))}"
            if path.exists()
            else ""
        )
    data["rows"] = rows
    data["video_count"] = sum(1 for row in rows if row.get("modality") == "video")
    data["audio_count"] = sum(1 for row in rows if row.get("modality") == "audio")
    data["available_count"] = sum(1 for row in rows if row.get("available"))
    return data


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


def _manifest_for(npz_path: Path) -> dict[str, Any]:
    candidate = npz_path.with_suffix(".manifest.json")
    if candidate.exists():
        return _read_json(candidate, {}) or {}
    if npz_path.name == "features.npz":
        candidate = npz_path.with_name("features.manifest.json")
        if candidate.exists():
            return _read_json(candidate, {}) or {}
    return {}


def _inspect_feature_npz(path: Path) -> dict[str, Any] | None:
    try:
        with np.load(path, allow_pickle=False) as data:
            if not {"x", "y", "subjects"}.issubset(data.files):
                return None
            x = np.asarray(data["x"])
            y = np.asarray(data["y"]).astype(int)
            subjects = [str(item) for item in np.asarray(data["subjects"]).tolist()]
            classes = _decode_names(data["class_names"]) if "class_names" in data.files else [str(i) for i in sorted(set(y.tolist()))]
    except (OSError, ValueError):
        return None
    manifest = _manifest_for(path)
    extra = manifest.get("extra", {}) if isinstance(manifest, dict) else {}
    kind = "demo" if "demo" in path.parts else "processed"
    source = extra.get("source") or ("合成示例" if kind == "demo" else "自定义")
    return {
        "id": _id_for(path),
        "name": path.stem.replace("_", " "),
        "file": path.name,
        "path": _rel(path),
        "kind": kind,
        "n_samples": int(x.shape[0]) if x.ndim else 0,
        "n_channels": int(x.shape[1]) if x.ndim > 1 else 0,
        "n_features": int(x.shape[2]) if x.ndim > 2 else 0,
        "n_subjects": len(set(subjects)),
        "n_classes": len(set(y.tolist())),
        "class_names": classes,
        "subjects": sorted(set(subjects)),
        "size_mb": _size_mb(path),
        "created_at": _mtime(path),
        "sha256": manifest.get("sha256", ""),
        "has_manifest": bool(manifest),
        "source": source,
        "n_trials": extra.get("n_trials"),
        "window_seconds": extra.get("window_seconds"),
        "manifest_path": _rel(path.with_suffix(".manifest.json")) if path.with_suffix(".manifest.json").exists() else "",
    }


@managed("features")
@cache_by(
    "feature_datasets",
    lambda: PROCESSED_DIR,
    lambda: ARTIFACTS / "demo",
    lambda: EXPERIMENTS_DIR,
    lambda: OUTPUT_DIR,
)
def list_feature_datasets() -> list[dict[str, Any]]:
    candidates: list[Path] = []
    for directory in (PROCESSED_DIR, ARTIFACTS / "demo"):
        if directory.exists():
            candidates.extend(directory.glob("*.npz"))
    candidates.extend((ARTIFACTS / "experiments").glob("*/features.npz"))
    candidates.extend(OUTPUT_DIR.glob("*/features.npz"))
    seen: set[Path] = set()
    result: list[dict[str, Any]] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen or path.name == "raw.npz":
            continue
        seen.add(resolved)
        info = _inspect_feature_npz(path)
        if info:
            result.append(info)
    result.sort(key=lambda item: (item["kind"] != "demo", item["created_at"]), reverse=True)
    return result


def _inspect_raw_npz(path: Path) -> dict[str, Any] | None:
    try:
        with np.load(path, allow_pickle=False) as data:
            if not {"x", "y", "subjects"}.issubset(data.files):
                return None
            shape = tuple(int(value) for value in np.asarray(data["x"]).shape)
            fs = float(np.asarray(data["fs"]).reshape(-1)[0]) if "fs" in data.files else None
            y = np.asarray(data["y"]).astype(int)
            subjects = [str(item) for item in np.asarray(data["subjects"]).tolist()]
    except (OSError, ValueError, TypeError):
        return None
    kind = "demo" if ("demo" in path.parts or "raw_demo" in path.parts) else "upload"
    return {
        "id": _id_for(path),
        "name": path.stem.replace("_", " "),
        "file": path.name,
        "path": _rel(path),
        "kind": kind,
        "n_trials": shape[0] if len(shape) > 0 else 0,
        "n_channels": shape[1] if len(shape) > 1 else 0,
        "n_samples": shape[2] if len(shape) > 2 else 0,
        "fs": fs,
        "n_subjects": len(set(subjects)),
        "n_classes": len(set(y.tolist())),
        "size_mb": _size_mb(path),
        "created_at": _mtime(path),
    }


@managed("raw_data")
@cache_by(
    "raw_datasets",
    lambda: RAW_DIR,
    lambda: UPLOAD_DIR,
    lambda: ARTIFACTS / "raw_demo",
    lambda: OUTPUT_DIR,
)
def list_raw_datasets() -> list[dict[str, Any]]:
    candidates: list[Path] = []
    for directory in (RAW_DIR, UPLOAD_DIR, ARTIFACTS / "raw_demo"):
        if directory.exists():
            candidates.extend(directory.glob("*.npz"))
    candidates.extend(OUTPUT_DIR.glob("*/raw.npz"))
    result = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen or path.name.startswith("features"):
            continue
        seen.add(resolved)
        info = _inspect_raw_npz(path)
        if info:
            result.append(info)
    result.sort(key=lambda item: item["created_at"], reverse=True)
    return result


def resolve_dataset(dataset_id: str) -> Path | None:
    for item in list_feature_datasets():
        if item["id"] == dataset_id:
            return ROOT / item["path"]
    return None


def resolve_raw(raw_id: str) -> Path | None:
    for item in list_raw_datasets():
        if item["id"] == raw_id:
            return ROOT / item["path"]
    return None


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


def _experiment_dirs() -> list[Path]:
    dirs = []
    if (ARTIFACTS / "demo").exists():
        dirs.append(ARTIFACTS / "demo")
    if EXPERIMENTS_DIR.exists():
        dirs.extend(path for path in EXPERIMENTS_DIR.iterdir() if path.is_dir())
    return dirs


def _experiment_info(path: Path) -> dict[str, Any] | None:
    metrics = _read_json(path / "metrics.json", {})
    if not metrics:
        return None
    overall = metrics.get("overall", {}) or {}
    if "accuracy" not in overall:
        return None
    run_id = "demo" if path.name == "demo" else path.name
    run_meta = _read_json(path / "run_meta.json", {})
    is_demo = run_id == "demo" or bool(run_meta.get("is_demo"))
    report = path / "report.html"
    confusion = path / "figures" / "confusion_matrix.png"
    per_subject = path / "figures" / "per_subject_accuracy.png"
    raw_setting = str(metrics.get("setting", ""))
    if raw_setting in {"loso", "leave-one-subject-out"}:
        setting, setting_label = "loso", "LOSO"
    elif raw_setting == "cross-session":
        setting, setting_label = "cross-session", "跨 Session"
    else:
        setting, setting_label = "subject-dependent", "被试依赖"
    return {
        "id": run_id,
        "label": "合成演示 · 软件验收" if is_demo else run_id,
        "path": _rel(path),
        "model": metrics.get("model", ""),
        "setting": setting,
        "setting_raw": raw_setting,
        "setting_label": setting_label,
        "n_samples": metrics.get("n_samples", 0),
        "n_subjects": metrics.get("n_subjects", 0),
        "n_classes": metrics.get("n_classes", 0),
        "accuracy": _number(overall.get("accuracy"), 0.0),
        "balanced_accuracy": _number(overall.get("balanced_accuracy"), 0.0),
        "macro_f1": _number(overall.get("macro_f1"), 0.0),
        "cohen_kappa": _number(overall.get("cohen_kappa"), 0.0),
        "accuracy_ci95": overall.get("accuracy_ci95", [None, None]),
        "folds": len(metrics.get("folds", []) or []),
        "created_at": _mtime(path / "metrics.json"),
        "has_report": report.exists(),
        "report_url": f"/api/experiments/{run_id}/report" if report.exists() else "",
        "confusion_url": f"/api/experiments/{run_id}/figure/confusion_matrix.png" if confusion.exists() else "",
        "per_subject_url": f"/api/experiments/{run_id}/figure/per_subject_accuracy.png" if per_subject.exists() else "",
        "is_demo": is_demo,
    }


def _experiment_cache_targets() -> list[Path]:
    # Runs are created before training finishes. Watching only the parent
    # directory misses metrics/report writes inside an existing run directory.
    files = ("metrics.json", "run_meta.json", "report.html",
             "figures/confusion_matrix.png", "figures/per_subject_accuracy.png")
    return [EXPERIMENTS_DIR, *(
        directory / name for directory in _experiment_dirs() for name in files
    )]


@managed("experiments", title_key="label")
@cache_by("experiments", _experiment_cache_targets)
def list_experiments() -> list[dict[str, Any]]:
    experiments = []
    for path in _experiment_dirs():
        info = _experiment_info(path)
        if info:
            experiments.append(info)
    experiments.sort(key=lambda item: item["created_at"], reverse=True)
    return experiments


def resolve_experiment(run_id: str) -> Path | None:
    if run_id == "demo":
        path = ARTIFACTS / "demo"
        return path if path.exists() else None
    if EXPERIMENTS_DIR.exists():
        candidate = EXPERIMENTS_DIR / run_id
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Documents / overview / system
# ---------------------------------------------------------------------------


@managed("documents", id_key="no", title_key="title")
@cache_by("docs", lambda: DELIVERABLES_DIR, lambda: record_store.STORE_DIR / "state.json")
def list_docs() -> list[dict[str, Any]]:
    result = []
    for doc in DOCS:
        docx = DELIVERABLES_DIR / doc["docx"]
        pdf = DELIVERABLES_DIR / "pdf" / doc["pdf"]
        if not docx.exists() and not pdf.exists():
            continue
        result.append(
            {
                **doc,
                "docx_exists": docx.exists(),
                "pdf_exists": pdf.exists(),
                "docx_size": _size_mb(docx),
                "pdf_size": _size_mb(pdf),
                "docx_url": f"/files/docx/{doc['no']}" if docx.exists() else "",
                "pdf_url": f"/files/pdf/{doc['no']}" if pdf.exists() else "",
            }
        )
    from .record_store import snapshot
    result.extend(snapshot().get("uploads", {}).get("documents", {}).values())
    return result


def resolve_doc(no: str, extension: str) -> Path | None:
    for doc in DOCS:
        if doc["no"] != no:
            continue
        if extension == "docx":
            path = DELIVERABLES_DIR / doc["docx"]
        elif extension == "pdf":
            path = DELIVERABLES_DIR / "pdf" / doc["pdf"]
        else:
            return None
        return path if path.exists() else None
    return None


def overview() -> dict[str, Any]:
    audit = audit_summary()
    quality = _quality_rows()
    selection = selection_payload()
    datasets = list_feature_datasets()
    raws = list_raw_datasets()
    experiments = list_experiments()
    from .experiment import summary as experiment_summary

    experiment = experiment_summary()
    # 新版自定义量表答卷落在统一 JSONL 仓库，不写入 session.responses；
    # 工作台统计需把两个口径相加，否则新问卷提交后计数仍为 0。
    try:
        from . import survey_meta  # 延迟导入，避免 survey_meta -> services 循环

        stored = survey_meta.total_responses()
        experiment["stored_responses"] = stored
        experiment["legacy_responses"] = experiment["responses"]
        experiment["responses"] = experiment["responses"] + stored
    except Exception:
        pass
    drill = _read_json(AUDIT_PROBE_DIR / "audit_summary.json", {}) or {}
    surveys = audit.get("surveys", {}) if audit else {}
    video = surveys.get("video", {})
    audio = surveys.get("audio", {})
    raw_total = sum(_int(item.get("raw_rows")) for item in surveys.values())
    dedup_total = sum(_int(item.get("dedup_rows")) for item in surveys.values())
    video_count = sum(1 for row in quality if row.get("modality") == "video")
    audio_count = sum(1 for row in quality if row.get("modality") == "audio")
    eeg_files = _count_eeg_files()
    quality_by_modality = {
        "video": _grade_counts(row for row in quality if row.get("modality") == "video"),
        "audio": _grade_counts(row for row in quality if row.get("modality") == "audio"),
    }
    alerts = []
    if not raw_total:
        alerts.append({"severity": "danger", "title": "原始数据未接入", "detail": "工作区没有原始 EEG，真实性能结论仍为空。"})
    if quality:
        alerts.append(
            {
                "severity": "warning",
                "title": "音乐片段长度不一致",
                "detail": "26/120 条标注片段偏离 60±15 s，正式实验前需统一截取规则。",
            }
        )
        problem_count = len({row.get("stimulus_id") for row in _issue_rows()})
        alerts.append(
            {
                "severity": "warning",
                "title": f"{problem_count} 条刺激存在播放问题",
                "detail": "视频 22 条、音乐 29 条；已记录严重度，建议抽检/替换。",
            }
        )
        alerts.append(
            {
                "severity": "info",
                "title": "材料表标签口径待统一",
                "detail": "素材表 116 条连续标签缺失；映射表应作为四象限权威。",
            }
        )
    if not selection["available"]:
        alerts.append({"severity": "info", "title": "尚未生成选材清单", "detail": "运行选材后，正式实验材料会出现在这里。"})
    real_experiments = [item for item in experiments if not item.get("is_demo")]
    best_experiment = max(real_experiments or experiments, key=lambda item: item.get("accuracy") or 0.0, default=None)
    if not experiments:
        alerts.append({"severity": "info", "title": "尚无训练实验", "detail": "可先用合成数据验证流水线，再接入真实 EEG。"})
    if not experiment["sessions"]:
        alerts.append({"severity": "info", "title": "尚无问卷会话", "detail": "到“问卷管理”新建问卷，并把分享链接发给被试。"})
    pipeline = [
        {"key": "experiment", "label": "问卷采集", "status": "done" if experiment["sessions"] else "idle", "detail": f"{experiment['sessions']} 个会话" if experiment["sessions"] else "待开始"},
        {"key": "responses", "label": "答卷管理", "status": "done" if experiment["responses"] else "idle", "detail": f"{experiment['responses']} 份答卷" if experiment["responses"] else "待采集"},
        {"key": "eeg", "label": "EEG 清洗", "status": "done" if eeg_files else "idle", "detail": f"{eeg_files} 个原始文件" if eeg_files else "待导入"},
        {"key": "features", "label": "特征构建", "status": "done" if datasets else "idle", "detail": f"{len(datasets)} 个特征集" if datasets else "待上传"},
        {"key": "training", "label": "模型训练", "status": "done" if experiments else "idle", "detail": f"{len(experiments)} 次实验" if experiments else "待运行"},
    ]
    return {
        "app": {"name": "EEG-EmoStudio", "version": APP_VERSION},
        "stats": {
            "stimuli": len(quality) or 240,
            "video": video_count or 120,
            "audio": audio_count or 120,
            "surveys_raw": raw_total,
            "surveys_dedup": dedup_total,
            "selected": selection["total"],
            "selected_grades": selection["grade_counts"],
            "experiments": len(experiments),
            "datasets": len(datasets),
            "raws": len(raws),
            "sessions": experiment["sessions"],
            "responses": experiment["responses"],
            "participants": experiment["participants"],
            "tests": 58,
        },
        "quality_grades": _grade_counts(quality),
        "quality_by_modality": quality_by_modality,
        "quality_by_category": _category_summary(quality),
        "pipeline": pipeline,
        "alerts": alerts,
        "experiment": experiment,
        "best_experiment": best_experiment,
        "recent_experiments": experiments[:5],
        "experiments": experiments,
        "datasets": datasets,
        "raws": raws,
        "selection": {key: selection[key] for key in ("available", "total", "grade_counts", "groups")},
        "audit": {
            "available": bool(audit),
            "generated_at": audit.get("generated_at", ""),
            "video": video,
            "audio": audio,
            "problem_stimuli": len({row.get("stimulus_id") for row in _issue_rows()}),
        },
        "eeg": {"files": eeg_files, "detected": drill.get("generated_at", "")},
        "system": system_info(),
    }


def system_info() -> dict[str, Any]:
    audit = audit_summary()
    selection = _read_json(SELECTION_DIR / "selection_summary.json", {})
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "app_version": APP_VERSION,
        "cwd": str(ROOT),
        "audit_available": bool(audit),
        "audit_generated_at": audit.get("generated_at", ""),
        "selection_available": bool(selection),
        "datasets": len(list_feature_datasets()),
        "raws": len(list_raw_datasets()),
        "experiments": len(list_experiments()),
        "docs": len(list_docs()),
        "eeg_files": _count_eeg_files(),
        "cache": cache_stats(),
    }


def models() -> list[dict[str, Any]]:
    return MODELS


def merge_feature_datasets(dataset_ids: list[str]) -> dict[str, Any]:
    """Merge selected feature sets (e.g. one per EEG subject) for LOSO."""

    if len(dataset_ids) < 2:
        raise ValueError("至少选择两个特征集")
    paths: list[Path] = []
    for dataset_id in dataset_ids:
        path = resolve_dataset(dataset_id)
        if not path:
            raise ValueError(f"数据集不存在：{dataset_id}")
        paths.append(path)
    loaded = [load_features(path) for path in paths]
    first = loaded[0]
    shape = tuple(first["x"].shape[1:])
    class_names = list(first["class_names"]) if first["class_names"] is not None else None
    for item in loaded[1:]:
        if tuple(item["x"].shape[1:]) != shape:
            raise ValueError("特征形状不一致，不能合并")
        if class_names is not None and item["class_names"] is not None and list(item["class_names"]) != class_names:
            raise ValueError("类别名不一致，不能合并")
    x = np.concatenate([item["x"] for item in loaded], axis=0)
    y = np.concatenate([item["y"] for item in loaded], axis=0)
    subjects = np.concatenate([np.asarray(item["subjects"]) for item in loaded]).astype(str)
    sessions = np.concatenate([np.asarray(item["sessions"]) for item in loaded]).astype(str)
    trial_ids = []
    for item in loaded:
        if item.get("trial_ids") is not None:
            trial_ids.extend([str(value) for value in np.asarray(item["trial_ids"]).tolist()])
        else:
            trial_ids.extend([""] * len(item["y"]))
    output = PROCESSED_DIR / f"merged_{datetime.now():%Y%m%d-%H%M%S}.npz"
    write_feature_dataset(
        output,
        x,
        y,
        subjects,
        sessions=sessions,
        class_names=class_names,
        feature_names=["delta", "theta", "alpha", "beta", "gamma"],
        trial_ids=trial_ids if any(trial_ids) else None,
        metadata={
            "source": "merged",
            "sources": [path.name for path in paths],
            "n_subjects": int(len(set(subjects.tolist()))),
            "note": "多个特征集合并；用于跨被试 LOSO。",
        },
    )
    info = _inspect_feature_npz(output)
    if info is None:
        raise ValueError("合并后数据集无法读取")
    return info


def experiments_payload() -> dict[str, Any]:
    experiments = list_experiments()
    real_runs = [item for item in experiments if not item.get("is_demo")]
    best_pool = real_runs or experiments
    return {
        "experiments": experiments,
        "best": max(best_pool, key=lambda item: item.get("accuracy") or 0.0, default=None),
        "count": len(experiments),
        "real_count": len(real_runs),
    }
