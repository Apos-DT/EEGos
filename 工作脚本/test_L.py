# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import re

pd.set_option("display.width", 250)
BASE = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集"
raw = pd.read_csv(BASE + r"\376653806_按文本_情绪诱发情况评估（音乐）_1088_1087(Sheet1).csv", encoding="utf-8-sig", dtype=str)
mp = pd.read_csv(BASE + r"\音乐对应关系.csv", encoding="utf-8-sig", dtype=str)
C = raw.columns
df = pd.DataFrame({
    "idx": raw[C[0]].astype(int), "sec": raw[C[2]].str.replace("秒", "", regex=False).astype(float),
    "rater": raw[C[7]].str.strip(), "sid_raw": raw[C[8]].str.strip(),
    "v_raw": raw[C[9]].str.strip(), "a_raw": raw[C[10]].str.strip(),
    "q6": raw[C[12]].str.strip(), "q11": raw[C[17]].fillna("").str.strip(),
})
df["sid"] = df["sid_raw"].map(lambda s: f"{int(re.search(r'(\d+)', s).group(1))}.mp3")
df = df.sort_values("idx").drop_duplicates(["rater", "sid"])
df["v"] = df["v_raw"].replace({"非常愉快": "9", "非常不愉快": "1"}).astype(float)
df["a"] = df["a_raw"].replace({"非常激烈": "9", "非常平静": "1"}).astype(float)
df = df.merge(mp[["新文件名", "类别"]], left_on="sid", right_on="新文件名", how="left")
df = df[df.rater != "刘佳悦"].copy()

gv, ga = df["v"].mean(), df["a"].mean()
df["v_c"] = df["v"] - df.groupby("rater")["v"].transform("mean") + gv
df["a_c"] = df["a"] - df.groupby("rater")["a"].transform("mean") + ga


def congruence(sub, centered):
    v = sub["v_c"] if centered else sub["v"]
    a = sub["a_c"] if centered else sub["a"]
    tv = 1 if sub["类别"].iloc[0][0] == "H" else 0
    ta = 1 if sub["类别"].iloc[0][2] == "H" else 0
    base_v = gv if centered else 5.0
    base_a = ga if centered else 5.0
    hit = ((v > base_v) == bool(tv)) & ((a > base_a) == bool(ta))
    mv, ma = v.mean(), a.mean()
    ideal = ((gv + 2) if tv else (gv - 2), (ga + 2) if ta else (ga - 2))
    dist = np.hypot(mv - ideal[0], ma - ideal[1])
    prox = np.clip(1 - dist / 5.657, 0, 1)
    adj = np.clip((hit.mean() - 0.25) / 0.6, 0, 1)
    return hit.mean(), prox, 15 * (0.6 * adj + 0.4 * prox)


out = []
for sid, sub in df.groupby("sid"):
    h0, p0, L0 = congruence(sub, False)
    h1, p1, L1 = congruence(sub, True)
    out.append(dict(sid=sid, cat=sub["类别"].iloc[0], hit_raw=h0, prox_raw=p0, L_raw=L0,
                    hit_c=h1, prox_c=p1, L_c=L1, v=sub["v"].mean(), a=sub["a"].mean(),
                    vc=sub["v_c"].mean(), ac=sub["a_c"].mean()))
o = pd.DataFrame(out)
print(o.groupby("cat")[["hit_raw", "L_raw", "hit_c", "L_c", "v", "a", "vc", "ac"]].mean().round(2))
print()
print("corr L_raw vs L_c:", o["L_raw"].corr(o["L_c"]).round(3))
print("L_c describe:", o["L_c"].describe().round(2).to_dict())
print(o.sort_values("L_c").head(8).to_string())
print(o.sort_values("L_c").tail(8).to_string())
