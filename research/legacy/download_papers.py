# -*- coding: utf-8 -*-
"""下载可公开获取的论文 PDF 到 文献/ 目录，并生成下载清单。"""
import csv
import os
import urllib.request

OUT = r"C:\Users\24114\Desktop\EEG Emotion Recognition\文献"
os.makedirs(OUT, exist_ok=True)
HEAD = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8"}

# (编号, 文件名, 候选 URL 列表, 来源说明)
ITEMS = [
    ("01", "01_EEG_Based_Emotion_Recognition_Tutorial_Review_2022.pdf",
     ["https://arxiv.org/pdf/2203.11279"], "arXiv:2203.11279"),
    ("03", "03_Emotion_Recognition_Affective_EEG_State_of_the_Art_2025.pdf",
     ["https://doi.org/10.2139/ssrn.5174448"], "SSRN（可能需登录）"),
    ("06", "06_SSAS_Source_Selection_Adversarial_Strategy_2026.pdf",
     ["https://arxiv.org/pdf/2512.13458"], "arXiv:2512.13458"),
    ("12", "12_MIND-EEG_Multi-Granularity_Discrete_Codebook_2026.pdf",
     ["https://arxiv.org/pdf/2501.16230"], "arXiv:2501.16230"),
    ("15", "15_CLISA_Contrastive_Subject-Invariant_EEG_2023.pdf",
     ["https://arxiv.org/pdf/2109.09559"], "arXiv:2109.09559"),
    ("16", "16_GMSS_Graph_Multi-Task_Self-Supervised_2023.pdf",
     ["https://arxiv.org/pdf/2205.01030"], "arXiv:2205.01030"),
    ("17", "17_DMMR_Denoising_Mixed_Mutual_Reconstruction_2024.pdf",
     ["https://ojs.aaai.org/index.php/AAAI/article/download/27819/27668"], "AAAI 开放获取"),
    ("D5", "D5_DEAP_Database_Emotion_Analysis_2012.pdf",
     ["https://access.archive-ouverte.unige.ch/access/metadata/1d5ce2a8-00d8-4793-8943-cf9e8aa56693/download",
      "https://archive-ouverte.unige.ch/unige:47405"], "UNIGE 机构库"),
    ("D6", "D6_MPED_Multi-Modal_Physiological_Emotion_Database_2019.pdf",
     ["https://ieeexplore.ieee.org/ielx7/6287639/8600701/08606087.pdf"], "IEEE Access 开放获取"),
    ("D7", "D7_DREAMER_EEG_ECG_Database_2018.pdf",
     ["https://research-portal.uws.ac.uk/files/53642872/2017_03_19_Katsigiannis_et_al_DREAMER_accepted.pdf"], "UWS 机构库"),
    ("D8", "D8_FACED_Finer-grained_Affective_Computing_EEG_2023.pdf",
     ["https://www.nature.com/articles/s41597-023-02650-w.pdf",
      "https://pmc.ncbi.nlm.nih.gov/articles/PMC10600242/pdf/41597_2023_Article_2650.pdf"], "Scientific Data 开放获取"),
]

# 其余闭源条目：仅记录，不下载
CLOSED = [
    ("02", "Research Progress of EEG-Based Emotion Recognition: A Survey", "10.1145/3666002"),
    ("04", "DDA: Dynamic Domain Adaptation for Class-Aware Cross-Subject and Cross-Session EEG Emotion Recognition", "10.1109/JBHI.2022.3210158"),
    ("05", "CMJDA: Multimodal Semi-Supervised Domain Adaptation ...", "10.1109/TIM.2025.3551924"),
    ("07", "BiDANN: A Bi-Hemisphere Domain Adversarial Neural Network Model", "10.1109/TAFFC.2018.2885474"),
    ("08", "TT-CDAN: A Novel Conditional Adversarial Domain Adaptation Network", "10.1109/TAFFC.2025.3588873"),
    ("09", "DAPLP: Unsupervised Domain Adaptation With Pseudo-Label Propagation", "10.1109/TIM.2025.3553234"),
    ("10", "MSGDAN: Multi-source Selective Graph Domain Adaptation Network", "10.1016/j.neunet.2024.106742"),
    ("11", "Sera: Separated Coarse-to-fine Representation Alignment", "10.1145/3746027.3754775"),
    ("13", "PCL-TDGCN: Prototypical Contrastive Learning with Temporal Dynamic GCN", "10.1109/TAFFC.2026.3671020"),
    ("14", "TAHAG: Two-Stage Domain Adaptation with Hybrid Adaptive Graph Learning", "10.1109/TAFFC.2025.3580787"),
    ("18", "MSHCL: Multi-Scale Hyperbolic Contrastive Learning", "10.1109/TAFFC.2025.3535542"),
    ("19", "Information Fusion: Regional to Global Fusion with Spatial-Temporal Semantic Alignment", "10.1016/j.inffus.2026.104224"),
    ("20", "SEED-VII: A Multimodal Dataset of Six Basic Emotions", "10.1109/TAFFC.2024.3485057"),
    ("D1", "SEED: Investigating Critical Frequency Bands and Channels", "10.1109/TAMD.2015.2431497"),
    ("D2", "SEED-IV / EmotionMeter: A Multimodal Framework", "10.1109/TCYB.2018.2797176"),
    ("D9", "MAHNOB-HCI: A Multimodal Database for Affect Recognition", "10.1109/T-AFFC.2011.25"),
]


def download(url, path, timeout=40):
    req = urllib.request.Request(url, headers=HEAD)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = (r.headers.get("content-type") or "").lower()
        if "pdf" not in ctype and "octet-stream" not in ctype:
            return False, f"not pdf content-type: {ctype}"
        data = r.read()
    if not data.startswith(b"%PDF"):
        return False, f"not pdf magic: {data[:20]!r}"
    if len(data) < 20000:
        return False, f"too small: {len(data)}"
    with open(path, "wb") as f:
        f.write(data)
    return True, f"{len(data)} bytes"


results = []
for key, fname, urls, source in ITEMS:
    path = os.path.join(OUT, fname)
    if os.path.exists(path) and os.path.getsize(path) > 20000:
        results.append([key, fname, "已存在", source, ""])
        print("SKIP exists", fname)
        continue
    ok = False
    msg = ""
    used = ""
    for u in urls:
        try:
            ok, msg = download(u, path)
            used = u
            if ok:
                break
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
    if ok:
        results.append([key, fname, "下载成功", source, used])
        print("OK", fname, msg)
    else:
        results.append([key, fname, "失败", source, used])
        print("FAIL", fname, msg)

for key, title, doi in CLOSED:
    results.append([key, "", "未下载（无公开 PDF）", f"https://doi.org/{doi}", title])

with open(os.path.join(OUT, "_下载清单.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["编号", "文件名", "状态", "来源/DOI", "备注"])
    w.writerows(results)

print("\nDONE", sum(1 for r in results if r[2] == "下载成功"), "downloaded")
