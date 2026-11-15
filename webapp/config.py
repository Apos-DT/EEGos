"""Web 层配置：路径来源 + 运行参数 + 进程内缓存。

设计要点
--------
1. **路径不重复定义**：所有目录来自 :mod:`eeg_emostudio.paths`，这里只做 Web 层的
   别名与再导出，保证 CLI、审计脚本、Web 控制台看到的是同一套路径。
2. **运行参数集中**：host / port / token / reload 只在这里读环境变量，避免散落在
   ``__main__`` 与各路由里。
3. **缓存很薄**：研究场景是「读多写少 + 单机单用户」，一个带 mtime 签名的进程内
   字典即可，不引入 Redis/磁盘缓存。写操作调用 :func:`invalidate` 精确失效。
"""

from __future__ import annotations

import copy
import fnmatch
import functools
import os
import time
from pathlib import Path
from stat import S_ISDIR
from threading import Lock
from typing import Any, Callable, Iterable, TypeVar

from eeg_emostudio import paths

T = TypeVar("T")

# --- 路径别名（沿用 webapp 内部既有名称，减少改动面） ----------------------
ROOT = paths.PROJECT_ROOT
DATA_DIR = paths.DATA_DIR
ARTIFACTS = paths.ARTIFACTS_DIR
DELIVERABLES_DIR = paths.DELIVERABLES_DIR

MEDIA_DIR = paths.MEDIA_DIR
VIDEO_DIR = paths.VIDEO_DIR
AUDIO_DIR = paths.AUDIO_DIR
MANIFEST = paths.MEDIA_MANIFEST

SURVEYS_DIR = paths.SURVEYS_DIR
RESPONSES_DIR = paths.SURVEY_RESPONSES_DIR
IMPORTS_DIR = paths.SURVEY_IMPORTS_DIR
STAGING_DIR = paths.SURVEY_STAGING_DIR

EXPERIMENT_DIR = paths.EXPERIMENT_DIR
SESSIONS_DIR = paths.SESSIONS_DIR

EEG_UPLOAD_DIR = paths.EEG_UPLOAD_DIR
UPLOAD_DIR = paths.UPLOADS_DIR
RAW_DIR = paths.RAW_DIR
PROCESSED_DIR = paths.PROCESSED_DIR
SEED_IV_DIR = paths.SEED_IV_DIR

AUDIT_DIR = paths.AUDIT_DIR
AUDIT_PROBE_DIR = paths.AUDIT_PROBE_DIR
SELECTION_DIR = paths.SELECTION_DIR
EXPERIMENTS_DIR = paths.EXPERIMENTS_DIR
WEB_JOBS_DIR = paths.WEB_JOBS_DIR
OUTPUT_DIR = paths.EEG_OUTPUT_DIR
SELECTION_CSV = paths.SELECTED_MATERIALS_CSV
SELECTED = paths.SELECTED_MATERIALS_CSV
QUALITY = paths.QUALITY_FILES

# 原始刺激源（不作为 git 内容，按约定不移动）
SOURCE_VIDEO_CANDIDATES = [
    paths.RAW_STIMULI_DIR / "视频压缩v2",
    paths.RAW_STIMULI_DIR / "VIDEOS" / "视频压缩v2",
]
SOURCE_AUDIO_CANDIDATES = [
    paths.RAW_STIMULI_DIR / "音乐测试v2",
    paths.RAW_STIMULI_DIR / "音乐测试v2" / "音乐测试v2",
]
MAPPING = {
    "video": paths.RAW_STIMULI_DIR / "视频对应关系.csv",
    "audio": paths.RAW_STIMULI_DIR / "音乐对应关系.csv",
}

# --- 运行参数 -------------------------------------------------------------
# 默认监听 0.0.0.0：被试扫码填答必须局域网可达，改成 127.0.0.1 会让已经发出的
# 分享链接直接失效，中断正在进行的采集。
# 代价是管理端也暴露在同网段：因此设置 EEG_WEB_TOKEN 后，除被试端（/q、
# /api/public）与健康检查外，所有页面和 API 都要求令牌。正式采集务必设置。
WEB_HOST = os.environ.get("EEG_WEB_HOST", "0.0.0.0").strip() or "0.0.0.0"
WEB_PORT = int(os.environ.get("EEG_WEB_PORT", "8770"))
WEB_RELOAD = os.environ.get("EEG_WEB_RELOAD", "0").strip().lower() in {"1", "true", "yes", "on"}
# 为空表示不校验；公开问卷路径（/q、/api/public）永远不校验。
ACCESS_TOKEN = os.environ.get("EEG_WEB_TOKEN", "").strip()
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

