"""Build the audit/selection Excel workbook used as a thesis appendix."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "artifacts" / "audit"
SELECTION = ROOT / "artifacts" / "selection"
OUT = ROOT / "deliverables" / "EEG-EmoStudio_数据审计工作簿.xlsx"

INK = "1F2937"
ACCENT = "1F4E79"
HEADER_FILL = PatternFill("solid", fgColor=ACCENT)
HEADER_FONT = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="微软雅黑", size=9, color=INK)
TITLE_FONT = Font(name="微软雅黑", size=16, bold=True, color=ACCENT)
SUBTITLE_FONT = Font(name="微软雅黑", size=10, color="5B6B7C")
THIN = Side(style="thin", color="B7C4D1")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
ALT_FILL = PatternFill("solid", fgColor="F2F6FA")


def _style_sheet(ws, title: str, subtitle: str, header_row: int = 4) -> None:
    ws.sheet_view.showGridLines = False
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    ws["A2"] = subtitle
    ws["A2"].font = SUBTITLE_FONT
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=8)
    ws.row_dimensions[1].height = 28
    ws.row_dimensions[2].height = 18
    for cell in ws[header_row]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True, shrink_to_fit=False)
        cell.border = BORDER
    ws.row_dimensions[header_row].height = 32
    ws.freeze_panes = f"A{header_row + 1}"


def _display_width(text: str) -> int:
    """Approximate Excel column width; CJK glyphs occupy about two units."""

    return sum(2 if ord(char) > 127 else 1 for char in str(text))


def _write_table(ws, frame: pd.DataFrame, start_row: int = 4, max_width: int = 42,
                 autofilter: bool = True) -> None:
    for col_idx, column in enumerate(frame.columns, start=1):
        ws.cell(row=start_row, column=col_idx, value=str(column))
    for row_idx, row in enumerate(frame.itertuples(index=False), start=start_row + 1):
        for col_idx, value in enumerate(row, start=1):
            if isinstance(value, float) and pd.isna(value):
                value = ""
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = BODY_FONT
            cell.alignment = Alignment(vertical="top", wrap_text=True, indent=1)
            cell.border = BORDER
            if row_idx % 2 == 0:
                cell.fill = ALT_FILL
    for col_idx, column in enumerate(frame.columns, start=1):
        values = frame[column].astype(str).tolist()[:200]
        widths = [_display_width(column)] + [_display_width(value) for value in values]
        width = min(max(widths) + 5, max_width)
        ws.column_dimensions[get_column_letter(col_idx)].width = max(width, 10)
    if len(frame) and autofilter:
        ws.auto_filter.ref = (
            f"A{start_row}:{get_column_letter(len(frame.columns))}{start_row + len(frame)}"
        )


def _add_section_title(ws, row: int, text: str) -> None:
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = Font(name="微软雅黑", size=12, bold=True, color=INK)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)


def build() -> Path:
    summary = json.loads((AUDIT / "audit_summary.json").read_text(encoding="utf-8"))
    video = pd.read_csv(AUDIT / "video_ratings_clean.csv", encoding="utf-8-sig")
    audio = pd.read_csv(AUDIT / "audio_ratings_clean.csv", encoding="utf-8-sig")
    rater_v = pd.read_csv(AUDIT / "video_rater_table.csv", encoding="utf-8-sig")
    rater_a = pd.read_csv(AUDIT / "audio_rater_table.csv", encoding="utf-8-sig")
    issues_v = pd.read_csv(AUDIT / "video_playback_issues.csv", encoding="utf-8-sig")
    issues_a = pd.read_csv(AUDIT / "audio_playback_issues.csv", encoding="utf-8-sig")
    quality = pd.read_csv(AUDIT / "quality_combined.csv", encoding="utf-8-sig")
    selected = pd.read_csv(SELECTION / "selected_materials.csv", encoding="utf-8-sig")

    wb = Workbook()

    # ---- 00 说明 ----
    ws = wb.active
    ws.title = "00_说明"
    ws.sheet_view.showGridLines = False
    ws["A1"] = "EEG-EmoStudio 数据审计与选材工作簿"
    ws["A1"].font = Font(name="微软雅黑", size=20, bold=True, color=ACCENT)
    ws["A2"] = "本科毕业设计支撑材料 · 数据审计报告附件"
    ws["A2"].font = SUBTITLE_FONT
    ws["A4"] = "生成日期"
    ws["B4"] = summary.get("generated_at", "")
    ws["A5"] = "工作区"
    ws["B5"] = summary.get("workspace", "")
    ws["A6"] = "审计对象"
    ws["B6"] = "视频/音乐刺激、预评价问卷、映射表、质量排序"
    ws["A7"] = "原始 EEG"
    ws["B7"] = "当前工作区未发现；本工作簿不包含 EEG 质量结论"
    for row in range(4, 8):
        ws[f"A{row}"].font = Font(name="微软雅黑", size=10, bold=True, color=INK)
        ws[f"B{row}"].font = BODY_FONT
        ws[f"B{row}"].alignment = Alignment(wrap_text=True, vertical="top")
    ws["A9"] = "工作表索引"
    ws["A9"].font = Font(name="微软雅黑", size=12, bold=True, color=INK)
    index = [
        ("01_审计总览", "问卷/映射/质量的核心计数与等级分布"),
        ("02_评分者核查", "视频与音乐评分者的评分数、均值、SD、直线作答"),
        ("03_问题清单", "播放问题逐条明细与严重度"),
        ("04_质量排序", "240 条材料的质量分、等级、四象限"),
        ("05_选材清单", "80 条正式实验候选材料"),
        ("06_数据问题台账", "DQ-01~DQ-16 及处理建议"),
        ("07_字段字典", "关键字段口径"),
        ("08_视频清洗", "去重后逐条评分"),
        ("09_音乐清洗", "去重后逐条评分"),
    ]
    for offset, (name, desc) in enumerate(index, start=10):
        ws.cell(row=offset, column=1, value=name).font = Font(name="微软雅黑", size=10, bold=True, color=ACCENT)
        ws.cell(row=offset, column=2, value=desc).font = BODY_FONT
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 90
    ws["A22"] = "口径提醒"
    ws["A22"].font = Font(name="微软雅黑", size=12, bold=True, color="B00020")
    ws.merge_cells("A23:B26")
    ws["A23"] = (
        "1. 质量分衡量材料可用性与标签一致性，不是情绪标签真值。\n"
        "2. 去重规则：同一评分者×刺激保留首次提交；问题严重度按多选并集计算。\n"
        "3. 选材不跨象限比较；默认 80 条 = 2 模态 × 4 象限 × 10 条。\n"
        "4. 合成数据/EEG 性能不在本工作簿内；请勿把质量分当作分类准确率。"
    )
    ws["A23"].font = BODY_FONT
    ws["A23"].alignment = Alignment(wrap_text=True, vertical="top")

    # ---- 01 总览 ----
    ws = wb.create_sheet("01_审计总览")
    _style_sheet(ws, "审计总览", "截至 2026-11-07；详细口径见《数据审计报告》", header_row=4)
    rows = []
    for kind, label in (("video", "视频"), ("audio", "音乐")):
        survey = summary["surveys"][kind]
        quality_info = summary["quality"][kind]
        issue_table = issues_v if kind == "video" else issues_a
        rows.append(
            {
                "模态": label,
                "原始问卷": survey["raw_rows"],
                "去重后": survey["dedup_rows"],
                "重复提交": survey["duplicate_rows"],
                "评分者": survey["n_raters"],
                "刺激数": survey["n_stimuli"],
                "编号写法": survey["stimulus_id_variants"],
                "问题刺激": int(issue_table["stimulus_id"].nunique()),
                "质量分范围": f"{quality_info['score_min']}–{quality_info['score_max']}",
                "质量分中位": quality_info["score_median"],
                "S": quality_info["grade_counts"].get("S", 0),
                "A": quality_info["grade_counts"].get("A", 0),
                "B": quality_info["grade_counts"].get("B", 0),
                "C": quality_info["grade_counts"].get("C", 0),
                "D": quality_info["grade_counts"].get("D", 0),
            }
        )
    overview = pd.DataFrame(rows)
    _write_table(ws, overview, start_row=4, max_width=22, autofilter=False)

    _add_section_title(ws, 8, "质量等级分布")
    grade_counts = {
        label: summary["quality"][kind]["grade_counts"]
        for kind, label in (("video", "视频"), ("audio", "音乐"))
    }
    grade_df = pd.DataFrame(
        {
            "等级": list("SABCD"),
            "视频": [grade_counts["视频"].get(g, 0) for g in "SABCD"],
            "音乐": [grade_counts["音乐"].get(g, 0) for g in "SABCD"],
        }
    )
    _write_table(ws, grade_df, start_row=9, max_width=12, autofilter=False)
    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.title = "视频/音乐质量等级分布"
    chart.y_axis.title = "素材数量"
    chart.x_axis.title = "等级"
    data = Reference(ws, min_col=2, max_col=3, min_row=9, max_row=14)
    cats = Reference(ws, min_col=1, min_row=10, max_row=14)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.height = 7
    chart.width = 15
    ws.add_chart(chart, "A16")

    # ---- 02 评分者 ----
    ws = wb.create_sheet("02_评分者核查")
    _style_sheet(ws, "评分者核查", "SD 均 <1.0 视为直线作答嫌疑；仅标记，不自动删除", header_row=4)
    rater_v.insert(0, "模态", "视频")
    rater_a.insert(0, "模态", "音乐")
    raters = pd.concat([rater_v, rater_a], ignore_index=True)
    _write_table(ws, raters, start_row=4, autofilter=False)

    # ---- 03 问题 ----
    ws = wb.create_sheet("03_问题清单")
    _style_sheet(ws, "播放问题清单", "按原始记录；severity 为多选严重度并集，非质量总分", header_row=4)
    issues_v.insert(0, "模态", "视频")
    issues_a.insert(0, "模态", "音乐")
    issues = pd.concat([issues_v, issues_a], ignore_index=True)
    _write_table(ws, issues, start_row=4)

    # ---- 04 质量 ----
    ws = wb.create_sheet("04_质量排序")
    _style_sheet(ws, "240 条材料质量排序", "质量分高≠情绪标签一定正确；需结合预实验", header_row=4)
    quality_cols = [
        "modality", "stimulus_id", "category", "quality_score", "grade", "rank",
        "n_raters", "problem_rate", "main_issue", "discrete_label",
    ]
    quality_subset = quality[[c for c in quality_cols if c in quality.columns]].copy()
    _write_table(ws, quality_subset, start_row=4)
    score_col = list(quality_subset.columns).index("quality_score") + 1
    ws.conditional_formatting.add(
        f"{get_column_letter(score_col)}5:{get_column_letter(score_col)}{4 + len(quality_subset)}",
        ColorScaleRule(start_type="min", start_color="F8696B", mid_type="percentile", mid_value=50,
                       mid_color="FFEB84", end_type="max", end_color="63BE7B"),
    )

    # ---- 05 选材 ----
    ws = wb.create_sheet("05_选材清单")
    _style_sheet(ws, "80 条平衡选材清单", "每模态×四象限 10 条；无 C/D；按质量分降序", header_row=4)
    selection_cols = [
        "selection_rank", "modality", "stimulus_id", "category", "quality_score",
        "grade", "category_rank", "main_issue", "selection_reason",
    ]
    selected_subset = selected[[c for c in selection_cols if c in selected.columns]].copy()
    _write_table(ws, selected_subset, start_row=4)

    # ---- 06 问题台账 ----
    ws = wb.create_sheet("06_数据问题台账")
    _style_sheet(ws, "数据问题台账", "S1 阻断 / S2 重要 / S3 一般；处理建议供课题组执行", header_row=4)
    ledger = pd.DataFrame(
        [
            ("DQ-01", "无原始 EEG", "工作区无 EEG 文件", "S1", "无法训练/验证", "导入首批并跑 QG-EEG-1~6", "课题组"),
            ("DQ-02", "音乐片段长度不一致", "26/120 超出 60±15 s", "S1", "预评价与正式实验不一致", "统一 60 s 或修订协议", "实验员"),
            ("DQ-03", "素材表与映射表标签不一致", "116 条连续标签缺失", "S1", "标签混用", "明确映射表为权威", "数据管理员"),
            ("DQ-04", "旧绝对路径", "D:\\desktop\\workspace\\...", "S2", "换机不可用", "改相对路径+哈希", "数据管理员"),
            ("DQ-05", "重复提交", "视频42/音乐15", "S2", "放大权重", "保留首次", "系统"),
            ("DQ-06", "编号写法混乱", "146/129 种；388→38", "S2", "关联失败", "别名+正则+审计", "系统"),
            ("DQ-07", "评分文字锚点", "261/201；105/167", "S2", "不能直接计算", "映射 1/9", "系统"),
            ("DQ-08", "播放问题多选", "36/78 条", "S2", "质量分偏差", "并集+矛盾标记", "系统"),
            ("DQ-09", "视频播放问题", "22 条", "S2", "诱发失败", "抽帧/试听复核", "实验员"),
            ("DQ-10", "音乐文件问题", "29 条，12 损坏", "S2", "无法播放", "转码/替换/剔除", "实验员"),
            ("DQ-11", "直线作答", "刘佳悦", "S2", "拉低一致性", "剔除/敏感性分析", "系统"),
            ("DQ-12", "部分评分者", "赵瀚仅30条", "S2", "样本不足", "保留并计 N", "数据管理员"),
            ("DQ-13", "素材表示例行", "121 行", "S3", "多 1 行", "读取排除", "系统"),
            ("DQ-14", "英文名/来源详情缺失", "1；507/575", "S3", "不影响分析", "记录", "数据管理员"),
            ("DQ-15", "118.mp3 元数据异常", "PyAV UnicodeDecodeError", "S3", "时长未知", "转码/人工核验", "实验员"),
            ("DQ-16", "无文件哈希", "映射表仅路径", "S2", "版本不可证", "入库计算 SHA-256", "系统"),
        ],
        columns=["编号", "问题", "证据", "严重度", "影响", "处理建议", "责任"],
    )
    _write_table(ws, ledger, start_row=4, autofilter=False)

    # ---- 07 字段字典 ----
    ws = wb.create_sheet("07_字段字典")
    _style_sheet(ws, "关键字段字典（摘要）", "完整版见《数据字典与数据治理规范》", header_row=4)
    fields = pd.DataFrame(
        [
            ("stimulus_id", "string", "刺激主键", "1.mp4…120.mp4 / 1.mp3…120.mp3"),
            ("modality", "enum", "刺激类型", "video/audio"),
            ("category", "enum", "四象限", "HVHA/HVLA/LVHA/LVLA"),
            ("valence", "float", "效价", "1–9；文字锚点已映射"),
            ("arousal", "float", "唤醒", "1–9；文字锚点已映射"),
            ("issue_severity", "float", "播放问题严重度", "0–1；多选并集"),
            ("quality_score", "float", "材料质量分", "0–100；非标签"),
            ("grade", "enum", "质量等级", "S/A/B/C/D"),
            ("rater", "string", "评分者（内部）", "规范化姓名；报告用伪 ID"),
            ("straightline_suspect", "bool", "直线作答嫌疑", "效价/唤醒 SD 均<1"),
            ("feature x", "float32", "DE 特征", "(samples, channels, bands)"),
            ("subject", "string", "被试伪匿名 ID", "S01…"),
        ],
        columns=["字段", "类型", "含义", "取值/规则"],
    )
    _write_table(ws, fields, start_row=4, autofilter=False)

    # ---- 08/09 清洗明细 ----
    for name, frame, title in [
        ("08_视频清洗", video, "视频问卷清洗明细"),
        ("09_音乐清洗", audio, "音乐问卷清洗明细"),
    ]:
        ws = wb.create_sheet(name)
        _style_sheet(ws, title, "已去重；敏感字段仅保留内部姓名，对外报告请脱敏", header_row=4)
        _write_table(ws, frame, start_row=4)

    wb.properties.title = "EEG-EmoStudio 数据审计与选材工作簿"
    wb.properties.creator = "EEG-EmoStudio"
    wb.properties.subject = "本科毕业设计支撑材料"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"[xlsx] written {path} ({path.stat().st_size} bytes)")
