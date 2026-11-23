# EEG-EmoStudio Web Console

本地研究控制台，FastAPI + Jinja2 + 原生 CSS/JS。业务记录使用本地 SQLite，媒体和科研产物保存在文件系统。

```powershell
start.bat             # Windows 双击；./start.sh 用于 Linux/macOS
python -m webapp      # 等价，容器方式见根目录 README
# 管理端 http://127.0.0.1:8770/surveys
# 被试端 /q/<token>（手机需与电脑同一局域网）
```

`start.bat` / `start.sh` 只做解释器探测，其余逻辑在 `scripts/launch.py`：端口被占用时复用已运行的服务（`--restart` 才会停掉旧进程再启动，且会先用 `/api/health` 确认那是本工作台）、缺 Web 依赖时询问是否安装、服务就绪后自动开浏览器。中文提示统一由 Python 侧输出，避免 `.bat` 的代码页乱码。

配置项（`EEG_WEB_HOST` / `EEG_WEB_PORT` / `EEG_WEB_TOKEN` / 数据目录外挂）见根目录 README 的「Web 控制台」一节。

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

| `/audit` | 历史预评价 | 240 材料/2,356 问卷归档，不进入日常流程 |
| `/eeg` | 原始 EEG 处理 | EEGLAB 上传、滤波/ICA/分段/DE |
| `/datasets` | 数据集 | 数据资源分组下的跨模态目录。切换到 `?tab=eeg` 可上传 EEG raw.npz、提取 DE 和管理特征集 |
| `/training` | 模型训练 | 配置、后台任务、日志、指标与图表 |
| `/experiments` | 实验记录 | 比较运行、报告/指标链接 |
| `/documents` | 项目文档 | 14 份 DOCX/PDF 下载 |
| `/system` | 系统状态 | 环境、API、任务、数据边界 |

**旧版页面已下线**：`/experiment`（现场实验固定量表）与 `/responses`（旧版统计页）均 302 跳转到 `/survey-data`。前者带 `?session=...` 时会解析会话归属问卷并直达该轮答卷详情。会话 JSON 与旧版只读 API 保留，用于回溯历史数据，但不再提供任何新建现场实验的界面入口。

### 模块地图（V0.7 骨架重排）

`main.py` 负责应用装配和启动时的数据库迁移。业务接口由对应域的 router 提供。

| 文件 | 职责 |
|---|---|
| `config.py` | 唯一配置源：目录（转发 `eeg_emostudio/paths.py`）、host/port/token、按 mtime 签名的进程内缓存 |
| `db.py`、`db_schema/` | SQLite 事务、连接和版本化表结构 |
| `common.py` | 模板环境、`render()`、任务序列化、Range 媒体响应、CSV 下载、问卷读取 |
| `schemas.py` | 全部请求体模型（`schema` 字段用 alias 规避 Pydantic 内置方法冲突） |
| `routers/core.py` | 工作台、系统状态、任务查询 |
| `routers/survey.py` | 问卷管理、量表版本、答卷与元数据、历史 CSV 导入 |
| `routers/public_survey.py` | 被试端填答与作答回看（公开，不校验令牌） |
| `routers/experiment.py` | 旧版现场会话存储与媒体播放（兼容层） |
| `routers/media.py` | 素材库浏览、预览、同步 |
| `routers/prep.py` | 质量审计与平衡选材（一次性制备） |
| `routers/datasets.py` | EEG 上传清洗、特征、数据集、训练、实验记录 |
| `routers/files.py` | 全部下载出口（白名单校验） |

路径统一由 `eeg_emostudio/paths.py` 定义，`webapp/config.py` 只做别名。改数据目录不再需要逐个模块改常量。

API 文档：`/api/swagger`。  
核心 API：`/api/overview`、`/api/surveys`、`/api/surveys/{id}/responses`、`/api/surveys/{id}/responses/{rid}`、`/api/media`、`/api/public/surveys/{token}`、`/api/experiment/responses`（旧版兼容）、`/api/eeg/uploads`、`/api/eeg/process`、`/api/datasets`、`/api/datasets/merge`、`/api/experiments`、`/api/jobs/{id}`。

任务在进程内线程池运行，任务状态和日志写入 SQLite。训练和特征任务继续调用现有 CLI 子进程。

## 本地 SQLite

缺省数据库为 `data/emostudio.sqlite3`，可用 `EEG_DB_PATH` 指向另一个本地文件。每次连接启用外键，使用 WAL 支持后台任务写入日志时继续查询。核心字段通过独立列和索引查询，变化较大的量表快照、答案内容和模型参数使用表内 JSON 保留原结构。

