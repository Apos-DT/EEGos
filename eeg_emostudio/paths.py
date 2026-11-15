"""项目路径的唯一来源。

分层约定
--------
* 本模块**不依赖任何交付层代码**（不 import FastAPI / Jinja2），因此核心算法包
  与 Web 控制台都能安全引用，不会出现 ``webapp -> eeg_emostudio -> webapp`` 的
  反向依赖。
* Web 运行参数（host / port / access token）不在这里，见 ``webapp/config.py``。
* 所有目录可用环境变量覆盖，便于把大数据目录挂到外部磁盘或容器卷：

  - ``EEG_DATA_DIR``：原始/中间数据（默认 ``<repo>/data``）
  - ``EEG_ARTIFACTS_DIR``：运行产物（默认 ``<repo>/artifacts``）
  - ``EEG_DELIVERABLES_DIR``：交付文档（默认 ``<repo>/deliverables``）

历史上 ``ROOT / "data" / ...`` 这类字面量散落在 webapp 的 9 个模块里，
改一次目录要改十几处；现在统一收敛到此文件。
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent

__all__ = [
    "PACKAGE_ROOT",
    "PROJECT_ROOT",
    "DATA_DIR",
    "ARTIFACTS_DIR",
    "DELIVERABLES_DIR",
    "RESEARCH_DIR",
    "RAW_STIMULI_DIR",
    "MEDIA_DIR",
    "VIDEO_DIR",
    "AUDIO_DIR",
    "MEDIA_MANIFEST",
    "SURVEYS_DIR",
    "SURVEY_RESPONSES_DIR",
    "SURVEY_IMPORTS_DIR",
    "SURVEY_STAGING_DIR",
    "EXPERIMENT_DIR",
    "SESSIONS_DIR",
    "EEG_UPLOAD_DIR",
    "RAW_DIR",
    "PROCESSED_DIR",
    "UPLOADS_DIR",
    "SEED_IV_DIR",
    "AUDIT_DIR",
    "AUDIT_PROBE_DIR",
    "SELECTION_DIR",
    "EXPERIMENTS_DIR",
    "WEB_JOBS_DIR",
    "EEG_OUTPUT_DIR",
    "SELECTED_MATERIALS_CSV",
    "QUALITY_RELATIVE",
    "QUALITY_FILES",
    "ensure_dirs",
]


def _resolve(env_name: str, default: Path) -> Path:
    raw = os.environ.get(env_name, "").strip()
    return Path(raw).expanduser().resolve() if raw else default


# --- 顶层三棵树 -----------------------------------------------------------
DATA_DIR = _resolve("EEG_DATA_DIR", PROJECT_ROOT / "data")
ARTIFACTS_DIR = _resolve("EEG_ARTIFACTS_DIR", PROJECT_ROOT / "artifacts")
DELIVERABLES_DIR = _resolve("EEG_DELIVERABLES_DIR", PROJECT_ROOT / "deliverables")

RESEARCH_DIR = PROJECT_ROOT / "research"
# 原始刺激素材，按项目约定不移动、不改名（且被 .gitignore 排除）
RAW_STIMULI_DIR = PROJECT_ROOT / "山科数据集"

# --- 素材库 ---------------------------------------------------------------
MEDIA_DIR = DATA_DIR / "media"
VIDEO_DIR = MEDIA_DIR / "video"
AUDIO_DIR = MEDIA_DIR / "audio"
MEDIA_MANIFEST = MEDIA_DIR / "manifest.json"

# --- 问卷 ---------------------------------------------------------------
SURVEYS_DIR = DATA_DIR / "surveys"
SURVEY_RESPONSES_DIR = DATA_DIR / "survey_responses"
SURVEY_IMPORTS_DIR = DATA_DIR / "survey_imports"
SURVEY_STAGING_DIR = SURVEY_IMPORTS_DIR / "_staging"

# --- 实验会话（新版问卷与旧版现场实验共用） -------------------------------
EXPERIMENT_DIR = DATA_DIR / "experiment"
SESSIONS_DIR = EXPERIMENT_DIR / "sessions"

# --- EEG 与数据集 ---------------------------------------------------------
EEG_UPLOAD_DIR = DATA_DIR / "eeg_uploads"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
UPLOADS_DIR = DATA_DIR / "uploads"
SEED_IV_DIR = DATA_DIR / "SEED_IV"

# --- 运行产物 -------------------------------------------------------------
AUDIT_DIR = ARTIFACTS_DIR / "audit"
AUDIT_PROBE_DIR = ARTIFACTS_DIR / "audit_probe"
SELECTION_DIR = ARTIFACTS_DIR / "selection"
EXPERIMENTS_DIR = ARTIFACTS_DIR / "experiments"
WEB_JOBS_DIR = ARTIFACTS_DIR / "web_jobs"
EEG_OUTPUT_DIR = ARTIFACTS_DIR / "eeg"
SELECTED_MATERIALS_CSV = SELECTION_DIR / "selected_materials.csv"

# --- 研究输入：素材质量排序 -------------------------------------------------
# 相对仓库根的路径（CLI / 审计脚本按 workspace 相对定位时使用同一份定义）
QUALITY_RELATIVE = {
    "video": "research/quality/video/视频质量排序.csv",
    "audio": "research/quality/audio/音乐歌曲质量排序.csv",
}
QUALITY_FILES = {kind: PROJECT_ROOT / rel for kind, rel in QUALITY_RELATIVE.items()}

# 初次启动时按需创建，避免各模块各自 mkdir
_RUNTIME_DIRS = (
    DATA_DIR,
    MEDIA_DIR,
    SURVEYS_DIR,
    SURVEY_RESPONSES_DIR,
    SURVEY_IMPORTS_DIR,
    SESSIONS_DIR,
    EEG_UPLOAD_DIR,
    RAW_DIR,
    PROCESSED_DIR,
    UPLOADS_DIR,
    ARTIFACTS_DIR,
    AUDIT_DIR,
    SELECTION_DIR,
    EXPERIMENTS_DIR,
    WEB_JOBS_DIR,
    EEG_OUTPUT_DIR,
)


def ensure_dirs() -> None:
    """幂等创建运行所需目录；权限不足时静默跳过（只读挂载场景）。"""

    for directory in _RUNTIME_DIRS:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
