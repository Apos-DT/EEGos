"""Read and validate the existing stimulus quality-ranking deliverables."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

GRADE_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
CATEGORIES = ("HVHA", "HVLA", "LVHA", "LVLA")


@dataclass
class QualityTable:
    frame: pd.DataFrame
    summary: dict[str, Any]

    def write_summary(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.summary, ensure_ascii=False, indent=2), encoding="utf-8")


def _pick(columns: list[str], *keywords: str) -> str | None:
    for column in columns:
        if all(keyword in column for keyword in keywords):
            return column
    return None


def load_quality_table(path: str | Path, kind: str = "video") -> QualityTable:
    """Load a quality-ranking CSV and map its Chinese headers to stable keys."""

    frame = pd.read_csv(path, encoding="utf-8-sig")
    columns = list(frame.columns)
    id_col = _pick(columns, "视频编号") or _pick(columns, "音乐歌曲编号") or _pick(columns, "编号")
    score_col = _pick(columns, "质量总分")
    grade_col = _pick(columns, "质量等级")
    category_col = _pick(columns, "情感类别")
    discrete_col = _pick(columns, "离散标签")
    rank_col = _pick(columns, "排名")
    missing = {
        "stimulus_id": id_col,
        "quality_score": score_col,
        "grade": grade_col,
        "category": category_col,
        "rank": rank_col,
    }
    absent = [key for key, value in missing.items() if value is None]
    if absent:
        raise ValueError(f"质量表缺少必要字段：{absent}; 实际列={columns}")

    out = pd.DataFrame(
        {
            "modality": "video" if kind == "video" else "audio",
            "stimulus_id": frame[id_col].astype(str).str.strip(),
            "quality_score": pd.to_numeric(frame[score_col], errors="coerce"),
            "grade": frame[grade_col].astype(str).str.strip().str.upper(),
            "category": frame[category_col].astype(str).str.strip().str.upper(),
            "rank": pd.to_numeric(frame[rank_col], errors="coerce"),
            "discrete_label": frame[discrete_col].astype(str).str.strip()
            if discrete_col
            else "",
        }
    )
    if "有效评分人数" in frame.columns:
        out["n_raters"] = pd.to_numeric(frame["有效评分人数"], errors="coerce")
    if "问题报告率" in frame.columns:
        out["problem_rate"] = pd.to_numeric(frame["问题报告率"], errors="coerce")
    if "主要问题" in frame.columns:
        out["main_issue"] = frame["主要问题"].fillna("").astype(str)

    summary = {
        "kind": kind,
        "rows": int(len(out)),
        "unique_ids": int(out["stimulus_id"].nunique()),
        "duplicate_ids": out.loc[out["stimulus_id"].duplicated(), "stimulus_id"].tolist(),
        "score_min": round(float(out["quality_score"].min()), 1),
        "score_max": round(float(out["quality_score"].max()), 1),
        "score_median": round(float(out["quality_score"].median()), 1),
        "grade_counts": {str(key): int(value) for key, value in out["grade"].value_counts().items()},
        "category_counts": {
            str(key): int(value) for key, value in out["category"].value_counts().items()
        },
        "invalid_categories": sorted(set(out["category"]) - set(CATEGORIES)),
        "missing_scores": int(out["quality_score"].isna().sum()),
    }
    return QualityTable(frame=out, summary=summary)


def combine_quality_tables(video: QualityTable | None, audio: QualityTable | None) -> pd.DataFrame:
    tables = [table.frame for table in (video, audio) if table is not None]
    if not tables:
        raise ValueError("至少需要视频或音乐一张质量表")
    combined = pd.concat(tables, ignore_index=True)
    combined["grade_order"] = combined["grade"].map(GRADE_ORDER).fillna(9).astype(int)
    return combined


def select_balanced(
    table: pd.DataFrame,
    per_class: int = 10,
    min_grade: str = "D",
    modalities: tuple[str, ...] = ("video", "audio"),
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Select a category-balanced stimulus set, preferring higher grades.

    Selection is deliberately *within* each modality and quadrant, because a
    global top-N ranking would over-select the easiest quadrant (usually
    HVHA) and destroy the experimental design.
    """

    if per_class < 1:
        raise ValueError("per_class 必须为正整数")
    if min_grade not in GRADE_ORDER:
        raise ValueError("min_grade 必须为 S/A/B/C/D")

    allowed = {grade for grade, order in GRADE_ORDER.items() if order <= GRADE_ORDER[min_grade]}
    picked: list[pd.DataFrame] = []
    warnings: list[str] = []
    for modality in modalities:
        subset = table[table["modality"] == modality]
        if subset.empty:
            continue
        for category in CATEGORIES:
            group = subset[(subset["category"] == category) & subset["grade"].isin(allowed)]
            group = group.sort_values(
                ["grade_order", "quality_score", "stimulus_id"],
                ascending=[True, False, True],
            )
            chosen = group.head(per_class).copy()
            if len(chosen) < per_class:
                warnings.append(
                    f"{modality}/{category} 仅有 {len(chosen)} 条满足等级 {min_grade}，目标 {per_class}"
                )
            chosen["category_rank"] = range(1, len(chosen) + 1)
            picked.append(chosen)
    if not picked:
        raise ValueError("没有满足条件的刺激材料")
    result = pd.concat(picked, ignore_index=True)
    result["selection_rank"] = range(1, len(result) + 1)
    result["selection_reason"] = result.apply(
        lambda row: f"{row['modality']}-{row['category']} 第{int(row['category_rank'])}名，等级{row['grade']}",
        axis=1,
    )

    summary = {
        "per_class": per_class,
        "min_grade": min_grade,
        "selected_total": int(len(result)),
        "by_modality_category": {
            f"{modality}/{category}": int(
                ((result["modality"] == modality) & (result["category"] == category)).sum()
            )
            for modality in modalities
            for category in CATEGORIES
        },
        "grade_counts": {str(key): int(value) for key, value in result["grade"].value_counts().items()},
        "min_selected_grade": max(result["grade"], key=lambda grade: GRADE_ORDER.get(grade, 9)),
        "warnings": warnings,
        "rule": "先按模态×四象限分层，再按等级与质量总分降序取前 N；不跨象限比较。",
    }
    return result, summary


