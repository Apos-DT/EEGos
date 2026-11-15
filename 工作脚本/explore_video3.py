# -*- coding: utf-8 -*-
import pandas as pd
import re

p = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\374437060_按文本_情绪诱发情况评估（视频）_1271_1269(Sheet1).csv"
df = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
c = df.columns
df["rater"] = df[c[7]].str.strip().str.replace("·", "", regex=False).str.replace(" ", "", regex=False)
df["sid"] = df[c[8]].str.strip().map(lambda s: "38.mp4" if s.startswith("388") else f"{int(re.search(r'(\d+)', s).group(1))}.mp4")
df["idx"] = df[c[0]].astype(int)
d = df.sort_values("idx").drop_duplicates(["rater", "sid"], keep="first")
pr = d[c[17]].fillna("").str.strip()
sub = d[pr.ne("没有问题")]
for kw in ["模糊", "杂音", "卡顿", "不同步", "加速", "内容", "音量"]:
    s = sub[pr.str.contains(kw)]
    print(f"--- {kw}: {len(s)}")
    for r, g in s.groupby("rater"):
        print("  ", r, sorted(g.sid.tolist(), key=lambda x: int(x[:-4])))
