"""Build the group-meeting deck for EEG-EmoStudio.

Run with the bundled Python that has python-pptx::

    <bundled-python> scripts/build_ppt.py

The deck uses the same visual language as the local web console and embeds
current page screenshots from ``ppt_assets/``.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "ppt_assets"
import os
OUT = Path(os.environ.get("PPT_OUT", str(ROOT / "deliverables" / "EEG-EmoStudio_组会汇报_20261108.pptx")))

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
W, H = 13.333, 7.5
INK = "102033"
INK_SOFT = "33465E"
MUTED = "68788E"
MUTED_2 = "92A0B2"
LINE = "DDE6F0"
BG = "F4F7FB"
WHITE = "FFFFFF"
NAVY = "082338"
TEAL = "0C7368"
TEAL_2 = "1B9A89"
MINT = "6FF2DB"
BLUE = "2F6FED"
AMBER = "B45309"
AMBER_BG = "FFF6E8"
RED = "B42318"
GREEN = "067647"
FONT = "Microsoft YaHei"
FONT_MONO = "Cascadia Code"


def rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value)


def set_font(run, size: float, bold: bool = False, color: str = INK,
             name: str = FONT, italic: bool = False) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = rgb(color)
    rpr = run._r.get_or_add_rPr()
    ea = rpr.find(qn("a:ea"))
    if ea is None:
        ea = rpr.makeelement(qn("a:ea"), {})
        rpr.append(ea)
    ea.set("typeface", name)


def transparency(shape, pct: float) -> None:
    """Set solid fill transparency in the range 0..1."""
    try:
        solid = shape.fill._xPr.find(qn("a:solidFill"))
        if solid is None:
            return
        color = solid.find(qn("a:srgbClr"))
        if color is None:
            return
        alpha = color.find(qn("a:alpha"))
        if alpha is None:
            alpha = color.makeelement(qn("a:alpha"), {})
            color.append(alpha)
        alpha.set("val", str(int((1 - pct) * 100000)))
    except Exception:
        pass


def textbox(slide, x, y, w, h, text, size=12, color=INK, bold=False,
            align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font=FONT,
            line_spacing=1.0, margins=(0, 0, 0, 0)):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(margins[0])
    tf.margin_right = Inches(margins[1])
    tf.margin_top = Inches(margins[2])
    tf.margin_bottom = Inches(margins[3])
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    p.space_before = Pt(0)
    p.space_after = Pt(0)
    p.line_spacing = line_spacing
    run = p.add_run()
    run.text = text
    set_font(run, size, bold=bold, color=color, name=font)
    return box


def paragraphs(slide, x, y, w, h, items, anchor=MSO_ANCHOR.TOP, margins=(0, 0, 0, 0)):
    """items: list of dict(text,size,color,bold,space_before,space_after,line_spacing,align)."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(margins[0])
    tf.margin_right = Inches(margins[1])
    tf.margin_top = Inches(margins[2])
    tf.margin_bottom = Inches(margins[3])
    tf.vertical_anchor = anchor
    first = True
    for item in items:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = item.get("align", PP_ALIGN.LEFT)
        p.space_before = Pt(item.get("space_before", 0))
        p.space_after = Pt(item.get("space_after", 0))
        p.line_spacing = item.get("line_spacing", 1.05)
        run = p.add_run()
        run.text = item["text"]
        set_font(run, item.get("size", 11), bold=item.get("bold", False),
                 color=item.get("color", INK), font=item.get("font", FONT))
    return box


def rect(slide, x, y, w, h, fill=WHITE, line=LINE, radius=True, line_width=0.8):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius:
        try:
            shape.adjustments[0] = 0.06
        except Exception:
            pass
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    shape.line.color.rgb = rgb(line)
    shape.line.width = Pt(line_width)
    shape.shadow.inherit = False
    return shape


def pill(slide, x, y, w, h, text, fill=WHITE, color=MUTED, line=LINE, size=9):
    shape = rect(slide, x, y, w, h, fill=fill, line=line)
    shape.adjustments[0] = 0.5
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = False
    tf.margin_left = Inches(0.04)
    tf.margin_right = Inches(0.04)
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = text
    set_font(run, size, bold=True, color=color)
    return shape


def circle_number(slide, x, y, d, number, fill=TEAL, color=WHITE):
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    shape.line.fill.background()
    shape.shadow.inherit = False
    tf = shape.text_frame
    tf.clear()
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = str(number)
    set_font(run, 10, bold=True, color=color)
    return shape


def line(slide, x1, y1, x2, y2, color=LINE, width=1.2):
    conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    conn.line.color.rgb = rgb(color)
    conn.line.width = Pt(width)
    return conn


def arrow(slide, x, y, w, h, color=TEAL):
    shape = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(color)
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def background(slide, color=BG):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(W), Inches(H))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(color)
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def add_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def header(slide, kicker, title, subtitle=None, page=None):
    textbox(slide, 0.68, 0.38, 11.8, 0.26, kicker.upper(), 8.5, TEAL, True)
    textbox(slide, 0.68, 0.63, 11.9, 0.55, title, 25, INK, True)
    if subtitle:
        textbox(slide, 0.68, 1.2, 11.9, 0.3, subtitle, 10, MUTED)
    line(slide, 0.68, 1.55, 12.65, 1.55, LINE, 0.9)
    if page is not None:
        textbox(slide, 12.1, 7.16, 0.55, 0.2, f"{page:02d}", 8, MUTED_2, True, PP_ALIGN.RIGHT)
    textbox(slide, 0.68, 7.16, 7.0, 0.2, "EEG-EmoStudio · 组会汇报 · 2026-11-08", 7.5, MUTED_2)