| 数据 | SQLite 中的记录 | 保留在磁盘的文件 |
|---|---|---|
| 问卷与实验采集 | 问卷、会话、答卷、导入批次及暂存元数据 | 导入源 CSV、历史 JSON/JSONL |
| 素材库 | 文件标识、模态、路径、评分信息与同步状态 | 音视频、原始来源表 |
| 数据集与 EEG | 数据集目录及模态、上传记录、信号与特征文件索引 | 发布包、MAT、SET、NPZ、处理报告及 manifests |
| 作业与模型实验 | 后台任务、日志、外部训练观测、实验索引和指标快照 | 检查点、图表、可独立复查的 JSON/HTML 报告与 CLI 进度文件 |
| 记录管理 | 标签、备注、软删除、上传登记、审计事件 | 原始资源文件 |
| 用户与认证 | `users`、`auth_sessions` | 暂无登录或注册入口 |

启动时自动创建数据库并迁移历史记录。每个业务域记录迁移进度，重复启动不会追加重复记录，也不会用旧 JSON 覆盖后续修改。原文件保留用于追溯。外部 CLI 或 DDA 产生新报告后，实验索引按文件签名更新。

在项目根目录可运行 `python -m webapp.migrate` 预先迁移，并查看完整性检查和各表记录数。SQLite 启用 WAL 后，运行期间使用 SQLite 备份接口生成一致的备份文件。离线备份可在停止服务后复制数据库，并另外备份原始媒体、数据文件和科研产物。

后续注册表单预留用户名、邮箱、显示名、密码和确认密码，登录表单预留用户名或邮箱与密码。账户表包含密码哈希、角色、状态及验证时间。确认密码仅用于校验，密码明文不入库。会话表预留令牌哈希、到期和撤销时间。现有管理端令牌机制与公开问卷访问方式继续生效。

## 问卷 schema 与元数据管理（V0.6）

问卷可自定义题目，历史问卷星 CSV 可导入并纳入统一管理。

**源文件与迁移目录**（业务记录迁入 SQLite，旧文件留作追溯）

```text
data/surveys/{survey_id}.json                 旧问卷定义
data/survey_responses/{survey_id}.jsonl       旧答卷记录
data/survey_imports/{batch_id}.json           旧导入批次登记
data/survey_imports/{batch_id}.source.csv     原始导出副本，按原始行号回查
data/survey_imports/_staging/                 两步导入的暂存区
data/experiment/sessions/                    旧会话及固定量表答卷
```

**题目 schema**：`webapp/questionnaire.py` 定义 5 种题型（text / rating / single / multiple / textarea）。每题可标注 `role`（rater、stimulus、valence、arousal、clarity、emotion、coverage、stability、familiarity、comprehension、issues、other 等），带角色的列才能参与归一化与质量评分；归一化复用 `eeg_emostudio/audit/normalize.py`，不重复实现清洗规则。内置视频/音乐两套 12 题标准量表，与既有问卷星导出逐列对应。

**版本化**：问卷保存 `schema_version` + `schema_hash`，改题时自动把旧量表压入 `schema_history` 并升版本；每份答卷记录当时的版本与指纹，因此修改量表后历史答卷仍可追溯。

**答卷元数据**：序号、提交时间、用时、来源、来源详情、IP 地区、IP 不可逆哈希、总分、评分者、素材编号（原始+归一）、批次、原始行号、逐题原始答案、按 role 归一化的值、有效性标记。**原始 IP 不落盘**。

**两步导入**：`POST /api/surveys/import/preview` 上传原始 CSV 字节（自动识别 UTF-8 BOM / GB18030 / UTF-16），按「题干关键词 + 取值形态」推断题型与字段映射并返回预览；`POST /api/surveys/import/commit` 确认后落盘。多选题按问卷星 `┋` 分隔符还原，文字锚点（`非常不愉快` 等）按既有规则转 1–9，同评分者 × 素材的重复只标记不删除。

**导出**：`responses.csv` 为问卷星兼容格式（7 个平台列 + 题目列、UTF-8 BOM，可与历史数据直接合并）；`responses.clean.csv` 为分析宽表（元数据列 + 每个 role 一列）。

**查看答卷**：`/survey-data?survey_id=X&tab=responses` 列出答卷，点「查看答卷」展开逐题的原始作答与归一化值，并可下载单份 JSON。支持 `response_id` 深链与 `session_id` 过滤；`/experiment?session=<id>` 会自动重定向到对应问卷的该轮答卷。被试完成一轮后，公开页「查看本轮作答」按会话回看自己的逐题答案（不会跨会话读取）。

**新增 API**：`/api/questionnaire/templates`、`/api/surveys/{id}/schema|metadata|quality|responses|responses/{response_id}|responses.csv|responses.clean.csv`、`/api/surveys/import/preview|commit`、`/api/surveys/imports`、`/api/surveys/imports/{batch}/source.csv`、`/api/public/surveys/{token}/sessions/{id}/answers|result`。

旧版固定量表问卷（无 `schema` 字段）仍走原有 `submit_response` 通道，公开页会自动回退到固定表单，历史会话数据可通过 `/api/experiment/responses.csv` 导出。