paths.ensure_dirs()


# --- 缓存 -----------------------------------------------------------------
_CACHE: dict[str, tuple[Any, Any]] = {}
_CACHE_LOCK = Lock()


def fingerprint(targets: Iterable[Path], pattern: str = "*") -> tuple[Any, ...]:
    """生成目录/文件的内容签名。

    对每个目标：文件取 (mtime_ns, size)；目录取其下 ``pattern`` 匹配项的
    (数量, 最大 mtime_ns, 总字节)。任何新增、删除、追加写入都会改变签名。

    实现上有意使用 ``os.scandir`` 而不是 ``Path.glob``：在 120 个文件的目录上
    glob + stat 约 7 ms，scandir + stat 约 0.24 ms。缓存本身很便宜，如果签名
    计算比重复读取还慢，缓存就白加了——这一点实测踩过。
    """

    parts: list[Any] = []
    for raw in targets:
        target = Path(raw)
        try:
            st = target.stat()
        except OSError:
            parts.append((str(target), "missing"))
            continue
        if not S_ISDIR(st.st_mode):
            parts.append((str(target), st.st_mtime_ns, st.st_size))
            continue
        count = 0
        newest = 0
        total = 0
        try:
            with os.scandir(target) as entries:
                for entry in entries:
                    if pattern != "*" and not fnmatch.fnmatch(entry.name, pattern):
                        continue
                    try:
                        if not entry.is_file():
                            continue
                        info = entry.stat()
                    except OSError:
                        continue
                    count += 1
                    if info.st_mtime_ns > newest:
                        newest = info.st_mtime_ns
                    total += info.st_size
        except OSError:
            pass
        # 目录自身的 mtime 也纳入：删除/新增条目会改变它，即使个别 stat 失败
        parts.append((str(target), count, newest, total, st.st_mtime_ns))
    return tuple(parts)


def cached(namespace: str, signature: Any, loader: Callable[[], T]) -> T:
    """签名未变则复用上次结果；签名变化则重新计算并覆盖。

    缓存内保存的是**深拷贝**：有些调用方会原地改写返回的行（例如
    ``stimuli_payload`` 会给 ``selection_payload`` 的行补 ``available`` 字段），
    直接共享对象会让改动渗进缓存，越调越脏。
    """

    with _CACHE_LOCK:
        entry = _CACHE.get(namespace)
        if entry is not None and entry[0] == signature:
            return copy.deepcopy(entry[1])  # type: ignore[return-value]
    value = loader()
    with _CACHE_LOCK:
        _CACHE[namespace] = (signature, copy.deepcopy(value))
    return value


def cache_by(namespace: str, *targets: Any, pattern: str = "*") -> Callable[[Callable[..., T]], Callable[..., T]]:
    """按目录签名缓存只读聚合函数。

    ``targets`` 可以是 ``Path``，也可以是返回 ``Path`` 的**可调用对象**。
    传 lambda 而不是直接传 Path 是有意的：测试会把仓库目录指到临时目录，
    装饰时求值会把旧路径固化进闭包，缓存就会永远读错地方。
    """

    def decorate(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def inner(*args: Any, **kwargs: Any) -> T:
            resolved: list[Path] = []
            for spec in targets:
                value = spec() if callable(spec) else spec
                if isinstance(value, (list, tuple, set)):
                    resolved.extend(Path(item) for item in value)
                else:
                    resolved.append(Path(value))
            key = namespace if not args and not kwargs else f"{namespace}|{args!r}|{sorted(kwargs.items())!r}"
            return cached(key, fingerprint(resolved, pattern), lambda: fn(*args, **kwargs))

        inner.cache_namespace = namespace  # type: ignore[attr-defined]
        return inner

    return decorate


def invalidate(*namespaces: str) -> None:
    """精确失效；不传则全部清空。"""

    with _CACHE_LOCK:
        if not namespaces:
            _CACHE.clear()
            return
        for name in namespaces:
            _CACHE.pop(name, None)


def cache_stats() -> dict[str, Any]:
    """供 /api/system 观测缓存规模。"""

    with _CACHE_LOCK:
        keys = sorted(_CACHE)
    return {"entries": len(keys), "keys": keys}
