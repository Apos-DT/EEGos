"""Build thesis-support DOCX files from the Markdown sources.

Run with the bundled Python that provides python-docx::

    <bundled-python> scripts/build_docx.py

The Markdown files remain the single source of truth.  The generated DOCX
contains a cover, an auto-updating TOC field, styled headings/tables/code and
page numbers.  Word will refresh the TOC on open because ``updateFields`` is
set; the user can also press F9.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import (
    WD_ALIGN_PARAGRAPH,
    WD_BREAK,
    WD_LINE_SPACING,
    WD_TAB_ALIGNMENT,
    WD_TAB_LEADER,
)
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
OUT_DIR = ROOT / "deliverables"

INK = "1F2937"
MUTED = "5B6B7C"
ACCENT = "1F4E79"
LIGHT = "F2F6FA"
BORDER = "B7C4D1"
CODE_BG = "F4F6F8"
QUOTE_BG = "FFF8E1"

DOCS = [
    ("01_可行性研究报告.md", "可行性研究报告", "01", "EEG-EmoStudio_01_可行性研究报告.docx"),
    ("02_软件需求规格说明书.md", "软件需求规格说明书", "02", "EEG-EmoStudio_02_软件需求规格说明书.docx"),
    ("03_项目计划与WBS.md", "项目计划与工作分解结构", "03", "EEG-EmoStudio_03_项目计划与WBS.docx"),
    ("04_文献综述与需求依据.md", "文献综述与需求依据", "04", "EEG-EmoStudio_04_文献综述与需求依据.docx"),
    ("05_数据审计报告.md", "数据审计报告", "05", "EEG-EmoStudio_05_数据审计报告.docx"),
    ("06_概要设计说明书.md", "概要设计说明书", "06", "EEG-EmoStudio_06_概要设计说明书.docx"),
    ("07_详细设计说明书.md", "详细设计说明书", "07", "EEG-EmoStudio_07_详细设计说明书.docx"),
    ("08_数据字典与数据治理规范.md", "数据字典与数据治理规范", "08", "EEG-EmoStudio_08_数据字典与数据治理规范.docx"),
    ("09_测试计划与验收标准.md", "测试计划与验收标准", "09", "EEG-EmoStudio_09_测试计划与验收标准.docx"),
    ("10_用户手册.md", "用户手册", "10", "EEG-EmoStudio_10_用户手册.docx"),
    ("11_毕业论文写作纲要.md", "毕业论文写作纲要", "11", "EEG-EmoStudio_11_毕业论文写作纲要.docx"),
    ("12_毕业设计符合性矩阵.md", "毕业设计符合性矩阵", "12", "EEG-EmoStudio_12_毕业设计符合性矩阵.docx"),
    ("13_配置管理与质量保证计划.md", "配置管理与质量保证计划", "13", "EEG-EmoStudio_13_配置管理与质量保证计划.docx"),
    ("14_开题报告草案.md", "开题报告（草案）", "14", "EEG-EmoStudio_14_开题报告草案.docx"),
]

INLINE_RE = re.compile(r"(\*\*.+?\*\*|`.+?`|\*[^*\n]+?\*)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


# ---------------------------------------------------------------------------
# Low-level OOXML helpers
# ---------------------------------------------------------------------------


def _set_run_font(run, name: str, size: float | None = None, bold: bool | None = None,
                  color: str | None = None, italic: bool | None = None) -> None:
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def _shade_paragraph(paragraph, fill: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.append(shd)


def _paragraph_border(paragraph, side: str = "bottom", color: str = BORDER,
                      size: int = 6, space: int = 4) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    pbdr = ppr.find(qn("w:pBdr"))
    if pbdr is None:
        pbdr = OxmlElement("w:pBdr")
        ppr.append(pbdr)
    element = OxmlElement(f"w:{side}")
    element.set(qn("w:val"), "single")
    element.set(qn("w:sz"), str(size))
    element.set(qn("w:space"), str(space))
    element.set(qn("w:color"), color)
    pbdr.append(element)


def _cell_shading(cell, fill: str) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def _set_cell_margins(cell, top: int = 60, bottom: int = 60, left: int = 90, right: int = 90) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for side, value in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tcpr.append(mar)


def _set_table_borders(table, color: str = BORDER, size: int = 4) -> None:
    tbl = table._tbl
    tblpr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{side}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(size))
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)
        borders.append(element)
    tblpr.append(borders)


def _repeat_header(row) -> None:
    trpr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    trpr.append(header)


def _cant_split(row) -> None:
    trpr = row._tr.get_or_add_trPr()
    node = OxmlElement("w:cantSplit")
    node.set(qn("w:val"), "true")
    trpr.append(node)


def _add_field(paragraph, instruction: str, placeholder: str = "") -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    run._r.append(begin)
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    run._r.append(instr)
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    run._r.append(separate)
    if placeholder:
        text = OxmlElement("w:t")
        text.text = placeholder
        run._r.append(text)
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(end)


def _add_page_number(paragraph) -> None:
    _set_run_font(paragraph.add_run("第 "), "宋体", 9, color=MUTED)
    _add_field(paragraph, "PAGE", "1")
    _set_run_font(paragraph.add_run(" 页 / 共 "), "宋体", 9, color=MUTED)
    _add_field(paragraph, "NUMPAGES", "1")
    _set_run_font(paragraph.add_run(" 页"), "宋体", 9, color=MUTED)


def _add_toc_field(paragraph) -> None:
    """Fallback TOC field used only when no precomputed page map exists."""

    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    run._r.append(begin)
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = ' TOC \\o "1-3" \\h \\z \\u '
    run._r.append(instr)
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    run._r.append(separate)
    text = OxmlElement("w:t")
    text.text = "在 Word 中右键此处 → 更新域，生成目录"
    run._r.append(text)
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(end)


def _add_static_toc(doc: Document, entries: list[dict]) -> None:
    """Render a precomputed TOC with dot leaders and real page numbers.

    Page numbers come from a first-pass PDF render (LibreOffice preserves
    heading bookmarks), so the final DOCX has a useful TOC even in viewers
    that do not update Word fields.
    """

    for entry in entries:
        level = int(entry.get("level", 1))
        title = str(entry.get("title", "")).strip()
        page = entry.get("page", "")
        if not title:
            continue
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm({1: 0.0, 2: 0.55, 3: 1.1}.get(level, 0.0))
        paragraph.paragraph_format.first_line_indent = Cm(0)
        paragraph.paragraph_format.space_before = Pt({1: 8, 2: 2, 3: 1}.get(level, 1))
        paragraph.paragraph_format.space_after = Pt({1: 4, 2: 1, 3: 0}.get(level, 0))
        paragraph.paragraph_format.line_spacing = 1.15
        paragraph.paragraph_format.tab_stops.add_tab_stop(
            Cm(15.25), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS
        )
        run = paragraph.add_run(title)
        _set_run_font(
            run,
            "黑体" if level == 1 else "宋体",
            12.5 if level == 1 else 11.0 if level == 2 else 10.5,
            bold=(level == 1),
            color=INK if level != 1 else ACCENT,
        )
        run = paragraph.add_run("\t")
        _set_run_font(run, "宋体", 10.5, color=MUTED)
        run = paragraph.add_run(str(page))
        _set_run_font(run, "宋体", 10.5, color=MUTED)


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------


def _east_asia(style, name: str) -> None:
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), name)


def _configure_styles(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "宋体"
    normal.font.size = Pt(12)
    _east_asia(normal, "宋体")
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.space_before = Pt(0)

    specs = {
        "Heading 1": ("黑体", 18, True, ACCENT, 18, 12),
        "Heading 2": ("黑体", 15, True, INK, 14, 8),
        "Heading 3": ("黑体", 12.5, True, INK, 10, 5),
        "Heading 4": ("黑体", 11, True, INK, 8, 4),
    }
    for name, (font, size, bold, color, before, after) in specs.items():
        style = doc.styles[name]
        style.font.name = font
        style.font.size = Pt(size)
        style.font.bold = bold
        style.font.color.rgb = RGBColor.from_string(color)
        _east_asia(style, font)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.line_spacing = 1.2

    caption = doc.styles["Caption"]
    caption.font.name = "宋体"
    caption.font.size = Pt(9.5)
    caption.font.color.rgb = RGBColor.from_string(MUTED)
    _east_asia(caption, "宋体")
    caption.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.space_before = Pt(3)
    caption.paragraph_format.space_after = Pt(8)


def _configure_section(section) -> None:
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.8)
    section.right_margin = Cm(2.6)
    section.header_distance = Cm(1.4)
    section.footer_distance = Cm(1.4)
    section.different_first_page_header_footer = True


def _header_footer(doc: Document, doc_no: str, title: str) -> None:
    section = doc.sections[0]
    header = section.header
    paragraph = header.paragraphs[0]
    paragraph.text = ""
    paragraph.paragraph_format.tab_stops.add_tab_stop(Cm(15.5), 2)  # right aligned
    run = paragraph.add_run("EEG-EmoStudio · 脑电情绪识别数据与模型工作台")
    _set_run_font(run, "宋体", 8.5, color=MUTED)
    run = paragraph.add_run("\t")
    _set_run_font(run, "宋体", 8.5, color=MUTED)
    run = paragraph.add_run(f"文档 {doc_no} · {title}")
    _set_run_font(run, "宋体", 8.5, color=MUTED)
    _paragraph_border(paragraph, "bottom", BORDER, 4, 2)

    footer = section.footer
    footer_paragraph = footer.paragraphs[0]
    footer_paragraph.text = ""
    footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_page_number(footer_paragraph)
    _paragraph_border(footer_paragraph, "top", BORDER, 4, 2)

    first_header = section.first_page_header
    first_header.paragraphs[0].text = ""
    first_footer = section.first_page_footer
    first_footer.paragraphs[0].text = ""


# ---------------------------------------------------------------------------
# Cover
# ---------------------------------------------------------------------------


def _cover(doc: Document, title: str, doc_no: str, version: str = "V1.0") -> None:
    band = doc.add_table(rows=1, cols=1)
    band.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = band.cell(0, 0)
    _cell_shading(cell, ACCENT)
    _set_cell_margins(cell, 140, 140, 180, 180)
    cell.width = Cm(15.5)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("本科毕业设计（论文）支撑材料")
    _set_run_font(run, "黑体", 12, bold=True, color="FFFFFF")

    for _ in range(2):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(12)
    run = p.add_run(title)
    _set_run_font(run, "黑体", 24, bold=True, color=INK)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("EEG-EmoStudio")
    _set_run_font(run, "Arial", 14, bold=True, color=ACCENT)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("脑电情绪识别数据制备与模型训练工作台")
    _set_run_font(run, "宋体", 13, color=MUTED)

    for _ in range(3):
        doc.add_paragraph()

    info = [
        ("文档编号", doc_no),
        ("文档版本", version),
        ("项目名称", "EEG-EmoStudio 脑电情绪识别数据制备与模型训练工作台"),
        ("专业", "软件工程"),
        ("学生", "赵祥生"),
        ("指导教师", "曾庆田 教授"),
        ("编制日期", date.today().strftime("%Y 年 %m 月 %d 日")),
    ]
    table = doc.add_table(rows=len(info), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for row, (key, value) in zip(table.rows, info):
        row.cells[0].width = Cm(3.6)
        row.cells[1].width = Cm(11.6)
        for cell in row.cells:
            _set_cell_margins(cell, 70, 70, 80, 80)
            _set_cell_borders_invisible(cell)
        p0 = row.cells[0].paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = p0.add_run(key)
        _set_run_font(run, "黑体", 10.5, bold=True, color=MUTED)
        p1 = row.cells[1].paragraphs[0]
        run = p1.add_run(value)
        _set_run_font(run, "宋体", 10.5, color=INK)

    for _ in range(2):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("2026 年 11 月")
    _set_run_font(run, "宋体", 11, color=MUTED)

    doc.add_page_break()


def _set_cell_borders_invisible(cell) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        element = OxmlElement(f"w:{side}")
        element.set(qn("w:val"), "nil")
        borders.append(element)
    tcpr.append(borders)


# ---------------------------------------------------------------------------
# Inline and block rendering
# ---------------------------------------------------------------------------


def _smart_join(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    # Remove spaces that Markdown line wrapping inserted between CJK chars.
    text = re.sub(r"(?<=[\u4e00-\u9fff，。；：、！？）“”‘’])\s+(?=[\u4e00-\u9fff，。；：、！？）“”‘’])", "", text)
    return text


def _strip_links(text: str) -> str:
    # Keep link label; for bare URLs in angle brackets, keep the URL.
    text = LINK_RE.sub(lambda match: match.group(1), text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    return text


def _add_inline(paragraph, text: str, size: float = 12, color: str = INK,
                base_bold: bool = False, font: str = "宋体") -> None:
    text = _strip_links(text)
    position = 0
    for match in INLINE_RE.finditer(text):
        if match.start() > position:
            run = paragraph.add_run(text[position : match.start()])
            _set_run_font(run, font, size, bold=base_bold, color=color)
        token = match.group(0)
        if token.startswith("**"):
            run = paragraph.add_run(token[2:-2])
            _set_run_font(run, "黑体", size, bold=True, color=color)
        elif token.startswith("`"):
            run = paragraph.add_run(token[1:-1])
            _set_run_font(run, "Consolas", size - 1, bold=base_bold, color="9C2F2F")
        elif token.startswith("*"):
            run = paragraph.add_run(token[1:-1])
            _set_run_font(run, font, size, bold=base_bold, italic=True, color=color)
        position = match.end()
    if position < len(text):
        run = paragraph.add_run(text[position:])
        _set_run_font(run, font, size, bold=base_bold, color=color)


def _add_body_paragraph(doc: Document, text: str, first_indent: bool = True) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.line_spacing = 1.5
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    if first_indent:
        paragraph.paragraph_format.first_line_indent = Cm(0.74)
    _add_inline(paragraph, text, 12, INK)


def _add_heading(doc: Document, text: str, level: int) -> None:
    paragraph = doc.add_heading(level=level)
    paragraph.paragraph_format.space_before = Pt({1: 6, 2: 14, 3: 10, 4: 8}.get(level, 6))
    paragraph.paragraph_format.space_after = Pt({1: 14, 2: 8, 3: 5, 4: 4}.get(level, 4))
    run = paragraph.add_run(text)
    font = "黑体"
    size = {1: 18, 2: 15, 3: 12.5, 4: 11}.get(level, 11)
    _set_run_font(run, font, size, bold=True, color=ACCENT if level == 1 else INK)


def _add_code_block(doc: Document, lines: list[str]) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Cm(0.5)
    paragraph.paragraph_format.right_indent = Cm(0.3)
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(8)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.keep_together = True
    _shade_paragraph(paragraph, CODE_BG)
    _paragraph_border(paragraph, "left", "8FA8BF", 18, 6)
    for index, line in enumerate(lines):
        run = paragraph.add_run(line)
        _set_run_font(run, "Consolas", 8.6, color="243447")
        if index < len(lines) - 1:
            run.add_break()


def _add_quote(doc: Document, lines: list[str]) -> None:
    text = _smart_join([line.lstrip("> ").rstrip() for line in lines])
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Cm(0.6)
    paragraph.paragraph_format.right_indent = Cm(0.4)
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.line_spacing = 1.3
    _shade_paragraph(paragraph, QUOTE_BG)
    _paragraph_border(paragraph, "left", "E0A800", 18, 6)
    _add_inline(paragraph, text, 10.5, "5A4B22")


def _add_list_item(doc: Document, content: str, bullet: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.left_indent = Cm(0.85)
    paragraph.paragraph_format.first_line_indent = Cm(-0.45)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.paragraph_format.line_spacing = 1.4
    run = paragraph.add_run(bullet)
    _set_run_font(run, "宋体", 12, color=ACCENT)
    _add_inline(paragraph, content, 12, INK)


def _add_image(doc: Document, image_path: Path, alt: str, figure_no: int) -> int:
    if not image_path.exists():
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(f"[缺少图片：{image_path.name}]")
        _set_run_font(run, "宋体", 9, color="B00020")
        return figure_no
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.space_after = Pt(2)
    run = paragraph.add_run()
    run.add_picture(str(image_path), width=Cm(15.4))
    caption = doc.add_paragraph(style="Caption")
    text = alt.strip() or image_path.stem
    if not text.startswith("图"):
        text = f"图 {figure_no}  {text}"
    run = caption.add_run(text)
    _set_run_font(run, "宋体", 9.5, color=MUTED)
    return figure_no + 1


def _column_widths(rows: list[list[str]]) -> list[float]:
    n_cols = max(len(row) for row in rows)
    weights = []
    for col in range(n_cols):
        lengths = [len(row[col]) for row in rows if col < len(row)]
        avg = sum(lengths) / max(len(lengths), 1)
        weights.append(min(max(avg, 6.0), 32.0))
    total = sum(weights) or 1.0
    return [15.4 * weight / total for weight in weights]


def _add_table(doc: Document, rows: list[list[str]]) -> None:
    if not rows:
        return
    n_cols = max(len(row) for row in rows)
    rows = [row + [""] * (n_cols - len(row)) for row in rows]
    table = doc.add_table(rows=len(rows), cols=n_cols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders(table, BORDER, 4)
    widths = _column_widths(rows)
    for r_idx, row in enumerate(rows):
        _cant_split(table.rows[r_idx])
        for c_idx, value in enumerate(row):
            cell = table.cell(r_idx, c_idx)
            cell.width = Cm(widths[c_idx])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _set_cell_margins(cell, 55, 55, 75, 75)
            if r_idx == 0:
                _cell_shading(cell, ACCENT)
            elif r_idx % 2 == 0:
                _cell_shading(cell, LIGHT)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.line_spacing = 1.15
            paragraph.paragraph_format.space_before = Pt(1)
            paragraph.paragraph_format.space_after = Pt(1)
            if r_idx == 0:
                _add_inline(paragraph, value, 9, "FFFFFF", base_bold=True, font="黑体")
            else:
                _add_inline(paragraph, value, 9, INK)
    _repeat_header(table.rows[0])
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(2)
    spacer.paragraph_format.line_spacing = 0.6


def _split_table_row(line: str) -> list[str]:
    line = line.strip().strip("|")
    parts = re.split(r"(?<!\\)\|", line)
    return [part.strip().replace("\\|", "|") for part in parts]


def _is_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def render_markdown(doc: Document, markdown_path: Path) -> dict:
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    figure_no = 1
    first_h1_skipped = False
    content_started = False
    index = 0
    paragraph_buffer: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        if paragraph_buffer:
            text = _smart_join(paragraph_buffer)
            if text.strip():
                _add_body_paragraph(doc, text)
            paragraph_buffer = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            language = stripped[3:].strip()
            code_lines = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index].rstrip("\n"))
                index += 1
            if code_lines:
                _add_code_block(doc, code_lines)
            index += 1
            continue

        if stripped.startswith("!["):
            flush_paragraph()
            match = IMAGE_RE.match(stripped)
            if match:
                alt, rel = match.group(1), match.group(2)
                image_path = (markdown_path.parent / rel).resolve()
                figure_no = _add_image(doc, image_path, alt, figure_no)
            index += 1
            continue

        if stripped.startswith("|") and index + 1 < len(lines) and _is_separator(lines[index + 1].strip()):
            flush_paragraph()
            table_lines = [stripped]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            rows = [_split_table_row(row) for row in table_lines]
            _add_table(doc, rows)
            continue

        if stripped.startswith("#"):
            flush_paragraph()
            match = re.match(r"^(#{1,4})\s+(.*)$", stripped)
            if not match:
                index += 1
                continue
            level = len(match.group(1))
            text = match.group(2).strip().rstrip("#").strip()
            if level == 1:
                if not first_h1_skipped:
                    first_h1_skipped = True
                    index += 1
                    continue
                doc.add_page_break()
            _add_heading(doc, text, level)
            content_started = True
            index += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip())
                index += 1
            _add_quote(doc, quote_lines)
            content_started = True
            continue

        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(2)
            paragraph.paragraph_format.space_after = Pt(6)
            _paragraph_border(paragraph, "bottom", BORDER, 4, 1)
            index += 1
            continue

        bullet_match = re.match(r"^\s*[-*+]\s+(.*)$", line)
        numbered_match = re.match(r"^\s*(\d+[.)])\s+(.*)$", line)
        checkbox_match = re.match(r"^\s*[-*+]\s+\[([ xX])\]\s+(.*)$", line)
        if checkbox_match:
            flush_paragraph()
            mark = "☑" if checkbox_match.group(1).lower() == "x" else "☐"
            _add_list_item(doc, checkbox_match.group(2), f"{mark} ")
            content_started = True
            index += 1
            continue
        if bullet_match:
            flush_paragraph()
            _add_list_item(doc, bullet_match.group(1), "• ")
            content_started = True
            index += 1
            continue
        if numbered_match:
            flush_paragraph()
            _add_list_item(doc, numbered_match.group(2), f"{numbered_match.group(1)} ")
            content_started = True
            index += 1
            continue

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        paragraph_buffer.append(line)
        index += 1

    flush_paragraph()
    return {"figures": figure_no - 1, "content_started": content_started}


def build_one(md_name: str, title: str, doc_no: str, out_name: str,
              toc_entries: list[dict] | None = None) -> Path:
    markdown_path = DOCS_DIR / md_name
    if not markdown_path.exists():
        raise FileNotFoundError(markdown_path)
    doc = Document()
    _configure_section(doc.sections[0])
    _configure_styles(doc)
    _header_footer(doc, doc_no, title)
    _cover(doc, title, doc_no)

    # TOC page
    heading = doc.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    heading.paragraph_format.space_before = Pt(6)
    heading.paragraph_format.space_after = Pt(14)
    run = heading.add_run("目  录")
    _set_run_font(run, "黑体", 18, bold=True, color=ACCENT)
    if toc_entries:
        _add_static_toc(doc, toc_entries)
        note_text = "说明：目录页码由构建脚本根据实际排版结果生成；若后续手动增删正文，请重新运行构建脚本。"
    else:
        toc_paragraph = doc.add_paragraph()
        toc_paragraph.paragraph_format.line_spacing = 1.4
        _add_toc_field(toc_paragraph)
        note_text = "提示：Word 打开时若目录未自动刷新，请右键目录 → “更新域” → “更新整个目录”。"
    note = doc.add_paragraph()
    note.paragraph_format.space_before = Pt(12)
    run = note.add_run(note_text)
    _set_run_font(run, "宋体", 8.5, color=MUTED)
    doc.add_page_break()

    render_markdown(doc, markdown_path)

    # Ensure fields update on open
    settings = doc.settings.element
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    settings.append(update)

    doc.core_properties.title = title
    doc.core_properties.subject = "EEG-EmoStudio 本科毕业设计支撑材料"
    doc.core_properties.author = "赵祥生"
    doc.core_properties.keywords = "EEG; emotion recognition; software engineering; data curation"
    doc.core_properties.comments = "Generated from Markdown by scripts/build_docx.py"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUT_DIR / out_name
    doc.save(output)
    return output


def validate(path: Path, title: str) -> dict:
    doc = Document(path)
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
    if title not in text:
        raise AssertionError(f"{path.name}: 未找到标题 {title}")
    if len(doc.paragraphs) < 10:
        raise AssertionError(f"{path.name}: 段落过少")
    return {
        "file": path.name,
        "paragraphs": len(doc.paragraphs),
        "tables": len(doc.tables),
        "images": len(doc.inline_shapes),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default=None, help="只构建文件名包含该字符串的文档")
    parser.add_argument("--toc-json", default=None, help="预计算目录页码 JSON（按文档编号索引）")
    args = parser.parse_args()
    toc_map: dict[str, list[dict]] = {}
    if args.toc_json:
        toc_path = Path(args.toc_json)
        if toc_path.exists():
            toc_map = json.loads(toc_path.read_text(encoding="utf-8"))
            print(f"[docx] loaded TOC page map: {toc_path}")
    results = []
    for md_name, title, doc_no, out_name in DOCS:
        if args.only and args.only not in md_name and args.only not in out_name:
            continue
        output = build_one(
            md_name,
            title,
            doc_no,
            out_name,
            toc_entries=toc_map.get(doc_no),
        )
        info = validate(output, title)
        info["toc_entries"] = len(toc_map.get(doc_no, []))
        results.append(info)
        print(f"[docx] {output.name}: {info['paragraphs']} paragraphs, "
              f"{info['tables']} tables, {info['images']} images, "
              f"toc={info['toc_entries']}, {info['size_bytes']} bytes")
    manifest = OUT_DIR / "docx_manifest.json"
    manifest.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[docx] manifest -> {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
