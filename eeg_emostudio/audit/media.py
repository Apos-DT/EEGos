"""Stimulus-library inspection: IDs, mappings, files and durations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .normalize import parse_clock_seconds


@dataclass
class MediaAuditResult:
    mapping: pd.DataFrame
    summary: dict[str, Any] = field(default_factory=dict)
    durations: pd.DataFrame | None = None

    def write_summary(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_mapping(path: str | Path) -> pd.DataFrame:
    """Load and normalise a stimulus-to-file mapping table."""

    source = Path(path)
    frame = pd.read_csv(source, encoding="utf-8-sig")
    required = {"编号", "新文件名", "类别"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"映射表缺少字段：{sorted(missing)}")
    frame = frame.copy()
    frame["编号"] = pd.to_numeric(frame["编号"], errors="coerce").astype("Int64")
    frame["新文件名"] = frame["新文件名"].astype(str).str.strip()
    frame["类别"] = frame["类别"].astype(str).str.strip().str.upper()
    frame["stimulus_id"] = frame["新文件名"]
    frame["category"] = frame["类别"]
    if "起始时间" in frame.columns:
        frame["start_s"] = frame["起始时间"].map(parse_clock_seconds)
        frame["end_s"] = frame["结束时间"].map(parse_clock_seconds)
        frame["segment_s"] = frame["end_s"] - frame["start_s"]
    return frame


def _probe_video(path: Path) -> float | None:
    try:
        import cv2  # type: ignore

        capture = cv2.VideoCapture(str(path))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frames = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        capture.release()
        return frames / fps if fps > 0 else None
    except Exception:
        return None


def _probe_audio(path: Path) -> tuple[float | None, str | None]:
    try:
        import av  # type: ignore

        with av.open(str(path)) as container:
            duration = float(container.duration / av.time_base) if container.duration else None
        return duration, None
    except Exception as exc:  # pragma: no cover - depends on local media stack
        return None, f"{type(exc).__name__}: {exc}"


def audit_media(
    mapping_path: str | Path,
    media_dir: str | Path,
    kind: str = "video",
    probe: bool = False,
) -> MediaAuditResult:
    """Check mapping integrity and, optionally, physical media durations.

    ``probe=False`` keeps the audit fast and deterministic; it still checks
    file presence.  Enabling ``probe`` uses OpenCV for video and PyAV for
    audio and records the measured duration for later comparison with the
    experimental protocol.
    """

    frame = load_mapping(mapping_path)
    media_root = Path(media_dir)
    files = [path for path in media_root.iterdir() if path.is_file()] if media_root.exists() else []
    names = {path.name for path in files}

    frame["file_exists"] = frame["新文件名"].isin(names)
    frame["category_ok"] = frame["类别"].isin({"HVHA", "HVLA", "LVHA", "LVLA"})
    duplicates = frame.loc[frame["新文件名"].duplicated(keep=False), "新文件名"].tolist()
    missing_files = frame.loc[~frame["file_exists"], "新文件名"].tolist()
    extra_files = sorted(names - set(frame["新文件名"]))

    probe_rows: list[dict[str, Any]] = []
    if probe:
        for _, row in frame.iterrows():
            path = media_root / row["新文件名"]
            if not path.exists():
                probe_rows.append({"file": row["新文件名"], "duration_s": None, "probe_error": "missing"})
                continue
            if kind == "video":
                duration = _probe_video(path)
                error = None if duration else "unreadable"
            else:
                duration, error = _probe_audio(path)
            probe_rows.append({"file": row["新文件名"], "duration_s": duration, "probe_error": error})
    durations = pd.DataFrame(probe_rows) if probe_rows else None

    category_counts = frame["类别"].value_counts().sort_index().to_dict()
    summary: dict[str, Any] = {
        "kind": kind,
        "mapping_rows": int(len(frame)),
        "mapping_unique_files": int(frame["新文件名"].nunique()),
        "category_counts": {str(key): int(value) for key, value in category_counts.items()},
        "category_balanced": bool(len(set(category_counts.values())) == 1),
        "duplicate_files": sorted(set(duplicates)),
        "missing_files": missing_files,
        "extra_files": extra_files,
        "invalid_category_rows": int((~frame["category_ok"]).sum()),
        "media_dir": str(media_root),
        "physical_file_count": int(len(files)),
    }

    if "segment_s" in frame.columns:
        valid = frame["segment_s"].dropna()
        summary["segment_duration"] = {
            "n": int(len(valid)),
            "min_s": round(float(valid.min()), 1),
            "median_s": round(float(valid.median()), 1),
            "max_s": round(float(valid.max()), 1),
            "outside_60s_pm15": int(((valid - 60.0).abs() > 15.0).sum()),
        }
        summary["segment_outliers"] = frame.loc[
            (frame["segment_s"] - 60.0).abs() > 15.0,
            ["新文件名", "start_s", "end_s", "segment_s"],
        ].to_dict(orient="records")

    if durations is not None and not durations.empty:
        measured = pd.to_numeric(durations["duration_s"], errors="coerce").dropna()
        summary["probe"] = {
            "n": int(len(measured)),
            "min_s": round(float(measured.min()), 1),
            "median_s": round(float(measured.median()), 1),
            "max_s": round(float(measured.max()), 1),
            "errors": durations.loc[durations["probe_error"].notna()].to_dict(orient="records"),
        }

    return MediaAuditResult(mapping=frame, summary=summary, durations=durations)


def audit_material_list(path: str | Path) -> dict[str, Any]:
    """Audit the human-maintained material spreadsheet.

    The spreadsheet intentionally contains an "示例" row and uses display
    formatting for durations; this function reports those conventions rather
    than treating them as fatal errors.
    """

    source = Path(path)
    result: dict[str, Any] = {"sheets": {}}
    workbook = pd.ExcelFile(source)
    for sheet in [name for name in workbook.sheet_names if name in {"视频", "音乐"}]:
        frame = pd.read_excel(source, sheet_name=sheet)
        ids = frame.iloc[:, 0].astype(str).str.strip()
        result["sheets"][sheet] = {
            "rows": int(len(frame)),
            "columns": list(frame.columns),
            "example_rows": int((ids == "示例").sum()),
            "missing_continuous_label": int(frame["预期连续情绪"].isna().sum()),
            "continuous_label_counts": {
                str(key): int(value)
                for key, value in frame["预期连续情绪"].value_counts(dropna=False).items()
            },
            "discrete_label_counts": {
                str(key): int(value)
                for key, value in frame["预期离散情绪"].value_counts(dropna=False).items()
            },
        }
    result["note"] = "素材表中的起始/结束时间可能为 Excel 日分数；映射表中的文本时间需统一转为秒。"
    return result
