# -*- coding: utf-8 -*-
"""
山科情感音乐数据集 —— 单曲质量评分与排序
"""
import pandas as pd
import numpy as np
import re
import json

pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 200)

BASE = r"C:\Users\24114\Desktop\EEG Emotion Recognition\山科数据集"
SURVEY = BASE + r"\376653806_按文本_情绪诱发情况评估（音乐）_1088_1087(Sheet1).csv"
MAP = BASE + r"\音乐对应关系.csv"

raw = pd.read_csv(SURVEY, encoding="utf-8-sig", dtype=str)
mp = pd.read_csv(MAP, encoding="utf-8-sig", dtype=str)

C = raw.columns
df = pd.DataFrame({
    "idx": raw[C[0]].astype(int),
    "time": pd.to_datetime(raw[C[1]], format="%Y/%m/%d %H:%M:%S", errors="coerce"),
    "sec": raw[C[2]].str.replace("秒", "", regex=False).astype(float),
    "rater": raw[C[7]].str.strip(),
    "sid_raw": raw[C[8]].str.strip(),
    "v_raw": raw[C[9]].str.strip(),
    "a_raw": raw[C[10]].str.strip(),
    "q5": raw[C[11]].str.strip(),
    "q6": raw[C[12]].str.strip(),
    "q7": raw[C[13]].str.strip(),
    "q8": raw[C[14]].str.strip(),
    "q9": raw[C[15]].str.strip(),
    "q10": raw[C[16]].str.strip(),
    "q11": raw[C[17]].fillna("").str.strip(),
    "q12": raw[C[18]].fillna("").str.strip(),
})


def norm_sid(s):
    m = re.search(r"(\d+)", str(s))
    return f"{int(m.group(1))}.mp3" if m else str(s)


df["sid"] = df["sid_raw"].map(norm_sid)
df["song_no"] = df["sid"].str.replace(".mp3", "", regex=False).astype(int)

# ---------- 量表编码 ----------
df["v"] = df["v_raw"].replace({"非常愉快": "9", "非常不愉快": "1"}).astype(float)
df["a"] = df["a_raw"].replace({"非常激烈": "9", "非常平静": "1"}).astype(float)

MAP5 = {"产生了非常清晰、突出的主导情绪": 16.0,
        "产生了较为清晰的主导情绪": 12.0,
        "能够辨认出情绪，但主导情绪不够明确": 7.0,
        "产生了一些情绪，但感受比较模糊": 3.0,
        "没有产生明显情绪": 0.0}
MAP7 = {"总时长75%以上": 12.0, "约占总时长50%-75%": 9.0, "约占总时长25%-50%": 5.5,
        "不足总时长25%": 2.0, "无法判断": 0.0}
MAP8 = {"主导情绪从头到尾基本稳定": 9.0, "有一定波动，但主导情绪不变": 7.0,
        "有明显反转或频繁情绪变化": 3.0, "无法判断": 1.0}
MAP9 = {"从未接触过": 1.0, "隐约听过": 0.8, "比较熟悉": 0.5, "非常熟悉": 0.2}
MAP10 = {"完全无法理解": 1.0, "大部分无法理解": 0.9, "能够理解一部分": 0.75,
         "大部分能够理解": 0.55, "基本完全理解": 0.35}
EMO = ["悲伤/失落", "激昂", "愉快", "温馨/放松", "恐惧/不安"]

df["s5"] = df["q5"].map(MAP5)
df["s7"] = df["q7"].map(MAP7)
df["s8"] = df["q8"].map(MAP8)
df["s6"] = np.where(df["q6"].isin(EMO), 8.0, 0.0)
df["s_int"] = 5.0 * np.clip((df["v"] - 5).abs().add((df["a"] - 5).abs()) / 4.0, 0, 1)
df["E_row"] = df[["s5", "s7", "s8", "s6", "s_int"]].sum(axis=1)

df["s9"] = df["q9"].map(MAP9)
df["s10"] = df["q10"].map(MAP10)
df["D_row"] = 10.0 * (0.6 * df["s9"] + 0.4 * df["s10"])

# ---------- Q11/Q12 问题解析 ----------
SEV = {
    "损坏": 1.0, "无法播放": 1.0, "音质": 0.8, "内容": 0.8,
    "音量": 0.55, "卡顿": 0.5, "其他": 0.5, "重复": 0.6,
}


def classify(text):
    if "无" == text.strip():
        return None
    if "损坏" in text:
        return "损坏"
    if ("无法播放" in text) or ("播放不了" in text):
        return "无法播放"
    if ("音质" in text) or ("模糊" in text) or ("糊" in text) or ("低音质" in text) or ("不清" in text) or ("录音" in text):
        return "音质"
    if ("名字" in text) or ("命名" in text) or ("对应" in text) or ("重复" in text) or ("不同" in text):
        return "内容"
    if ("过大" in text) or ("过小" in text):
        return "音量"
    if "卡顿" in text:
        return "卡顿"
    return "其他"


