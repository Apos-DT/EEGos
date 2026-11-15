# -*- coding: utf-8 -*-
"""生成交付物：Excel 工作簿、排序图、Markdown 报告"""
import os
import json
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.utils import get_column_letter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = r"C:\Users\24114\Desktop\EEG Emotion Recognition"
OUT = os.path.join(ROOT, "音乐质量评分输出")
res = pd.read_pickle(os.path.join(OUT, "_res.pkl"))
rows = pd.read_pickle(os.path.join(OUT, "_rows.pkl"))
rater_stats = pd.read_csv(os.path.join(OUT, "_rater_stats.csv"), encoding="utf-8-sig")
sens = pd.read_csv(os.path.join(OUT, "_sensitivity.csv"), encoding="utf-8-sig")
meta = json.load(open(os.path.join(OUT, "_meta.json"), encoding="utf-8"))

res = res.sort_values("rank").reset_index(drop=True)

GRADE_FILL = {"S": "F2D06B", "A": "BFE3C0", "B": "BFD7F0", "C": "F7D2A8", "D": "F2B8B5"}
GRADE_TEXT = {"S": "可直接用于正式实验", "A": "优先使用", "B": "可用（次级）",
              "C": "谨慎使用", "D": "不建议使用"}
GRADE_COLOR = {"S": "#C9A227", "A": "#2E7D32", "B": "#1565C0", "C": "#EF6C00", "D": "#C62828"}

HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(color="FFFFFF", bold=True, size=10)
THIN = Side(style="thin", color="D0D0D0")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def style_header(ws, row=1, ncol=None):
    ncol = ncol or ws.max_column
    for c in range(1, ncol + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[row].height = 30


def set_widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


wb = Workbook()

# ================================================================== #
# Sheet 1 排序总表
# ================================================================== #
ws = wb.active
ws.title = "01_排序总表"
headers = ["排名", "音乐歌曲编号", "质量总分", "质量等级", "使用建议", "情感类别(四象限)", "四象限内排名",
           "有效评分人数", "问题人数", "问题报告率", "问题指数", "主要问题",
           "基础分", "播放门控", "情绪诱发E(50)", "一致性C(20)", "标签效度L(15)",
           "干扰控制D(10)", "样本N(5)", "平均效价", "平均唤醒", "标签命中率",
           "分数95%CI", "排名95%CI", "离散标签", "离散标签一致率", "离散类内排名"]
ws.append(headers)

for _, r in res.iterrows():
    ws.append([
        int(r["rank"]), r["sid"], round(float(r["Score"]), 1), r["grade"],
        GRADE_TEXT[r["grade"]], r["cat"], int(r["rank_in_cat"]),
        int(r["n_valid"]), int(r["problem_raters"]), round(float(r["raw_rate"]), 2),
        round(float(r["w"]), 3), r["tags"] if isinstance(r["tags"], str) and r["tags"] else "无",
        round(float(r["Base"]), 1), round(float(r["G"]), 3),
        round(float(r["E"]), 1), round(float(r["C"]), 1), round(float(r["L"]), 1),
        round(float(r["D"]), 1), round(float(r["N"]), 1),
        round(float(r["v_mean"]), 2), round(float(r["a_mean"]), 2),
        round(float(r["hit_rate"]), 2),
        f'{r["ci_lo"]:.1f}–{r["ci_hi"]:.1f}', f'{int(r["rank_lo"])}–{int(r["rank_hi"])}',
        r["discrete"], round(float(r["discrete_agree"]), 2), int(r["rank_in_discrete"]),
    ])

style_header(ws)
set_widths(ws, [6, 12, 9, 8, 20, 14, 11, 11, 8, 9, 8, 22, 8, 8, 11, 10, 11, 10, 8, 8, 8, 9, 12, 10, 11, 13, 11])
ws.freeze_panes = "C2"
ws.auto_filter.ref = f"A1:AA{ws.max_row}"

for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=len(headers)):
    for cell in row:
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")
    row[11].alignment = Alignment(horizontal="left", vertical="center")
    row[4].alignment = Alignment(horizontal="left", vertical="center")
    g = row[3].value
    row[3].fill = PatternFill("solid", fgColor=GRADE_FILL[g])
    row[3].font = Font(bold=True)
    row[2].number_format = "0.0"
    row[9].number_format = "0%"
    row[10].number_format = "0.000"
    row[13].number_format = "0.000"
    row[25].number_format = "0%"

