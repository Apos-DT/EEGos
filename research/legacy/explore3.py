# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import re

pd.set_option("display.width", 240)
pd.set_option("display.max_rows", 200)

P = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\376653806_按文本_情绪诱发情况评估（音乐）_1088_1087(Sheet1).csv"
df = pd.read_csv(P, encoding="utf-8-sig", dtype=str)
df["name"] = df.iloc[:, 7].str.strip()
df["sid"] = df.iloc[:, 8].map(lambda s: f"{int(re.search(r'(\d+)', s).group(1))}.mp3")
pr = df.iloc[:, 17].fillna("")
q12 = df.iloc[:, 18].fillna("")

def tag(x):
    x = str(x)
    if "无" == x.replace("其他〖", "").replace("〗", "").strip():
        return "无"
    if "损坏" in x:
        return "损坏"
    if "无法播放" in x or "播放不了" in x:
        return "无法播放"
    if "音质" in x or "模糊" in x or "糊" in x or "低音质" in x or "不清" in x or "录音" in x:
        return "音质"
    if "过大" in x or "过小" in x:
        return "音量"
    if "卡顿" in x:
        return "卡顿"
    if "名字" in x or "命名" in x or "对应" in x or "重复" in x:
        return "内容"
    if x.strip() == "没有问题":
        return "无"
    return "其他:" + x

df["ptag"] = pr.map(tag)
df["q12_flag"] = ~q12.eq("没有")
print(pd.crosstab(df["name"], df["ptag"]))
print()
print("q12 by rater")
print(df[df.q12_flag].groupby(["name", "q12"]).size().to_string())
