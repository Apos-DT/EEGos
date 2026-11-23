# 数据目录约定

> 本目录用于**本地实验数据**，不提交到 Git。原始数据只读；派生数据写入新文件。

```text
data/
├── emostudio.sqlite3 # 问卷、素材清单、任务、实验与文件索引（不入库）
├── external/       # 外部数据集原始发布包与许可材料（不入库）
├── raw/            # 采集设备导出或公开数据集转换后的 raw.npz（只读）
├── interim/        # 清洗中间结果（可删除）
├── processed/      # features.npz + manifest（冻结版本）
└── metadata/       # 被试/会话/Trial 清单（V1.1）
```

`external/<数据集 ID>/raw/` 保留官方文件与原始划分，`access/` 保存许可材料。
当前目录包括 `meld`、`emorynlp`、`noxi`、`iemocap`。SEED-IV 继续使用原有 `data/SEED_IV/`。
网页「数据集目录」从 SQLite 读取来源、模态与用途，实时检查本地文件状态。
内置目录由 `webapp/dataset_catalog.py` 初始化，新增版本可用数据库迁移登记描述和模态，再增加对应的文件检查与解析器。
`GET /api/datasets/catalog` 提供目录记录，`GET /api/datasets` 继续提供可训练的 EEG 特征集。
外部发布包只在目录登记。EEG 适配器将经检查的脑电时间序列或特征产物输出到对应 EEG 工作区后，再提交制备或训练。

## raw.npz 最小契约

```python
x        # (trials, channels, samples), float32, µV
y        # (trials,), int64, 0..K-1
subjects # (trials,), str, S01...
fs       # 标量，Hz，也可在提取时指定
modality # 可选文本标量，值为 "EEG"
class_names  # 可选
```

未标记模态的 NPZ 通过网页上传时需核对采集来源并勾选 EEG 确认。
调用 `POST /api/raw/upload` 时，确认来源后可传查询参数 `eeg_confirmed=true`。

## 命名建议

```text
raw/selfcollected_S01_S1.npz
processed/selfcollected_v1.0.npz
processed/selfcollected_v1.0.manifest.json
```

## 禁止

- 把姓名、学号、联系方式写入 `x/y/subjects` 或文件名；
- 用 `0` 代替缺失评分；
- 直接覆盖 `raw/` 或已冻结的 `processed/` 文件；
- 把原始 EEG/媒体提交到公开仓库。

## 相关命令

```powershell
python -m eeg_emostudio features --raw data/raw/xxx.npz --out data/processed/xxx.npz --fs 1000 --target-fs 200
python -m eeg_emostudio train --data data/processed/xxx.npz --out experiments/xxx_loso --model dualview --setting loso
```