ws.conditional_formatting.add(
    f"C2:C{ws.max_row}",
    ColorScaleRule(start_type="num", start_value=30, start_color="F8696B",
                   mid_type="num", mid_value=60, mid_color="FFEB84",
                   end_type="num", end_value=90, end_color="63BE7B"))

# ================================================================== #
# Sheet 2 评分规则
# ================================================================== #
ws = wb.create_sheet("02_评分规则")
ws.append(["环节", "规则/指标", "权重或取值", "说明"])
rule_rows = [
    ["数据清洗", "歌曲编号归一", "提取数字→N.mp3", f"原始 {meta['n_variants']} 种写法（含 118mp3 等漏写点号）归并为 {meta['n_songs']} 首歌"],
    ["数据清洗", "重复提交", "同评分者×同歌曲保留首次", f"删除 {meta['n_raw'] - meta['n_dedup']} 条重复记录（{meta['n_raw']}→{meta['n_dedup']}）"],
    ["数据清洗", "直线作答筛查", "效价与唤醒组内SD均<1.0", f"剔除 {'、'.join(meta['excluded'])}（SD 0.74/0.62，与共识相关仅 0.11/0.10）"],
    ["数据清洗", "无效行剔除", "播放问题含 损坏/无法播放/音质 的行", "该行未有效聆听，不计入情绪诱发、一致性、标签效度聚合"],
    ["", "", "", ""],
    ["总分结构", "Base 基础分", "100 分", "E 50 + C 20 + L 15 + D 10 + N 5"],
    ["", "E 情绪诱发有效性", "50 分", "Q5 明确度16 + Q7 覆盖时长12 + Q8 稳定性9 + Q6 情绪可归类8 + 效价/唤醒强度5"],
    ["", "C 跨评分者一致性", "20 分", "20×[0.5×主导情绪份额(扣除随机水平) + 0.5×效价/唤醒离散度]"],
    ["", "L 情感标签效度", "15 分", "15×[0.6×目标象限命中率 + 0.4×均值点与象限理想点接近度]，类别取自《音乐对应关系.csv》"],
    ["", "D 干扰控制", "10 分", "10×(0.6×不熟悉程度 + 0.4×歌词不可理解程度)；越不熟悉、越少语义加工得分越高"],
    ["", "N 样本充分性", "5 分", "5×min(1, 有效评分人数/8)"],
    ["", "", "", ""],
    ["播放门控", "问题严重度 p", "0–1", "损坏/无法播放 1.0；音质 0.8；内容不符 0.8；音量 0.55；卡顿 0.5；重复 0.6；其他 0.5"],
    ["", "多问题叠加", "1−∏(1−pi)", "同一行多选时按概率并集叠加"],
    ["", "自相矛盾处理", "×0.9", "勾选“没有问题”同时又填写具体问题，视为弱化的问题报告"],
    ["", "Q12 补充因素", "0.4–0.8", "音质类 0.6、音量类 0.5、损坏/无法播放 0.8，与 Q11 取并集"],
    ["", "问题指数 w", "0–1", "全部去重记录的严重度均值（Q11/Q12 为客观技术报告，不因评分者情绪作答无效而丢弃）"],
    ["", "播放门控 G", "exp(−3w)×(w>0 时 ×0.75)", "任一条问题即先打 0.75 折“一票否决”，再按问题指数指数衰减；下限 0.05"],
    ["", "最终得分", "Base × G", "0–100 分；技术问题对总分影响最大"],
    ["", "", "", ""],
    ["离散标签", "主标签判定", "≥40% 且唯一领先", "第6题多数票；须同时多于第二名和“无法判断”，否则归入“混合/不明确”"],
    ["", "类内排序", "同一标签内按质量总分降序", "跨类别不做比较，详见工作表 08_离散情绪排序"],
    ["", "", "", ""],
    ["等级", "S ≥ 85", "9 首", "质量优秀，可直接进入正式实验"],
    ["", "A 75–85", "21 首", "质量良好，优先使用"],
    ["", "B 60–75", "39 首", "可用，作为次级备选"],
    ["", "C 40–60", "27 首", "谨慎使用：可能有个别播放问题或诱发偏弱"],
    ["", "D < 40", "24 首", "不建议使用：文件损坏/音质差/标签严重不符"],
]
for r in rule_rows:
    ws.append(r)

