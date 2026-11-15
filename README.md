# EEG-EmoStudio：脑电情绪识别数据制备与模型训练工作台

> 面向跨被试 EEG 情绪识别的“实验采集 → EEG 处理 → 模型训练”一体化系统。  
> 同时按软件工程本科毕业设计规范组织需求、设计、实现、测试与论文材料。  
> GitHub 仓库：[Apos-DT/EEGos](https://github.com/Apos-DT/EEGos)（项目代号 EEG-EmoStudio）。

**当前版本**：V0.5.0（可分享问卷 + 素材库）  
**文档版本**：V1.2（2026-11-15）  
**研究场景**：视频/音乐刺激诱发情绪，62/32 导 EEG，离散标签 + 效价/唤醒连续标签，跨被试（LOSO/UDA）评估。

---

## 1. 现在有什么

### 1.1 已核实的真实数据

| 数据 | 规模/内容 | 位置 |
|---|---|---|
| 视频刺激 | 120 段，2–5 min，四象限各 30 | `山科数据集/VIDEOS/视频压缩v2/` |
| 音乐刺激 | 120 首，标注片段约 60 s，四象限各 30 | `山科数据集/音乐测试v2/音乐测试v2/` |
| 视频预评价 | 1,269 条原始问卷，去重后 1,227 条，11 名评分者 | `山科数据集/374437060_...csv` |
| 音乐预评价 | 1,087 条原始问卷，去重后 1,072 条，9 名评分者 | `山科数据集/376653806_...csv` |
| 质量排序 | 视频/音乐各 120 条，S/A/B/C/D 五级 | `research/quality/video/`、`research/quality/audio/` |
| **SEED-IV** | **15 被试 × 3 sessions × 24 trials = 1,080 trial；62 通道、5 频带、4 类；37,575 个 4 s 窗口** | `data/SEED_IV/` |
| 素材库 | 120 视频 + 120 音乐；统一纳管 | `data/media/` |

### 1.2 已实现的软件能力

- `experiment`：本地视频播放 + 问卷填写（效价、唤醒、主导情绪、强度、熟悉度），会话与响应落盘。
- `audit`：问卷字段识别、编号归一、重复提交、直线作答、文本锚点、播放问题并集、映射/媒体文件核对。
- `select`：按“模态 × 四象限”分层选材，优先 S/A/B 级，输出可直接执行的实验材料清单。
- `eeglab`：EEGLAB `.set/.fdt` 导入 → 带通/陷波/重参考/重采样 → 事件分段/剔除 → DE 特征。
- `features`：`raw.npz` → 带通/陷波/重参考/重采样 → 5 频带 DE 特征。
- `train`：被试依赖与 LOSO 跨被试训练；MLP、DGCNN、DualView-MultiProto、EEGNet；指标、置信区间、混淆矩阵、检查点。
- `demo`：合成特征端到端跑通，生成自包含 HTML 报告，专门用于软件验收，不作为科研结论。
- 28 项单元/集成测试全部通过（含 Web 与问卷/素材测试）；实际数据审计结果与既有质量报告的 22/29 条问题视频（音乐）计数一致。

### 1.3 实际数据审计的关键结论

1. 视频问卷 1,269 → 1,227 条（删除 42 条重复提交）；音乐 1,087 → 1,072 条（删除 15 条）。
2. 视频编号有 146 种写法，音乐 129 种；视频存在 `388.mp4 → 38.mp4` 的显式误写。
3. 效价/唤醒同时含数字与“非常愉快/非常激烈”等文字锚点，已统一为 1–9 分。
4. 音乐有 26/120 条标注片段偏离 60±15 s（23–167 s），正式实验前必须统一截取规则。
5. 视频 22 条、音乐 29 条存在播放问题；与既有质量报告完全一致。
6. 选材示例：每模态每象限 10 条，共 80 条；26 条 S、22 条 A、32 条 B，无 C/D。
7. SEED-IV 官方特征已接入：15 被试、3 sessions、1,080 trials、37,575 窗口；真实 LOSO 的 MLP 基线为 **42.78%**，DualView 初步为 **27.69%**（未调参，待改进）。
8. SEED-IV 原始 200 Hz 数据的自实现预处理/DE 复现与眼动多模态尚未执行，论文中需明确“官方特征”与“自采原始数据”的边界。

---

## 2. 快速开始

要求：Windows 10/11，Python 3.11+。本机验证环境为 Python 3.12.6、PyTorch 2.9.1 CPU。

```powershell
pip install -r requirements.txt   # 可选：pip install opencv-python av mne

# 1) 数据审计（不读取媒体时长，速度快）
python -m eeg_emostudio audit --workspace . --out artifacts/audit

# 2) 需要媒体真实时长时（视频用 OpenCV，音频用 PyAV）
python -m eeg_emostudio audit --workspace . --out artifacts/audit_probe --probe-media

# 3) 分层选材（每模态每象限 10 条）
python -m eeg_emostudio select --workspace . --out artifacts/selection --per-class 10 --min-grade D

# 4) 合成数据端到端演示（验证软件，不是科研结果）
python -m eeg_emostudio demo --out artifacts/demo --epochs 40 --model dualview

# 5) 导入 EEGLAB 原始数据（.set 数据内嵌，或 .set+.fdt 的 zip）
python -m eeg_emostudio eeglab --input data/eeg_uploads/S01/S01.set `
  --out artifacts/eeg/S01 --subject S01 --target-fs 200 --ica

# 6) 接入本地 SEED-IV 官方特征（15 被试 × 3 sessions × 24 trials）
python -m eeg_emostudio seed-iv --root data/SEED_IV `
  --out data/processed/seed_iv_de_LDS_trial.npz --aggregate trial

# 7) 真实/自有 EEG：先整理为 raw.npz，再提特征、训练
python -m eeg_emostudio features --raw data/raw/sub01.npz --out data/features/sub01.npz --fs 1000 --target-fs 200
python -m eeg_emostudio train --data data/features/sub01.npz --out experiments/sub01_loso --model dualview --setting loso

# 8) 测试
python -m unittest discover -s tests -v
```

### Web 控制台（V0.5）

```powershell
python -m webapp
# 管理端 http://127.0.0.1:8770/surveys
# 被试端由问卷生成的 /q/<token> 分享链接进入
```

10 个日常页面（含工作台），按三大功能域组织：实验（问卷管理、实验问卷、素材库）、EEG 信号（原始 EEG 处理、数据集与特征）、模型训练（模型训练、实验记录），以及项目文档与系统状态；另有 1 个历史预评价归档页。  
API 文档：`/api/swagger`；页面与 API 共用同一套数据/算法。

### raw.npz 契约

```text
x        float32, (trials, channels, samples)，单位 µV
y        int64,   (trials,)，0-based 类别
subjects (trials,), 被试伪匿名 ID
fs       scalar, 采样率（也可命令行传入）
class_names 可选，字符串数组
```

> 当前 `features` 接受已分段的固定长度 trial。EDF/BDF 等连续记录应先由采集适配器切分为 trial；MNE 作为可选依赖，不强制安装。

---

## 3. 目录结构

顶层按「代码 / 文档 / 研究过程资料 / 本地数据 / 运行产物」五类组织，后两类默认由 `.gitignore` 排除。

```text
EEGos/
├── README.md · pyproject.toml · requirements.txt · run_web.py · .gitignore
│
│  ── 代码（可运行、全部入库）──────────────────────
├── eeg_emostudio/           # 核心算法包，cli.py 为统一入口
│   ├── audit/               # 问卷、映射、媒体、质量表审计与选材
│   ├── data/                # 预处理、DE 特征、SEED-IV 适配、划分、清单
│   ├── models/              # MLP / DGCNN / DualView / EEGNet
│   ├── training/            # LOSO、指标、训练循环
│   └── reporting/           # 图表与 HTML 报告
├── webapp/                  # FastAPI + Jinja2 + 原生 CSS/JS 本地控制台
├── tests/                   # unittest 测试（28 项）
├── scripts/                 # 图表、DOCX/PPT/工作簿构建脚本
├── configs/                 # 预留 YAML 配置（后续接入）
│
│  ── 文档（毕设规范）──────────────────────────────
├── docs/                    # 00–17 毕业设计文档（Markdown 源，唯一事实源）
│   └── assets/              # 架构图、数据流图、甘特图、数据实体图
│
│  ── 研究过程资料 ─────────────────────────────────
├── research/                # 见 research/README.md
│   ├── quality/video/       # 视频预评价质量排序（select 的输入证据）
│   ├── quality/audio/       # 音乐预评价质量排序
│   ├── references/          # 参考文献清单（CSV/XLSX）
│   ├── weekly/              # 周工作汇报
│   └── legacy/              # 原有数据探索/评分脚本（保留不动）
│
│  ── 本地数据（体积/许可原因不入库）──────────────
├── data/                    # raw/processed/SEED_IV/media；仅 README 与清单 JSON 入库
├── 山科数据集/              # 原始刺激与问卷（项目约定：不移动、不改名）
├── 文献/                    # 9 篇可公开获取的参考文献 PDF
│
│  ── 运行产物（可由脚本再生成，不入库）──────────
├── artifacts/               # 审计、选材、演示、实验
├── deliverables/            # Word/Excel/PDF 交付物
└── ppt_assets/             # 组会汇报页面截图
```

---

## 4. 文档地图

| 文档 | 解决的问题 | 对应毕业设计环节 |
|---|---|---|
| [文档索引](docs/00_文档索引与使用说明.md) | 读什么、按什么顺序读、如何形成论文 | 全过程 |
| [可行性研究报告](docs/01_可行性研究报告.md) | 值不值得做、能不能做、风险在哪 | 开题 |
| [软件需求规格说明书](docs/02_软件需求规格说明书.md) | 系统必须做什么、做到什么程度 | 需求分析 |
| [项目计划与 WBS](docs/03_项目计划与WBS.md) | 谁在何时交付什么 | 项目管理 |
| [文献综述与需求依据](docs/04_文献综述与需求依据.md) | 研究缺口、基线、方法依据 | 绪论/相关工作 |
| [数据审计报告](docs/05_数据审计报告.md) | 现有数据到底能支撑什么 | 数据与实验章节 |
| [概要设计说明书](docs/06_概要设计说明书.md) | 系统怎么分层、模块怎么协作 | 总体设计 |
| [详细设计说明书](docs/07_详细设计说明书.md) | 算法、接口、数据结构怎么落地 | 详细设计 |
| [数据字典与治理规范](docs/08_数据字典与数据治理规范.md) | 每个字段的含义、质量门禁、隐私 | 数据管理 |
| [测试计划与验收标准](docs/09_测试计划与验收标准.md) | 怎么证明系统正确、科研可复现 | 测试/验收 |
| [用户手册](docs/10_用户手册.md) | 研究者如何真正使用 | 使用/部署 |
| [毕业论文写作纲要](docs/11_毕业论文写作纲要.md) | 如何把工程变成论文 | 论文撰写 |
| [毕业设计符合性矩阵](docs/12_毕业设计符合性矩阵.md) | 是否满足学校/专业要求 | 自检/答辩 |
| [配置管理与质量保证计划](docs/13_配置管理与质量保证计划.md) | 版本、评审、复现、变更 | 工程管理 |
| [开题报告草案](docs/14_开题报告草案.md) | 可直接改写为学校模板 | 开题 |
| [Web 系统设计与使用说明](docs/15_Web系统设计与使用说明.md) | 前后端、页面、API 与任务模型 | 系统实现 |
| [SEED-IV 真实数据接入报告](docs/16_SEED_IV数据接入报告.md) | 数据清单、适配器、真实基线 | 数据/实验 |
| [实验采集与 EEG 预处理说明](docs/17_实验采集与EEG预处理说明.md) | 视频问卷、EEGLAB 清洗、数据对齐 | 实验/信号 |

> Word 版由 `scripts/build_docx.py` 从 Markdown 统一生成，封面、目录、页眉页脚和图表编号可按学校模板再调整。

---

## 5. 科研使用边界（必须写进论文）

- 本文的“质量分”衡量的是 **刺激材料可用性与标签一致性**，不是情绪标签真值，也不能替代被试自评。
- 合成数据演示只证明软件流水线可运行；论文中的性能数字必须来自真实 EEG 和预先注册的划分方案。
- LOSO 划分严格按被试隔离；验证集只从训练被试中切分，测试被试不参与标准化、早停或超参选择。
- 任何跨被试结论至少报告：每折指标、总体 OOF 指标、95% CI、混淆矩阵、分被试结果、随机水平。
- 若使用 DEAP/SEED 等公开数据，必须遵守各自许可证与引用要求；自采数据必须完成伦理审批与知情同意。

---

## 6. 下一步（按优先级）

1. 把 `raw.npz` 适配器接到实际采集设备（BrainVision/NeuroScan/Neuracle 等）与事件文件。
2. 用 5–10 名被试的预实验数据跑通真实 LOSO，修正预处理参数与伪迹阈值。
3. 补齐 SEED/DEAP 公开数据基线，形成“同设置可比”的对照表。
4. 完成 DualView-MultiProto 的消融（双视角、多原型、域适应）与统计检验。
5. 按学校模板定稿 DOCX/PPT，完成查重与答辩演练。

---

## 7. 引用与致谢

系统实现参考了 EEG 情绪识别综述、跨被试域适应与图/原型方法，以及 DEAP、MPED、FACED 等公开数据集的实验范式。完整文献列表见 `research/references/参考文献清单_汇总.xlsx` 与 `docs/04_文献综述与需求依据.md`。原始数据、质量评分与文献由课题组提供；本仓库不重新分发受版权保护的刺激材料。
