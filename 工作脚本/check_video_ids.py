# -*- coding: utf-8 -*-
import pandas as pd
import re

p = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\374437060_按文本_情绪诱发情况评估（视频）_1271_1269(Sheet1).csv"
df = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
c = df.columns
df["rater"] = df[c[7]].str.strip().str.replace("·", "", regex=False)
df["sid"] = df[c[8]].str.strip().map(lambda s: f"{int(re.search(r'(\d+)', s).group(1))}.mp4")
allv = set(f"{i}.mp4" for i in range(1, 121))
for r, g in df.groupby("rater"):
    miss = sorted(allv - set(g.sid), key=lambda x: int(x[:-4]))
    extra = sorted(set(g.sid) - allv, key=lambda x: int(x[:-4]))
    print(r, len(g), len(set(g.sid)), "missing:", miss[:8], "extra:", extra)
print()
print("张涵博 388 row context")
print(df[(df.rater == "张涵博") & (df[c[8]].str.contains("388"))][[c[0], c[8], c[9], c[10]]].to_string())
print("张涵博 has 38?", "38.mp4" in set(df[df.rater == "张涵博"].sid))
print("张涵博 has 88?", "88.mp4" in set(df[df.rater == "张涵博"].sid))
