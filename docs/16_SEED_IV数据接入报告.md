# SEED-IV 真实数据接入报告

**项目**：EEG-EmoStudio 脑电情绪识别数据制备与模型训练工作台  
**文档编号**：16  
**版本**：V1.0  
**日期**：2026-11-08  
**数据目录**：`data/SEED_IV/`  
**数据来源**：SJTU SEED-IV（Center for Brain-like Computing and Machine Intelligence）

---

## 1. 结论先行

1. SEED-IV 已接入系统：**15 名被试 × 3 个 session × 24 个 trial = 1,080 个 trial**，62 通道、5 频带、4 类情绪。
2. 官方预计算特征共 **37,575 个 4 s 窗口**；按 trial 聚合后为 **1,080 个 trial 级样本**。
3. 已生成两个可直接训练的数据集：
   - `data/processed/seed_iv_de_LDS.npz`：37,575 个窗口样本；
   - `data/processed/seed_iv_de_LDS_trial.npz`：1,080 个 trial 级样本。
4. 已完成真实 LOSO 基线：
   - MLP：Accuracy **42.78%**，Macro-F1 **0.4291**，κ **0.237**（四类随机水平 25%）；
   - DualView：Accuracy **27.69%**，Macro-F1 **0.2689**，κ **0.036**（未调参，初步结果）。
5. 当前结论：数据链路已真实跑通，但跨被试性能仍有限；DualView 需要针对真实 SEED-IV 重新调参与改进，不能把窗口级/合成结果当作论文结论。

---

## 2. 数据清单

### 2.1 目录结构

```text
data/SEED_IV/
├── eeg_feature_smooth/       # 45 个 MAT（3 sessions × 15 subjects）
│   ├── 1/  ... 3/
├── eeg_raw_data/             # 45 个 MAT，200 Hz 原始 EEG
│   ├── 1/  ... 3/
├── eye_feature_smooth/       # 45 个 MAT，眼动特征（暂未接入）
├── eye_raw_data/             # 45 个 MAT，眼动原始数据（暂未接入）
├── Channel Order.xlsx        # 62 通道顺序
├── seed-iv-stimulation.xlsx  # 刺激片段与标签
└── ReadMe.txt                # 标签、版权、引用
```

### 2.2 标签

ReadMe 给出的每个 session 的 24 个标签：

```text
session1 = [1,2,3,0,2,0,0,1,0,1,2,1,1,1,2,3,2,2,3,3,0,3,0,3]
session2 = [2,1,3,0,0,2,0,2,3,3,2,3,2,0,1,1,2,1,0,3,0,1,3,1]
session3 = [1,2,2,1,3,3,3,1,1,2,1,0,2,3,3,0,2,3,0,0,2,0,1,0]
```

| 编码 | 英文 | 中文 |
|---:|---|---|
| 0 | neutral | 平静 |
| 1 | sad | 悲伤 |
| 2 | fear | 恐惧 |
| 3 | happy | 快乐 |

每个 session 每类 **6 个 trial**；15 名被试合计每类 **270 个 trial**，四类完全平衡。

### 2.3 特征格式

`eeg_feature_smooth/{session}/{subject}_{date}.mat` 包含：

```text
de_LDS1 ... de_LDS24          # (62, T, 5)
de_movingAve1 ... 24
psd_LDS1 ... 24
psd_movingAve1 ... 24
```

- 62 通道，顺序见 `Channel Order.xlsx`；
- 5 个频带：δ / θ / α / β / γ；
- T 为 4 s 窗口数，本数据范围 **10–64**；
- 本系统默认使用 `de_LDS`（LDS 平滑后的 DE）。

### 2.4 数据量

| 项目 | 数值 |
|---|---:|
| 被试 | 15 |
| Session | 3 |
| Trial | 1,080 |
| 特征窗口 | 37,575 |
| 通道 | 62 |
| 频带 | 5 |
| 窗口长度 | 4 s |
| 窗口范围 | 10–64 / trial |
| 类别 trial 数 | 270 / 类 |
| 类别窗口数 | 平静 10,170；悲伤 10,245；恐惧 9,225；快乐 7,935 |

---

## 3. 接入实现

### 3.1 适配器

新增 `eeg_emostudio/data/seed_iv.py`：

- 自动定位 `{subject}_{date}.mat`；
- 读取 `de_LDS/de_movingAve/psd_LDS/psd_movingAve`；
- 将 `(62, T, 5)` 转为 `(T, 62, 5)`；
- 绑定 `subject / session / trial / label / trial_id`；
- 校验 62 通道、5 频带、无 NaN/Inf；
- 支持按 session/subject 子集构建。

### 3.2 两种数据集

**窗口级**（研究用，保留时间信息）：

```text
data/processed/seed_iv_de_LDS.npz
x: (37575, 62, 5)
y: 0..3
subjects: S01..S15
sessions: session1..3
trial_ids: S01_session1_T01...
```

**Trial 级**（快速基线/统计用，对窗口取均值）：

```text
data/processed/seed_iv_de_LDS_trial.npz
x: (1080, 62, 5)
每个 trial 一个样本
```

两者均带 `manifest.json`、`SHA-256` 与 `class_names`。

### 3.3 CLI

```powershell
# 审计
python -m eeg_emostudio seed-iv --root data/SEED_IV --audit-only

# 窗口级
python -m eeg_emostudio seed-iv --root data/SEED_IV `
  --out data/processed/seed_iv_de_LDS.npz --aggregate window

