# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

OUT = r"C:\Users\24114\Desktop\EEG Emotion Recognition\research\quality\audio"
rows = pd.read_pickle(OUT + r"\_rows.pkl")
res = pd.read_pickle(OUT + r"\_res.pkl")
EMO = ["悲伤/失落", "激昂", "愉快", "温馨/放松", "恐惧/不安"]

out = []
for sid, g in rows.groupby("sid"):
    vg = g[g["valid"]]
    if len(vg) == 0:
        vg = g
    n = len(vg)
    counts = vg["q6"].value_counts()
    emo_counts = {e: int(counts.get(e, 0)) for e in EMO}
    unk = int(counts.get("无法判断", 0))
    top = max(emo_counts, key=emo_counts.get)
    top_n = emo_counts[top]
    second = sorted(emo_counts.values(), reverse=True)[1] if len(emo_counts) > 1 else 0
    share = top_n / n
    out.append(dict(sid=sid, n=n, top=top, top_n=top_n, second=second, unk=unk,
                    share=share, tie=(top_n == second and top_n > 0)))
o = pd.DataFrame(out)
print("max share distribution")
print(o["share"].round(2).value_counts().sort_index())
print("ties", o["tie"].sum())
for th in [0.375, 0.4, 0.45, 0.5]:
    lab = o["top"].where((o["share"] >= th) & (~o["tie"]) & (o["top_n"] > o["unk"]), "混合/不明确")
    print(f"threshold {th}: assigned { (lab!='混合/不明确').sum() }, mixed {(lab=='混合/不明确').sum()}")
    print(lab.value_counts().to_dict())
print()
print(o.sort_values("share").head(20).to_string(index=False))
