# -*- coding: utf-8 -*-
"""生成《高宇261022.pptx》参考文献清单（xlsx + csv + md）"""
import csv
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT = r"C:\Users\24114\Desktop\EEG Emotion Recognition\research\references"
os.makedirs(OUT, exist_ok=True)

# 字段：编号, PPT写法, 标题, 作者, 期刊/会议, 年份, DOI/官方链接, 开放获取, 备注, PPT页码
REFS = [
    ["1", "EEG Based Emotion Recognition: A Tutorial and Review",
     "EEG Based Emotion Recognition: A Tutorial and Review",
     "Li et al.", "ACM Computing Surveys", "2022",
     "https://doi.org/10.1145/3524499", "https://arxiv.org/abs/2203.11279",
     "综述/教程；ACM DL 与 arXiv 均有", "11"],
    ["2", "Research Progress of EEG-Based Emotion Recognition: A Survey",
     "Research Progress of EEG-Based Emotion Recognition: A Survey",
     "Wang, Zhang, Di", "ACM Computing Surveys", "2024",
     "https://doi.org/10.1145/3666002", "",
     "综述；闭源，需机构订阅", "11"],
    ["3", "Emotion recognition via affective EEG signals: State of the art",
     "Emotion recognition via affective EEG signals: State of the art",
     "Meng et al.", "Neurocomputing", "2025",
     "https://doi.org/10.1016/j.neucom.2025.130418", "https://doi.org/10.2139/ssrn.5174448",
     "综述；SSRN 有预印本", "11"],
    ["4", "DDA (JBHI, Li et al., 2022)",
     "Dynamic Domain Adaptation for Class-Aware Cross-Subject and Cross-Session EEG Emotion Recognition",
     "Li et al.", "IEEE Journal of Biomedical and Health Informatics (JBHI)", "2022",
     "https://doi.org/10.1109/JBHI.2022.3210158", "",
     "方法；闭源", "11"],
    ["5", "CMJDA (TIM, Zhao et al., 2025)",
     "Multimodal Semi-Supervised Domain Adaptation Using Cross-Modal Learning and Joint Distribution Alignment for Cross-Subject Emotion Recognition",
     "Jiménez-Guarneros et al.", "IEEE Transactions on Instrumentation and Measurement (TIM)", "2025",
     "https://doi.org/10.1109/TIM.2025.3551924", "",
     "PPT 写“Zhao et al.”，实际第一作者为 Jiménez-Guarneros，建议核对", "11"],
    ["6", "SSAS (ESWA, Liu et al., 2025)",
     "SSAS: Cross-subject EEG-based emotion recognition through source selection with adversarial strategy",
     "Liu, Oung, Lee", "Expert Systems with Applications (ESWA)", "2026（online 2025）",
     "https://doi.org/10.1016/j.eswa.2025.130843", "https://doi.org/10.2139/ssrn.5534268",
     "PPT 标注 2025，正式卷期为 2026；SSRN 有预印本", "11, 13–15"],
    ["7", "BiDANN (TAFFC, Li et al., 2021)",
     "A Bi-Hemisphere Domain Adversarial Neural Network Model for EEG Emotion Recognition",
     "Li et al.", "IEEE Transactions on Affective Computing (TAFFC)", "2021",
     "https://doi.org/10.1109/TAFFC.2018.2885474", "",
     "正式卷期 2021，early access 2018", "11"],
    ["8", "TT-CDAN (TAFFC, Huang et al., 2025)",
     "A Novel Conditional Adversarial Domain Adaptation Network for EEG Cross-Subject Emotion Recognition",
     "Huang et al.", "IEEE Transactions on Affective Computing (TAFFC)", "2025",
     "https://doi.org/10.1109/TAFFC.2025.3588873", "",
     "PPT 缩写为 TT-CDAN；按 Huang et al. 2025 TAFFC 匹配到该文，标题未出现 TT-CDAN，建议核对", "11"],
    ["9", "DAPLP (TIM, Zhong et al., 2025)",
     "Unsupervised Domain Adaptation With Pseudo-Label Propagation for Cross-Domain EEG Emotion Recognition",
     "Zhong et al.", "IEEE Transactions on Instrumentation and Measurement (TIM)", "2025",
     "https://doi.org/10.1109/TIM.2025.3553234", "",
     "方法；闭源", "11"],
    ["10", "MSGDAN (NN, Wang et al., 2024)",
     "Multi-source Selective Graph Domain Adaptation Network for cross-subject EEG emotion recognition",
     "Wang et al.", "Neural Networks", "2024",
     "https://doi.org/10.1016/j.neunet.2024.106742", "",
     "方法；闭源", "11"],
    ["11", "Sera (MM, Jia et al., 2025)",
     "Sera: Separated Coarse-to-fine Representation Alignment for Cross-subject EEG-based Emotion Recognition",
     "Jia et al.", "ACM Multimedia (ACM MM)", "2025",
     "https://doi.org/10.1145/3746027.3754775", "",
     "方法；闭源", "11"],
    ["12", "MIND-EEG (TAFFC, Zhang et al., 2026)",
     "MIND-EEG: Multi-Granularity Integration Network With Discrete Codebook for EEG-Based Emotion Recognition",
     "Zhang et al.", "IEEE Transactions on Affective Computing (TAFFC)", "2026",
     "https://doi.org/10.1109/TAFFC.2025.3608571", "https://arxiv.org/abs/2501.16230",
     "正式卷期 2026；arXiv 有预印本", "11"],
    ["13", "PCL-TDGCN (TAFFC, Yang et al., 2026)",
     "Prototypical Contrastive Learning With Temporal Dynamic Graph Convolutional Network for EEG-Based Emotion Recognition",
     "Yang et al.", "IEEE Transactions on Affective Computing (TAFFC)", "2026",
     "https://doi.org/10.1109/TAFFC.2026.3671020", "",
     "方法；闭源", "11, 16–18"],
    ["14", "TAHAG (TAFFC, Gong et al., 2025)",
     "TAHAG: Two-Stage Domain Adaptation With Hybrid Adaptive Graph Learning for EEG Emotion Recognition",
     "Gong et al.", "IEEE Transactions on Affective Computing (TAFFC)", "2025",
     "https://doi.org/10.1109/TAFFC.2025.3580787", "",
     "方法；闭源", "11"],
    ["15", "CLISA (TAFFC, Shen et al., 2022)",
     "Contrastive Learning of Subject-Invariant EEG Representations for Cross-Subject Emotion Recognition",
     "Shen et al.", "IEEE Transactions on Affective Computing (TAFFC)", "2023（early access 2022）",
     "https://doi.org/10.1109/TAFFC.2022.3164516", "https://arxiv.org/abs/2109.09559",
     "PPT 标注 2022，正式卷期 2023；arXiv 有预印本", "11"],
    ["16", "GMSS (TAFFC, Li et al., 2023)",
     "GMSS: Graph-Based Multi-Task Self-Supervised Learning for EEG Emotion Recognition",
     "Li et al.", "IEEE Transactions on Affective Computing (TAFFC)", "2023",
     "https://doi.org/10.1109/TAFFC.2022.3170428", "https://arxiv.org/abs/2205.01030",
     "正式卷期 2023，early access 2022；arXiv 有预印本", "11"],
    ["17", "DMMR (AAAI, Wang et al., 2024)",
     "DMMR: Cross-Subject Domain Generalization for EEG-Based Emotion Recognition via Denoising Mixed Mutual Reconstruction",
     "Wang, Zhang, Tang", "AAAI Conference on Artificial Intelligence", "2024",
     "https://doi.org/10.1609/aaai.v38i1.27819", "https://ojs.aaai.org/index.php/AAAI/article/download/27819/27668",
     "AAAI 开放获取", "11"],
    ["18", "MSHCL (TAFFC, Chang et al., 2025)",
     "Multi-Scale Hyperbolic Contrastive Learning for Cross-Subject EEG Emotion Recognition",
     "Chang et al.", "IEEE Transactions on Affective Computing (TAFFC)", "2025",
     "https://doi.org/10.1109/TAFFC.2025.3535542", "",
     "方法；闭源", "11"],
    ["19", "Information Fusion 2026 多模态论文",
     "Emotion recognition using multimodal physiological signals through regional to global fusion with a spatial-temporal semantic alignment mechanism",
     "Shen et al.", "Information Fusion", "2026",
     "https://doi.org/10.1016/j.inffus.2026.104224", "",
     "方法；闭源", "19–22"],
    ["20", "SEED-VII 数据集（2025）",
     "SEED-VII: A Multimodal Dataset of Six Basic Emotions With Continuous Labels for Emotion Recognition",
     "Jiang et al.", "IEEE Transactions on Affective Computing (TAFFC)", "2025",
     "https://doi.org/10.1109/TAFFC.2024.3485057", "",
     "数据集论文；PPT 第 26–27 页引用", "26–27"],
]

