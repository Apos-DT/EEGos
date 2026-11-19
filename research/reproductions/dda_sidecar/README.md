# DDA 独立复现附件

本目录仅归档复现 runner、报告生成器和依赖清单，不作为 EEG-EmoStudio 核心算法包导入。实际运行仍在项目同级的外部 `DDA-reproduction/` checkout，通过子进程接口调用。

上游：<https://github.com/JC-Journal-Club/DDA>，基准提交 `1f1b2bdbbf9a1156272dfdf67831dc43fffb23d1`。上游网络文件不复制到系统；源码附件遵循 GPL-2.0，许可证随本目录保存。

## 恢复运行目录（Windows PowerShell，项目根目录执行）

```powershell
git clone https://github.com/JC-Journal-Club/DDA ../DDA-reproduction
git -C ../DDA-reproduction checkout 1f1b2bdbbf9a1156272dfdf67831dc43fffb23d1
Copy-Item research/reproductions/dda_sidecar/run_seed4_dda.py,research/reproductions/dda_sidecar/dda_report.py,research/reproductions/dda_sidecar/requirements-sidecar.txt ../DDA-reproduction/
python -m venv ../DDA-reproduction/.venv
../DDA-reproduction/.venv/Scripts/python.exe -m pip install -r ../DDA-reproduction/requirements-sidecar.txt
```

配置 `EEG_DDA_REPO` 和 `EEG_DDA_PYTHON` 可更换外部运行位置。官方数据独立放在 `data/SEED_IV/`，不会随代码分发。协议假设、峰值选择偏差和运行记录格式见 [集成说明](../../../docs/18_DDA论文复现与外部集成.md)。CUDA 不可用时 runner 会报错，不能静默退回 CPU。

修改研究附件后，需要同步到实际外部运行目录；此目录不构成对上游作者仓库的修改或推送。
