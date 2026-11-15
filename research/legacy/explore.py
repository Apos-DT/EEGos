# -*- coding: utf-8 -*-
import pandas as pd
import re

pd.set_option("display.width", 220)
pd.set_option("display.max_colwidth", 80)

P = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\376653806_按文本_情绪诱发情况评估（音乐）_1088_1087(Sheet1).csv"
df = pd.read_csv(P, encoding="utf-8-sig", dtype=str)

def norm(s):
    m = re.search(r"(\d+)", str(s))
    return f"{int(m.group(1))}.mp3" if m else str(s)

df["sid"] = df.iloc[:, 8].map(norm)
df["name"] = df.iloc[:, 7].str.strip()
pr = df.iloc[:, 17].fillna("")
d = df[~pr.str.strip().eq("没有问题")]
print(d.groupby(["sid", pr]).size().to_string())
print()
print(d[["sid", "name", pr, df.columns[18]]].to_string())
