# -*- coding: utf-8 -*-
import pandas as pd
import re

pd.set_option("display.width", 250)
P = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\376653806_按文本_情绪诱发情况评估（音乐）_1088_1087(Sheet1).csv"
df = pd.read_csv(P, encoding="utf-8-sig", dtype=str)
df["name"] = df.iloc[:, 7].str.strip()
df["sid"] = df.iloc[:, 8].map(lambda s: f"{int(re.search(r'(\d+)', s).group(1))}.mp3")

dup = df[df.duplicated(["name", "sid"], keep=False)].sort_values(["name", "sid", "序号"])
print("dup rows:", len(dup))
print(dup[["序号", "name", "sid", df.columns[9], df.columns[10], df.columns[17]]].to_string())
print()
print("n per song after dedupe:")
n = df.drop_duplicates(["name", "sid"])["sid"].value_counts()
print(n.value_counts().sort_index())
print("songs with n<8:", n[n < 8].to_dict())
print("total after dedupe:", len(df.drop_duplicates(["name", "sid"])))
