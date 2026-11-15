# Web 系统设计与使用说明

**项目**：EEG-EmoStudio 脑电情绪识别数据制备与模型训练工作台  
**文档编号**：15  
**版本**：V1.0  
**日期**：2026-11-07  
**定位**：在 CLI 原型之上增加完整前后端，形成可直接演示、可日常使用的本地科研控制台。

---

## 1. 目标与边界

### 1.1 目标

- 研究者不需要记命令，就能完成“审计 → 选材 → 上传/特征 → 训练 → 看报告”；
- 每个页面都能看到真实数据、真实状态和下一步动作，而不是静态占位；
- 训练/特征等长任务可离开页面、后台执行、回来查看日志与结果；
- 全部资源本地化，不依赖 CDN、云服务或外部数据库；
- 保持 CLI 与 Web 共用同一套数据/算法，避免“页面一套、论文一套”。

### 1.2 不做什么

- 不做多用户/权限系统（V1.0 单机、单研究者）；
- 不做公网部署；默认只监听 `127.0.0.1`；
- 主界面不依赖 CDN；`/api/swagger` 使用 FastAPI 默认模板（离线时仅影响 API 文档页）。
- 不做在线 EEG 实时推理；
- 不替代伦理审批、设备驱动、版权清理。

---

## 2. 信息架构

```text
工作台 /                 三域入口、资产与流水线
实验
  问卷管理 /surveys          选素材、自定义题目、生成分享链接、编辑/关闭
  问卷数据 /survey-data      逐题答卷查看、元数据、质量诊断、导入导出
  素材库 /media              240 条视频/音乐、同步、预览、筛选
  被试端 /q/{token}          打开链接、播放素材、填写问卷、回看本轮作答
EEG 信号
  原始 EEG 处理 /eeg       EEGLAB 上传、滤波/ICA/分段/DE
  数据集与特征 /datasets     raw.npz、特征集、manifest
模型训练
  模型训练 /training        模型/设置/超参、后台任务、日志、指标
  实验记录 /experiments     运行比较、报告、metrics.json
系统
  项目文档 /documents       14 份 DOCX/PDF、打包下载
  系统状态 /system          Python/平台、API、任务、数据边界
  历史预评价 /audit         一次性数据制备归档（不在主导航）
```

> 旧版「现场实验」`/experiment` 与「实验问卷」`/responses` 页面已下线，均重定向到
> `/survey-data`；带 `?session=<id>` 访问时定位到该轮答卷详情。会话 JSON、旧版
> 只读 API 与 CSV 导出保留用于历史数据回溯，但不再提供新建现场实验的界面入口。

### 2.1 视觉语言

- 深海军蓝侧栏 + 青绿色强调色，传达“实验室/可信数据”；
- 内容区浅灰蓝背景，白色卡片、18 px 圆角、轻阴影；
- 关键状态使用 S/A/B/C/D 色阶、红/琥珀/蓝提示；
- 所有页面统一顶栏、面包屑、页脚免责声明；
- 响应式：≥1180 px 双栏，920 px 以下抽屉式导航，560 px 单栏。

### 2.2 交互原则

- 每个页面只有一个主行动（Primary）；
- 危险/边界信息用琥珀/红色提示，不藏在帮助页；
- 长任务显示实时日志与进度，失败给出可操作错误；
- 表格支持搜索与标签筛选，避免“翻 240 行”；
- 图表使用原生 SVG，无外部库，悬停显示数值。

---

## 3. 技术架构

```text
Browser
  ├── Jinja2 服务端渲染（首屏、表格、卡片）
  ├── 原生 CSS 设计系统（webapp/static/css/app.css）
  └── 原生 JS：API、轮询、任务控制台、SVG 图表
        │ fetch / JSON
FastAPI (webapp/main.py)
  ├── 页面路由（11 个，含工作台）
  ├── 只读 API（overview/audit/selection/datasets/experiments/docs/jobs）
  ├── 写入 API（audit/selection/features/train/upload）
  ├── 文件下载（DOCX/PDF/审计 CSV/打包 ZIP）
  └── JobManager（线程池 + 子进程）
        │ subprocess
现有 CLI：eeg_emostudio eeglab/audit/select/features/train；实验会话由 webapp/experiment.py 管理
        │
artifacts/、data/、deliverables/（同一套事实源）
```