def selection_markdown(selected: pd.DataFrame, summary: dict[str, Any]) -> str:
    lines = [
        "# 正式实验刺激材料选择报告",
        "",
        f"- 每个模态×情绪象限选取：**{summary['per_class']}** 条",
        f"- 总选取数：**{summary['selected_total']}** 条",
        f"- 最低允许等级：**{summary['min_grade']}**",
        f"- 选择规则：{summary['rule']}",
        "",
        "## 分层结果",
        "",
        "| 模态/象限 | 选取数 | 平均质量分 | 最低等级 |",
        "|---|---:|---:|---|",
    ]
    for key, count in summary["by_modality_category"].items():
        modality, category = key.split("/")
        part = selected[(selected["modality"] == modality) & (selected["category"] == category)]
        avg = float(part["quality_score"].mean()) if len(part) else float("nan")
        worst = max(part["grade"], key=lambda grade: GRADE_ORDER.get(grade, 9)) if len(part) else "—"
        lines.append(f"| {key} | {count} | {avg:.1f} | {worst} |")
    lines += ["", "## 警告", ""]
    lines += [f"- {warning}" for warning in summary["warnings"]] or ["- 无"]
    lines += [
        "",
        "## 说明",
        "",
        "该表只解决“材料质量与类别平衡”，不替代伦理审查、版权核查和正式实验前的设备联调。",
        "音乐材料若片段长度偏离 60 s，需在实验程序中统一截取，或修订刺激协议后重新评价。",
    ]
    return "\n".join(lines) + "\n"
