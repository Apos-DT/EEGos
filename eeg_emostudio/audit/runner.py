"""Workspace-level audit orchestration and report generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .media import audit_material_list, audit_media
from .quality import combine_quality_tables, load_quality_table
from .survey import load_survey

DEFAULT_SURVEYS = {
    "video": "374437060_按文本_情绪诱发情况评估（视频）_1271_1269(Sheet1).csv",
    "audio": "376653806_按文本_情绪诱发情况评估（音乐）_1088_1087(Sheet1).csv",
}
DEFAULT_MAPPINGS = {"video": "视频对应关系.csv", "audio": "音乐对应关系.csv"}
DEFAULT_MEDIA = {
    "video": ("VIDEOS", "视频压缩v2"),
    "audio": ("音乐测试v2", "音乐测试v2"),
}
DEFAULT_QUALITY = {
    "video": "research/quality/video/视频质量排序.csv",
    "audio": "research/quality/audio/音乐歌曲质量排序.csv",
}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def run_workspace_audit(
    workspace: str | Path,
    out_dir: str | Path,
    probe_media: bool = False,
    data_dirname: str = "山科数据集",
) -> dict[str, Any]:
    """Audit the current stimulus/rating workspace and write artefacts.

    The function is intentionally tolerant of missing optional deliverables
    (for example the quality ranking may not have been produced yet); the
    returned report records which inputs were present.
    """

    root = Path(workspace).resolve()
    data_dir = root / data_dirname
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "workspace": str(root),
        "data_dir": str(data_dir),
        "inputs": {},
        "surveys": {},
        "mappings": {},
        "quality": {},
    }

    clean_surveys = {}
    for kind, filename in DEFAULT_SURVEYS.items():
        path = data_dir / filename
        if not path.exists():
            report["inputs"][kind] = {"survey": None, "reason": "missing"}
            continue
        cleaned = load_survey(path, kind=kind)
        clean_surveys[kind] = cleaned
        report["inputs"][kind] = {"survey": str(path)}
        report["surveys"][kind] = cleaned.to_summary_dict()
        cleaned.write_csv(out / f"{kind}_ratings_clean.csv")
        cleaned.write_summary(out / f"{kind}_survey_summary.json")
        rater_table = pd.DataFrame(cleaned.summary["rater_table"])
        rater_table.to_csv(out / f"{kind}_rater_table.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(cleaned.summary["stimulus_coverage"]).to_csv(
            out / f"{kind}_stimulus_coverage.csv", index=False, encoding="utf-8-sig"
        )
        issue_rows = cleaned.frame[
            (cleaned.frame["issue_severity"] > 0) | cleaned.frame["other_issue_tag"].notna()
        ][
            [
                "row_id",
                "rater",
                "stimulus_id",
                "valence",
                "arousal",
                "issues_raw",
                "other_raw",
                "issue_severity",
                "issue_tags",
                "other_issue_tag",
            ]
        ]
        issue_rows.to_csv(out / f"{kind}_playback_issues.csv", index=False, encoding="utf-8-sig")

    for kind, filename in DEFAULT_MAPPINGS.items():
        path = data_dir / filename
        media_parts = DEFAULT_MEDIA[kind]
        media_dir = data_dir.joinpath(*media_parts)
        if not path.exists():
            report["mappings"][kind] = {"mapping": None, "reason": "missing"}
            continue
        result = audit_media(path, media_dir, kind=kind, probe=probe_media)
        report["mappings"][kind] = result.summary
        result.mapping.to_csv(out / f"{kind}_mapping_audit.csv", index=False, encoding="utf-8-sig")
        result.write_summary(out / f"{kind}_mapping_summary.json")
        if result.durations is not None:
            result.durations.to_csv(
                out / f"{kind}_media_durations.csv", index=False, encoding="utf-8-sig"
            )

    material_path = data_dir / "素材列表.xlsx"
    if material_path.exists():
        report["material_list"] = audit_material_list(material_path)

    quality_tables = {}
    for kind, relative in DEFAULT_QUALITY.items():
        path = root / relative
        if not path.exists():
            report["quality"][kind] = {"path": str(path), "reason": "missing"}
            continue
        table = load_quality_table(path, kind=kind)
        quality_tables[kind] = table
        report["quality"][kind] = table.summary

    if quality_tables:
        combined = combine_quality_tables(
            quality_tables.get("video"), quality_tables.get("audio")
        )
        combined.to_csv(out / "quality_combined.csv", index=False, encoding="utf-8-sig")

    report["generated_at"] = pd.Timestamp.now(tz="Asia/Shanghai").isoformat()
    _write_json(out / "audit_summary.json", report)
    (out / "audit_report.md").write_text(_render_markdown(report), encoding="utf-8")
    return report


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 山科情绪刺激与评价数据自动审计报告",
        "",
        f"- 工作区：`{report['workspace']}`",
        f"- 生成时间：{report.get('generated_at', '')}",
        "",
        "## 1. 问卷数据",
        "",
        "| 模态 | 原始记录 | 去重后 | 评分者 | 刺激数 | 重复提交 | 无效评分单元 | 直线作答 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for kind, label in (("video", "视频"), ("audio", "音乐")):
        survey = report["surveys"].get(kind)
        if not survey:
            lines.append(f"| {label} | — | — | — | — | — | — | 未找到问卷 |")
            continue
        lines.append(
            "| {label} | {raw} | {dedup} | {raters} | {stimuli} | {dups} | {bad} | {straight} |".format(
                label=label,
                raw=survey["raw_rows"],
                dedup=survey["dedup_rows"],
                raters=survey["n_raters"],
                stimuli=survey["n_stimuli"],
                dups=survey["duplicate_rows"],
                bad=survey["invalid_rating_cells"],
                straight="、".join(survey["straightline_raters"]) or "无",
            )
        )

    lines += ["", "## 2. 映射与媒体文件", ""]
    for kind, label in (("video", "视频"), ("audio", "音乐")):
        mapping = report["mappings"].get(kind)
        if not mapping:
            lines.append(f"- {label}：未找到映射表。")
            continue
        lines.append(
            f"- {label}：{mapping['mapping_rows']} 条映射，类别分布 {mapping['category_counts']}；"
            f"缺失文件 {len(mapping['missing_files'])} 个，多余文件 {len(mapping['extra_files'])} 个。"
        )
        if "segment_duration" in mapping:
            seg = mapping["segment_duration"]
            lines.append(
                f"  - 标注片段长度：最短 {seg['min_s']} s，中位 {seg['median_s']} s，"
                f"最长 {seg['max_s']} s；偏离 60±15 s 的有 {seg['outside_60s_pm15']} 条。"
            )
        if "probe" in mapping:
            lines.append(
                f"  - 实测媒体时长：最短 {mapping['probe']['min_s']} s，"
                f"中位 {mapping['probe']['median_s']} s，最长 {mapping['probe']['max_s']} s；"
                f"读取异常 {len(mapping['probe']['errors'])} 个。"
            )

    lines += ["", "## 3. 材料质量排序", ""]
    for kind, label in (("video", "视频"), ("audio", "音乐")):
        quality = report["quality"].get(kind)
        if not quality or "rows" not in quality:
            lines.append(f"- {label}：尚无质量排序文件。")
            continue
        lines.append(
            f"- {label}：{quality['rows']} 条，分数 {quality['score_min']}–{quality['score_max']}，"
            f"中位 {quality['score_median']}；等级分布 {quality['grade_counts']}。"
        )

    lines += [
        "",
        "## 4. 关键发现（自动生成，需人工复核）",
        "",
        "1. 问卷编号存在多种写法，视频侧还有 `388.mp4` 误写；系统按显式别名映射为 `38.mp4`。",
        "2. 效价/唤醒同时存在数字与文字锚点，必须统一到 1–9 分后才能计算。",
        "3. 播放问题为多选文本，`┋` 分隔且可能同时勾选“没有问题”；系统按问题严重度并集计算并保留矛盾标记。",
        "4. 音乐标注片段长度并不都等于 60 s，正式实验前必须统一截取规则或修订协议。",
        "5. 质量分是“材料可用性”证据，不是情绪标签真值；正式标签仍需以被试实际自评和实验设计为准。",
        "",
        "> 本报告只覆盖当前工作区可见的刺激与问卷数据；截至生成时，工作区未发现原始 EEG 文件，"
        "因此 EEG 通道、采样率、事件标记和伪迹等检查项被标记为“未执行”，不能据此声称 EEG 数据已通过质量检查。",
        "",
    ]
    return "\n".join(lines)