DATASETS = [
    ["D1", "SEED", "Investigating Critical Frequency Bands and Channels for EEG-Based Emotion Recognition with Deep Neural Networks",
     "Zheng, Lu", "IEEE Transactions on Autonomous Mental Development", "2015",
     "https://doi.org/10.1109/TAMD.2015.2431497", "", "PPT 数据集对比表中出现", "25"],
    ["D2", "SEED-IV", "EmotionMeter: A Multimodal Framework for Recognizing Human Emotions",
     "Zheng et al.", "IEEE Transactions on Cybernetics", "2019",
     "https://doi.org/10.1109/TCYB.2018.2797176", "", "SEED-IV 数据集论文", "25"],
    ["D3", "SEED-V", "未检索到独立的公开论文",
     "—", "—", "—", "", "", "数据集对比表中出现，但未找到对应论文，建议查 SEED 系列数据集主页", "25"],
    ["D4", "SEED-VII", "SEED-VII: A Multimodal Dataset of Six Basic Emotions With Continuous Labels for Emotion Recognition",
     "Jiang et al.", "IEEE Transactions on Affective Computing", "2025",
     "https://doi.org/10.1109/TAFFC.2024.3485057", "", "同主表第 20 条", "25–27"],
    ["D5", "DEAP", "DEAP: A Database for Emotion Analysis Using Physiological Signals",
     "Koelstra et al.", "IEEE Transactions on Affective Computing", "2012",
     "https://doi.org/10.1109/T-AFFC.2011.15", "", "数据集论文", "25"],
    ["D6", "MPED", "MPED: A Multi-Modal Physiological Emotion Database for Discrete Emotion Recognition",
     "Song et al.", "IEEE Access", "2019",
     "https://doi.org/10.1109/ACCESS.2019.2891579", "", "开放获取", "25"],
    ["D7", "DREAMER", "DREAMER: A Database for Emotion Recognition Through EEG and ECG Signals From Wireless Low-cost Off-the-Shelf Devices",
     "Katsigiannis, Ramzan", "IEEE Journal of Biomedical and Health Informatics", "2018",
     "https://doi.org/10.1109/JBHI.2017.2688239", "", "数据集论文", "25"],
    ["D8", "FACED", "A Large Finer-grained Affective Computing EEG Dataset",
     "Chen et al.", "Scientific Data", "2023",
     "https://doi.org/10.1038/s41597-023-02650-w", "", "开放获取", "25"],
    ["D9", "MAHNOB-HCI", "A Multimodal Database for Affect Recognition and Implicit Tagging",
     "Soleymani et al.", "IEEE Transactions on Affective Computing", "2012",
     "https://doi.org/10.1109/T-AFFC.2011.25", "", "数据集论文", "25"],
]

