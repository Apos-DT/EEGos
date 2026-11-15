# -*- coding: utf-8 -*-
import csv
import os

OUT = r"C:\Users\24114\Desktop\EEG Emotion Recognition\文献"

ROWS = [
    ("01", "EEG Based Emotion Recognition: A Tutorial and Review", "已下载",
     "01_EEG_Based_Emotion_Recognition_Tutorial_Review_2022.pdf",
     "arXiv:2203.11279（作者版，非 ACM 排版）"),
    ("02", "Research Progress of EEG-Based Emotion Recognition: A Survey", "未下载（闭源）", "",
     "https://doi.org/10.1145/3666002"),
    ("03", "Emotion recognition via affective EEG signals: State of the art", "未下载（SSRN 连接超时）", "",
     "https://doi.org/10.1016/j.neucom.2025.130418"),
    ("04", "DDA: Dynamic Domain Adaptation for Class-Aware Cross-Subject and Cross-Session EEG Emotion Recognition", "未下载（闭源）", "",
     "https://doi.org/10.1109/JBHI.2022.3210158"),
    ("05", "CMJDA: Multimodal Semi-Supervised Domain Adaptation ...", "未下载（闭源）", "",
     "https://doi.org/10.1109/TIM.2025.3551924"),
    ("06", "SSAS: Cross-subject EEG-based emotion recognition through source selection with adversarial strategy", "已下载",
     "06_SSAS_Source_Selection_Adversarial_Strategy_2026.pdf", "arXiv:2512.13458"),
    ("07", "BiDANN: A Bi-Hemisphere Domain Adversarial Neural Network Model", "未下载（闭源）", "",
     "https://doi.org/10.1109/TAFFC.2018.2885474"),
    ("08", "TT-CDAN: A Novel Conditional Adversarial Domain Adaptation Network", "未下载（闭源）", "",
     "https://doi.org/10.1109/TAFFC.2025.3588873"),
    ("09", "DAPLP: Unsupervised Domain Adaptation With Pseudo-Label Propagation", "未下载（闭源）", "",
     "https://doi.org/10.1109/TIM.2025.3553234"),
    ("10", "MSGDAN: Multi-source Selective Graph Domain Adaptation Network", "未下载（闭源）", "",
     "https://doi.org/10.1016/j.neunet.2024.106742"),
    ("11", "Sera: Separated Coarse-to-fine Representation Alignment", "未下载（闭源）", "",
     "https://doi.org/10.1145/3746027.3754775"),
    ("12", "MIND-EEG: Multi-Granularity Integration Network With Discrete Codebook", "已下载",
     "12_MIND-EEG_Multi-Granularity_Discrete_Codebook_2026.pdf", "arXiv:2501.16230"),
    ("13", "PCL-TDGCN: Prototypical Contrastive Learning With Temporal Dynamic GCN", "未下载（闭源）", "",
     "https://doi.org/10.1109/TAFFC.2026.3671020"),
    ("14", "TAHAG: Two-Stage Domain Adaptation With Hybrid Adaptive Graph Learning", "未下载（闭源）", "",
     "https://doi.org/10.1109/TAFFC.2025.3580787"),
    ("15", "CLISA: Contrastive Learning of Subject-Invariant EEG Representations", "已下载",
     "15_CLISA_Contrastive_Subject-Invariant_EEG_2023.pdf", "arXiv:2109.09559"),
    ("16", "GMSS: Graph-Based Multi-Task Self-Supervised Learning", "已下载",
     "16_GMSS_Graph_Multi-Task_Self-Supervised_2023.pdf", "arXiv:2205.01030"),
    ("17", "DMMR: Cross-Subject Domain Generalization via Denoising Mixed Mutual Reconstruction", "已下载",
     "17_DMMR_Denoising_Mixed_Mutual_Reconstruction_2024.pdf", "AAAI 开放获取"),
    ("18", "MSHCL: Multi-Scale Hyperbolic Contrastive Learning", "未下载（闭源）", "",
     "https://doi.org/10.1109/TAFFC.2025.3535542"),
    ("19", "Information Fusion: Regional to Global Fusion with Spatial-Temporal Semantic Alignment", "未下载（闭源）", "",
     "https://doi.org/10.1016/j.inffus.2026.104224"),
    ("20", "SEED-VII: A Multimodal Dataset of Six Basic Emotions", "未下载（闭源）", "",
     "https://doi.org/10.1109/TAFFC.2024.3485057"),
    ("D1", "SEED: Investigating Critical Frequency Bands and Channels", "未下载（闭源）", "",
     "https://doi.org/10.1109/TAMD.2015.2431497"),
    ("D2", "SEED-IV / EmotionMeter", "未下载（闭源）", "",
     "https://doi.org/10.1109/TCYB.2018.2797176"),
    ("D5", "DEAP: A Database for Emotion Analysis Using Physiological Signals", "已下载",
     "D5_DEAP_Database_Emotion_Analysis_2012.pdf", "UNIGE 机构库"),
    ("D6", "MPED: A Multi-Modal Physiological Emotion Database", "已下载",
     "D6_MPED_Multi-Modal_Physiological_Emotion_Database_2019.pdf", "IEEE Access 开放获取"),
    ("D7", "DREAMER: A Database for Emotion Recognition Through EEG and ECG", "未下载（403）", "",
     "https://doi.org/10.1109/JBHI.2017.2688239"),
    ("D8", "FACED: A Large Finer-grained Affective Computing EEG Dataset", "已下载",
     "D8_FACED_Finer-grained_Affective_Computing_EEG_2023.pdf", "Scientific Data 开放获取"),
    ("D9", "MAHNOB-HCI: A Multimodal Database for Affect Recognition", "未下载（闭源）", "",
     "https://doi.org/10.1109/T-AFFC.2011.25"),
]

with open(os.path.join(OUT, "_下载清单.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["编号", "文献", "状态", "本地文件", "来源/DOI"])
    w.writerows(ROWS)

downloaded = [r for r in ROWS if r[2] == "已下载"]
lines = [
    "# 文献下载说明",
    "",
    f"共整理 27 条文献，**已下载 {len(downloaded)} 篇可公开获取的 PDF**；其余 18 条为闭源或链接不可达，"
    "已在 `_下载清单.csv` 中逐条标注 DOI。",
    "",
    "## 已下载",
    "",
]
for r in downloaded:
    lines.append(f"- `{r[3]}` — {r[1]}（{r[4]}）")
lines += [
    "",
    "## 未下载（需机构订阅 / 链接不可达）",
    "",
    "| 编号 | 文献 | DOI |",
    "|---|---|---|",
]
for r in ROWS:
    if r[2] != "已下载":
        lines.append(f"| {r[0]} | {r[1]} | [{r[4]}]({r[4]}) |")
lines += [
    "",
    "## 说明",
    "",
    "- 有 arXiv 版本的，优先下载作者版；页码/排版可能与正式版不同。",
    "- 闭源论文（IEEE / Elsevier / ACM）需要校园网、VPN 或图书馆文献传递；DOI 链接为官方页面。",
    "- 原有文件 `fncom-15-758212.pdf` 未做改动。",
    "- 下载清单：`_下载清单.csv`。",
]
with open(os.path.join(OUT, "_README.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("downloaded", len(downloaded), "rows", len(ROWS))