for c in range(1, 5):
    ws.cell(row=1, column=c).fill = HDR_FILL
    ws.cell(row=1, column=c).font = HDR_FONT
    ws.cell(row=1, column=c).alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[1].height = 26
set_widths(ws, [12, 24, 28, 95])
for i, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=4), start=2):
    for cell in row:
        cell.alignment = Alignment(vertical="top", wrap_text=True)
        cell.border = BORDER
    if row[0].value:
        for cell in row:
            cell.fill = PatternFill("solid", fgColor="EDEDED")
            cell.font = Font(bold=True)
    ws.row_dimensions[i].height = 34

# 门控示例
start = ws.max_row + 2
ws.cell(row=start, column=1, value="门控效果示例").font = Font(bold=True, size=11)
ws.cell(row=start + 1, column=1, value="情形")
ws.cell(row=start + 1, column=2, value="问题指数 w")
ws.cell(row=start + 1, column=3, value="播放门控 G")
ws.cell(row=start + 1, column=4, value="说明")
examples = [
    ["无任何问题", 0.0, 1.000, "不扣分"],
    ["1/9 人报音量问题", 0.061, 0.624, "单条轻微问题即扣约 38%"],
    ["2/8 人报音质差", 0.200, 0.411, "音质问题可信度较高，扣约 59%"],
    ["3/9 人报文件损坏", 0.333, 0.276, "扣约 72%，基本退出候选"],
    ["半数人报文件损坏/无法播放", 0.500, 0.167, "扣约 83%"],
]
for e in examples:
    ws.append(e)
for c in range(1, 5):
    cell = ws.cell(row=start + 1, column=c)
    cell.fill = HDR_FILL
    cell.font = HDR_FONT
    cell.alignment = Alignment(horizontal="center", vertical="center")
ws.cell(row=start, column=1).font = Font(bold=True, size=11)
for rr in range(start + 1, ws.max_row + 1):
    for c in range(1, 5):
        cell = ws.cell(row=rr, column=c)
        cell.border = BORDER
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.cell(row=rr, column=2).number_format = "0.000"
    ws.cell(row=rr, column=3).number_format = "0.000"

src = ws.max_row + 2
ws.cell(row=src, column=1, value="数据来源：376653806_按文本_情绪诱发情况评估（音乐）_1088_1087(Sheet1).csv；"
                                  "类别标签：音乐对应关系.csv；生成脚本：工作脚本/音乐质量评分.py").alignment = Alignment(wrap_text=True)
ws.merge_cells(start_row=src, start_column=1, end_row=src, end_column=4)
ws.row_dimensions[src].height = 30

# ================================================================== #
# Sheet 3 问题清单
# ================================================================== #
ws = wb.create_sheet("03_问题清单")
ws.append(["排名", "音乐歌曲编号", "质量总分", "质量等级", "有效评分人数", "问题人数",
           "问题报告率", "问题指数", "主要问题", "播放门控", "基础分", "因问题损失分数"])
prob = res[res["w"] > 0].sort_values("rank")
for _, r in prob.iterrows():
    ws.append([int(r["rank"]), r["sid"], round(float(r["Score"]), 1), r["grade"],
               int(r["n_valid"]), int(r["problem_raters"]), round(float(r["raw_rate"]), 2),
               round(float(r["w"]), 3), r["tags"], round(float(r["G"]), 3),
               round(float(r["Base"]), 1), round(float(r["Base"] - r["Score"]), 1)])
style_header(ws)
set_widths(ws, [6, 12, 9, 8, 11, 8, 10, 9, 28, 9, 8, 12])
ws.freeze_panes = "C2"
ws.auto_filter.ref = f"A1:L{ws.max_row}"
for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
    for cell in row:
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")
    row[8].alignment = Alignment(horizontal="left", vertical="center")
    row[9].number_format = "0.000"
    row[3].fill = PatternFill("solid", fgColor=GRADE_FILL[row[3].value])

# ================================================================== #
# Sheet 4 评分者核查
# ================================================================== #
ws = wb.create_sheet("04_评分者核查")
ws.append(["评分者", "有效评分数", "效价均值", "唤醒均值", "效价SD", "唤醒SD",
           "效价共识相关", "唤醒共识相关", "作答时间中位数(秒)", "判定"])