HEAD = ["序号", "PPT 中的写法", "文献名称", "作者", "期刊/会议", "年份",
        "DOI / 官方链接", "开放获取 / 预印本", "备注", "PPT 页码"]
WIDTHS = [6, 30, 70, 22, 34, 18, 44, 44, 50, 12]

HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(color="FFFFFF", bold=True, size=10)
THIN = Side(style="thin", color="D0D0D0")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
LINK_FONT = Font(color="0563C1", underline="single")


def build_sheet(ws, title, rows):
    ws.append([title])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(HEAD))
    ws.cell(row=1, column=1).font = Font(bold=True, size=12)
    ws.append(HEAD)
    for c in range(1, len(HEAD) + 1):
        cell = ws.cell(row=2, column=c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[2].height = 28
    for r in rows:
        ws.append(r)
    for rr in range(3, ws.max_row + 1):
        for c in range(1, len(HEAD) + 1):
            cell = ws.cell(row=rr, column=c)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=True,
                                       horizontal="center" if c in (1, 6, 10) else "left")
        for c in (7, 8):
            cell = ws.cell(row=rr, column=c)
            if cell.value:
                cell.hyperlink = cell.value
                cell.font = LINK_FONT
        ws.row_dimensions[rr].height = 48
    for i, w in enumerate(WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "C3"
    ws.auto_filter.ref = f"A2:J{ws.max_row}"


wb = Workbook()
ws1 = wb.active
ws1.title = "01_方法文献"
build_sheet(ws1, "《高宇261022.pptx》方法/综述类文献（共 20 条）", REFS)

ws2 = wb.create_sheet("02_数据集文献")
build_sheet(ws2, "PPT 数据集对比表中出现的公开数据集（补充，共 9 条）", DATASETS)

xlsx = os.path.join(OUT, "高宇261022_参考文献清单.xlsx")
wb.save(xlsx)

# CSV 合并
with open(os.path.join(OUT, "高宇261022_参考文献清单.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["类别"] + HEAD)
    for r in REFS:
        w.writerow(["方法/综述"] + r)
    for r in DATASETS:
        w.writerow(["数据集"] + r)

print("saved", xlsx)
print("refs", len(REFS), "datasets", len(DATASETS))
