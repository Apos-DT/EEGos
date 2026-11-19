# 原始 EEG 处理协议与验证

## 数据实查

本机 `data/SEED_IV/eeg_raw_data/1/1_20160518.mat` 为 24 个 `cz_eeg1`–`cz_eeg24` 矩阵，通道数为 62，trial 时长不同。第一个 trial 形状为 `(62, 33601)`。文件没有采样率/单位字段：200 Hz 来自 [SEED-IV 官方发布协议](https://bcmi.sjtu.edu.cn/home/seed/seed-iv.html)，输入 µV 是须由用户核对并写入报告的单位假设，不从幅值自动猜测。通道顺序已与本机 `Channel Order.xlsx` 核对；会话标签来自本机 ReadMe.txt。每个会话每个被试必须恰好有一个 MAT，且包含完整、不重复的 24 个原始 trial。官方特征 MAT 不能作为原始信号导入。

## 研究方法与实现边界

采用逐记录检查、坏导复核、滤波/参考、分段质量控制及 ICA 审阅的可追溯流程，参考 [MNE 预处理工作流](https://mne.tools/stable/documentation/cookbook.html) 和 [MNE ICA 文档](https://mne.tools/stable/auto_tutorials/preprocessing/40_artifact_correction_ica.html)。这些是可解释且可复核的基础；不存在适合所有 EEG 数据的单一“前沿清洗按钮”。

| 方法 | 当前实现 | 适用条件 / 注意 |
|---|---|---|
| 原始 trial 独立处理 | 支持 | 不拼接不同电影片段，不让滤波或窗口跨越 trial |
| 零相位带通 / 工频陷波 | 支持，SciPy SOS Butterworth 4 阶、forward-backward；notch Q=30 | 参数写入报告，严格校验 Nyquist，不静默修改频率 |
| 平均参考、抗混叠降采样 | 支持 | 人工排除坏导后再参考；resample_poly，目标采样率不能高于输入 |
| 坏导检查 | 平直信号、robust log-STD 异常记录，CSV 导出；手动按名称排除 | 异常提示不是生理诊断；不凭不完整坐标做自动插值 |
| 窗口伪迹剔除 | 峰峰值与平直通道阈值，逐窗口保留/拒绝 | 阈值需按单位与数据复核，拒绝记录包含窗口原位置 |
| MNE ICA | 支持固定分解审阅与重用后人工选择排除成分 | 单被试单会话，拟合使用通过质量检查的窗口及 1 Hz 高通副本，至少60秒；不做自动脑源分类 |
| ASR | 未集成 | [EEGLAB 官方说明](https://eeglab.org/plugins/clean_rawdata/)要求合适的校准和参数，不能将阈值拒绝冒充 ASR |
| ICLabel | 未集成 | [官方示例](https://mne.tools/mne-icalabel/stable/generated/examples/00_iclabel.html)说明其训练条件涉及平均参考、1–100 Hz 与 extended infomax；公开200 Hz数据无法直接满足相同高截止条件 |
| AutoReject / 空间插值 | 未集成 | 需要可靠的电极坐标、合理的校准/交叉验证；本机 CB1/CB2 位置不应随意替代 |

## 页面操作

1. 打开 `/eeg`，默认是“SEED-IV 原始 MAT”。选择会话、被试，可选择全部15名被试批量处理。
2. “检查首个所选文件”读取 MAT 结构与首个 trial 的真实信号；可展开24个trial的形状、时长和标签。
3. 核对输入采样率和单位。质量控制预设为1–75 Hz、50 Hz陷波、平均参考、4秒窗/4秒步长、两端各裁剪1秒、200 µV峰峰值上限、0.1 µV平直阈值。
4. “SEED-IV频带基线”预设关闭额外陷波、CAR、边界裁剪和窗口拒绝，保留1–75 Hz与4秒窗口。**两种预设都是重新计算特征，均未复现官方 LDS 平滑。**
5. 提交后在后台逐文件处理，日志输出每个trial保留/候选窗口数。页面刷新可恢复当前服务中的任务；服务重启后从处理记录查看落盘结果。
6. 结果包括处理前后波形、平均功率谱、保留/剔除窗口数、逐trial质量表、参数与输入SHA256。单被试流程检查结果先进入数据集管理；跨被试训练需多名被试的数据。
7. EEGLAB .set/.zip 原有入口保留为第二个页签。事件越界时标签同步过滤，重采样后的事件latency同步换算；不会因跳过边界事件而错配标签。

## ICA 审阅与应用

ICA采用MNE `ICA(method="fastica")`，固定种子，最多500迭代，拟合成分数最多40且低于保留通道数。选“拟合并保存”仅保存分解与成分波形，特征仍来自未删除成分的数据。审阅需结合波形、频谱、空间分布及参考信号，不能只凭一张波形图确认伪迹。

应用模式选择既有成功审阅任务并填写0起始的成分编号。服务端校验相同源文件SHA256、采样率、单位、频率、参考与坏导设置，加载原 `review-ica.fif`，随后才执行 `ICA.apply(exclude=...)`。不重新拟合并假定成分编号相同；不允许跨被试/会话复用编号。未收敛的参考分解禁止应用。

## 输出与可复现性

目录：`artifacts/eeg/raw-时间戳-任务后缀/`。

- `features.npz`：`x=(windows, channels, 5)`，以及 `y/subjects/sessions/trial_ids`。五频带1–4、4–8、8–14、14–31、31–50 Hz。DE使用微伏输入和自然对数 `0.5*ln(2*pi*e*variance)`，频带过滤在完整trial上进行，再逐窗计算。常数地板1e-12避免log(0)。
- `features.manifest.json`：输出形状、数据指纹、完整参数、源文件SHA256、通道与数据版本说明。
- `window_index.npz`：每个保留窗口的原始trial标识与起始秒数。按被试/trial划分评估，重叠窗口不可随机分散至训练和测试集。
- `raw.npz`：可选，保留窗口的清洗后信号，带fs、标签及同样的组标识。默认不保存以避免批量任务产生数GB数据。
- `eeg_report.json`：运行起止、环境版本、代码SHA256、源文件指纹、逐trial和逐窗的接受/拒绝原因、ICA信息。
- `channel_qc.csv`：各trial各保留通道的STD、峰峰值与异常提示。
- `waveform.png`、`spectrum.png`：首个trial处理前后可视化，不代表全部数据质量；整体质量看CSV与逐trial统计。
- `review-ica.fif`、`ica_profile.json`、`ica_components.png`：ICA审阅任务输出。
- `report.html`：可查看参数和质量记录的报告；失败任务也保留已写出的报告。

所有任务保留原数据，处理结果写新目录。新特征自动出现在“数据集与特征”，与原始官方 `de_LDS` 独立管理。原始信号处理不导入PyTorch；训练依赖已改为CLI命令按需加载。

## 环境

主信号链使用NumPy/SciPy/Matplotlib。MNE/ICA安装在独立 `.venv-eeg`，不修改DDA GPU环境。可用 `EEG_PROCESS_PYTHON` 覆盖处理解释器。

```powershell
python -m venv .venv-eeg --system-site-packages
.\.venv-eeg\Scripts\python.exe -m pip install -r requirements-eeg.txt
```

本机已验证MNE 1.13.2、scikit-learn 1.8.0。没有MNE时基础信号链仍可运行；ICA需独立环境的可用依赖。

## 验证记录

- 真实 S01/session 1 完整24个trial：836个候选窗口，763个有效窗口、73个拒绝窗口，输出763×62×5，四类情绪齐全。该次运行约13.4秒，系单文件流程验证，不能作为分类成绩。
- 单元检查：显式V/µV转换等价、严格Nyquist、重复scope拒绝、短trial不补零、不跨trial造窗口、两被试48个trial的身份与标签保持、EEGLAB边界事件标签与重采样latency。
- MNE合成信号端到端检查：保存固定分解、再次加载同一模型、移除指定成分后输出实际改变。该检查不用于伪迹识别效果评估。
- session 1 全部15文件/360trial批处理通过网页完成，耗时149.938秒；12,540个候选窗口，保留9,046个，拒绝3,494个，输出9,046×62×5，15名被试与四类情绪均保留。结果目录 `artifacts/eeg/raw-20261120-011938-d0fff0/`，标签、窗口索引、全部源文件SHA256及数据集发现接口已核验。这是预处理结果，不是模型分类准确率。
