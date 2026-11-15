# -*- coding: utf-8 -*-
"""
山科情感视频数据集 —— 单条视频质量评分与排序（生产脚本）

与音乐版使用同一套评分框架：
  Base = E(50) + C(20) + L(15) + D(10) + N(5)
  Final = Base × G（第11题播放问题门控）
差异：
  - 第10题改为“片段可理解度”，理解度越高越好（音乐版是歌词理解越低越好）
  - 第11题按视频问题类型赋权（画面模糊、音画不同步、杂音、卡顿等）
  - 目标人数 10（10 名完整评分者）
"""
import os
import re
import json
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 200)

SEED = 20260810
RNG = np.random.default_rng(SEED)

ROOT = r"C:\Users\24114\Desktop\EEG Emotion Recognition"
DATA = os.path.join(ROOT, "山科数据集")
OUT = os.path.join(ROOT, "视频质量评分输出")
os.makedirs(OUT, exist_ok=True)

SURVEY = os.path.join(DATA, "374437060_按文本_情绪诱发情况评估（视频）_1271_1269(Sheet1).csv")
MAPCSV = os.path.join(DATA, "视频对应关系.csv")

# ------------------------------------------------------------------ #
# 1. 读取与清洗
# ------------------------------------------------------------------ #
raw = pd.read_csv(SURVEY, encoding="utf-8-sig", dtype=str)
mp = pd.read_csv(MAPCSV, encoding="utf-8-sig", dtype=str)
C = raw.columns

