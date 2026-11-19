# DDA 论文复现与外部集成

**论文**：Li et al., *Dynamic Domain Adaptation for Class-Aware Cross-Subject and Cross-Session EEG Emotion Recognition*, IEEE JBHI, 2022. DOI: `10.1109/JBHI.2022.3210158`
**外部代码**：[JC-Journal-Club/DDA](https://github.com/JC-Journal-Club/DDA)
**数据**：本地 `data/SEED_IV/`，复现使用官方 `eeg_feature_smooth/*/*.mat` 中的 `de_LDS1`–`de_LDS24`。

## 集成边界

作者仓库独立放在项目同级的 `DDA-reproduction/`，不复制到 `eeg_emostudio/`，也不作为 EEG-EmoStudio 的 Python 模块导入。Web 层只通过子进程调用 sidecar CLI，将配置和日志写入现有 JobManager，并将标准化的 `metrics.json` 写入 `artifacts/experiments/`，使实验记录页可以发现结果。

调用入口：`POST /api/integrations/dda/run`，可在 `/api/swagger` 执行。任务状态与日志仍通过既有 `/api/jobs/{job_id}` 查看。`EEG_DDA_REPO` 可指定 sidecar 目录；`EEG_DDA_PYTHON` 可指定能导入 PyTorch、NumPy、SciPy 的独立解释器。缺省仓库路径为项目同级的 `DDA-reproduction`。

## 当前 sidecar 实现说明

上游当前提交为 `1f1b2bdbbf9a1156272dfdf67831dc43fffb23d1`。检查 `UDDA/seed4/train.py` 可见 GDD 与 CDD/LSD 的训练代码被注释，实际更新目标只有源域交叉熵；脚本还把数据目录写死，并周期性以目标标签评估、挑选峰值。因此直接调用该脚本不能视为论文 DDA 复现。

为保留系统边界，`DDA-reproduction/run_seed4_dda.py` 是外置 sidecar：复用上游 `network.py` 的 MLP 编码器/分类器，在该目录单独实现论文的 GDD、LSD、动态权重与 UDDA/SDDA 训练流程。论文未在正文给出伪标签置信阈值，当前暂按上游注释示例设为 0.75；这是需记录的复现假设。sidecar 不改动上游跟踪文件。

另一个需要明确记录的实现差异：sidecar 保留作者 `train.py` 的 `zip(source_loader, target_loader)` batch 配对，因此每轮迭代数由较短的 DataLoader 决定；这和论文算法框中“直到所有 source 样本都抽取过”的文字可能不同。结果文件会记录此口径，不能隐去这一点。

数据划分按论文的逐 session / 整体 session 定义，并与作者 `runsession*.sh` 的执行方式对应：跨被试在每个 session 内留一名被试作目标域、其余 14 名作源域，共 45 折；跨 session 每折留一个完整 session 作目标域、其余两个 session 的全部 15 名被试作源域，共 3 折。官方四类标签为平静、悲伤、恐惧、快乐。输入保留 4 秒 DE 窗口，不使用 trial 平均值。

结果区分两种口径：

- `overall.accuracy`：训练结束时目标域准确率均值；
- `overall.paper_protocol_peak_accuracy`：每隔 10 轮按目标域标签评估并选取峰值的均值，与论文 peak 报告口径接近，但会因目标测试集参与 checkpoint 选择而偏乐观。

两者必须同时报告；峰值口径不应单独作为无偏泛化估计。SDDA 默认使用目标域前 4 个 trial 的标签，剩余目标数据以无标签形式参与适配；UDDA 不使用目标标签梯度。启动训练前应先用 1 个 fold 做流程检查，再按论文 epoch 数运行完整折数。

## API 示例

网页入口：打开“模型训练”（`/training`），在“1 · 选择方法”中直接选择 DDA，与 MLP、DGCNN、DualView 并列。DDA 选项内部再选择 UDDA/SDDA 变体，数据固定为当前适配器支持的本机 SEED-IV；其后配置协议、目标域、训练参数。默认运行 1 折，完整训练需明确选择“运行全部所选折”。高级参数提供 batch size、学习率、β、伪标签阈值和评估间隔。常规模型只展示适用参数，原型参数仅在 DualView 下可见。启动前显示本次实验摘要。

点击“启动实验”后，下方控制台显示后台任务日志，完成后显示最终指标、目标测试峰值及报告链接。DDA 直接读取本机 SEED-IV，因此没有 NPZ 数据集时也可运行。完整实现仍位于外部 sidecar，系统核心只调用 CLI。

### 报告与溯源记录（2026-11-20 更新）

新任务保存以下文件：

- `run_meta.json`：任务提交、运行开始、数据加载完成、训练结束、运行结束时间（Asia/Shanghai，含 +08:00）、耗时、完整可配置参数和固定参数、环境版本、GPU、上游提交及本地代码 SHA256。
- `dataset_manifest.json`：本次加载的 45 个 MAT 文件的相对路径、大小和 SHA256；逐折结果说明真正参与该折的源域会话、被试与目标域。
- `timeline.jsonl`：运行、数据加载、逐折起止、每次 epoch 评估及异常的时间线。评估记录保存当时准确率、loss 和耗时。
- `metrics.json`：最终准确率与训练峰值、峰值 epoch、逐折种子与起止、混淆矩阵、分类别/分被试指标及完整协议口径。
- `progress.json`：已完成折的增量记录；运行失败时仍保留已完成的折。
- `training.log`：从网页启动的任务保留外部进程输出。
- `code/`：新任务所用 runner、报告生成器、作者网络文件的代码快照。
- `report.html`：汇总以上记录的可独立打开报告，含中文字段、指标卡片、导航、逐折评估明细和可展开的文件清单/时间线；失败任务也生成报告。

旧任务第一次查看报告时由外部报告生成器升级版式。原始任务没有记录过的时间、环境或文件版本标记为“未记录”，不从文件修改时间或当前环境反推，也不修改已有指标。已在运行中的旧 runner 不会自动获得新增的溯源记录。

已通过网页完成 UDDA 的 1 epoch GPU 端到端检查（seed=0），确认 CUDA 设备、45 文件清单、时间节点和结果均正确落盘；这类检查任务仅用于流程检查，不能作为论文复现成绩。

```json
{
  "setting": "cross-subject",
  "algorithm": "UDDA",
  "epochs": 600,
  "seed": 42,
  "target_subject": "S01",
  "target_session": "1",
  "max_folds": 1
}
```

要运行完整跨被试 UDDA，省略 `target_subject` 与 `target_session`，并将 `max_folds` 设为 `0`。跨 session 可设 `setting` 为 `cross-session`；该划分按论文把每个完整 session 聚合为一个域。单折流程检查可指定 `target_subject: "S01"`、`target_session: "1"`、`max_folds: 1`。

## 当前环境状态与注意事项

- 用户提供的 `C:\Users\24114\.conda\envs\pytorch_env\python.exe` 路径在本机不存在。已在外部 sidecar 环境 `DDA-reproduction/.venv` 安装 PyTorch `2.9.1+cu126`，验证 `torch.cuda.is_available() == True`，设备为 NVIDIA GeForce RTX 4060 Laptop GPU（8 GB）。
- 已完成一个 600 epoch 的跨被试 UDDA 单折流程验证（S01/session 1）：最终准确率 50.18%，每 10 epoch 目标测试峰值 61.46%，结果归档于 `artifacts/experiments/20261119_dda_udda_cross_subject_smoke/`。这只是单折运行检查，不是论文整体结果。
- 完整跨被试 UDDA（45 折 × 600 epoch）已在 RTX 4060 上启动，输出目录为 `artifacts/experiments/20261119_dda_udda_cross_subject_full/`。该任务尚未完成，现有文件夹不能作为完整结果引用。
- 上游仓库许可证为 GPL-2.0，外部 checkout 保留其许可证；不要把上游代码拷入本项目或与系统核心打包分发。
- 原始数据、刺激/被试信息遵守 SEED-IV 使用许可。本接口只发现本机数据，不上传数据。
- 论文报告 SEED-IV 的 SDDA 平均峰值准确率：跨被试 81.58%，跨 session 80.82%。这些是对照值，不代表本机复现结果。


## 本机后台训练监控

训练页的“本机训练监控”每 5 秒调用 `GET /api/training/monitor`，读取本项目 JobManager（含落盘的历史任务）、Windows CIM 进程和实验进度文件。支持网页提交的常规模型训练及输出位于本项目实验目录的独立 DDA CLI 任务。启动器/工作进程按输出目录合并，显示实际工作进程 PID；刷新页面或重启 Web 服务后也能重新发现仍在训练的进程。

监控显示开始时间、运行时长、数据集、协议、已完成折数、最近评估 epoch、进度更新时间、近期日志与参数；报告生成后可直接打开。新 DDA 任务通过 `heartbeat.json`、`progress.json` 和 `timeline.jsonl` 提供进度，常规模型按已完成 LOSO 折的日志更新。旧 DDA 进程没有落盘进度时只显示真实进程状态，不估造 epoch 或百分比。网页提交的训练进程 PID/输出目录同时写入任务 runtime 记录，原始输出保存为 training.log。

显卡信息来自 nvidia-smi，包括 GPU 利用率、显存和温度，表示整卡总占用（包括其他应用），不归因给单个任务。进程探测或显卡查询失败时明确显示不可用；落盘任务仍标为 running 但实际进程已退出时标为“进程已退出 · 无完成记录”。监控是只读操作，不提供终止或重启训练功能，也不导入 PyTorch。

## 源码归档与迁移

独立 runner、报告生成器、依赖与 GPL-2.0 许可证归档于 `research/reproductions/dda_sidecar/`。按该目录 README 恢复项目同级的外部 checkout；运行时仍通过 CLI 接口调用，不导入系统核心。不要提交虚拟环境、wheel 或原始数据。
