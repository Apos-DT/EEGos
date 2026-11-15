# -*- coding: utf-8 -*-
import pandas as pd

r = pd.read_csv(r"C:\Users\24114\Desktop\EEG Emotion Recognition\research\quality\audio\音乐歌曲质量排序.csv",
                encoding="utf-8-sig")
c = {k: k for k in r.columns}
for _, x in r.head(25).iterrows():
    print(f"| {x['排名']} | {x['音乐歌曲编号']} | {x['质量总分']:.1f} | {x['质量等级']} | {x['情感类别']} | {x['主要问题']} |")
print("---BOTTOM")
for _, x in r.tail(10).iterrows():
    print(f"| {x['排名']} | {x['音乐歌曲编号']} | {x['质量总分']:.1f} | {x['质量等级']} | {x['情感类别']} | {x['主要问题']} |")
print("---IDS")
ids = [str(i).replace(".mp3", "") for i in r["音乐歌曲编号"]]
for i in range(0, 120, 12):
    print(", ".join(ids[i:i + 12]) + ",")
