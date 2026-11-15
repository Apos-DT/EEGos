# 实验采集与 EEG 预处理说明

**文档编号**：17  
**版本**：V1.0（2026-11-15）  
**对应页面**：`/surveys`、`/survey-data`、`/media`、`/q/{token}`、`/eeg`

---

## 1. 系统三域架构

系统从“按技术分层”调整为“按科研任务分域”：

```text
实验
  问卷管理 /surveys
  问卷数据 /survey-data        逐题答卷、元数据、质量诊断
  素材库 /media
  被试端 /q/{token}

EEG 信号
  原始 EEG 处理 /eeg
  数据集与特征 /datasets

模型训练
  模型训练 /training
  实验记录 /experiments

系统
  项目文档 /documents
  系统状态 /system
```

数据流：

```text
视频 + 问卷响应 ──┐
                  ├─→ 被试编号/刺激顺序对齐 ─→ 特征 ─→ LOSO 训练 ─→ 报告
EEGLAB .set/.fdt ─┘
```

---

## 2. 问卷管理与被试端

### 2.1 管理端做什么

1. 在 `/surveys/new` 从素材库勾选视频/音乐；
2. 保存后生成固定分享链接 `/q/{token}`；
3. 被试打开链接，填写实验前状态，逐条播放并评分；
4. 管理端在 `/surveys` 查看响应数、复制链接、关闭/编辑问卷。

### 2.2 一轮被试流程

1. 管理端在 `/surveys/new` 选择素材；保存后生成 `/q/{token}` 分享链接；
2. 被试打开链接，填写编号、睡眠、疲劳度、当前心情；
3. 问卷按管理端选择的素材顺序播放；
4. 素材顺序避免相邻刺激的主导情绪相同；
5. 浏览器播放视频或音频，**不显示情绪类别**，避免预期偏差；
6. 被试看完后点击“我看完了，填写问卷”；
7. 提交后自动进入下一个素材；
8. 完成后保存会话，可导出 CSV。

素材统一从 `data/media/video` 与 `data/media/audio` 读取；通过 `/q/{token}/media/{session_id}` 以 HTTP Range 流式播放。

### 2.3 问卷字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `valence` | 1–9 | 效价，1 非常不愉快，9 非常愉快 |
| `arousal` | 1–9 | 唤醒，1 非常平静，9 非常激动 |
| `discrete` | 平静/悲伤/恐惧/快乐/其他 | 主导情绪 |
| `intensity` | 1–5 | 情绪强度 |
| `familiarity` | 1–5 | 对片段熟悉度 |
| `previous_viewed` | bool | 之前是否看过 |
| `watch_seconds` | int | 实际观看时长 |
| `note` | str | 补充说明 |

### 2.4 存储

```text
data/surveys/<survey_id>.json               # 问卷方案、素材顺序、分享 token、版本化题目 schema
data/experiment/sessions/<session_id>.json  # 会话播放进度（新版与旧版共用目录）
data/survey_responses/<survey_id>.jsonl     # 新版逐题答卷，每行一条完整记录
data/survey_imports/<batch_id>.*           # 历史问卷星导入批次与原始 CSV 副本
```

会话包含：被试信息、刺激序列、当前进度、时间戳与状态（running/completed/aborted）。**新版自定义量表的答卷不写入会话的 `responses` 数组**，而是逐条落入统一 JSONL 仓库；会话只承担播放游标，进度按 `session_id` 回查 JSONL 统计。

导出：`/api/surveys/{survey_id}/responses.csv`（问卷星兼容）与 `responses.clean.csv`（分析宽表），均为 UTF-8 BOM；旧版固定量表历史数据仍可用 `/api/experiment/responses.csv` 导出。管理端在 `/surveys` 查看每份问卷的答卷数，在 `/survey-data` 逐题查看、筛选与下载单份答卷 JSON；被试完成一轮后可在 `/q/{token}` 完成页回看本轮作答。

### 2.5 与 EEG 对齐

- 被试编号必须与 EEG 文件/记录一致；
- 会话 JSON 保存刺激顺序与 `stimulus_id`；
- EEGLAB 事件码映射到 0–3 类别后，按事件切 trial；
- 当前**不自动做设备时间同步**；需要利用采集软件的事件标记或同步盒。

---

## 3. 原始 EEG 处理

### 3.1 支持格式

- `.set`：EEGLAB 连续数据，数据内嵌；
- `.zip`：包含 `.set + .fdt` 的 EEGLAB 导出；
- 暂不支持 `.edf/.bdf/.cnt` 原生导入；可先用 EEGLAB 转成 `.set`。

### 3.2 处理链

```text
读取 .set/.fdt
  → 检查通道/采样率/NaN/Inf
  → 带通 0.1–70 Hz
  → 50 Hz 陷波
  → 平均参考 CAR
  → 重采样到 200 Hz
  → 可选 ICA（FastICA，保存分解，不自动剔除）
  → 按事件切 4 s trial
  → 峰峰值 >150 µV 剔除
  → 5 频带 × 1 s 窗 DE
  → raw.npz / features.npz / manifest
```

### 3.3 事件映射

默认：

```text
1=0  2=1  3=2  4=3
```

对应：平静、悲伤、恐惧、快乐。若设备事件码不同，在页面“事件码 → 类别”中修改。

没有事件时：

- 仍输出 `eeg_clean.npz` 与预览图；
- 不生成 `raw.npz/features.npz`；
- 页面明确提示“未生成训练集”。

### 3.4 输出

```text
artifacts/eeg/<upload_id>/
├── eeg_clean.npz
├── eeg_preview.png
├── eeg_report.json
├── raw.npz            # 有事件时
├── features.npz       # 有事件时
└── ica_components.npz # 勾选 ICA 时
```

同时复制到：

```text
data/raw/<upload_id>_raw.npz
data/processed/<upload_id>_features.npz
```

训练页会自动扫描到新的特征集。

> 单个 `.set` 只产生一名被试的特征集。要做 LOSO，请在“数据集与特征”页勾选多名被试的特征集并点击“合并所选”；系统会生成 `merged_*.npz`。

### 3.5 CLI

```powershell
python -m eeg_emostudio eeglab `
  --input data/eeg_uploads/S01/S01.set `
  --out artifacts/eeg/S01 `
  --subject S01 `
  --bandpass 0.1,70 --notch 50 --target-fs 200 `
  --event-map 1=0,2=1,3=2,4=3 `
  --ica
```

---

## 4. 当前边界

1. 视频实验只支持本地视频文件；不支持在线视频/版权流媒体；
2. 问卷和 EEG 的时间同步依赖采集设备事件标记，当前没有硬件驱动；
3. ICA 仅保存分解结果，自动剔除眼电/肌电需要人工审阅或后续规则；
4. `.set` 的通道位置/事件结构因 EEGLAB 导出方式不同可能需要适配；
5. 实验数据含个人信息时，应按伦理审批要求脱敏、加密和限期保存。

---

## 5. 验收要点

- 视频接口支持 HTTP Range（206），可拖动进度条；
- 问卷提交后会话进度 +1，刷新页面可继续；
- 导出 CSV 字段与 JSON 一致；
- EEGLAB 上传后能看到通道、采样率、时长、事件数；
- 清洗后能下载 clean/raw/features/report；
- 有事件的数据在训练页出现新的特征集。