def picture_card(slide, path, x, y, w, h, caption=None):
    img = Image.open(path)
    img_ratio = img.width / img.height
    box_ratio = w / h
    if img_ratio > box_ratio:
        draw_w = w
        draw_h = w / img_ratio
    else:
        draw_h = h
        draw_w = h * img_ratio
    px = x + (w - draw_w) / 2
    py = y + (h - draw_h) / 2
    # thin outer card
    rect(slide, x - 0.06, y - 0.06, w + 0.12, h + 0.12, fill=WHITE, line=LINE)
    slide.shapes.add_picture(str(path), Inches(px), Inches(py), Inches(draw_w), Inches(draw_h))
    if caption:
        textbox(slide, x, y + h + 0.1, w, 0.22, caption, 7.5, MUTED_2)


def stat_card(slide, x, y, w, h, label, value, detail, color=TEAL):
    rect(slide, x, y, w, h, fill=WHITE, line=LINE)
    textbox(slide, x + 0.16, y + 0.14, w - 0.3, 0.22, label, 8.5, MUTED)
    textbox(slide, x + 0.16, y + 0.38, w - 0.3, 0.4, value, 21, color, True)
    textbox(slide, x + 0.16, y + 0.82, w - 0.3, 0.3, detail, 7.8, MUTED_2)


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def cover(prs):
    slide = add_slide(prs)
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(W), Inches(H))
    bg.line.fill.background()
    bg.fill.gradient()
    bg.fill.gradient_angle = 118
    stops = bg.fill.gradient_stops
    stops[0].color.rgb = rgb("071F32")
    stops[1].color.rgb = rgb("0C6B62")
    bg.shadow.inherit = False

    # soft circles / waves
    for x, y, d, color, pct in [
        (9.8, -0.8, 4.2, MINT, 0.92),
        (11.2, 4.9, 3.4, BLUE, 0.92),
        (-0.9, 5.8, 2.8, TEAL_2, 0.82),
    ]:
        c = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
        c.fill.solid()
        c.fill.fore_color.rgb = rgb(color)
        c.line.fill.background()
        transparency(c, pct)
    for y in [5.15, 5.55, 5.95]:
        wav = slide.shapes.add_shape(MSO_SHAPE.WAVE, Inches(8.0), Inches(y), Inches(5.6), Inches(0.5))
        wav.fill.background()
        wav.line.color.rgb = rgb(MINT)
        wav.line.width = Pt(1.1)
        transparency(wav, 0.55)
        wav.shadow.inherit = False

    slide.shapes.add_picture(str(ASSETS / "logo.png"), Inches(0.72), Inches(0.55), Inches(0.55), Inches(0.55))
    textbox(slide, 1.38, 0.61, 3.5, 0.24, "EEG-EmoStudio", 14, WHITE, True)
    textbox(slide, 1.4, 0.86, 3.0, 0.18, "EEG RESEARCH OS", 7.2, "9FC3C8", True)

    pill(slide, 0.72, 1.55, 2.0, 0.3, "组会汇报 · 2026.11.08", fill="103C4D", color=MINT, line="2A5864", size=8)

    textbox(slide, 0.72, 2.0, 11.8, 0.9, "从数据制备到模型训练：", 29, WHITE, True)
    textbox(slide, 0.72, 2.52, 11.8, 0.9, "一个可复现的 EEG 情绪识别工作台", 33, WHITE, True)
    textbox(slide, 0.75, 3.58, 8.6, 0.4, "EEG-EmoStudio 的设计思路、核心功能与当前进展", 13, "A9C8D0")

    line(slide, 0.75, 5.92, 6.7, 5.92, "3C6E78", 0.8)
    textbox(slide, 0.75, 6.08, 2.0, 0.25, "汇报人", 8, "7FAAB4")
    textbox(slide, 1.45, 6.06, 1.4, 0.3, "赵祥生", 11, WHITE, True)
    textbox(slide, 2.85, 6.08, 2.3, 0.25, "指导教师", 8, "7FAAB4")
    textbox(slide, 3.65, 6.06, 2.4, 0.3, "曾庆田 教授", 11, WHITE, True)
    textbox(slide, 0.75, 6.58, 5.4, 0.25, "软件工程 · 本科毕业设计", 8.5, "7FAAB4")
    textbox(slide, 10.2, 6.55, 2.5, 0.25, "LOCAL FIRST · REPRODUCIBLE", 7.5, MINT, True, PP_ALIGN.RIGHT)
    notes(slide, "各位老师、同学晚上好，我是赵祥生。今晚汇报的是我这段时间做的 EEG-EmoStudio：它不是一个单独的模型，而是一套把数据制备、特征、训练和报告串起来的工作台。")

    return slide


