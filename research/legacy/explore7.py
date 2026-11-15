# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import re

p = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\376653806_按文本_情绪诱发情况评估（音乐）_1088_1087(Sheet1).csv"
m = pd.read_csv(r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\音乐对应关系.csv", encoding="utf-8-sig")
df = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
df["rater"] = df.iloc[:, 7].str.strip()
df["sid"] = df.iloc[:, 8].map(lambda s: f"{int(re.search(r'(\d+)', s).group(1))}.mp3")
df["v"] = df.iloc[:, 9].replace({"非常愉快": "9", "非常不愉快": "1"}).astype(float)
df["a"] = df.iloc[:, 10].replace({"非常激烈": "9", "非常平静": "1"}).astype(float)
df = df.merge(m[["新文件名", "类别"]], left_on="sid", right_on="新文件名")
print(df.groupby("类别")[["v", "a"]].agg(["mean", "std"]).round(2))
print()
print(df.groupby("rater")[["v", "a"]].mean().round(2))
print()
print(df.groupby(["rater", "类别"])[["v", "a"]].mean().round(1).unstack(1).to_string())