def parse_q11(s):
    """返回 (问题严重度 0-1, 问题标签集合, 是否自相矛盾)"""
    s = str(s)
    if s == "" or s == "没有问题":
        return 0.0, set(), False
    parts = [p for p in s.split("┋") if p]
    has_none = "没有问题" in parts
    tags, sev_comp = set(), []
    for p in parts:
        if p == "没有问题":
            continue
        m = re.search(r"〖(.*)〗", p)
        content = m.group(1) if m else p
        t = classify(content)
        if t is None:
            continue
        tags.add(t)
        sev_comp.append(SEV[t])
    if not sev_comp:
        return 0.0, set(), False
    s_or = 1.0 - np.prod([1.0 - x for x in sev_comp])  # 多问题叠加
    if has_none:
        s_or *= 0.9
    return float(s_or), tags, has_none


def parse_q12(s):
    s = str(s).strip()
    if s in ("", "没有"):
        return 0.0, ""
    m = re.search(r"〖(.*)〗", s)
    content = m.group(1) if m else s
    t = classify(content)
    if t is None:
        return 0.0, ""
    w = {"音质": 0.6, "音量": 0.5, "内容": 0.5, "损坏": 0.8, "无法播放": 0.8}.get(t, 0.4)
    return w, t


q11 = df["q11"].map(parse_q11)
q12 = df["q12"].map(parse_q12)
df["p11"] = [x[0] for x in q11]
df["p11_tags"] = [x[1] for x in q11]
df["p11_contra"] = [x[2] for x in q11]
df["p12"] = [x[0] for x in q12]
df["p12_tag"] = [x[1] for x in q12]
# 行级综合问题严重度（Q11 与 Q12 取并集）
df["p_row"] = 1.0 - (1.0 - df["p11"]) * (1.0 - df["p12"])
# 无法有效聆听（严重技术问题）→ 该行情绪评分不计入 E/C/L
df["severe"] = df["p11_tags"].map(lambda t: bool(t & {"损坏", "无法播放", "音质"}))

# ---------- 去重：同一评分者对同一首歌的重复提交，保留首次 ----------
before = len(df)
df = df.sort_values("idx").drop_duplicates(["rater", "sid"], keep="first").copy()
print(f"去重：{before} -> {len(df)} 行")

# ---------- 歌曲级聚合 ----------
rows = []
for sid, g in df.groupby("sid"):
    n_all = len(g)
    vg = g[~g["severe"]]
    n_valid = len(vg)
    if n_valid == 0:
        vg, n_valid = g, len(g)
    E = vg["E_row"].mean()
    D = vg["D_row"].mean()

    # 一致性
    share = vg["q6"].isin(EMO)
    unknown = (vg["q6"] == "无法判断").mean()
    max_share = vg.loc[share, "q6"].value_counts(normalize=True).max() if share.any() else 0.0
    max_share = 0.0 if pd.isna(max_share) else max_share
    adj_agree = max_share * (1 - unknown)
    disp = (vg["v"].std(ddof=1) + vg["a"].std(ddof=1)) / 2 if n_valid > 1 else np.nan
    cons = np.clip(1 - (disp - 0.7) / 2.0, 0, 1) if not np.isnan(disp) else 0.5
    C = 20.0 * (0.5 * adj_agree + 0.5 * cons)

    # 标签效度
    cat = mp.set_index("新文件名").loc[sid, "类别"] if sid in set(mp["新文件名"]) else None
    if cat:
        want_v_hi, want_a_hi = cat[0] == "H", cat[2] == "H"
        hit = ((vg["v"] > 5) == want_v_hi) & ((vg["a"] > 5) == want_a_hi)
        hit_rate = hit.mean()
        mv, ma = vg["v"].mean(), vg["a"].mean()
        ideal = (7.0 if want_v_hi else 3.0, 7.0 if want_a_hi else 3.0)
        dist = np.hypot(mv - ideal[0], ma - ideal[1])
        prox = np.clip(1 - dist / 5.657, 0, 1)
        adj_hit = np.clip((hit_rate - 0.25) / 0.6, 0, 1)
        L = 15.0 * (0.6 * adj_hit + 0.4 * prox)
    else:
        cat, hit_rate, dist, L = "", np.nan, np.nan, np.nan

    N = 5.0 * min(1.0, n_valid / 9.0)
    Base = E + C + L + D + N
    w = g["p_row"].mean()  # 问题指数 0-1
    G = float(np.clip(np.exp(-2.5 * w), 0.05, 1.0))
    Score = Base * G

    raw_rate = (g["p11"] > 0).mean()
    tags = set()
    for t in g["p11_tags"]:
        tags |= t
    rows.append(dict(sid=sid, song_no=int(sid.split(".")[0]), n=n_all, n_valid=n_valid,
                     E=E, C=C, L=L, D=D, N=N, Base=Base, w=w, G=G, Score=Score,
                     v_mean=vg["v"].mean(), a_mean=vg["a"].mean(),
                     v_sd=vg["v"].std(ddof=1), a_sd=vg["a"].std(ddof=1),
                     hit_rate=hit_rate, cat=cat, adj_agree=adj_agree, disp=disp,
                     raw_rate=raw_rate, tags="、".join(sorted(tags))))

res = pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)
res["rank"] = np.arange(1, len(res) + 1)
print(res.head(20).to_string())
print(res.tail(15).to_string())
print(res["Score"].describe())
print(res["Base"].describe())
print(res["w"].describe())
res.to_csv(r"C:\Users\24114\Desktop\EEG Emotion Recognition\research\legacy\_tmp_res.csv", index=False, encoding="utf-8-sig")
