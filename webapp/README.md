# EEG-EmoStudio Web Console

本地研究控制台，FastAPI + Jinja2 + 原生 CSS/JS；主界面无 CDN、无 node 构建、无外部数据库。

```powershell
python -m webapp
# http://127.0.0.1:8770
```

> **改代码后必须重启服务**。`python -m webapp` 默认 `reload=False`，Jinja2 却会自动重新读取被修改的模板文件；若不重启，就会出现「旧 Python 进程 + 新模板」错配——新模板引用了旧路由没有传入的变量，页面直接返回 500（2026-11-15 `/surveys/new` 曾因此报错）。开发期可启用自动重载：
>
> ```powershell
> $env:EEG_WEB_RELOAD = "1"; python -m webapp
> ```
>
> 模板里的脚本注入变量均已加 `|default` 兜底，即使版本错配也只是功能降级，不会再抛 500。

页面（管理端日常页面 + 被试端 + 历史归档）：

| 路径 | 页面 | 能力 |
|---|---|---|
| `/` | 工作台 | 三大功能域入口、资产与流水线 |
| `/surveys` | 问卷管理 | 选素材、自定义题目、生成分享链接、编辑/关闭问卷 |
| `/survey-data` | 问卷数据与元数据 | 逐题答卷查看/搜索/筛选、答卷元数据、题目作答率、质量诊断、历史 CSV 导入、两种格式导出 |
| `/media` | 素材库 | 240 条视频/音乐，同步、预览、筛选 |
| `/q/{token}` | 被试端 | 打开链接、播放素材、填写问卷、完成后回看本轮逐题作答 |

**旧版页面已下线**：`/experiment`（现场实验固定量表）与 `/responses`（旧版统计页）均 302 跳转到 `/survey-data`。前者带 `?session=...` 时会解析会话归属问卷并直达该轮答卷详情。会话 JSON 与旧版只读 API 保留，用于回溯历史数据，但不再提供任何新建现场实验的界面入口。
| `/audit` | 历史预评价 | 240 材料/2,356 问卷归档，不进入日常流程 |
| `/eeg` | 原始 EEG 处理 | EEGLAB 上传、滤波/ICA/分段/DE |
| `/datasets` | 数据集与特征 | 上传 raw.npz、提取 DE、管理特征集 |
| `/training` | 模型训练 | 配置、后台任务、日志、指标与图表 |
| `/experiments` | 实验记录 | 比较运行、报告/指标链接 |
| `/documents` | 项目文档 | 14 份 DOCX/PDF 下载 |
| `/system` | 系统状态 | 环境、API、任务、数据边界 |

API 文档：`/api/swagger`。  
核心 API：`/api/overview`、`/api/surveys`、`/api/surveys/{id}/responses`、`/api/surveys/{id}/responses/{rid}`、`/api/media`、`/api/public/surveys/{token}`、`/api/experiment/responses`（旧版兼容）、`/api/eeg/uploads`、`/api/eeg/process`、`/api/datasets`、`/api/datasets/merge`、`/api/experiments`、`/api/jobs/{id}`。

任务在进程内线程池运行，日志写入 `artifacts/web_jobs/`；训练/特征任务通过现有 CLI 子进程执行，避免 Web 层复制算法。

## 问卷 schema 与元数据管理（V0.6）

不再依赖问卷星：问卷可自定义题目，历史问卷星 CSV 可导入并纳入统一管理。沿用纯 JSON 文件方案，无数据库、无新依赖。

**文件布局**（`data/` 下的运行时数据由 `.gitignore` 排除）

```text
data/surveys/{survey_id}.json                 问卷定义（含版本化 schema）
data/survey_responses/{survey_id}.jsonl       答卷，每行一条完整记录（追加写）
data/survey_imports/{batch_id}.json           导入批次登记（行数/指纹/列映射）
data/survey_imports/{batch_id}.source.csv     原始导出副本，按原始行号回查
data/survey_imports/_staging/                 两步导入的暂存区
data/experiment/sessions/                    会话播放进度（新版/旧版共用，仅存游标）
```

**题目 schema**：`webapp/questionnaire.py` 定义 5 种题型（text / rating / single / multiple / textarea）。每题可标注 `role`（rater、stimulus、valence、arousal、clarity、emotion、coverage、stability、familiarity、comprehension、issues、other 等），带角色的列才能参与归一化与质量评分；归一化复用 `eeg_emostudio/audit/normalize.py`，不重复实现清洗规则。内置视频/音乐两套 12 题标准量表，与既有问卷星导出逐列对应。

**版本化**：问卷保存 `schema_version` + `schema_hash`，改题时自动把旧量表压入 `schema_history` 并升版本；每份答卷记录当时的版本与指纹，因此修改量表后历史答卷仍可追溯。

**答卷元数据**：序号、提交时间、用时、来源、来源详情、IP 地区、IP 不可逆哈希、总分、评分者、素材编号（原始+归一）、批次、原始行号、逐题原始答案、按 role 归一化的值、有效性标记。**原始 IP 不落盘**。

**两步导入**：`POST /api/surveys/import/preview` 上传原始 CSV 字节（自动识别 UTF-8 BOM / GB18030 / UTF-16），按「题干关键词 + 取值形态」推断题型与字段映射并返回预览；`POST /api/surveys/import/commit` 确认后落盘。多选题按问卷星 `┋` 分隔符还原，文字锚点（`非常不愉快` 等）按既有规则转 1–9，同评分者 × 素材的重复只标记不删除。

**导出**：`responses.csv` 为问卷星兼容格式（7 个平台列 + 题目列、UTF-8 BOM，可与历史数据直接合并）；`responses.clean.csv` 为分析宽表（元数据列 + 每个 role 一列）。

**查看答卷**：`/survey-data?survey_id=X&tab=responses` 列出答卷，点「查看答卷」展开逐题的原始作答与归一化值，并可下载单份 JSON。支持 `response_id` 深链与 `session_id` 过滤；`/experiment?session=<id>` 会自动重定向到对应问卷的该轮答卷。被试完成一轮后，公开页「查看本轮作答」按会话回看自己的逐题答案（不会跨会话读取）。

**新增 API**：`/api/questionnaire/templates`、`/api/surveys/{id}/schema|metadata|quality|responses|responses/{response_id}|responses.csv|responses.clean.csv`、`/api/surveys/import/preview|commit`、`/api/surveys/imports`、`/api/surveys/imports/{batch}/source.csv`、`/api/public/surveys/{token}/sessions/{id}/answers|result`。

旧版固定量表问卷（无 `schema` 字段）仍走原有 `submit_response` 通道，公开页会自动回退到固定表单；其历史会话数据仍可通过 `/api/experiment/responses.csv` 导出。全部 36 项自动化测试通过。