for _, r in rater_stats.sort_values("v_sd", ascending=False).iterrows():
    ws.append([r["rater"], int(r["n"]), round(float(r["v_mean"]), 2), round(float(r["a_mean"]), 2),
               round(float(r["v_sd"]), 2), round(float(r["a_sd"]), 2),
               round(float(r["r_v"]), 2), round(float(r["r_a"]), 2),
               int(r["med_sec"]), "剔除：直线作答" if r["excluded"] else "保留"])
style_header(ws)
set_widths(ws, [10, 10, 9, 9, 8, 8, 11, 11, 16, 18])
for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
    for cell in row:
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")
    if row[9].value.startswith("剔除"):
        row[9].fill = PatternFill("solid", fgColor="F2B8B5")
note_row = ws.max_row + 2
ws.cell(row=note_row, column=1,
        value="注：效价/唤醒共识相关 = 该评分者逐曲均值与其余评分者留一均值的 Pearson 相关。"
              "直线作答者两项 SD 均 < 1.0，且与共识几乎不相关。").alignment = Alignment(wrap_text=True)
ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=10)
ws.row_dimensions[note_row].height = 34

# ================================================================== #
# Sheet 5 逐条评分
# ================================================================== #
ws = wb.create_sheet("05_逐条评分")
ws.append(["问卷序号", "评分者", "音乐歌曲编号", "效价(1-9)", "唤醒(1-9)",
           "主导情绪明确度", "主导情绪", "覆盖时长", "稳定性", "熟悉度", "歌词理解",
           "情绪诱发E", "干扰控制D", "Q11原文", "Q12原文", "问题严重度", "计入情绪聚合"])
for _, r in rows.sort_values(["sid", "rater"]).iterrows():
    ws.append([int(r["idx"]), r["rater"], r["sid"], float(r["v"]), float(r["a"]),
               r["q5"], r["q6"], r["q7"], r["q8"], r["q9"], r["q10"],
               round(float(r["E_row"]), 1), round(float(r["D_row"]), 1),
               r["q11"], r["q12"], round(float(r["p_row"]), 2),
               "是" if r["valid"] else "否"])
style_header(ws)
set_widths(ws, [8, 9, 12, 8, 8, 26, 14, 18, 22, 10, 13, 10, 10, 30, 22, 10, 11])
ws.freeze_panes = "D2"
ws.auto_filter.ref = f"A1:Q{ws.max_row}"
for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
    for cell in row:
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)
    row[5].alignment = Alignment(horizontal="left", vertical="center")
    row[13].alignment = Alignment(horizontal="left", vertical="center")
    if row[16].value == "否":
        row[16].fill = PatternFill("solid", fgColor="F2B8B5")

# ================================================================== #
# Sheet 6 稳健性与置信区间
# ================================================================== #
ws = wb.create_sheet("06_稳健性")
ws.append(["检验场景", "与主排序的 Spearman 秩相关", "解读"])
interp = {
    "含无效评分者": "把直线作答者放回样本，排序几乎不变",
    "E权重+20%": "情绪诱发权重上调 20%，排序高度一致",
    "C权重+20%": "一致性权重上调 20%，排序高度一致",
    "L权重+20%": "标签效度权重上调 20%，排序高度一致",
    "门控k=2.0": "门控衰减更平缓，排序几乎不变",
    "门控k=4.0": "门控衰减更陡峭，排序几乎不变",
    "不含标签效度L": "完全不使用映射表，排序仍高度一致（偏离主要来自标签明显不符的曲目，如 108.mp3）",
    "不含干扰控制D": "不考虑熟悉度/歌词干扰，排序几乎不变",
}
for _, r in sens.iterrows():
    ws.append([r.iloc[0], float(r.iloc[1]), interp.get(r.iloc[0], "")])
style_header(ws)
set_widths(ws, [20, 24, 55])
for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
    for cell in row:
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")
    row[1].number_format = "0.0000"
    row[2].alignment = Alignment(horizontal="left", vertical="center")

r0 = ws.max_row + 2
notes = [
    "置信区间说明：对 8 名评分者做 500 次有放回重抽样（固定随机种子 20260810），"
    "重新计算单曲得分与排名，取 2.5%–97.5% 分位。",
    "Q11/Q12 为文件层面的客观技术事实，重抽样时固定不变，因此技术问题歌曲的分数区间较窄。",
    "由于仅 8 名评分者，单曲名次的区间较宽；Top 10 稳定处于前 20 名，组内具体名次不宜过度解读。",
]
for i, t in enumerate(notes):
    c = ws.cell(row=r0 + i, column=1, value=t)
    c.alignment = Alignment(wrap_text=True)
    ws.merge_cells(start_row=r0 + i, start_column=1, end_row=r0 + i, end_column=3)
    ws.row_dimensions[r0 + i].height = 30

