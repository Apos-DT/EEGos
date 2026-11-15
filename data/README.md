# 数据目录约定

> 本目录用于**本地实验数据**，不提交到 Git。原始数据只读；派生数据写入新文件。

```text
data/
├── raw/            # 采集设备导出或公开数据集转换后的 raw.npz（只读）
├── interim/        # 清洗中间结果（可删除）
├── processed/      # features.npz + manifest（冻结版本）
└── metadata/       # 被试/会话/Trial 清单（V1.1）
```

## raw.npz 最小契约

```python
x        # (trials, channels, samples), float32, µV
y        # (trials,), int64, 0..K-1
subjects # (trials,), str, S01...
fs       # 标量，Hz
class_names  # 可选
```

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
