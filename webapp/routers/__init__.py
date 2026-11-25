"""路由包：按业务域拆分，注册顺序即匹配顺序。

原先把 85 条路由全部堆在 ``main.py``（1333 行）里，改一个问卷接口要在
上千行里找。现在按「谁改谁」归并：

- :mod:`.core`           工作台首页、系统状态、任务查询
- :mod:`.dashboard_queue` 工作台实时任务、日志与受管任务终止
- :mod:`.survey`         问卷管理、答卷数据与元数据、历史导入
- :mod:`.public_survey`  被试端填答与作答回看（无需登录）
- :mod:`.experiment`     旧版现场会话存储（兼容层，只读为主）
- :mod:`.media`          素材库浏览、预览、同步
- :mod:`.prep`           质量审计与平衡选材（一次性制备）
- :mod:`.datasets`       EEG 上传清洗、特征、训练、实验记录
- :mod:`.files`          全部文件下载出口（白名单校验）

新增接口时先想清楚属于哪个域；跨域的就说明域边界没划对。
"""

from __future__ import annotations

from fastapi import APIRouter

from . import account, core, dashboard_queue, datasets, dda, experiment, files, media, prep, public_survey, raw_eeg, records, survey

# 顺序有意义：先注册的优先匹配。同一前缀下「字面量」路由必须早于「参数化」路由。
ALL_ROUTERS: list[APIRouter] = [
    account.router,
    core.router,
    dashboard_queue.router,
    survey.router,
    public_survey.router,
    experiment.router,
    media.router,
    prep.router,
    datasets.router,
    raw_eeg.router,
    dda.router,
    files.router,
    records.router,
]
