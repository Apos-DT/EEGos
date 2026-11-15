# -*- coding: utf-8 -*-
import pandas as pd

r = pd.read_csv(r"C:\Users\24114\Desktop\EEG Emotion Recognition\视频质量评分输出\视频质量排序.csv",
                encoding="utf-8-sig")
for _, x in r.head(20).iterrows():
    print(f"| {x['排名']} | {x['视频编号']} | {x['质量总分']:.1f} | {x['质量等级']} | {x['情感类别(四象限)']} | {x['离散标签']} |")
print("---BOTTOM")
for _, x in r.tail(8).iterrows():
    print(f"| {x['排名']} | {x['视频编号']} | {x['质量总分']:.1f} | {x['质量等级']} | {x['情感类别(四象限)']} | {x['主要问题']} |")
print("---IDS")
ids = [str(i).replace(".mp4", "") for i in r["视频编号"]]
for i in range(0, 120, 12):
    print(", ".join(ids[i:i + 12]) + ",")
