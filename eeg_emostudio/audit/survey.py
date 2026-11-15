"""Ingestion and cleaning of the stimulus-rating questionnaire exports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .normalize import (
    canonical_stimulus_id,
    normalize_rater,
    parse_free_text_issue,
    parse_issue_cell,
    parse_rating,
)


class SurveySchemaError(ValueError):
    """Raised when a required questionnaire column cannot be identified."""


def _find_column(columns: list[str], *keywords: str) -> str | None:
    for column in columns:
        if all(keyword in column for keyword in keywords):
            return column
    return None


def _require(columns: list[str], label: str, *keywords: str) -> str:
    # When only a label is supplied it doubles as the search keyword; this
    # keeps call sites readable while still allowing multi-keyword matching.
    search_terms = keywords or (label,)
    column = _find_column(columns, *search_terms)
    if column is None:
        raise SurveySchemaError(f"未找到{label}列（关键词：{search_terms}）")
    return column


@dataclass
class SurveyCleanResult:
    """Cleaned questionnaire plus a serialisable audit summary."""

    frame: pd.DataFrame
    raw_rows: int
    dedup_rows: int
    kind: str
    column_map: dict[str, str]
    summary: dict[str, Any] = field(default_factory=dict)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "raw_rows": self.raw_rows,
            "dedup_rows": self.dedup_rows,
            "column_map": self.column_map,
            **self.summary,
        }

    def write_csv(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.frame.to_csv(target, index=False, encoding="utf-8-sig")

    def write_summary(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_summary_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_survey(path: str | Path, kind: str = "video") -> SurveyCleanResult:
    """Load, normalise and audit one questionnaire export.

    Parameters
    ----------
    path:
        CSV exported by 问卷星 (UTF-8 with BOM by default).
    kind:
        ``"video"`` or ``"audio"``; selects the stimulus-ID namespace and
        the questionnaire wording used in the audit report.
    """

    if kind not in {"video", "audio"}:
        raise ValueError("kind must be 'video' or 'audio'")

    source = Path(path)
    raw = pd.read_csv(source, encoding="utf-8-sig", dtype=str)
    if raw.empty:
        raise SurveySchemaError(f"问卷为空：{source}")
    columns = list(raw.columns)

    mapping = {
        "row_id": columns[0],
        "submitted_at": _find_column(columns, "提交", "时间") or columns[1],
        "duration": _find_column(columns, "所用时间") or columns[2],
        "rater": _require(columns, "评分者姓名", "姓名"),
        "stimulus_raw": _require(
            columns,
            "刺激编号",
            "视频编号" if kind == "video" else "音乐歌曲编号",
        ),
        "valence": _require(columns, "效价"),
        "arousal": _require(columns, "唤醒"),
        "clarity": _require(columns, "主导情绪明确度", "明确", "主导情绪"),
        "emotion": _require(columns, "主导情绪类别", "请选择", "主导情绪"),
        "coverage": _require(columns, "主导情绪覆盖时长", "覆盖"),
        "stability": _require(columns, "反转"),
        "familiarity": _require(columns, "熟悉"),
        "comprehension": _require(columns, "理解"),
        "issues": _require(columns, "播放过程中"),
        "other": _require(columns, "未被上述"),
    }

    df = pd.DataFrame(
        {
            "row_id": pd.to_numeric(raw[mapping["row_id"]], errors="coerce"),
            "submitted_at": raw[mapping["submitted_at"]],
            "duration_s": pd.to_numeric(
                raw[mapping["duration"]].astype(str).str.extract(r"(\d+(?:\.\d+)?)")[0],
                errors="coerce",
            ),
            "rater": raw[mapping["rater"]].map(normalize_rater),
            "stimulus_raw": raw[mapping["stimulus_raw"]].astype(str).str.strip(),
            "valence_raw": raw[mapping["valence"]],
            "arousal_raw": raw[mapping["arousal"]],
            "clarity": raw[mapping["clarity"]].astype(str).str.strip(),
            "emotion": raw[mapping["emotion"]].astype(str).str.strip(),
            "coverage": raw[mapping["coverage"]].astype(str).str.strip(),
            "stability": raw[mapping["stability"]].astype(str).str.strip(),
            "familiarity": raw[mapping["familiarity"]].astype(str).str.strip(),
            "comprehension": raw[mapping["comprehension"]].astype(str).str.strip(),
            "issues_raw": raw[mapping["issues"]].fillna("").astype(str).str.strip(),
            "other_raw": raw[mapping["other"]].fillna("").astype(str).str.strip(),
        }
    )

    df["stimulus_id"] = df["stimulus_raw"].map(lambda value: canonical_stimulus_id(value, kind))
    df["valence"] = df["valence_raw"].map(lambda value: parse_rating(value, "valence"))
    df["arousal"] = df["arousal_raw"].map(lambda value: parse_rating(value, "arousal"))
    df["submitted_at"] = pd.to_datetime(df["submitted_at"], errors="coerce")

    # Keep the first complete submission per (rater, stimulus).  The source
    # export is already chronologically ordered, but sorting makes the rule
    # explicit and reproducible.
    df = df.sort_values(["submitted_at", "row_id"], na_position="last").reset_index(drop=True)
    before = len(df)
    df = df.drop_duplicates(subset=["rater", "stimulus_id"], keep="first").reset_index(drop=True)
    dedup_rows = len(df)

    issue_parsed = df["issues_raw"].map(parse_issue_cell)
    df["issue_severity"] = [item[0] for item in issue_parsed]
    df["issue_tags"] = ["、".join(item[1]) for item in issue_parsed]
    df["issue_contradiction"] = [item[2] for item in issue_parsed]
    other_parsed = df["other_raw"].map(parse_free_text_issue)
    df["other_issue_tag"] = [item[0] for item in other_parsed]
    df["other_issue_text"] = [item[1] for item in other_parsed]

    # Rater-level diagnostics
    rater_rows: list[dict[str, Any]] = []
    for rater, group in df.groupby("rater", dropna=False):
        valence_sd = float(group["valence"].std(ddof=0)) if group["valence"].notna().any() else float("nan")
        arousal_sd = float(group["arousal"].std(ddof=0)) if group["arousal"].notna().any() else float("nan")
        straightline = bool(
            np.isfinite(valence_sd)
            and np.isfinite(arousal_sd)
            and valence_sd < 1.0
            and arousal_sd < 1.0
        )
        rater_rows.append(
            {
                "rater": rater,
                "n_ratings": int(len(group)),
                "valence_mean": round(float(group["valence"].mean()), 3),
                "arousal_mean": round(float(group["arousal"].mean()), 3),
                "valence_sd": round(valence_sd, 3),
                "arousal_sd": round(arousal_sd, 3),
                "median_duration_s": round(float(group["duration_s"].median()), 1),
                "straightline_suspect": straightline,
            }
        )
    rater_table = pd.DataFrame(rater_rows).sort_values("n_ratings", ascending=False)

    id_variants = df["stimulus_raw"].nunique()
    n_stimuli = df["stimulus_id"].nunique()
    invalid_ids = int(df["stimulus_id"].isna().sum())
    invalid_ratings = int(df["valence"].isna().sum() + df["arousal"].isna().sum())
    missing_required = int(df[["rater", "stimulus_id", "valence", "arousal"]].isna().any(axis=1).sum())

    text_anchors = {
        "valence_text": int(df["valence_raw"].astype(str).str.contains("非常").sum()),
        "arousal_text": int(df["arousal_raw"].astype(str).str.contains("非常").sum()),
    }

    rating_coverage = (
        df.groupby("stimulus_id")
        .agg(
            n_raters=("rater", "nunique"),
            valence_mean=("valence", "mean"),
            arousal_mean=("arousal", "mean"),
            valence_sd=("valence", "std"),
            arousal_sd=("arousal", "std"),
            problem_rate=("issue_severity", lambda values: float((values > 0).mean())),
        )
        .reset_index()
    )
    rating_coverage["id_number"] = rating_coverage["stimulus_id"].str.extract(r"(\d+)").astype(int)
    rating_coverage = rating_coverage.sort_values("id_number").drop(columns="id_number")

    summary = {
        "duplicate_rows": int(before - dedup_rows),
        "n_raters": int(df["rater"].nunique()),
        "n_stimuli": int(n_stimuli),
        "stimulus_id_variants": int(id_variants),
        "invalid_stimulus_ids": invalid_ids,
        "invalid_rating_cells": invalid_ratings,
        "rows_with_missing_required": missing_required,
        "text_anchor_counts": text_anchors,
        "straightline_raters": rater_table.loc[
            rater_table["straightline_suspect"], "rater"
        ].tolist(),
        "partial_raters": rater_table.loc[
            rater_table["n_ratings"] < rater_table["n_ratings"].max(), "rater"
        ].tolist(),
        "rater_table": rater_table.to_dict(orient="records"),
        "stimulus_coverage": rating_coverage.round(3).to_dict(orient="records"),
    }

    return SurveyCleanResult(
        frame=df,
        raw_rows=len(raw),
        dedup_rows=dedup_rows,
        kind=kind,
        column_map=mapping,
        summary=summary,
    )


def infer_kind_from_filename(path: str | Path) -> str:
    """Infer questionnaire kind from a filename; useful for CLI ergonomics."""

    text = Path(path).name
    if "音乐" in text or "歌曲" in text or "music" in text.lower():
        return "audio"
    if "视频" in text or "video" in text.lower():
        return "video"
    raise ValueError("无法从文件名判断问卷类型，请显式传入 --kind")
