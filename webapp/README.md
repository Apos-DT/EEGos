# EEG-EmoStudio Web Console

本地研究控制台，FastAPI + Jinja2 + 原生 CSS/JS；主界面无 CDN、无 node 构建、无外部数据库。

```powershell
python -m webapp
# http://127.0.0.1:8770
```

页面（管理端日常页面 + 被试端 + 历史归档）：

| 路径 | 页面 | 能力 |
|---|---|---|
| `/` | 工作台 | 三大功能域入口、资产与流水线 |
| `/surveys` | 问卷管理 | 选素材、生成分享链接、编辑/关闭问卷 |
| `/responses` | 实验问卷 | 响应明细、完成率、CSV 导出 |
| `/media` | 素材库 | 240 条视频/音乐，同步、预览、筛选 |
| `/q/{token}` | 被试端 | 打开链接、播放素材、填写问卷 |
| `/audit` | 历史预评价 | 240 材料/2,356 问卷归档，不进入日常流程 |
| `/eeg` | 原始 EEG 处理 | EEGLAB 上传、滤波/ICA/分段/DE |
| `/datasets` | 数据集与特征 | 上传 raw.npz、提取 DE、管理特征集 |
| `/training` | 模型训练 | 配置、后台任务、日志、指标与图表 |
| `/experiments` | 实验记录 | 比较运行、报告/指标链接 |
| `/documents` | 项目文档 | 14 份 DOCX/PDF 下载 |
| `/system` | 系统状态 | 环境、API、任务、数据边界 |

API 文档：`/api/swagger`。  
核心 API：`/api/overview`、`/api/surveys`、`/api/media`、`/api/public/surveys/{token}`、`/api/experiment/responses`、`/api/eeg/uploads`、`/api/eeg/process`、`/api/datasets`、`/api/datasets/merge`、`/api/experiments`、`/api/jobs/{id}`。

任务在进程内线程池运行，日志写入 `artifacts/web_jobs/`；训练/特征任务通过现有 CLI 子进程执行，避免 Web 层复制算法。
