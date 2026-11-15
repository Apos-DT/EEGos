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
q12 = d[c[18]].fillna("").str.strip()

prows = d[pr.ne("没有问题")]
print("problem rows", len(prows))
print(prows.groupby(["sid", pr]).size().to_string())
print()
print("by rater")
print(prows.groupby("rater").size())
print()
print("q12 rows")
print(d[q12.ne("没有")][["rater", "sid", c[17], c[18]]].to_string())
