# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import re

p = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\376653806_按文本_情绪诱发情况评估（音乐）_1088_1087(Sheet1).csv"
df = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
df["rater"] = df.iloc[:, 7].str.strip()
df["sid"] = df.iloc[:, 8].map(lambda s: f"{int(re.search(r'(\d+)', s).group(1))}.mp3")
df["v"] = df.iloc[:, 9].replace({"非常愉快": "9", "非常不愉快": "1"}).astype(float)
df["a"] = df.iloc[:, 10].replace({"非常激烈": "9", "非常平静": "1"}).astype(float)
df["sec"] = df.iloc[:, 2].str.replace("秒", "", regex=False).astype(float)
df = df.sort_values("序号").drop_duplicates(["rater", "sid"])

piv_v = df.pivot_table(index="sid", columns="rater", values="v", aggfunc="mean")
piv_a = df.pivot_table(index="sid", columns="rater", values="a", aggfunc="mean")

print("rater-level stats")
for r in piv_v.columns:
    others_v = piv_v.drop(columns=[r]).mean(axis=1)
    others_a = piv_a.drop(columns=[r]).mean(axis=1)
    print(f"{r}: sd_v={piv_v[r].std():.2f} sd_a={piv_a[r].std():.2f} "
          f"r_v={piv_v[r].corr(others_v):.2f} r_a={piv_a[r].corr(others_a):.2f} "
          f"med_sec={df[df.rater==r]['sec'].median():.0f}")

# leave-one-out consensus vs each rater
print()
print("per-song sd with/without 刘佳悦:", piv_v.drop(columns=["刘佳悦"]).std(axis=1).mean(), piv_v.std(axis=1).mean())
