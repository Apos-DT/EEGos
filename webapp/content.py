"""Static metadata shared by the web templates and API."""

from __future__ import annotations

APP_NAME = "EEG-EmoStudio"
APP_SUBTITLE = "实验采集 · EEG 处理 · 模型训练"
APP_VERSION = "0.5.0"

NAV_GROUPS = [
    {
        "label": "实验",
        "items": [
            {"key": "surveys", "label": "问卷管理", "href": "/surveys", "icon": "play"},
            {"key": "survey_data", "label": "问卷数据", "href": "/survey-data", "icon": "chart"},
            {"key": "media", "label": "素材库", "href": "/media", "icon": "sliders"},
        ],
    },
    {
        "label": "EEG 信号",
        "items": [
            {"key": "eeg", "label": "原始 EEG 处理", "href": "/eeg", "icon": "waves"},
            {"key": "datasets", "label": "数据集与特征", "href": "/datasets", "icon": "database"},
        ],
    },
    {
        "label": "模型训练",
        "items": [
            {"key": "training", "label": "模型训练", "href": "/training", "icon": "cpu"},
            {"key": "experiments", "label": "实验记录", "href": "/experiments", "icon": "activity"},
        ],
    },
    {
        "label": "系统",
        "items": [
            {"key": "documents", "label": "项目文档", "href": "/documents", "icon": "file"},
            {"key": "system", "label": "系统状态", "href": "/system", "icon": "settings"},
        ],
    },
]
NAV = [item for group in NAV_GROUPS for item in group["items"]]

PAGE_META = {
    "dashboard": "工作台",
    "experiment": "实验会话",
    "surveys": "问卷管理",
    "survey_builder": "新建问卷",
    "survey_data": "问卷数据与元数据",
    "responses": "问卷数据",
    "media": "素材库",
    "stimuli": "素材库",
    "audit": "历史预评价审计",
    "selection": "刺激库",
    "eeg": "原始 EEG 处理",
    "datasets": "数据集与特征",
    "training": "模型训练",
    "experiments": "实验记录",
    "documents": "项目文档",
    "system": "系统状态",
}

DOCS = [
    {
        "no": "01", "title": "可行性研究报告", "category": "立项",
        "desc": "研究价值、技术路线、成本、伦理与风险。",
        "docx": "EEG-EmoStudio_01_可行性研究报告.docx", "pdf": "01.pdf",
    },
    {
        "no": "02", "title": "软件需求规格说明书", "category": "需求",
        "desc": "18 项功能需求、非功能指标、用例、验收与追溯。",
        "docx": "EEG-EmoStudio_02_软件需求规格说明书.docx", "pdf": "02.pdf",
    },
    {
        "no": "03", "title": "项目计划与 WBS", "category": "管理",
        "desc": "16 周进度、WBS、资源、风险与质量计划。",
        "docx": "EEG-EmoStudio_03_项目计划与WBS.docx", "pdf": "03.pdf",
    },
    {
        "no": "04", "title": "文献综述与需求依据", "category": "研究",
        "desc": "29 条文献、8 个公开数据集、跨被试方法与缺口。",
        "docx": "EEG-EmoStudio_04_文献综述与需求依据.docx", "pdf": "04.pdf",
    },
    {
        "no": "05", "title": "数据审计报告", "category": "数据",
        "desc": "2,356 条问卷、240 条材料、22/29 条问题刺激与选材。",
        "docx": "EEG-EmoStudio_05_数据审计报告.docx", "pdf": "05.pdf",
    },
    {
        "no": "06", "title": "概要设计说明书", "category": "设计",
        "desc": "分层架构、模块、数据流、接口、部署与关键决策。",
        "docx": "EEG-EmoStudio_06_概要设计说明书.docx", "pdf": "06.pdf",
    },
    {
        "no": "07", "title": "详细设计说明书", "category": "设计",
        "desc": "清洗规则、DE 公式、LOSO 算法、模型与训练细节。",
        "docx": "EEG-EmoStudio_07_详细设计说明书.docx", "pdf": "07.pdf",
    },
    {
        "no": "08", "title": "数据字典与治理规范", "category": "数据",
        "desc": "字段口径、编码、隐私分级、质量门禁与生命周期。",
        "docx": "EEG-EmoStudio_08_数据字典与数据治理规范.docx", "pdf": "08.pdf",
    },
    {
        "no": "09", "title": "测试计划与验收标准", "category": "测试",
        "desc": "30 个测试用例、58 项自动化测试与验收矩阵。",
        "docx": "EEG-EmoStudio_09_测试计划与验收标准.docx", "pdf": "09.pdf",
    },
    {
        "no": "10", "title": "用户手册", "category": "使用",
        "desc": "安装、CLI 命令、数据契约、科研工作流与 FAQ。",
        "docx": "EEG-EmoStudio_10_用户手册.docx", "pdf": "10.pdf",
    },
    {
        "no": "11", "title": "毕业论文写作纲要", "category": "论文",
        "desc": "章节结构、图表清单、实验设计、答辩问题。",
        "docx": "EEG-EmoStudio_11_毕业论文写作纲要.docx", "pdf": "11.pdf",
    },
    {
        "no": "12", "title": "毕业设计符合性矩阵", "category": "论文",
        "desc": "逐项对照毕业要求，标注证据与待补项。",
        "docx": "EEG-EmoStudio_12_毕业设计符合性矩阵.docx", "pdf": "12.pdf",
    },
    {
        "no": "13", "title": "配置管理与质量保证", "category": "管理",
        "desc": "版本、评审、可复现、备份与变更控制。",
        "docx": "EEG-EmoStudio_13_配置管理与质量保证计划.docx", "pdf": "13.pdf",
    },
    {
        "no": "14", "title": "开题报告（草案）", "category": "立项",
        "desc": "背景、现状、内容、方法、进度与参考文献。",
        "docx": "EEG-EmoStudio_14_开题报告草案.docx", "pdf": "14.pdf",
    },
]

MODELS = [
    {
        "key": "dualview", "name": "DualView", "tag": "推荐",
        "desc": "电极视角 + 脑区视角，类内多原型正则。",
        "meta": "特征模型 · 低参数量",
    },
    {
        "key": "dgcnn", "name": "DGCNN", "tag": "图基线",
        "desc": "由当前样本动态构图，聚合电极关系。",
        "meta": "特征模型 · kNN 图",
    },
    {
        "key": "mlp", "name": "MLP", "tag": "强基线",
        "desc": "通道×频带展平后的两层感知机。",
        "meta": "特征模型 · 快速",
    },
    {
        "key": "eegnet", "name": "EEGNet", "tag": "原始波形",
        "desc": "时间卷积 + 深度可分离卷积的端到端基线。",
        "meta": "需要 raw 时间序列",
    },
]