def slide_one_page(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Overview", "一页看懂：系统解决什么问题", "把“材料—问卷—EEG—特征—模型—报告”做成同一条可追溯链路", 2)
    cards = [
        ("01", "数据制备", "240 条刺激、2,356 条问卷", "清洗 / 质量门控 / 80 条平衡选材", TEAL),
        ("02", "模型训练", "raw.npz → 5 频带 DE", "LOSO 跨被试 / 多模型 / 指标与图表", BLUE),
        ("03", "工程证据", "配置、manifest、SHA-256", "每个数字都能回到数据版本与随机种子", "6941C6"),
    ]
    for i, (num, title, value, desc, color) in enumerate(cards):
        x = 0.7 + i * 4.1
        rect(slide, x, 1.82, 3.82, 1.95, fill=WHITE, line=LINE)
        circle_number(slide, x + 0.2, 1.99, 0.34, num, fill=color)
        textbox(slide, x + 0.67, 1.99, 2.9, 0.3, title, 13, INK, True)
        textbox(slide, x + 0.2, 2.48, 3.4, 0.3, value, 11.5, color, True)
        textbox(slide, x + 0.2, 2.86, 3.4, 0.55, desc, 9.3, MUTED, line_spacing=1.25)

    rect(slide, 0.7, 4.08, 11.95, 0.78, fill="F8FBFD", line="E4EDF5")
    stages = ["刺激库", "预评价", "审计/选材", "EEG / 特征", "LOSO 训练", "报告"]
    for i, stage in enumerate(stages):
        x = 0.9 + i * 1.95
        pill(slide, x, 4.3, 1.45, 0.34, stage, fill=WHITE, color=INK_SOFT, line=LINE, size=8.2)
        if i < len(stages) - 1:
            arrow(slide, x + 1.5, 4.4, 0.28, 0.12, color="AFC4D5")

    stat_y = 5.25
    stats = [("240", "刺激材料"), ("2,356", "预评价问卷"), ("80", "平衡选材"), ("1,080", "SEED-IV trial")]
    for i, (value, label) in enumerate(stats):
        x = 0.7 + i * 3.02
        textbox(slide, x, stat_y, 2.4, 0.48, value, 27, INK, True)
        textbox(slide, x, stat_y + 0.48, 2.4, 0.22, label, 8.3, MUTED)

    textbox(slide, 0.7, 6.45, 11.9, 0.26, "目标不是“再跑一个模型”，而是让一次情绪实验从材料到结论都可复核；58 项自动化测试通过。", 9.6, TEAL, True)
    notes(slide, "先用一页说明全貌：数据制备、模型训练、工程证据三块。下面的流水线是后面每一页展开的顺序。")

    return slide


def slide_problems(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Motivation", "为什么不是再写一套脚本？", "真实问题不在“模型不够新”，而在数据与评估的每个环节都可能失控", 3)
    items = [
        ("数据不可审计", "146 种视频编号写法、文字锚点、播放问题；材料质量分缺少来源与复核。", "01", AMBER),
        ("标签不确定", "预设情绪 ≠ 被试实际体验；26/120 条音乐片段偏离 60±15 s。", "02", BLUE),
        ("评估易泄漏", "标准化、早停、调参若使用测试被试，跨被试结果会虚高且不可复现。", "03", TEAL),
    ]
    for i, (title, body, num, color) in enumerate(items):
        x = 0.7 + i * 4.1
        rect(slide, x, 1.8, 3.82, 2.55, fill=WHITE, line=LINE)
        textbox(slide, x + 0.22, 2.0, 0.6, 0.5, num, 22, color, True)
        textbox(slide, x + 0.22, 2.55, 3.3, 0.3, title, 14, INK, True)
        textbox(slide, x + 0.22, 2.98, 3.35, 0.9, body, 9.5, MUTED, line_spacing=1.35)
        textbox(slide, x + 0.22, 3.78, 3.3, 0.25, ["→ 需要审计与质量门控", "→ 需要预设/实际双标签", "→ 需要 LOSO + 代码断言"][i], 7.8, color, True)
        line(slide, x + 0.22, 4.1, x + 3.55, 4.1, "EDF2F7", 1)

    rect(slide, 0.7, 4.75, 11.95, 1.25, fill=NAVY, line=NAVY)
    textbox(slide, 0.98, 4.98, 11.4, 0.35, "所以系统的切入点不是“再换一个网络”", 15, WHITE, True)
    textbox(slide, 0.98, 5.38, 11.4, 0.3, "而是把数据、训练、证据放进同一条可复核的流水线，让方法改进发生在可信的基线上。", 10.5, "A9C8D0")
    textbox(slide, 0.7, 6.45, 11.9, 0.26, "三个痛点分别对应：数据审计、材料选材、LOSO 防泄漏。", 9.5, TEAL, True)
    notes(slide, "这三个问题是我在实际整理数据和看论文时遇到的。尤其跨被试，如果划分或标准化不严谨，结果很容易看起来很好但不可复现。")

    return slide


def slide_principles(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Design principles", "四个设计原则，决定系统长什么样", "先保证可信，再追求更复杂的模型", 4)
    principles = [
        ("单一事实源", "CLI、Web、论文读同一套 JSON / CSV / NPZ，不在页面里复制业务规则。", TEAL),
        ("契约优先", "raw.npz、features.npz、manifest 字段固定；新增数据集只写适配器。", BLUE),
        ("泄漏感知", "被试隔离、训练折内标准化、OOF 汇总；划分有代码断言。", "6941C6"),
        ("本地优先", "FastAPI + Jinja2 + 原生 JS；数据不出本机，答辩现场一条命令可启动。", AMBER),
    ]
    for i, (title, body, color) in enumerate(principles):
        col, row = i % 2, i // 2
        x = 0.7 + col * 6.1
        y = 1.82 + row * 2.15
        rect(slide, x, y, 5.85, 1.82, fill=WHITE, line=LINE)
        line(slide, x, y, x, y + 1.82, color, 3)
        textbox(slide, x + 0.22, y + 0.22, 5.3, 0.3, title, 14, INK, True)
        textbox(slide, x + 0.22, y + 0.65, 5.35, 0.95, body, 9.7, MUTED, line_spacing=1.35)

    textbox(slide, 0.7, 6.45, 11.9, 0.26, "明确不做：多用户/公网/临床诊断；先把科研闭环跑通。", 9.5, TEAL, True)
    notes(slide, "这四个原则是取舍：不用 React、不接数据库、不做权限，都是为了让系统在毕业设计周期内可靠地跑起来。")

    return slide


def slide_architecture(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Architecture", "从数据到证据：四层架构", "页面、算法、数据契约分层，Web 不重写算法", 5)
    layers = [
        ("表现层", "8 个页面 · CLI · HTML 报告", "页面路由 / 表单 / SVG 图表 / 下载", "E8F3F1", TEAL),
        ("应用服务层", "审计 · 选材 · 特征 · 训练 · 报告", "编排用例、任务队列、进度与日志", "EAF0FF", BLUE),
        ("领域层", "数据规则 · 划分 · 指标 · 模型", "编号归一 / LOSO / 指标 / DualView", "F2ECFF", "6941C6"),
        ("数据与基础设施层", "CSV · NPZ · JSON · 媒体 · 检查点", "artifact 目录 + SHA-256 + 运行清单", "FFF4E2", AMBER),
    ]
    for i, (name, sub, detail, fill, color) in enumerate(layers):
        y = 1.82 + i * 1.12
        rect(slide, 0.7, y, 7.2, 0.94, fill=fill, line="DCE5EF")
        textbox(slide, 0.9, y + 0.13, 1.7, 0.28, name, 11.5, color, True)
        textbox(slide, 2.5, y + 0.1, 5.1, 0.28, sub, 10.2, INK_SOFT, True)
        textbox(slide, 2.5, y + 0.43, 5.2, 0.25, detail, 8.3, MUTED)
        if i < 3:
            arrow(slide, 3.95, y + 0.98, 0.22, 0.1, color="A9BCCE")

    # right screenshot
    picture_card(slide, ASSETS / "shot_dashboard.png", 8.25, 1.85, 4.25, 2.78)
    textbox(slide, 8.25, 4.78, 4.25, 0.25, "Web 控制台 · 工作台", 8.5, MUTED, True)
    for i, (label, color) in enumerate([("8 pages", TEAL), ("20+ APIs", BLUE), ("Job queue", "6941C6")]):
        pill(slide, 8.25 + i * 1.35, 5.15, 1.22, 0.28, label, fill=WHITE, color=color, line=LINE, size=7.2)
    textbox(slide, 0.7, 6.45, 7.2, 0.26, "同一套数据服务同时支撑 CLI 与 Web。", 9.5, TEAL, True)
    notes(slide, "四层架构的关键是：Web 只是表现层，真正的规则和算法在领域层/CLI，页面不复制逻辑。")

    return slide


def slide_feature_map(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Product", "8 个页面，覆盖完整科研工作流", "不是静态原型：表单会启动任务，任务结果落盘并可下载", 6)
    features = [
        ("工作台", "资产总览 / 质量分布 / 流水线", "01", TEAL),
        ("数据审计", "评分者 / 播放问题 / 质量排序", "02", AMBER),
        ("材料选材", "分层规则 / 80 条清单 / 导出", "03", BLUE),
        ("数据集", "上传 raw.npz / 提取 DE / manifest", "04", TEAL),
        ("模型训练", "模型 / LOSO / 实时日志 / 指标", "05", "6941C6"),
        ("实验记录", "运行对比 / 报告 / 指标 JSON", "06", BLUE),
        ("项目文档", "14 份 DOCX/PDF / 打包下载", "07", AMBER),
        ("系统状态", "API 健康 / 数据边界 / 任务记录", "08", TEAL),
    ]
    for i, (title, desc, num, color) in enumerate(features):
        col, row = i % 4, i // 4
        x = 0.7 + col * 3.08
        y = 1.82 + row * 2.05
        rect(slide, x, y, 2.88, 1.75, fill=WHITE, line=LINE)
        textbox(slide, x + 0.16, y + 0.14, 0.45, 0.2, num, 8, color, True)
        textbox(slide, x + 0.16, y + 0.46, 2.5, 0.3, title, 12, INK, True)
        textbox(slide, x + 0.16, y + 0.86, 2.52, 0.65, desc, 8.6, MUTED, line_spacing=1.25)

    textbox(slide, 0.7, 6.2, 11.9, 0.3, "页面职责按科研流程拆，不按技术栈拆；每个页面只回答一个“下一步做什么”。", 9.5, TEAL, True)
    notes(slide, "八个页面不是堆功能，是按工作流拆的。每个页面有一个主要动作，避免研究者在一堆表格里找按钮。")

    return slide


def slide_audit(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Data audit", "先把数据说清楚：审计不是走形式", "把 2,356 条问卷与 240 条材料变成可复核的证据", 7)
    stats = [
        ("1,227 / 1,269", "视频问卷（去重后）", "删除 42 条重复提交"),
        ("1,072 / 1,087", "音乐问卷（去重后）", "删除 15 条重复提交"),
        ("22 / 29", "视频 / 音乐问题刺激", "模糊、杂音、损坏、卡顿"),
    ]
    for i, (value, label, detail) in enumerate(stats):
        y = 1.78 + i * 1.27
        rect(slide, 0.7, y, 5.6, 1.08, fill=WHITE, line=LINE)
        textbox(slide, 0.88, y + 0.14, 2.1, 0.42, value, 19, TEAL, True)
        textbox(slide, 2.9, y + 0.17, 3.2, 0.28, label, 9.5, INK, True)
        textbox(slide, 2.9, y + 0.5, 3.15, 0.26, detail, 8, MUTED)
    rect(slide, 0.7, 5.62, 5.6, 0.72, fill=AMBER_BG, line="F1D9AE")
    textbox(slide, 0.9, 5.79, 5.2, 0.25, "另有：编号 146 / 129 种写法 · 26/120 音乐片段偏离 60±15 s", 8.4, AMBER, True)
    textbox(slide, 0.7, 6.5, 5.6, 0.25, "质量分 ≠ 情绪标签真值；它只回答“材料是否可用”。", 8.6, MUTED)
    picture_card(slide, ASSETS / "shot_audit.png", 6.55, 1.78, 6.1, 4.02)
    textbox(slide, 6.55, 5.95, 6.1, 0.25, "数据审计页 · 真实运行结果：计数、问题清单与质量排序同源", 7.8, MUTED)
    notes(slide, "审计结果和既有质量报告对上了：重复数、问题刺激数一致。这一步为后面的选材提供了可解释的依据。")

    return slide


def slide_selection(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Stimulus curation", "从 240 条到 80 条：把实验设计写进代码", "不是总榜前 N，而是按“模态 × 四象限”分层选材", 8)
    rect(slide, 0.7, 1.8, 5.65, 0.72, fill=NAVY, line=NAVY)
    textbox(slide, 0.92, 1.98, 5.2, 0.32, "2 模态 × 4 象限 × 10 条 = 80 条", 16, WHITE, True)
    rules = [
        ("先分层", "模态内按 HVHA/HVLA/LVHA/LVLA 分组，不跨象限比分数。"),
        ("再排序", "等级 S→A→B→C→D，同等级按质量总分降序。"),
        ("给理由", "输出每条材料的选择理由、类内排名与主要问题。"),
        ("会告警", "某层不足时明确提示，而不是悄悄降低标准。"),
    ]
    for i, (title, body) in enumerate(rules):
        y = 2.75 + i * 0.73
        circle_number(slide, 0.72, y + 0.02, 0.24, str(i + 1), fill=TEAL)
        textbox(slide, 1.08, y - 0.01, 1.2, 0.25, title, 9.5, INK, True)
        textbox(slide, 2.12, y - 0.02, 4.0, 0.48, body, 8.6, MUTED, line_spacing=1.3)
    rect(slide, 0.7, 5.78, 5.65, 0.8, fill="F8FBFD", line="E4EDF5")
    textbox(slide, 0.9, 5.91, 5.2, 0.25, "结果：S 26 · A 22 · B 32 · 无 C/D", 10, TEAL, True)
    textbox(slide, 0.9, 6.2, 5.2, 0.22, "音乐 HVLA 最低 67.4，建议先做 5–10 人预实验。", 7.8, MUTED)
    picture_card(slide, ASSETS / "shot_selection.png", 6.55, 1.8, 6.1, 4.02)
    textbox(slide, 6.55, 5.95, 6.1, 0.25, "材料选材页 · 规则、分层结果、80 条清单与下载", 7.8, MUTED)
    notes(slide, "选材的关键是避免 HVHA 垄断总榜。按象限分层后，每个情绪条件都有足够 Trial，同时优先 S/A。")

    return slide


def slide_dataset(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Dataset & features", "统一契约：raw.npz → 5 频带 DE", "先定义数据形状，再谈模型；所有派生数据带 manifest", 9)
    rect(slide, 0.7, 1.8, 5.55, 1.85, fill=NAVY, line=NAVY)
    code = [
        "x        (trials, channels, samples)   float32 µV",
        "y        (trials,)                    int64 0..K-1",
        "subjects (trials,)                    S01…",
        "fs       scalar                       Hz",
    ]
    for i, line_text in enumerate(code):
        textbox(slide, 0.9, 2.02 + i * 0.34, 5.15, 0.28, line_text, 7.8, "C7DED8", font=FONT_MONO)
    textbox(slide, 0.7, 3.82, 5.55, 0.25, "输入：一次 trial 的固定长度 EEG 数组", 8.3, MUTED)
    arrow(slide, 3.25, 4.12, 0.55, 0.2, color=TEAL)
    rect(slide, 0.7, 4.45, 5.55, 1.02, fill="F8FBFD", line="E4EDF5")
    textbox(slide, 0.9, 4.61, 5.2, 0.3, "DE = 0.5 · ln(2πeσ²)", 13, TEAL, True)
    textbox(slide, 0.9, 4.98, 5.2, 0.26, "δ 1–4 · θ 4–8 · α 8–14 · β 14–30 · γ 30–45 Hz；1 s 窗", 8.2, MUTED)
    textbox(slide, 0.7, 5.68, 5.55, 0.52, "输出：features.npz + manifest（形状/类别/被试/SHA-256）+ build.json", 8.4, INK_SOFT, True, line_spacing=1.35)
    picture_card(slide, ASSETS / "shot_datasets.png", 6.55, 1.8, 6.1, 4.02)
    textbox(slide, 6.55, 5.95, 6.1, 0.25, "数据集页 · 上传、特征参数、可训练数据集与数据契约", 7.8, MUTED)
    notes(slide, "数据契约是我觉得最值得在组里统一的：不管用 SEED、DEAP 还是自采，都先落成 raw.npz，后面的代码不变。")

    return slide


def slide_training(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Training", "训练不是调参：先保证划分诚实", "LOSO 每折留一名被试；验证、标准化、早停都不碰测试被试", 10)
    # fold diagram
    textbox(slide, 0.7, 1.78, 5.6, 0.26, "Leave-One-Subject-Out", 8.5, TEAL, True)
    for i in range(8):
        x = 0.7 + i * 0.68
        fill = AMBER if i == 3 else "E8F3F1"
        color = WHITE if i == 3 else TEAL
        shape = rect(slide, x, 2.12, 0.52, 0.52, fill=fill, line=fill)
        textbox(slide, x, 2.26, 0.52, 0.2, f"S{i+1:02d}", 6.2, color, True, PP_ALIGN.CENTER)
    textbox(slide, 0.7, 2.72, 5.7, 0.25, "橙色 = 当前折测试被试；其余被试进入训练池", 7.8, MUTED)
    bullets = [
        ("验证集", "只从训练被试中分层切分，不碰测试被试。"),
        ("标准化", "均值和方差只在训练折拟合，验证/测试只 transform。"),
        ("汇总", "所有折预测拼成 OOF，再算 ACC / Macro-F1 / κ。"),
        ("模型", "MLP、DGCNN、DualView、EEGNet（原始波形）。"),
    ]
    for i, (k, v) in enumerate(bullets):
        y = 3.25 + i * 0.62
        textbox(slide, 0.7, y, 0.8, 0.24, k, 9, TEAL, True)
        textbox(slide, 1.52, y - 0.01, 4.8, 0.42, v, 8.5, MUTED, line_spacing=1.25)
    rect(slide, 0.7, 5.85, 5.65, 0.7, fill=AMBER_BG, line="F1D9AE")
    textbox(slide, 0.9, 5.99, 5.2, 0.25, "跨被试结论必须报告：每折、OOF、95% CI、最差被试。", 8.2, AMBER, True)
    picture_card(slide, ASSETS / "shot_training.png", 6.55, 1.8, 6.1, 4.02)
    textbox(slide, 6.55, 5.95, 6.1, 0.25, "模型训练页 · 模型/设置/超参、后台任务与最近实验", 7.8, MUTED)
    notes(slide, "这一页想强调评估协议比模型选择更重要。标准化只在训练折拟合，测试折不参与任何选择。")

    return slide


def slide_reproducible(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Reproducibility", "每个数字都能回到：数据 + 配置 + 种子", "不是“我电脑上跑过”，而是换一台机器也能复核", 11)
    steps = [
        ("01", "数据版本", "manifest + SHA-256"),
        ("02", "划分", "folds.json + seed"),
        ("03", "配置", "模型/超参/环境"),
        ("04", "结果", "metrics + report"),
    ]
    for i, (num, title, body) in enumerate(steps):
        x = 0.7 + i * 3.06
        rect(slide, x, 1.8, 2.82, 1.45, fill=WHITE, line=LINE)
        textbox(slide, x + 0.18, 1.98, 0.5, 0.26, num, 8, TEAL, True)
        textbox(slide, x + 0.18, 2.32, 2.45, 0.3, title, 11, INK, True)
        textbox(slide, x + 0.18, 2.72, 2.42, 0.3, body, 8.5, MUTED)
        if i < 3:
            arrow(slide, x + 2.84, 2.38, 0.2, 0.12, color="A9BCCE")
    rect(slide, 0.7, 3.62, 11.95, 1.9, fill="F8FBFD", line="E4EDF5")
    textbox(slide, 0.95, 3.82, 11.3, 0.28, "一次运行至少留下 7 类证据", 11, INK, True)
    checks = [
        "代码提交 / 版本", "数据 manifest + 哈希", "folds.json 与种子", "完整配置",
        "环境与硬件", "metrics.json", "HTML/PNG 报告",
    ]
    for i, item in enumerate(checks):
        col = i % 4
        row = i // 4
        x = 0.95 + col * 2.95
        y = 4.28 + row * 0.46
        textbox(slide, x, y, 0.18, 0.2, "✓", 9, GREEN, True)
        textbox(slide, x + 0.24, y - 0.01, 2.6, 0.25, item, 8.4, INK_SOFT)
    textbox(slide, 0.7, 5.85, 11.95, 0.5, "复现判定：同数据 + 同配置 + 同环境重跑，ACC 差异 ≤ 0.5 个百分点；超过则查非确定性/数据变更/依赖升级。", 8.8, MUTED, line_spacing=1.3)
    notes(slide, "可复现不是口号，是七个必须留下的证据。论文里的每个数字都应该能从 manifest 和 metrics 回溯。")

    return slide


def slide_web(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Web architecture", "为什么 Web 层不重写算法？", "页面只做编排与展示，训练/审计仍调用同一套 CLI", 12)
    boxes = [
        ("Browser", "Jinja2 + 原生 JS\nSVG 图表 / 表单", "EAF0FF", BLUE),
        ("FastAPI", "8 页面 + JSON API\n文件白名单", "E8F3F1", TEAL),
        ("JobManager", "线程池 + 状态/日志\n1.4 s 轮询", "F2ECFF", "6941C6"),
        ("CLI", "audit / select\nfeatures / train", "FFF4E2", AMBER),
        ("artifacts", "NPZ · JSON · PNG\nmanifest", "F8FBFD", MUTED),
    ]
    for i, (title, body, fill, color) in enumerate(boxes):
        x = 0.7 + i * 2.53
        rect(slide, x, 1.95, 2.2, 1.38, fill=fill, line="DCE5EF")
        textbox(slide, x + 0.16, 2.13, 1.9, 0.28, title, 11.5, color, True)
        textbox(slide, x + 0.16, 2.55, 1.9, 0.6, body, 8.2, INK_SOFT, line_spacing=1.3)
        if i < len(boxes) - 1:
            arrow(slide, x + 2.23, 2.48, 0.24, 0.12, color="A9BCCE")
    textbox(slide, 0.7, 3.65, 11.9, 0.26, "一个训练任务的生命周期", 9, TEAL, True)
    lifecycle = [
        ("提交", "表单参数"),
        ("排队", "线程池"),
        ("运行", "子进程日志"),
        ("完成", "metrics + report"),
        ("回看", "实验记录"),
    ]
    for i, (title, body) in enumerate(lifecycle):
        x = 0.7 + i * 2.4
        textbox(slide, x, 3.98, 1.7, 0.3, title, 10, INK, True)
        textbox(slide, x, 4.28, 2.0, 0.3, body, 7.8, MUTED)
        if i < len(lifecycle) - 1:
            line(slide, x + 1.55, 4.12, x + 2.25, 4.12, "C8D7E4", 1)
    rect(slide, 0.7, 4.95, 11.95, 1.1, fill=NAVY, line=NAVY)
    textbox(slide, 0.95, 5.13, 11.2, 0.28, "设计取舍：不引入 Node 构建、不接外部数据库、不做公网部署。", 11, WHITE, True)
    textbox(slide, 0.95, 5.48, 11.2, 0.25, "答辩现场一条命令启动；所有页面与论文命令共用同一套事实源。", 8.8, "A9C8D0")
    textbox(slide, 0.7, 6.3, 11.9, 0.3, "本机访问：127.0.0.1:8770　·　API 文档：/api/swagger", 8.8, TEAL, True)
    notes(slide, "Web 层没有复制算法，只是把现有 CLI 包了一层任务和页面。这样页面、论文、脚本三边的结果不会分叉。")

    return slide


def slide_results(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "SEED-IV baseline", "真实 SEED-IV 初测：链路跑通，性能仍有提升空间", "1,080 trial / 15 被试 / 4 类 / 15 折 LOSO；trial 级均值特征", 13)
    picture_card(slide, ASSETS / "shot_report.png", 0.7, 1.78, 7.9, 5.05)
    metrics = [
        ("Accuracy", "42.78%"), ("Balanced", "42.78%"),
        ("Macro-F1", "0.429"), ("Cohen's κ", "0.237"),
    ]
    for i, (label, value) in enumerate(metrics):
        col, row = i % 2, i // 2
        x = 8.95 + col * 1.95
        y = 1.85 + row * 1.02
        textbox(slide, x, y, 1.8, 0.22, label, 7.8, MUTED)
        textbox(slide, x, y + 0.24, 1.8, 0.35, value, 18, TEAL, True)
    rect(slide, 8.95, 4.08, 3.75, 1.02, fill=AMBER_BG, line="F1D9AE")
    textbox(slide, 9.12, 4.2, 3.4, 0.26, "DualView 27.69%：未调参", 8.4, AMBER, True)
    textbox(slide, 9.12, 4.48, 3.4, 0.5, "仅作初步对照，暂不作为方法有效性的结论。", 7.5, AMBER, line_spacing=1.25)
    textbox(slide, 8.95, 5.35, 3.75, 0.26, "这次验证了什么？", 9, INK, True)
    items = ["SEED-IV 官方特征接入", "15 折 LOSO 无泄漏", "OOF 指标 + 95% CI", "报告与混淆矩阵可复查"]
    for i, item in enumerate(items):
        y = 5.66 + i * 0.29
        textbox(slide, 8.98, y, 0.16, 0.2, "✓", 8.5, GREEN, True)
        textbox(slide, 9.2, y - 0.01, 3.4, 0.24, item, 8.0, MUTED)
    textbox(slide, 0.7, 6.9, 7.9, 0.2, "报告截图 · 真实 SEED-IV MLP LOSO；随机水平 25%", 7.2, MUTED_2)
    notes(slide, "这是真实 SEED-IV 的 trial 级结果：MLP 42.78%，比四类随机水平 25% 高，但还不足以作为最终方法结论。DualView 27.69%，说明结构需要针对真实跨被试分布改进。")

    return slide


def slide_next(prs):
    slide = add_slide(prs)
    background(slide)
    header(slide, "Status & next", "现在能做什么，下一步还缺什么", "系统侧已闭环；科研侧已有 SEED-IV 真实基线", 14)
    cols = [
        ("已具备", "✓ SEED-IV 15 被试接入\n✓ 1,080 trial / 37,575 窗口\n✓ 数据审计与质量门控\n✓ 80 条平衡选材\n✓ LOSO 训练与报告\n✓ 58 项自动化测试", "E8F3F1", TEAL),
        ("关键缺口", "! 自采 EEG 尚未接入\n! DualView 27.69%，待改进\n! 26/120 音乐片段待统一\n! 标签体系与 60 s 规则\n! 窗口级/域适应未完成", "FFF6E8", AMBER),
        ("下一步", "1. 窗口级 LOSO 基线\n2. 域适应 / 原型改进\n3. 自采 EEG 预实验\n4. 主实验 + 消融 + 统计\n5. 论文第 5 章", "EAF0FF", BLUE),
    ]
    for i, (title, body, fill, color) in enumerate(cols):
        x = 0.7 + i * 4.08
        rect(slide, x, 1.82, 3.86, 3.72, fill=fill, line="E3EAF2")
        textbox(slide, x + 0.22, 2.02, 3.4, 0.3, title, 13, color, True)
        textbox(slide, x + 0.22, 2.45, 3.4, 2.2, body, 9.6, INK_SOFT, line_spacing=1.5)
        line(slide, x + 0.22, 4.95, x + 3.6, 4.95, "D7E3EE", 0.8)
        textbox(slide, x + 0.22, 5.08, 3.4, 0.3, ["当前状态：SEED-IV 可跑通", "风险：DualView 未达 MLP 基线", "目标：本学期完成主实验"][i], 7.8, color, True)
    rect(slide, 0.7, 5.8, 11.95, 0.82, fill=NAVY, line=NAVY)
    textbox(slide, 0.95, 5.94, 11.2, 0.25, "今晚想请组里拍板的三件事", 8.5, MINT, True)
    textbox(slide, 0.95, 6.2, 11.2, 0.25, "① 标签体系（四象限 / 离散 5 类）　② 音乐片段是否统一 60 s　③ 自采 EEG 数据与设备协议", 9.0, WHITE)
    notes(slide, "SEED-IV 已经接入并跑出真实基线：MLP 42.78%，DualView 27.69%。下一步要针对真实分布做域适应和原型改进；自采 EEG 还需要设备与协议。")

    return slide


def slide_summary(prs):
    slide = add_slide(prs)
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(W), Inches(H))
    bg.line.fill.background()
    bg.fill.gradient()
    bg.fill.gradient_angle = 118
    stops = bg.fill.gradient_stops
    stops[0].color.rgb = rgb("071F32")
    stops[1].color.rgb = rgb("0C6B62")
    bg.shadow.inherit = False
    for x, y, d, color, pct in [(10.0, -1.0, 4.0, MINT, 0.92), (-1.0, 5.5, 3.2, TEAL_2, 0.82)]:
        c = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
        c.fill.solid(); c.fill.fore_color.rgb = rgb(color); c.line.fill.background(); transparency(c, pct)

    textbox(slide, 0.75, 0.75, 2.0, 0.25, "TAKEAWAYS", 8.5, MINT, True)
    textbox(slide, 0.75, 1.15, 11.4, 0.8, "一句话：把 EEG 情绪实验做成一条可复现的流水线", 27, WHITE, True)
    textbox(slide, 0.75, 1.9, 11.2, 0.4, "数据可审计 · 评估无泄漏 · 结果可追溯 · 页面可使用", 11, "A9C8D0")
    items = [
        ("01", "数据侧", "240 条材料、2,356 条问卷、SEED-IV 1,080 trial 已接入。"),
        ("02", "模型侧", "raw.npz → 5 频带 DE → LOSO；真实 MLP 42.78%。"),
        ("03", "工程侧", "8 个页面、58 项测试、manifest/哈希/报告。"),
    ]
    for i, (num, title, body) in enumerate(items):
        y = 3.0 + i * 0.95
        textbox(slide, 0.78, y, 0.5, 0.3, num, 9, MINT, True)
        textbox(slide, 1.3, y - 0.03, 2.0, 0.3, title, 12, WHITE, True)
        textbox(slide, 3.2, y - 0.02, 8.0, 0.35, body, 10, "B7D2D9")
    line(slide, 0.75, 6.15, 6.0, 6.15, "3C6E78", 0.8)
    textbox(slide, 0.75, 6.3, 5.0, 0.25, "现场演示：127.0.0.1:8770", 8.8, MINT, True)
    textbox(slide, 0.75, 6.6, 6.0, 0.25, "赵祥生 · 软件工程 · 2026-11-08", 8.2, "7FAAB4")
    textbox(slide, 9.0, 6.3, 3.7, 0.3, "谢谢，欢迎批评指正", 12, WHITE, True, PP_ALIGN.RIGHT)
    notes(slide, "我的汇报到这里。核心是三句话：数据可审计、评估无泄漏、结果可追溯。欢迎老师和同学批评指正。")

    return slide


def build():
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)
    cover(prs)
    slide_one_page(prs)
    slide_problems(prs)
    slide_principles(prs)
    slide_architecture(prs)
    slide_feature_map(prs)
    slide_audit(prs)
    slide_selection(prs)
    slide_dataset(prs)
    slide_training(prs)
    slide_reproducible(prs)
    slide_web(prs)
    slide_results(prs)
    slide_next(prs)
    slide_summary(prs)

    prs.core_properties.title = "EEG-EmoStudio 组会汇报"
    prs.core_properties.subject = "脑电情绪识别数据制备与模型训练系统"
    prs.core_properties.author = "赵祥生"
    prs.core_properties.comments = "组会汇报，2026-11-08"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"[pptx] written {path} ({path.stat().st_size} bytes)")
