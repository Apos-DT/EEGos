"""Extract heading page numbers from first-pass PDFs for static DOCX TOCs.

Usage::

    python scripts/extract_toc.py --pdf-dir deliverables/pdf_pass1 --out deliverables/toc_pages.json

The PDF outline is produced by LibreOffice from the DOCX heading styles.  We
pair it with the Markdown heading order (skipping fenced code blocks) so that
the TOC semantics come from the source, not from PDF level quirks.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"


def markdown_headings(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    headings: list[tuple[int, str]] = []
    in_code = False
    first_h1 = True
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip().rstrip("#").strip()
        if level == 1 and first_h1:
            first_h1 = False
            continue
        headings.append((level, title))
    return headings


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).replace("：", ":").replace("，", ",")


def extract_for_pdf(pdf_path: Path, md_path: Path) -> list[dict]:
    headings = markdown_headings(md_path)
    doc = fitz.open(pdf_path)
    pdf_toc = [
        (int(level), str(title).strip(), int(page))
        for level, title, page in doc.get_toc(simple=True)
        if str(title).strip() and str(title).strip() not in {"目录", "目 录"}
    ]
    doc.close()

    if len(headings) == len(pdf_toc):
        pairs = list(zip(headings, pdf_toc))
    else:
        # Fallback: pair by title, preserving order and page monotonicity.
        pairs = []
        cursor = 0
        for level, title in headings:
            target = normalize(title)
            found = None
            for index in range(cursor, len(pdf_toc)):
                if normalize(pdf_toc[index][1]) == target:
                    found = index
                    break
            if found is None:
                page = pdf_toc[min(cursor, len(pdf_toc) - 1)][2] if pdf_toc else ""
                pairs.append(((level, title), (level, title, page)))
            else:
                pairs.append(((level, title), pdf_toc[found]))
                cursor = found + 1

    min_level = min((level for level, _ in headings), default=1)
    entries: list[dict] = []
    for (level, title), (_pdf_level, _pdf_title, page) in pairs:
        entries.append(
            {
                "level": max(1, min(3, level - min_level + 1)),
                "title": title,
                "page": page,
            }
        )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-dir", default="deliverables/pdf_pass1")
    parser.add_argument("--out", default="deliverables/toc_pages.json")
    args = parser.parse_args()
    pdf_dir = (ROOT / args.pdf_dir).resolve() if not Path(args.pdf_dir).is_absolute() else Path(args.pdf_dir)
    out_path = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)

    result: dict[str, list[dict]] = {}
    for md_path in sorted(DOCS_DIR.glob("*.md")):
        prefix = md_path.name.split("_")[0]
        pdf_path = pdf_dir / f"{prefix}.pdf"
        if not pdf_path.exists():
            print(f"[toc] skip {prefix}: missing {pdf_path.name}")
            continue
        entries = extract_for_pdf(pdf_path, md_path)
        result[prefix] = entries
        print(f"[toc] {prefix}: {len(entries)} entries, {pdf_path.name}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[toc] written {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
