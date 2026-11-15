# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

res = pd.read_csv(r"C:\Users\24114\Desktop\EEG Emotion Recognition\工作脚本\_tmp_res.csv", encoding="utf-8-sig")
print(res.groupby("cat").agg(n=("sid", "size"), score=("Score", "mean"), base=("Base", "mean"),
                             E=("E", "mean"), C=("C", "mean"), L=("L", "mean"),
                             hit=("hit_rate", "mean"), w=("w", "mean")).round(2))
print()
print("top30 category counts:")
print(res.head(30)["cat"].value_counts())
print("bottom30 category counts:")
print(res.tail(30)["cat"].value_counts())
print()
print("score by w bucket")
res["wb"] = pd.cut(res["w"], [-0.001, 0, 0.1, 0.2, 0.3, 0.5])
print(res.groupby("wb", observed=True)["Score"].agg(["count", "mean", "min", "max"]).round(1))
print()
print("songs with 0 problems:", (res["w"] == 0).sum(), " any:", (res["w"] > 0).sum())
print(res[res["w"] > 0].sort_values("Score", ascending=False)[["sid", "Base", "w", "G", "Score", "raw_rate", "tags"]].head(20).to_string())
