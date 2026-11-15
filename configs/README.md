# 配置目录（预留）

当前 V0.1.0 的训练参数通过 CLI 传入，便于在论文中直接记录命令与种子；本目录预留给 V1.1 的 YAML 配置：

```yaml
data: data/processed/selfcollected_v1.0.npz
model: dualview
setting: loso
seed: 42
epochs: 60
```

在 YAML 配置加载器实现前，请使用 `python -m eeg_emostudio train --help` 中的参数，并把命令写入实验记录。