### 3.1 为什么不用 React

- 页面以数据展示/表单/表格为主，Jinja2 首屏更快；
- 无需 Node 构建链，答辩现场 `python -m webapp` 即可；
- 无 CDN 依赖，离线可用；
- 复杂交互（任务轮询、图表、筛选）用少量原生 JS 足够。

### 3.2 任务模型

```text
POST /api/{audit|selection|features|train}/run
  → JobManager.submit(kind, title, runner)
  → status: queued → running → success/failed
  → logs 追加，写 artifacts/web_jobs/{id}.json
GET /api/jobs/{id}
  → 前端每 1.4 s 轮询，更新控制台/进度/状态
```

- 训练与特征任务调用现有 CLI 子进程，保证与论文命令完全一致；
- 审计/选材任务同样走 CLI，避免 Web 层重写业务规则；
- 任务最多 2 个并发，避免 CPU 被打满；
- 失败保留最后 20 行 traceback 与完整日志尾部。

### 3.3 数据流

- 上传 `raw.npz` → `data/raw/`；
- 提取特征 → `data/processed/*_features.npz` + manifest；
- 训练 → `artifacts/experiments/{run_id}/`；
- 审计/选材 → `artifacts/audit/`、`artifacts/selection/`；
- 文档 → `deliverables/`，PDF 在 `deliverables/pdf/`。

---

## 4. API 契约（节选）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/overview` | 三大功能域统计、质量分布、流水线、最近实验 |
| GET/POST | `/api/surveys` | 问卷列表/创建问卷 |
| POST | `/api/surveys/{id}/toggle` | 开放/关闭分享链接 |
| GET | `/api/media` | 素材库（视频/音乐/纳管状态） |
| POST | `/api/media/sync` | 从源目录同步到 `data/media` |
| POST | `/api/public/surveys/{token}/sessions` | 被试打开链接后创建作答会话 |
| GET | `/q/{token}/media/{session_id}` | 被试端 Range 流式播放 |
| POST | `/api/public/surveys/{token}/sessions/{id}/answers` | 按 schema 提交逐题答卷（写入 JSONL） |
| GET | `/api/public/surveys/{token}/sessions/{id}/result` | 被试回看本轮逐题作答 |
| GET | `/api/surveys/{id}/responses` | 答卷列表（完整记录） |
| GET | `/api/surveys/{id}/responses/{response_id}` | 单份答卷详情 + 题目定义 |
| GET | `/api/surveys/{id}/metadata` / `/quality` | 元数据与质量诊断 |
| GET | `/api/surveys/{id}/responses.csv` / `/responses.clean.csv` | 问卷星兼容 / 分析宽表导出 |
| POST | `/api/experiment/sessions` | 旧版现场会话（仅保留 API 兼容，无界面入口） |
| GET | `/api/experiment/sessions/{id}` | 会话进度与当前视频 |
| POST | `/api/experiment/sessions/{id}/responses` | 旧版固定量表提交（兼容） |
| GET | `/api/experiment/responses.csv` | 导出旧版固定量表 CSV |
| POST | `/api/eeg/upload?filename=...` | 上传 `.set` 或 `.zip`，≤500 MB |
| POST | `/api/eeg/process` | EEGLAB 清洗/分段/DE → job |
| GET | `/api/eeg/uploads` | 最近 EEG 导入与状态 |
| GET | `/api/audit` | 审计摘要、评分者、播放问题、质量表 |
| POST | `/api/audit/run` | `{probe_media}` → job |
| GET | `/api/selection` | 选材清单、分组、等级 |
| POST | `/api/selection/run` | `{per_class,min_grade,modalities}` → job |
| POST | `/api/raw/upload?filename=...` | 原始 octet-stream，≤300 MB |
| GET | `/api/raw` | 原始数据列表 |
| POST | `/api/features/run` | `{raw_id,fs,target_fs,window,step,aggregate,notch}` → job |
| GET | `/api/datasets` | 特征集列表（形状/被试/类别/manifest） |
| POST | `/api/datasets/merge` | `{dataset_ids:[...]}` 合并多被试特征集 |
| POST | `/api/train/run` | `{dataset_id,model,setting,epochs,...}` → job |
| GET | `/api/jobs/{id}` | 状态、日志、结果 |
| GET | `/api/experiments` | 运行列表与最佳结果 |
| GET | `/api/experiments/{id}/report` | HTML 报告 |
| GET | `/files/docx/{no}` / `/files/pdf/{no}` | 文档下载 |
| GET | `/files/bundle` | DOCX+PDF+manifest 打包 |