# ================================================================== #
# Sheet 7 类别内排序
# ================================================================== #
ws = wb.create_sheet("07_类别内排序")
ws.append(["情感类别", "类别内排名", "总排名", "音乐歌曲编号", "质量总分", "质量等级", "主要问题"])
for cat in ["HVHA", "HVLA", "LVHA", "LVLA"]:
    sub = res[res["cat"] == cat].sort_values("rank_in_cat")
    for _, r in sub.iterrows():
        ws.append([cat, int(r["rank_in_cat"]), int(r["rank"]), r["sid"],
                   round(float(r["Score"]), 1), r["grade"],
                   r["tags"] if isinstance(r["tags"], str) and r["tags"] else "无"])
style_header(ws)
set_widths(ws, [10, 11, 8, 12, 9, 8, 24])
ws.auto_filter.ref = f"A1:G{ws.max_row}"
for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
    for cell in row:
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")
    row[6].alignment = Alignment(horizontal="left", vertical="center")
    row[5].fill = PatternFill("solid", fgColor=GRADE_FILL[row[5].value])

# ================================================================== #
# Sheet 8 离散情绪排序
# ================================================================== #
ws = wb.create_sheet("08_离散情绪排序")
DORDER = ["悲伤/失落", "激昂", "愉快", "温馨/放松", "恐惧/不安", "混合/不明确"]
TITLE_FILL = PatternFill("solid", fgColor="DCE6F1")

ws.append(["一、离散情绪类别汇总（第6题多数票：≥40%、严格多于第二名、且多于“无法判断”）"])
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=10)
ws.cell(row=1, column=1).font = Font(bold=True, size=12)
ws.cell(row=1, column=1).fill = TITLE_FILL
ws.row_dimensions[1].height = 24

ws.append(["离散标签", "歌曲数", "平均分", "最高分", "S", "A", "B", "C", "D", "最高分曲目"])
sum_hdr = ws.max_row
style_header(ws, row=sum_hdr, ncol=10)
sum_rows = []
for lab in DORDER:
    sub = res[res["discrete"] == lab]
    if len(sub) == 0:
        continue
    best = sub.sort_values("Score", ascending=False).iloc[0]
    gc_ = sub["grade"].value_counts()
    ws.append([lab, len(sub), round(float(sub["Score"].mean()), 1), round(float(sub["Score"].max()), 1),
               int(gc_.get("S", 0)), int(gc_.get("A", 0)), int(gc_.get("B", 0)),
               int(gc_.get("C", 0)), int(gc_.get("D", 0)),
               f'{best["sid"]}（{best["Score"]:.1f}）'])
    sum_rows.append(ws.max_row)
for rr in sum_rows:
    for c in range(1, 11):
        cell = ws.cell(row=rr, column=c)
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(row=rr, column=2).number_format = "0"
    ws.cell(row=rr, column=3).number_format = "0.0"
    ws.cell(row=rr, column=4).number_format = "0.0"

# 明细
ttl2 = ws.max_row + 2
ws.cell(row=ttl2, column=1, value="二、各类别内部排序（同一标签内按质量分从高到低；跨类别不做比较）")
ws.merge_cells(start_row=ttl2, start_column=1, end_row=ttl2, end_column=10)
ws.cell(row=ttl2, column=1).font = Font(bold=True, size=12)
ws.cell(row=ttl2, column=1).fill = TITLE_FILL
ws.row_dimensions[ttl2].height = 24

ws.append(["离散标签", "类内排名", "总排名", "音乐歌曲编号", "质量总分", "质量等级",
           "标签一致率", "评分人数", "四象限", "主要问题"])
det_hdr = ws.max_row
style_header(ws, row=det_hdr, ncol=10)
det_rows = []
for lab in DORDER:
    sub = res[res["discrete"] == lab].sort_values(["rank_in_discrete", "Score"], ascending=[True, False])
    for _, r in sub.iterrows():
        ws.append([lab, int(r["rank_in_discrete"]), int(r["rank"]), r["sid"],
                   round(float(r["Score"]), 1), r["grade"], round(float(r["discrete_agree"]), 2),
                   int(r["n_valid"]), r["cat"],
                   r["tags"] if isinstance(r["tags"], str) and r["tags"] else "无"])
        det_rows.append(ws.max_row)
