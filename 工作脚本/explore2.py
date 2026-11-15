# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import re

pd.set_option("display.width", 220)
P = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\376653806_按文本_情绪诱发情况评估（音乐）_1088_1087(Sheet1).csv"
df = pd.read_csv(P, encoding="utf-8-sig", dtype=str)


def norm(s):
    m = re.search(r"(\d+)", str(s))
    return f"{int(m.group(1))}.mp3" if m else str(s)


df["sid"] = df.iloc[:, 8].map(norm)
df["name"] = df.iloc[:, 7].str.strip()
df["sec"] = df.iloc[:, 2].str.replace("秒", "").astype(float)
print("time describe")
print(df["sec"].describe())
print(df["sec"].quantile([0.01, 0.05, 0.1, 0.25, 0.5]))
print("short rows(<120s):", (df["sec"] < 120).sum(), " <60:", (df["sec"] < 60).sum())

v = df.iloc[:, 9].replace({"非常愉快": "9", "非常不愉快": "1"}).astype(float)
a = df.iloc[:, 10].replace({"非常激烈": "9", "非常平静": "1"}).astype(float)
df["v"], df["a"] = v, a
print("valence", v.describe())
print("arousal", a.describe())

g = df.groupby("sid").agg(n=("sid", "size"), v_sd=("v", "std"), a_sd=("a", "std"), v_mean=("v", "mean"), a_mean=("a", "mean"))
print("sd describe")
print(g[["v_sd", "a_sd"]].describe())
print(g.sort_values("v_sd", ascending=False).head(10))

# emotion agreement
emo = df.iloc[:, 11]
tab = df.groupby("sid")[df.columns[11]].apply(lambda s: s.value_counts(normalize=True).max())
print("max emotion share describe")
print(tab.describe())
print("unknowable share per song describe")
unk = df.assign(u=emo.eq("无法判断")).groupby("sid")["u"].mean()
print(unk.describe())
