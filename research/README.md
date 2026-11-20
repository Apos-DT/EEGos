# research/ — 研究过程资料

本目录归档毕设研究过程中产生的**可版本化资料**：预评价的质量排序、参考文献清单、周报，以及早期的数据探索脚本。它们不是运行时代码，也不参与 `python -m eeg_emostudio` / `python -m webapp` 的执行。

| 子目录 | 内容 | 与代码的关系 |
|---|---|---|
| `quality/video/` | 120 段视频的 S/A/B/C/D 质量排序、评分报告、评分者统计 | 由 `eeg_emostudio/cli.py` 的 `select` 命令与 `webapp` 素材库读取，作为选材输入证据 |
| `quality/audio/` | 120 首音乐的质量排序与评分报告 | 同上 |
| `references/` | 参考文献清单汇总（CSV/XLSX）与 `slides/` 参考 PPT | `docs/04_文献综述与需求依据.md` 的写作依据 |
| `reproductions/dda_sidecar/` | 独立 DDA 复现源码与许可证归档 | 运行时经系统接口调用项目外的 checkout，不导入核心算法包 |
| `weekly/` | 周工作汇报（TXT/DOCX） | 进度记录 |
| `legacy/` | 早期数据探索、质量评分与交付物生成脚本 | 历史快照；部分脚本仍含本机绝对路径，重跑前需核对输入位置 |

## 说明

- `quality/` 下的 CSV 是**输入证据**，因此入库；`*.pkl`、日志、`_tmp_*` 与 `pptx_imgs/` 等中间产物由 `.gitignore` 排除。
- `legacy/` 中的脚本使用开发机的绝对路径（如 `C:\Users\...\Desktop\EEG Emotion Recognition\...`），仅作方法与过程留档；正式可复现的流程以 `eeg_emostudio/` 与 `scripts/` 为准。
- 原始刺激、问卷（`山科数据集/`）、SEED-IV 特征（`data/SEED_IV/`）与文献 PDF（`文献/`）因体积与许可原因不入库，位置保持项目原有约定。

参考演示稿 `高宇261022.pptx` 已归入 `references/slides/`，与同名文献清单集中保存；`legacy/extract_pptx.py` 已改为按项目相对路径读取。
