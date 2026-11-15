# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import re

pd.set_option("display.width", 240)
P = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\374437060_按文本_情绪诱发情况评估（视频）_1271_1269(Sheet1).csv"
M = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集\视频对应关系.csv"
df = pd.read_csv(P, encoding="utf-8-sig", dtype=str)
mp = pd.read_csv(M, encoding="utf-8-sig", dtype=str)
c = df.columns

df["rater"] = df[c[7]].str.strip().str.replace("·", "", regex=False).str.replace(" ", "", regex=False)
df["sid_raw"] = df[c[8]].str.strip()
df["sid"] = df["sid_raw"].map(lambda s: "38.mp4" if s.startswith("388") else f"{int(re.search(r'(\d+)', s).group(1))}.mp4")
df["sec"] = df[c[2]].str.replace("秒", "", regex=False).astype(float)
df["v"] = df[c[9]].replace({"非常愉快": "9", "非常不愉快": "1"}).astype(float)
df["a"] = df[c[10]].replace({"非常激烈": "9", "非常平静": "1"}).astype(float)
df["v_raw"] = df[c[9]].str.strip()
df["a_raw"] = df[c[10]].str.strip()

print("rows", len(df), "songs", df.sid.nunique(), "raters", df.rater.nunique())
print("raw id variants", df.sid_raw.nunique())
print("missing videos", sorted(set(mp["新文件名"]) - set(df.sid)))
print("extra videos", sorted(set(df.sid) - set(mp["新文件名"])))

df["idx"] = df[c[0]].astype(int)
d = df.sort_values("idx").drop_duplicates(["rater", "sid"], keep="first")
print("after dedupe", len(d))
print("per-rater counts")
print(d.groupby("rater").size())
print("per-video count distribution")
print(d.groupby("sid").size().value_counts().sort_index())
print("time median", d.sec.median())

# rater reliability
piv_v = d.pivot_table(index="sid", columns="rater", values="v", aggfunc="mean")
piv_a = d.pivot_table(index="sid", columns="rater", values="a", aggfunc="mean")
for r in piv_v.columns:
    ov = piv_v.drop(columns=[r]).mean(axis=1)
    oa = piv_a.drop(columns=[r]).mean(axis=1)
    print(f"{r}: n={d[d.rater==r].shape[0]} vmean={piv_v[r].mean():.2f} amean={piv_a[r].mean():.2f} "
          f"vsd={piv_v[r].std():.2f} asd={piv_a[r].std():.2f} rv={piv_v[r].corr(ov):.2f} ra={piv_a[r].corr(oa):.2f} "
          f"medsec={d[d.rater==r].sec.median():.0f}")

print("\ncategory means")
d2 = d.merge(mp[["新文件名", "类别"]], left_on="sid", right_on="新文件名")
print(d2.groupby("类别")[["v", "a"]].agg(["mean", "std"]).round(2))
print(d2.groupby("类别")["q6" if "q6" in d2 else c[12]].apply(lambda s: s.value_counts(normalize=True).head(3)))