for rr in det_rows:
    for c in range(1, 11):
        cell = ws.cell(row=rr, column=c)
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(row=rr, column=5).number_format = "0.0"
    ws.cell(row=rr, column=7).number_format = "0%"
    ws.cell(row=rr, column=10).alignment = Alignment(horizontal="left", vertical="center")
    ws.cell(row=rr, column=6).fill = PatternFill("solid", fgColor=GRADE_FILL[ws.cell(row=rr, column=6).value])

set_widths(ws, [13, 9, 8, 12, 9, 8, 11, 9, 8, 26])
ws.auto_filter.ref = f"A{det_hdr}:J{ws.max_row}"

note = ws.max_row + 2
ws.cell(row=note, column=1,
        value="说明：离散标签来自第6题“实际产生的主导情绪”的多数票，是评分者的主观归类；"
              "四象限（HVHA/HVLA/LVHA/LVLA）来自连续标签（效价/唤醒）。两套标签不是一一对应："
              "例如“悲伤/失落”会分布在 HVLA、LVHA、LVLA 三个象限。").alignment = Alignment(wrap_text=True, vertical="top")
ws.merge_cells(start_row=note, start_column=1, end_row=note, end_column=10)
ws.row_dimensions[note].height = 46

xlsx_path = os.path.join(OUT, "音乐歌曲质量评分与排序.xlsx")
wb.save(xlsx_path)
print("saved", xlsx_path)

# 离散情绪排序单独导出 CSV
_d = res.copy()
_order = {k: i for i, k in enumerate(DORDER)}
_d["__o"] = _d["discrete"].map(_order)
_d = _d.sort_values(["__o", "rank_in_discrete", "Score"], ascending=[True, True, False])
_dout = pd.DataFrame({
    "离散标签": _d["discrete"],
    "类内排名": _d["rank_in_discrete"],
    "总排名": _d["rank"],
    "音乐歌曲编号": _d["sid"],
    "质量总分": _d["Score"].round(1),
    "质量等级": _d["grade"],
    "标签一致率": _d["discrete_agree"].round(2),
    "评分人数": _d["n_valid"],
    "四象限": _d["cat"],
    "主要问题": _d["tags"].replace("", "无"),
})
_dout.to_csv(os.path.join(OUT, "离散情绪分类排序.csv"), index=False, encoding="utf-8-sig")
print("saved discrete csv")

# ================================================================== #
# 图
# ================================================================== #
fp = r"C:\Windows\Fonts\msyh.ttc"
if os.path.exists(fp):
    font_manager.fontManager.addfont(fp)
plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

fig, axes = plt.subplots(1, 2, figsize=(15, 7.2), gridspec_kw={"width_ratios": [1, 1]})
for ax, data, title in [(axes[0], res.head(18).iloc[::-1], "质量最高的 18 首"),
                        (axes[1], res.tail(18).iloc[::-1], "质量最低的 18 首")]:
    colors = [GRADE_COLOR[g] for g in data["grade"]]
    bars = ax.barh(data["sid"], data["Score"], color=colors, edgecolor="white", height=0.72)
    for b, s in zip(bars, data["Score"]):
        ax.text(b.get_width() + 1.2, b.get_y() + b.get_height() / 2, f"{s:.1f}",
                va="center", fontsize=8.5, color="#333333")
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.set_xlim(0, 100)
    ax.set_xlabel("质量总分", fontsize=10)
    ax.tick_params(axis="y", labelsize=9)
    ax.grid(axis="x", alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)

from matplotlib.patches import Patch
legend = [Patch(facecolor=GRADE_COLOR[g], label=f"{g} 级") for g in ["S", "A", "B", "C", "D"]]
fig.legend(handles=legend, loc="lower center", ncol=5, frameon=False, fontsize=9.5)
fig.suptitle("山科音乐数据集：单曲质量评分排序（共 120 首）", fontsize=15, fontweight="bold", y=0.98)
fig.tight_layout(rect=[0, 0.05, 1, 0.95])
png_path = os.path.join(OUT, "质量排序_Top18_Bottom18.png")
fig.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
plt.close(fig)
print("saved", png_path)
