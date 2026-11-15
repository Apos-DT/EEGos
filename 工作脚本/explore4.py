# -*- coding: utf-8 -*-
import pandas as pd
import re

P = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\376653806_按文本_情绪诱发情况评估（音乐）_1088_1087(Sheet1).csv"
df = pd.read_csv(P, encoding="utf-8-sig", dtype=str)
df["name"] = df.iloc[:, 7].str.strip()
df["sid"] = df.iloc[:, 8].map(lambda s: f"{int(re.search(r'(\d+)', s).group(1))}.mp3")
pr = df.iloc[:, 17].fillna("")

for kw in ["损坏", "无法播放", "音质", "模糊", "过大", "过小"]:
    sub = df[pr.str.contains(kw)]
    print(f"--- {kw}: {len(sub)} rows")
    for nm, g in sub.groupby("name"):
        print(f"  {nm}: {sorted(g['sid'].tolist(), key=lambda x:int(x.split('.')[0]))}")