# trial 级
python -m eeg_emostudio seed-iv --root data/SEED_IV `
  --out data/processed/seed_iv_de_LDS_trial.npz --aggregate trial
```

### 3.4 Web 集成

- `data/processed/*.npz` 会被 `/datasets` 自动扫描；
- 数据卡显示 `SEED-IV` 来源、trial 数、62 通道、5 特征、15 被试；
- 训练页自动识别大数据集，建议 15 epochs / batch 128；trial 级 1,080 样本保持 40 epochs / batch 32；
- 实验记录页优先展示真实运行，合成 demo 单独标记。

---

## 4. 数据质量审计

| 检查 | 结果 |
|---|---|
| 15 名被试 × 3 sessions | 通过 |
| 每 session 24 trials | 通过 |
| 62 通道 | 通过 |
| 5 频带 | 通过 |
| 无 NaN/Inf | 通过 |
| 标签与 ReadMe 一致 | 通过 |
| 每类 270 trial | 通过 |
| 训练/测试被试隔离 | 由 LOSO 代码断言保证 |

**未执行**：

- 原始 EEG 的通道阻抗、工频噪声、眼电/肌电伪迹检查（官方特征已预处理，但原始文件尚未重跑）；
- 原始 200 Hz 数据到 DE 的复现实验（当前使用官方预计算 `de_LDS`）；
- 眼动特征/多模态融合。

---

## 5. 真实基线结果

### 5.1 设置

- 数据：`seed_iv_de_LDS_trial.npz`（1,080 trial）；
- 评估：LOSO，15 折；每折留一名被试；
- 标准化：只在训练折拟合；
- 指标：Accuracy、Balanced Accuracy、Macro-F1、Cohen's κ、95% CI；
- 随机水平：25%。

### 5.2 MLP 基线

```powershell
python -m eeg_emostudio train `
  --data data/processed/seed_iv_de_LDS_trial.npz `
  --out artifacts/experiments/seediv_trial_mlp_loso `
  --model mlp --setting loso --epochs 40 --batch-size 64 `
  --hidden 64 --dropout 0.3 --seed 42
```

| 指标 | 数值 |
|---|---:|
| Accuracy | 0.4278 |
| Balanced Accuracy | 0.4278 |
| Macro-F1 | 0.4291 |
| Cohen's κ | 0.2370 |
| Accuracy 95% CI | 0.4000–0.4556 |
| 分被试 Accuracy 范围 | 0.2500–0.5833 |

**分类别召回**：平静 0.470、悲伤 0.393、恐惧 0.382、快乐 0.467。  
混淆矩阵显示恐惧/悲伤与平静之间存在明显混淆，符合跨被试情绪识别的难度。

### 5.3 DualView 初步结果

```powershell
python -m eeg_emostudio train `
  --data data/processed/seed_iv_de_LDS_trial.npz `
  --out artifacts/experiments/seediv_trial_dualview_loso `
  --model dualview --setting loso --epochs 40 --batch-size 64 `
  --hidden 48 --dropout 0.3 --prototypes 2 --proto-weight 0.1 --seed 42
```

| 指标 | 数值 |
|---|---:|
| Accuracy | 0.2769 |
| Macro-F1 | 0.2689 |
| Cohen's κ | 0.0358 |

**解读**：DualView 目前仅略高于随机水平，说明在 SEED-IV 的强跨被试分布偏移下，现有双视角/原型设计没有自动带来收益；需要做特征标准化、域适应、原型初始化与超参搜索后再比较。不能把“结构存在”当作“方法有效”。

---

## 6. 结果解释与边界

1. **窗口级 vs trial 级**：trial 级均值会丢失时间动态，但能降低窗口自相关和计算量；论文应同时报告窗口级或明确说明聚合方式。
2. **官方特征 vs 自实现**：当前使用官方 `de_LDS`，没有重跑原始 200 Hz 到 DE 的全流程；论文需说明特征来源。
3. **跨被试难度**：四类 25% 随机水平，42.8% 是“有信息但不高”的基线；不能与文献中经过域适应/调参的 SOTA 直接比较。
4. **DualView 失败**：这是有价值的负结果，说明需要针对真实数据改进，而不是继续用合成数据讲故事。
5. **数据许可**：SEED-IV 仅用于研究，不随项目再分发；论文引用 EmotionMeter 原文。

---

## 7. 下一步

1. **窗口级基线**：用 MLP/DGCNN/DualView 在 37,575 窗口上跑 LOSO，比较 trial 级聚合的影响；
2. **域适应**：DANN/MMD/原型对齐，以 LOSO 为目标域，严格不使用目标标签；
3. **DualView 改进**：输入标准化、区域划分按 10-20 系统、原型初始化/温度、类别权重；
4. **原始数据复现**：用 `eeg_raw_data` 重跑 0.1–70 Hz 滤波 + 4 s DE，核对与官方特征的一致性；
5. **多模态**：接入 `eye_feature_smooth`，做 EEG + 眼动的区域到全局融合；
6. **trial 级投票**：窗口级预测按 trial 多数票汇总，报告 trial-level 指标；
7. **论文表述**：把 42.78% 作为真实基线，把 DualView 27.69% 作为待改进结果，不夸大。

---

## 8. 引用与合规

- Zheng W.-L., Liu W., Lu Y., Lu B.-L., Cichocki A. EmotionMeter: A Multimodal Framework for Recognizing Human Emotions. IEEE Transactions on Cybernetics, 2018.
- SEED-IV 数据版权归上海交通大学 BCMI 所有；仅用于本研究，不再分发原始数据。
- 当前工作区数据路径：`data/SEED_IV/`。
