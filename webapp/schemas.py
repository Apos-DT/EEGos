"""请求体模型（对外契约）。

集中放在一处而不是散在路由文件里，原因有两个：
1. 同一份契约会被多个路由复用（例如 ``ExperimentResponseRequest`` 同时服务旧版
   现场通道与新版公开问卷通道），分散定义会写出两份不一致的 schema。
2. Pydantic 校验规则是接口文档的一部分，集中便于对照 docs 与前端。

注意：``schema`` 是 ``BaseModel`` 的内置方法名，问卷字段一律用
``Field(alias="schema")`` + ``populate_by_name`` 接收，否则会遮蔽内置属性。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExperimentCreateRequest(BaseModel):
    participant_code: str = Field(..., min_length=1, max_length=64)
    limit: int = Field(8, ge=1, le=40)
    age: int | None = Field(None, ge=10, le=100)
    gender: str = Field("", max_length=24)
    consent: bool = True
    note: str = Field("", max_length=500)
    sleep_hours: float | None = Field(None, ge=0, le=24)
    fatigue: int | None = Field(None, ge=1, le=5)
    mood: int | None = Field(None, ge=1, le=9)


class ExperimentResponseRequest(BaseModel):
    valence: int = Field(..., ge=1, le=9)
    arousal: int = Field(..., ge=1, le=9)
    discrete: str = Field(..., min_length=1, max_length=24)
    intensity: int = Field(..., ge=1, le=5)
    familiarity: int = Field(..., ge=1, le=5)
    previous_viewed: bool = False
    watch_seconds: int = Field(0, ge=0, le=86400)
    note: str = Field("", max_length=500)


class SurveyCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=1000)
    material_ids: list[str] = Field(..., min_length=1, max_length=240)
    require_code: bool = True
    allow_multiple: bool = True
    kind: str = Field("", max_length=16)
    questions: list[dict[str, Any]] | None = Field(default=None, alias="schema")
    target_n: int = Field(0, ge=0, le=100000)


class SurveyUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=1000)
    material_ids: list[str] | None = None
    questions: list[dict[str, Any]] | None = Field(default=None, alias="schema")
    target_n: int | None = Field(None, ge=0, le=100000)
    require_code: bool | None = None
    allow_multiple: bool | None = None
    # 切换视频/音乐标准量表时必须同步落盘，否则刺激编号会按旧模态归一化
    kind: str = Field("", max_length=16)


class SchemaAnswersRequest(BaseModel):
    answers: dict[str, Any]
    watch_seconds: int = Field(0, ge=0, le=86400)


class ImportCommitRequest(BaseModel):
    staging_id: str = Field(..., min_length=1, max_length=128)
    survey_id: str = ""
    title: str = Field("", max_length=120)
    description: str = Field("", max_length=1000)
    mark_duplicates: bool = True


class PublicStartRequest(BaseModel):
    participant_code: str = Field(..., min_length=1, max_length=64)
    age: int | None = Field(None, ge=10, le=100)
    gender: str = Field("", max_length=24)
    sleep_hours: float | None = Field(None, ge=0, le=24)
    fatigue: int | None = Field(None, ge=1, le=5)
    mood: int | None = Field(None, ge=1, le=9)
    consent: bool = True


class EEGProcessRequest(BaseModel):
    upload_id: str
    subject: str = Field("", max_length=64)
    bandpass_low: float = Field(0.1, ge=0.1, le=45)
    bandpass_high: float = Field(70.0, ge=1, le=100)
    notch: float = Field(50.0, ge=0, le=120)
    target_fs: float = Field(200.0, ge=0, le=5000)
    reref: str = Field("car", pattern="^(none|car)$")
    epoch_start: float = Field(-0.2, ge=-5, le=0)
    epoch_end: float = Field(4.0, ge=0.5, le=20)
    reject: float = Field(150.0, ge=1, le=2000)
    event_map: str = Field("1=0,2=1,3=2,4=3", max_length=200)
    window: float = Field(1.0, ge=0.2, le=10)
    ica: bool = False


class AuditRequest(BaseModel):
    probe_media: bool = False


class SelectionRequest(BaseModel):
    per_class: int = Field(10, ge=1, le=50)
    min_grade: str = Field("D", pattern="^[SABCD]$")
    modalities: list[str] = Field(default_factory=lambda: ["video", "audio"])


class FeatureRequest(BaseModel):
    raw_id: str
    fs: float | None = Field(None, gt=0, le=5000)
    target_fs: float | None = Field(None, gt=0, le=5000)
    window: float = Field(1.0, gt=0, le=60)
    step: float | None = Field(None, gt=0, le=60)
    aggregate: str = Field("mean", pattern="^(mean|std|concat)$")
    notch: float | None = Field(50.0, ge=0, le=120)


class MergeRequest(BaseModel):
    dataset_ids: list[str] = Field(..., min_length=2, max_length=50)


class TrainRequest(BaseModel):
    dataset_id: str
    model: str = "dualview"
    setting: str = "loso"
    epochs: int = Field(40, ge=1, le=300)
    batch_size: int = Field(32, ge=1, le=512)
    lr: float = Field(1e-3, gt=0, le=1)
    seed: int = Field(42, ge=0, le=2**31 - 1)
    hidden: int = Field(32, ge=4, le=256)
    dropout: float = Field(0.25, ge=0, le=0.9)
    prototypes: int = Field(2, ge=1, le=12)
    proto_weight: float = Field(0.1, ge=0, le=10)


class DDARequest(BaseModel):
    """Run configuration for the separately installed DDA sidecar."""

    setting: str = Field("cross-subject", pattern="^(cross-subject|cross-session)$")
    algorithm: str = Field("UDDA", pattern="^(UDDA|SDDA)$")
    epochs: int = Field(600, ge=1, le=600)
    seed: int = Field(42, ge=0, le=2**31 - 1)
    target_labeled_trials: int = Field(4, ge=0, le=24)
    target_subject: str | None = Field(None, pattern="^S(0[1-9]|1[0-5])$")
    target_session: str | None = Field(None, pattern="^[1-3]$")
    max_folds: int = Field(0, ge=0, le=90)
    batch_size: int = Field(30, ge=2, le=512)
    lr: float = Field(0.001, gt=0, le=1)
    beta: float = Field(0.3, ge=0, le=10)
    pseudo_threshold: float = Field(0.75, ge=0, le=1)
    eval_interval: int = Field(10, ge=1, le=600)