Swagger：`/api/swagger`。

---

## 5. 页面验收

| 页面 | 必须可见 | 主操作 | 验收 |
|---|---|---|---|
| 工作台 | 三大功能域卡片、实验/问卷/EEG/训练统计、质量图、流水线 | 开始实验/处理 EEG | 数字与 API 一致 |
| 问卷管理 | 问卷列表、素材数、响应数、分享链接 | 新建/编辑/复制链接 | 公开链接可打开 |
| 被试端 | 被试编号、素材播放器、问卷表单、进度 | 开始/提交 | 视频/音频 Range 可播放、响应落盘 |
| 实验问卷 | 响应数、完成率、均值、会话/明细表 | 导出 CSV | CSV 字段与 JSON 一致 |
| 原始 EEG 处理 | 上传摘要、滤波/ICA/分段参数、预览 | 开始清洗 | 生成 clean/raw/features/report |
| 素材库 | 240 条视频/音乐、同步、预览、筛选 | 新建问卷 | 本地文件可播放 |
| 历史预评价审计 | 视频/音乐计数、22/29 问题、等级图、3 张表 | 运行审计 | 仅历史证据，不进入日常流程 |
| 数据集 | 上传、raw 列表、特征集、契约 | 上传/提特征 | 上传校验、manifest 生成 |
| 模型训练 | 模型/设置/超参、日志、4 指标、2 图 | 开始训练 | 任务成功、结果可视 |
| 实验记录 | 最佳、总数、对比图、运行表 | 新建训练 | 报告/JSON 可打开 |
| 项目文档 | 14 卡片、分类筛选、打包 | 打包下载 | DOCX/PDF 200 |
| 系统状态 | 环境、API、任务、边界 | 健康检查 | health 返回 ok |

---

## 6. 本地运行

```powershell
pip install -r requirements.txt
python -m webapp
# 打开 http://127.0.0.1:8770
```

- 端口占用：`$env:EEG_WEB_PORT=8771; python -m webapp`
- 只监听本机：默认 `127.0.0.1`；
- 测试：`python -m unittest discover -s tests -v`（36 项，含 Web 与问卷/素材测试）；
- 任务日志：`artifacts/web_jobs/`。

---

## 7. 安全、隐私与边界

- 默认仅本机访问，无公网暴露；
- 上传文件只接受 `raw.npz`，校验 `x/y/subjects` 与形状，≤300 MB；
- 下载文件使用白名单（审计/选材文件名、文档编号），避免路径遍历；
- 页面不渲染姓名/IP；报告只显示被试伪 ID；
- 合成 demo 在所有页面标注“仅软件验收”，不进入科研性能表；
- 原始 EEG 未接入时，工作台/系统页明确显示“阻断/未接入”。

---

## 8. 与毕业设计文档的关系

- 本文是 `02_软件需求规格说明书` FR-16（命令行）的 Web 扩展；
- 页面/接口/任务模型可作为论文“系统实现”章节的截图与说明；
- 测试结果并入 `09_测试计划与验收标准`（36 项）；
- 数据边界并入 `05_数据审计报告` 与 `08_数据字典`；
- 视觉设计不作为创新点，创新点仍是数据门控 + 双视角 + 多原型。

---

## 9. 后续

1. 真实 EEG 接入后，在 `/datasets` 上传并跑 `/training` 主实验；
2. 增加只读的“实验详情页”（当前用报告/JSON 链接）；
3. 增加多用户/权限与局域网部署说明（如需要）；
4. 增加 Playwright 端到端测试（当前环境无法启动浏览器，改用 TestClient + 手工检查）。
