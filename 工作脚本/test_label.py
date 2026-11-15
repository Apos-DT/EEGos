# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

OUT = r"C:\Users\24114\Desktop\EEG Emotion Recognition\音乐质量评分输出"
rows = pd.read_pickle(OUT + r"\_rows.pkl")
res = pd.read_pickle(OUT + r"\_res.pkl")
EMO = ["悲伤/失落", "激昂", "愉快", "温馨/放松", "恐惧/不安"]


def assign(g):
    vg = g[g["valid"]]
    if len(vg) == 0:
        vg = g
    n = len(vg)
    c = vg["q6"].value_counts()
    emo = {e: int(c.get(e, 0)) for e in EMO}
    unk = int(c.get("无法判断", 0))
    top = max(emo, key=emo.get)
    top_n = emo[top]
    second = sorted(emo.values(), reverse=True)[1]
    share = top_n / n
    if share >= 0.4 and top_n > second and top_n > unk:
        return top, share, n, top_n, unk
    return "混合/不明确", share, n, top_n, unk


lab = {sid: assign(g) for sid, g in rows.groupby("sid")}
res["lab"] = res["sid"].map(lambda s: lab[s][0])
res["agree"] = res["sid"].map(lambda s: lab[s][1])
res["n_lab"] = res["sid"].map(lambda s: lab[s][2])
res["top_n"] = res["sid"].map(lambda s: lab[s][3])
res["unk"] = res["sid"].map(lambda s: lab[s][4])

print(res["lab"].value_counts())
print()
for L in ["悲伤/失落", "激昂", "愉快", "温馨/放松", "恐惧/不安", "混合/不明确"]:
    sub = res[res.lab == L].sort_values("Score", ascending=False)
    print(f"=== {L} n={len(sub)} mean={sub.Score.mean():.1f}")
    print(sub.head(6)[["sid", "Score", "grade", "cat", "agree", "tags"]].round(2).to_string(index=False))
print()
print("cross tab label x quadrant")
print(pd.crosstab(res.lab, res.cat, margins=True))