df = pd.DataFrame({
    "idx": raw[C[0]].astype(int),
    "submit": raw[C[1]],
    "sec": raw[C[2]].str.replace("秒", "", regex=False).astype(float),
    "rater": raw[C[7]].str.strip().str.replace("·", "", regex=False).str.replace(" ", "", regex=False),
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
    s = str(s).strip()
    if s.startswith("388"):  # 张涵博把 38.mp4 误写成 388.mp4
        return "38.mp4"
    m = re.search(r"(\d+)", s)
    return f"{int(m.group(1))}.mp4" if m else s


df["sid"] = df["sid_raw"].map(norm_sid)
df["video_no"] = df["sid"].str.replace(".mp4", "", regex=False).astype(int)

raw_sid_variants = sorted(df["sid_raw"].unique())
n_variants = len(raw_sid_variants)
n_songs = df["sid"].nunique()

n0 = len(df)
df = df.sort_values("idx").drop_duplicates(["rater", "sid"], keep="first").copy()
n_dedup = len(df)

df["v"] = df["v_raw"].replace({"非常愉快": "9", "非常不愉快": "1"}).astype(float)
df["a"] = df["a_raw"].replace({"非常激烈": "9", "非常平静": "1"}).astype(float)

# ---- 评分者有效性筛查 ----
rater_stats = df.groupby("rater").agg(
    n=("v", "size"), v_sd=("v", "std"), a_sd=("a", "std"),
    v_mean=("v", "mean"), a_mean=("a", "mean"), med_sec=("sec", "median"),
).reset_index()

cons_v, cons_a = {}, {}
pv = df.pivot_table(index="sid", columns="rater", values="v", aggfunc="mean")
pa = df.pivot_table(index="sid", columns="rater", values="a", aggfunc="mean")
for r in pv.columns:
    cons_v[r] = pv[r].corr(pv.drop(columns=[r]).mean(axis=1))
    cons_a[r] = pa[r].corr(pa.drop(columns=[r]).mean(axis=1))
rater_stats["r_v"] = rater_stats["rater"].map(cons_v)
rater_stats["r_a"] = rater_stats["rater"].map(cons_a)
rater_stats["straightline"] = (rater_stats["v_sd"] < 1.0) & (rater_stats["a_sd"] < 1.0)
rater_stats["excluded"] = rater_stats["straightline"]
excluded = rater_stats.loc[rater_stats["excluded"], "rater"].tolist()

# ------------------------------------------------------------------ #
# 2. 逐条评分
# ------------------------------------------------------------------ #
MAP5 = {"产生了非常清晰、突出的主导情绪": 16.0,
        "产生了较为清晰的主导情绪": 12.0,
        "能够辨认出情绪，但主导情绪不够明确": 7.0,
        "产生了一些情绪，但感受比较模糊": 3.0,
        "没有产生明显情绪": 0.0}
MAP7 = {"总时长75%以上": 12.0, "约占总时长50%-75%": 9.0, "约占总时长25%-50%": 5.5,
        "不足总时长25%": 2.0, "无法判断": 0.0}
MAP8 = {"主导情绪从头到尾基本稳定": 9.0, "有一定波动，但主导情绪不变": 7.0,
        "有明显反转或频繁情绪变化": 3.0, "无法判断": 1.0}
MAP9 = {"从未接触过": 1.0, "隐约见过或听过": 0.8,
        "比较熟悉，知道大概故事情节": 0.5, "非常熟悉，能预想到后续内容": 0.2}
# 视频第10题：理解度越高越好（片段自洽）
MAP10 = {"基本完全理解": 1.0, "大部分能够理解": 0.8, "能够理解一部分": 0.55,
         "大部分无法理解": 0.25, "完全无法理解": 0.0}
EMO = ["悲伤/失落", "激昂", "愉快", "温馨/放松", "恐惧/不安"]

df["s5"] = df["q5"].map(MAP5)
df["s7"] = df["q7"].map(MAP7)
df["s8"] = df["q8"].map(MAP8)
df["s6"] = np.where(df["q6"].isin(EMO), 8.0, 0.0)
df["s_int"] = 5.0 * np.clip(((df["v"] - 5).abs() + (df["a"] - 5).abs()) / 4.0, 0, 1)
df["E_row"] = df[["s5", "s7", "s8", "s6", "s_int"]].sum(axis=1)

df["s9"] = df["q9"].map(MAP9)
df["s10"] = df["q10"].map(MAP10)
df["D_row"] = 10.0 * (0.5 * df["s9"] + 0.5 * df["s10"])

# ---- Q11 / Q12 视频问题 ----
SEV = {"损坏": 1.0, "无法播放": 1.0, "不同步": 0.9, "加速": 0.9, "模糊": 0.8,
       "杂音": 0.65, "内容": 0.6, "卡顿": 0.6, "音量": 0.55, "其他": 0.5}


def classify(text):
    if text.strip() in ("无", "没有"):
        return None
    if "损坏" in text:
        return "损坏"
    if ("无法播放" in text) or ("播放不了" in text):
        return "无法播放"
    if "不同步" in text:
        return "不同步"
    if ("加速" in text) or ("倍速" in text):
        return "加速"
    if ("模糊" in text) or ("清晰度" in text) or ("画质" in text) or (("画面" in text) and ("不清" in text)):
        return "模糊"
    if ("过大" in text) or ("过小" in text):
        return "音量"
    if "卡顿" in text:
        return "卡顿"
    if any(k in text for k in ["杂音", "噪音", "音频", "声音", "听不清", "不清晰"]):
        return "杂音"
    if any(k in text for k in ["难以理解", "看不懂", "不理解", "字幕"]):
        return "内容"
    return "其他"


def parse_q11(s):
    s = str(s)
    if s in ("", "没有问题"):
        return 0.0, set(), False
    parts = [p for p in s.split("┋") if p]
    has_none = "没有问题" in parts
    tags, sev = set(), []
    for p in parts:
        if p == "没有问题":
            continue
        m = re.search(r"〖(.*)〗", p)
        t = classify(m.group(1) if m else p)
        if t is None:
            continue
        tags.add(t)
        sev.append(SEV[t])
    if not sev:
        return 0.0, set(), False
    v = 1.0 - float(np.prod([1.0 - x for x in sev]))
    if has_none:
        v *= 0.9
    return v, tags, has_none


def parse_q12(s):
    s = str(s).strip()
    if s in ("", "没有", "nan"):
        return 0.0, ""
    m = re.search(r"〖(.*)〗", s)
    t = classify(m.group(1) if m else s)
    if t is None:
        return 0.0, ""
    w = {"模糊": 0.6, "杂音": 0.55, "加速": 0.7, "不同步": 0.7,
         "内容": 0.5, "卡顿": 0.5, "音量": 0.5, "损坏": 0.8, "无法播放": 0.8}.get(t, 0.4)
    return w, t


q11 = df["q11"].map(parse_q11)
q12 = df["q12"].map(parse_q12)
df["p11"] = [x[0] for x in q11]
df["p11_tags"] = [x[1] for x in q11]
df["p11_contra"] = [x[2] for x in q11]
df["p12"] = [x[0] for x in q12]
df["p12_tag"] = [x[1] for x in q12]
df["p_row"] = 1.0 - (1.0 - df["p11"]) * (1.0 - df["p12"])
df["p_tags_all"] = [set(a) | ({b} if b else set()) for a, b in zip(df["p11_tags"], df["p12_tag"])]
df["severe"] = df["p11_tags"].map(lambda t: bool(t & {"损坏", "无法播放", "不同步", "加速"}))
df["valid"] = ~df["severe"]

# 剔除无效评分者（保留 df_all 用于敏感性分析）
df_all = df.copy()
df = df[~df["rater"].isin(excluded)].copy()
RATERS = sorted(df["rater"].unique())
N_R = len(RATERS)
N_TARGET = 10.0  # 10 名完整评分者
n_analysis = len(df)

# ------------------------------------------------------------------ #
# 3. 单条聚合
# ------------------------------------------------------------------ #
cat_map = mp.set_index("新文件名")["类别"].to_dict()


def want(cat):
    return (cat[0] == "H", cat[2] == "H")


prob_song = df_all.groupby("sid").agg(
    w_fixed=("p_row", "mean"),
    raw_rate_fixed=("p_row", lambda s: float((s > 0).mean())),
    problem_raters_fixed=("p_row", lambda s: int((s > 0).sum())),
)
TAG_MAP = df_all.groupby("sid")["p_tags_all"].apply(
    lambda S: "、".join(sorted(set().union(*S))) if len(S) else "")


def score_all(d, with_detail=True):
    d = d.copy()
    d["is_emo"] = d["q6"].isin(EMO)
    d["is_unk"] = d["q6"].eq("无法判断")
    d["cat"] = d["sid"].map(cat_map)
    wv = d["cat"].map(lambda c: want(c)[0])
    wa = d["cat"].map(lambda c: want(c)[1])
    d["hit"] = ((d["v"] > 5) == wv) & ((d["a"] > 5) == wa)
    d["e_v"] = np.where(d["valid"], d["E_row"], np.nan)
    d["d_v"] = np.where(d["valid"], d["D_row"], np.nan)
    d["v_v"] = np.where(d["valid"], d["v"], np.nan)
    d["a_v"] = np.where(d["valid"], d["a"], np.nan)
    d["hit_v"] = np.where(d["valid"], d["hit"], np.nan)
    d["emo_v"] = np.where(d["valid"] & d["is_emo"], 1.0, 0.0)
    d["unk_v"] = np.where(d["valid"] & d["is_unk"], 1.0, np.nan)
    n_valid = d.groupby("sid")["valid"].sum()
    zero = n_valid[n_valid == 0].index
    if len(zero):
        mask = d["sid"].isin(zero)
        for a, b in [("e_v", "E_row"), ("d_v", "D_row"), ("v_v", "v"), ("a_v", "a"), ("hit_v", "hit")]:
            d.loc[mask, a] = d.loc[mask, b]
        d.loc[mask, "emo_v"] = d.loc[mask, "is_emo"].astype(float)
        d.loc[mask, "unk_v"] = d.loc[mask, "is_unk"].astype(float)
    d["valid_n"] = d["valid"].astype(int)
    d.loc[d["sid"].isin(zero), "valid_n"] = 1

    g = d.groupby("sid")
    out = pd.DataFrame(index=g.size().index)
    out["n_all"] = g.size()
    out["n_valid"] = g["valid_n"].sum()
    out["E"] = g["e_v"].mean()
    out["D"] = g["d_v"].mean()
    out["v_mean"] = g["v_v"].mean()
    out["a_mean"] = g["a_v"].mean()
    out["v_sd"] = g["v_v"].std(ddof=1)
    out["a_sd"] = g["a_v"].std(ddof=1)
    out["hit_rate"] = g["hit_v"].mean()
    out["emo_rate"] = g["emo_v"].mean()
    out["unk_rate"] = g["unk_v"].mean().fillna(0)

    out["disp"] = (out["v_sd"] + out["a_sd"]) / 2
    cons = np.clip(1 - (out["disp"] - 0.7) / 2.0, 0, 1).fillna(0.5)
    emo_counts = d[d["valid"] & d["is_emo"]].groupby(["sid", "q6"]).size().unstack(fill_value=0)
    for e in EMO:
        if e not in emo_counts.columns:
            emo_counts[e] = 0
    max_share = (emo_counts[EMO].max(axis=1) / out["n_valid"]).fillna(0)
    out["max_share"] = max_share
    adj_agree = (max_share * (1 - out["unk_rate"])).fillna(0)
    agree_norm = np.clip((adj_agree - 0.2) / 0.5, 0, 1)
    out["C"] = 20.0 * (0.5 * agree_norm + 0.5 * cons)

    out["cat"] = g["cat"].first()
    ideal_v = np.where(out["cat"].map(lambda c: want(c)[0]), 7.0, 3.0)
    ideal_a = np.where(out["cat"].map(lambda c: want(c)[1]), 7.0, 3.0)
    dist = np.hypot(out["v_mean"] - ideal_v, out["a_mean"] - ideal_a)
    prox = np.clip(1 - dist / 5.657, 0, 1)
    adj_hit = np.clip((out["hit_rate"] - 0.25) / 0.6, 0, 1)
    out["prox"] = prox
    out["L"] = 15.0 * (0.6 * adj_hit.fillna(0) + 0.4 * prox.fillna(0))
    out.loc[out["cat"].isna(), "L"] = 10.0

    out["N"] = 5.0 * np.minimum(1.0, out["n_valid"] / N_TARGET)
    out["Base"] = out[["E", "C", "L", "D", "N"]].sum(axis=1)

    out["w"] = out.index.map(prob_song["w_fixed"])
    out["raw_rate"] = out.index.map(prob_song["raw_rate_fixed"])
    out["problem_raters"] = out.index.map(prob_song["problem_raters_fixed"])
    out["tags"] = out.index.map(TAG_MAP).fillna("")
    out["G"] = np.clip(np.exp(-3.0 * out["w"]) * np.where(out["w"] > 0, 0.75, 1.0), 0.05, 1.0)
    out["Score"] = out["Base"] * out["G"]
    return out.reset_index()


res = score_all(df)
res = res.sort_values(["Score", "sid"], ascending=[False, True]).reset_index(drop=True)
res["rank"] = np.arange(1, len(res) + 1)
res["rank_in_cat"] = res.groupby("cat")["Score"].rank(ascending=False, method="min").astype(int)


def grade(s):
    # 视频分数整体偏高（多数片段诱发清晰），阈值按视频分布校准
    if s >= 92:
        return "S"
    if s >= 85:
        return "A"
    if s >= 75:
        return "B"
    if s >= 60:
        return "C"
    return "D"


res["grade"] = res["Score"].map(grade)

# ---- 离散情绪标签（第 6 题多数票） ----
DISCRETE_ORDER = ["悲伤/失落", "激昂", "愉快", "温馨/放松", "恐惧/不安", "混合/不明确"]


def assign_discrete(g):
    vg = g[g["valid"]]
    if len(vg) == 0:
        vg = g
    n = len(vg)
    c = vg["q6"].value_counts()
    emo = {e: int(c.get(e, 0)) for e in DISCRETE_ORDER[:-1]}
    unk = int(c.get("无法判断", 0))
    top = max(emo, key=emo.get)
    top_n = emo[top]
    second = sorted(emo.values(), reverse=True)[1]
    share = top_n / n
    if share >= 0.4 and top_n > second and top_n > unk:
        return top, share, top_n, unk
    return "混合/不明确", share, top_n, unk


disc = {sid: assign_discrete(g) for sid, g in df.groupby("sid")}
res["discrete"] = res["sid"].map(lambda s: disc[s][0])
res["discrete_agree"] = res["sid"].map(lambda s: disc[s][1])
res["discrete_top_n"] = res["sid"].map(lambda s: disc[s][2])
res["discrete_unk"] = res["sid"].map(lambda s: disc[s][3])
res["rank_in_discrete"] = res.groupby("discrete")["Score"].rank(ascending=False, method="min").astype(int)

# ------------------------------------------------------------------ #
# 4. Bootstrap
# ------------------------------------------------------------------ #
B = 500
boot_scores = np.zeros((B, n_songs))
sids = res["sid"].tolist()
sid_pos = {s: i for i, s in enumerate(sids)}

for b in range(B):
    samp = RNG.choice(RATERS, size=N_R, replace=True)
    parts = [df[df["rater"] == r] for r in samp]
    bd = pd.concat(parts, keys=np.arange(len(parts))).reset_index(drop=True)
    br = score_all(bd).set_index("sid")["Score"]
    boot_scores[b, [sid_pos[s] for s in br.index]] = br.values

lo = np.percentile(boot_scores, 2.5, axis=0)
hi = np.percentile(boot_scores, 97.5, axis=0)
res["ci_lo"] = [lo[sid_pos[s]] for s in res["sid"]]
res["ci_hi"] = [hi[sid_pos[s]] for s in res["sid"]]
boot_rank = np.argsort(np.argsort(-boot_scores, axis=1), axis=1) + 1
res["rank_lo"] = [np.percentile(boot_rank[:, sid_pos[s]], 2.5) for s in res["sid"]]
res["rank_hi"] = [np.percentile(boot_rank[:, sid_pos[s]], 97.5) for s in res["sid"]]


# 敏感性
def spearman(a, b):
    return pd.Series(a).corr(pd.Series(b), method="spearman")


sens = {}
# 无直线作答者；改为检验“剔除仅完成 29 条的部分评分者赵瀚”的影响
alt = df[df["rater"] != "赵瀚"].copy()
sens["剔除部分评分者赵瀚"] = spearman(res.set_index("sid")["Score"], score_all(alt).set_index("sid")["Score"])

base_w = np.array([0.50, 0.20, 0.15, 0.10, 0.05])
for tag, delta in [("E权重+20%", 0), ("C权重+20%", 1), ("L权重+20%", 2)]:
    w = base_w.copy()
    w[delta] *= 1.2
    w = w / w.sum()
    s = res[["E", "C", "L", "D", "N"]].values @ w * res["G"].values
    sens[tag] = spearman(res["Score"], s)

for k in [2.0, 4.0]:
    g2 = np.clip(np.exp(-k * res["w"]) * np.where(res["w"] > 0, 0.75, 1.0), 0.05, 1.0)
    sens[f"门控k={k}"] = spearman(res["Score"], res["Base"] * g2)

s_noL = (res["E"] + res["C"] + res["D"] + res["N"]) * res["G"]
sens["不含标签效度L"] = spearman(res["Score"], s_noL)
s_noD = (res["E"] + res["C"] + res["L"] + res["N"]) * res["G"]
sens["不含干扰控制D"] = spearman(res["Score"], s_noD)
sens_df = pd.DataFrame({"敏感性场景": list(sens.keys()), "Spearman秩相关": [round(v, 4) for v in sens.values()]})

# ------------------------------------------------------------------ #
# 5. 汇总输出
# ------------------------------------------------------------------ #
def fmt(x, n=1):
    return np.round(x, n)


rank_out = pd.DataFrame({
    "排名": res["rank"],
    "视频编号": res["sid"],
    "质量总分": fmt(res["Score"]),
    "质量等级": res["grade"],
    "情感类别(四象限)": res["cat"],
    "四象限内排名": res["rank_in_cat"],
    "有效评分人数": res["n_valid"],
    "问题人数": res["problem_raters"],
    "问题报告率": fmt(res["raw_rate"], 2),
    "问题指数": fmt(res["w"], 3),
    "主要问题": res["tags"].replace("", "无"),
    "基础分": fmt(res["Base"]),
    "播放门控": fmt(res["G"], 3),
    "情绪诱发E": fmt(res["E"]),
    "一致性C": fmt(res["C"]),
    "标签效度L": fmt(res["L"]),
    "干扰控制D": fmt(res["D"]),
    "样本N": fmt(res["N"]),
    "平均效价": fmt(res["v_mean"], 2),
    "平均唤醒": fmt(res["a_mean"], 2),
    "标签命中率": fmt(res["hit_rate"], 2),
    "分数95%CI": [f"{a:.1f}–{b:.1f}" for a, b in zip(res["ci_lo"], res["ci_hi"])],
    "排名95%CI": [f"{int(a)}–{int(b)}" for a, b in zip(res["rank_lo"], res["rank_hi"])],
    "离散标签": res["discrete"],
    "离散标签一致率": fmt(res["discrete_agree"], 2),
    "离散类内排名": res["rank_in_discrete"],
})
rank_out.to_csv(os.path.join(OUT, "视频质量排序.csv"), index=False, encoding="utf-8-sig")

grade_counts = res["grade"].value_counts().reindex(["S", "A", "B", "C", "D"]).fillna(0).astype(int)

res.to_pickle(os.path.join(OUT, "_res.pkl"))
df.to_pickle(os.path.join(OUT, "_rows.pkl"))
rater_stats.to_csv(os.path.join(OUT, "_rater_stats.csv"), index=False, encoding="utf-8-sig")
sens_df.to_csv(os.path.join(OUT, "_sensitivity.csv"), index=False, encoding="utf-8-sig")
with open(os.path.join(OUT, "_meta.json"), "w", encoding="utf-8") as f:
    json.dump(dict(n_raw=n0, n_dedup=n_dedup, n_analysis=n_analysis, n_songs=n_songs,
                   n_variants=n_variants, excluded=excluded, n_raters=N_R,
                   n_target=N_TARGET, grade_counts=grade_counts.to_dict(), B=B), f, ensure_ascii=False, indent=2)

print(rank_out.head(12).to_string(index=False))
print()
print(rank_out.tail(10).to_string(index=False))
print()
print(grade_counts.to_string())
print(sens_df.to_string(index=False))
print("done")
