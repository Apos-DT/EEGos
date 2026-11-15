# -*- coding: utf-8 -*-
from pptx import Presentation
import re

p = r"C:\Users\24114\Desktop\EEG Emotion Recognition\高宇261022.pptx"
prs = Presentation(p)


def walk(shapes, out):
    for sh in shapes:
        if sh.shape_type == 6:  # group
            walk(sh.shapes, out)
            continue
        if sh.has_text_frame:
            for para in sh.text_frame.paragraphs:
                t = "".join(r.text for r in para.runs).strip()
                if t:
                    out.append(t)
                for r in para.runs:
                    if r.hyperlink and r.hyperlink.address:
                        out.append("[LINK] " + r.hyperlink.address)
        if sh.has_table:
            for row in sh.table.rows:
                out.append(" | ".join(c.text.strip() for c in row.cells))
        if sh.has_chart:
            out.append("[CHART]")


for i, s in enumerate(prs.slides, 1):
    out = []
    walk(s.shapes, out)
    notes = ""
    if s.has_notes_slide:
        notes = s.notes_slide.notes_text_frame.text.strip()
    print(f"\n===== SLIDE {i} =====")
    print("\n".join(out))
    if notes:
        print("[NOTES]", notes)

# core properties
cp = prs.core_properties
print("\nCORE", cp.title, cp.author, cp.created, cp.last_modified_by)
