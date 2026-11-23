"""Shareable questionnaire definitions built from the managed media library."""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime
from .record_store import managed
from . import record_store
from typing import Any

from .experiment import advance_session_record, load_session, public_session, submit_response
from .media import item_by_id, load_manifest, media_path
from .questionnaire import (
    QUESTION_TYPE_LABELS,
    QUESTION_TYPES,
    ROLES,
    default_schema,
    normalize_schema,
    schema_fingerprint,
    schema_for_survey,
    survey_kind,
)
from .config import ROOT
from .db import transaction
from . import survey_db


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _save(survey: dict[str, Any], *, conn=None) -> None:
    survey["updated_at"] = _now()
    if conn is not None:
        survey_db.save_survey(conn, survey)
    else:
        with transaction(write=True) as conn:
            survey_db.save_survey(conn, survey)


def _ordered(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Avoid adjacent same discrete labels while preserving chosen set."""

    pool = materials[:]
    ordered: list[dict[str, Any]] = []
    while pool:
        index = next(
            (i for i, item in enumerate(pool) if not ordered or item.get("discrete_label") != ordered[-1].get("discrete_label")),
            0,
        )
        ordered.append(pool.pop(index))
    return ordered


def infer_kind(survey: dict[str, Any]) -> str:
    """旧问卷没有 kind 字段时，按素材模态推断量表版本。"""

    return survey_kind(survey)


def get_schema(survey: dict[str, Any]) -> list[dict[str, Any]]:
    """读取题目定义；对旧版问卷惰性补默认量表，不改写历史文件。

    与 survey_meta 的写/导出侧共用 questionnaire.schema_for_survey，
    保证同一份旧问卷在所有端点拿到一致的题目定义。
    """

    return schema_for_survey(survey)


def _public(survey: dict[str, Any]) -> dict[str, Any]:
    status = survey.get("status", "open")
    status_label = {"open": "开放", "closed": "已关闭", "archived": "历史导入"}.get(status, status)
    sessions = survey_db.count_sessions(survey["id"])
    stored = survey_db.count_responses(survey["id"])
    return {
        "id": survey["id"],
        "token": survey["token"],
        "title": survey["title"],
        "description": survey.get("description", ""),
        "status": status,
        "status_label": status_label,
        "created_at": survey["created_at"],
        "updated_at": survey.get("updated_at", survey["created_at"]),
        "kind": infer_kind(survey),
        "origin": survey.get("origin", {"type": "local"}),
        "schema_version": int(survey.get("schema_version", 1) or 1),
        "n_questions": len(get_schema(survey)),
        "n_materials": len(survey.get("materials", [])),
        "n_video": sum(1 for item in survey.get("materials", []) if item.get("modality") == "video"),
        "n_audio": sum(1 for item in survey.get("materials", []) if item.get("modality") == "audio"),
        "n_sessions": sessions,
        "n_stored_responses": stored,
        "n_responses": sessions + stored,
        "public_path": f"/q/{survey['token']}",
        "materials": survey.get("materials", []),
    }


def _material_items(material_ids: list[str]) -> list[dict[str, Any]]:
    if not material_ids:
        raise ValueError("请选择至少一个素材")
    manifest = load_manifest(refresh=True)
    by_id = {item["id"]: item for item in manifest["items"]}
    items = []
    seen = set()
    for item_id in material_ids:
        if item_id in seen:
            continue
        item = by_id.get(item_id) or item_by_id(item_id)
        if not item:
            raise ValueError(f"素材不存在：{item_id}")
        if not item.get("available"):
            raise ValueError(f"素材文件缺失：{item_id}")
        seen.add(item_id)
        items.append(
            {
                "id": item["id"],
                "stimulus_id": item["filename"],
                "modality": item["modality"],
                "category": item.get("category", ""),
                "discrete_label": item.get("discrete_label", ""),
                "quality_score": item.get("quality_score") or 0,
                "grade": item.get("grade", ""),
            }
        )
    return _ordered(items)


def create_survey(
    title: str,
    description: str = "",
    material_ids: list[str] | None = None,
    require_code: bool = True,
    allow_multiple: bool = True,
    kind: str = "",
    schema: list[dict[str, Any]] | None = None,
    target_n: int = 0,
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise ValueError("请填写问卷标题")
    items = _material_items(material_ids or [])
    resolved_kind = kind if kind in {"video", "audio"} else (
        "audio" if items and all(item.get("modality") == "audio" for item in items) else "video"
    )
    questions = normalize_schema(schema) if schema is not None else default_schema(resolved_kind)
    if not questions:
        raise ValueError("问卷至少需要一道题")
    survey = {
        "id": f"Q{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}",
        "token": secrets.token_urlsafe(7),
        "title": title,
        "description": description.strip()[:1000],
        "created_at": _now(),
        "status": "open",
        "kind": resolved_kind,
        "settings": {"require_code": require_code, "allow_multiple": allow_multiple},
        "schema": questions,
        "schema_version": 1,
        "schema_hash": schema_fingerprint(questions),
        "schema_history": [],
        "target_n": max(0, int(target_n or 0)),
        "origin": {"type": "local"},
        "materials": items,
    }
    _save(survey)
    return _public(survey)


def create_survey_from_import(
    title: str,
    description: str,
    kind: str,
    schema: list[dict[str, Any]],
    source_filename: str,
    *, conn=None,
) -> dict[str, Any]:
    """为历史问卷星导出创建归档问卷（不绑定本地素材，不对外发布）。"""

    questions = normalize_schema(schema)
    survey = {
        "id": f"Q{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}",
        "token": secrets.token_urlsafe(7),
        "title": (title or "历史问卷导入").strip()[:120],
        "description": (description or "").strip()[:1000],
        "created_at": _now(),
        "status": "archived",
        "kind": kind,
        "settings": {"require_code": True, "allow_multiple": False},
        "schema": questions,
        "schema_version": 1,
        "schema_hash": schema_fingerprint(questions),
        "schema_history": [],
        "target_n": 0,
        "origin": {"type": "wjx_import", "filename": source_filename},
        "materials": [],
    }
    _save(survey, conn=conn)
    return survey


def update_survey(
    survey_id: str,
    title: str,
    description: str,
    material_ids: list[str] | None = None,
    schema: list[dict[str, Any]] | None = None,
    target_n: int | None = None,
    require_code: bool | None = None,
    allow_multiple: bool | None = None,
    kind: str = "",
) -> dict[str, Any]:
    materials = _material_items(material_ids) if material_ids is not None else None
    with transaction(write=True) as conn:
        survey = load_survey(survey_id, conn=conn)
        survey["title"] = title.strip() or survey["title"]
        survey["description"] = (description or "").strip()[:1000]
        if materials is not None:
            survey["materials"] = materials
        if kind in {"video", "audio"}:
            survey["kind"] = kind
        if target_n is not None:
            survey["target_n"] = max(0, int(target_n))
        settings = survey.get("settings", {})
        if require_code is not None:
            settings["require_code"] = bool(require_code)
        if allow_multiple is not None:
            settings["allow_multiple"] = bool(allow_multiple)
        survey["settings"] = settings
        if schema is not None:
            new_schema = normalize_schema(schema)
            if not new_schema:
                raise ValueError("问卷至少需要一道题")
            old_schema = get_schema(survey)
            if schema_fingerprint(new_schema) != survey.get("schema_hash", schema_fingerprint(old_schema)):
                history = list(survey.get("schema_history") or [])
                history.append({
                    "version": int(survey.get("schema_version", 1) or 1),
                    "schema_hash": survey.get("schema_hash") or schema_fingerprint(old_schema),
                    "schema": old_schema,
                    "retired_at": _now(),
                })
                survey["schema_history"] = history
                survey["schema_version"] = int(survey.get("schema_version", 1) or 1) + 1
                survey["schema"] = new_schema
                survey["schema_hash"] = schema_fingerprint(new_schema)
        # 旧问卷（无 schema 字段）在编辑时正式落盘当前量表，避免版本悬空
        survey.setdefault("schema", get_schema(survey))
        survey.setdefault("schema_hash", schema_fingerprint(survey["schema"]))
        survey.setdefault("schema_version", 1)
        survey.setdefault("kind", infer_kind(survey))
        _save(survey, conn=conn)
    return _public(survey)

def _settings(survey: dict[str, Any]) -> dict[str, Any]:
    settings = survey.get("settings", {})
    return {
        "require_code": bool(settings.get("require_code", True)),
        "allow_multiple": bool(settings.get("allow_multiple", True)),
    }


def load_survey(survey_id: str, *, conn=None) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", survey_id):
        raise ValueError("非法问卷 id")
    if conn is not None:
        survey = survey_db.get_survey(conn, survey_id)
    else:
        with transaction() as db:
            survey = survey_db.get_survey(db, survey_id)
    if survey is None:
        raise FileNotFoundError("问卷不存在")
    return survey


def survey_by_token(token: str) -> dict[str, Any]:
    survey = survey_db.get_survey_by_token(token)
    if survey is None or record_store.metadata("surveys", survey["id"]).get("deleted_at"):
        raise FileNotFoundError("问卷链接不存在")
    return survey


@managed("surveys", title_key="title")
def list_surveys() -> list[dict[str, Any]]:
    return [_public(survey) for survey in survey_db.list_surveys()]


def toggle_survey(survey_id: str) -> dict[str, Any]:
    with transaction(write=True) as conn:
        survey = load_survey(survey_id, conn=conn)
        status = survey.get("status", "open")
        # 历史导入问卷是归档证据，不等于「被关闭的在线问卷」，不能被重新发布。
        if status == "archived":
            raise ValueError("历史导入问卷不可重新开放，请另建问卷发布")
        survey["status"] = "closed" if status == "open" else "open"
        _save(survey, conn=conn)
    return _public(survey)


def start_response(
    token: str,
    participant_code: str,
    age: int | None = None,
    gender: str = "",
    sleep_hours: float | None = None,
    fatigue: int | None = None,
    mood: int | None = None,
    consent: bool = True,
) -> dict[str, Any]:
    survey = survey_by_token(token)
    if survey.get("status") == "archived":
        raise ValueError("历史导入问卷不接受新答卷")
    if survey.get("status") != "open":
        raise ValueError("问卷已关闭")
    code = re.sub(r"[^A-Za-z0-9_-]+", "", participant_code or "").strip()
    if not code and survey.get("settings", {}).get("require_code", True):
        raise ValueError("请填写被试编号")
    if not code:
        code = f"ANON-{uuid.uuid4().hex[:6]}"
    if not consent:
        raise ValueError("需要确认知情同意")
    session_id = f"E{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
    sequence = []
    for item in survey.get("materials", []):
        path = media_path(item["modality"], item["stimulus_id"])
        if not path:
            raise ValueError(f"素材文件缺失：{item['stimulus_id']}")
        sequence.append(
            {
                "stimulus_id": item["stimulus_id"],
                "modality": item["modality"],
                "category": item.get("category", ""),
                "discrete_label": item.get("discrete_label", ""),
                "quality_score": item.get("quality_score", 0),
                "grade": item.get("grade", ""),
                "path": str(path.relative_to(ROOT)),
            }
        )
    session = {
        "id": session_id,
        "survey_id": survey["id"],
        "survey_token": token,
        "survey_title": survey["title"],
        "participant_code": code,
        "pre_session": {
            "age": age,
            "gender": gender,
            "sleep_hours": sleep_hours,
            "fatigue": fatigue,
            "mood": mood,
        },
        "consent": True,
        "note": "",
        "created_at": _now(),
        "updated_at": _now(),
        "status": "running",
        "current_index": 0,
        "sequence": sequence,
        "responses": [],
    }
    with transaction(write=True) as conn:
        survey_db.save_session(conn, session)
    return public_session(session)


def validate_public_session(token: str, session_id: str) -> dict[str, Any]:
    survey = survey_by_token(token)
    session = load_session(session_id)
    if session.get("survey_id") != survey["id"] or session.get("survey_token") != token:
        raise ValueError("会话不属于该问卷")
    return session


def public_media(token: str, session_id: str) -> tuple[Path, str]:
    session = validate_public_session(token, session_id)
    index = int(session.get("current_index", 0))
    if session.get("status") != "running" or index >= len(session["sequence"]):
        raise FileNotFoundError("当前没有待播放素材")
    item = session["sequence"][index]
    path = media_path(item["modality"], item["stimulus_id"])
    if not path:
        raise FileNotFoundError("素材文件不存在")
    return path, "audio/mpeg" if item["modality"] == "audio" else "video/mp4"


def public_submit(token: str, session_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """旧版固定量表通道，仅保留给无 schema 的旧问卷。

    新版自定义量表问卷必须走 submit_schema_answers，否则同一会话的答卷会
    分裂在 session.responses（5 个硬编码字段）与统一答卷仓库两处。
    """

    survey = survey_by_token(token)
    if survey.get("schema"):
        raise ValueError("该问卷使用自定义量表，请通过新版答卷通道提交")
    validate_public_session(token, session_id)
    return submit_response(session_id, data)


def question_templates() -> dict[str, Any]:
    """问卷设计器所需的题型、角色与两套标准量表模板。"""

    return {
        "types": [{"value": value, "label": QUESTION_TYPE_LABELS[value]} for value in QUESTION_TYPES],
        "roles": [{"value": value, "label": label} for value, label in ROLES.items()],
        "templates": {
            "video": default_schema("video"),
            "audio": default_schema("audio"),
        },
    }


def submit_schema_answers(
    token: str,
    session_id: str,
    answers: dict[str, Any],
    client_ip: str = "",
    watch_seconds: int = 0,
) -> dict[str, Any]:
    """自定义量表通道：按问卷 schema 校验并写入统一答卷仓库。

    刺激编号与评分者由会话自动填充，避免被试手填造成编号污染；
    session 仅承担播放进度，答卷本体单独写入数据库 并携带完整元数据。
    """

    survey = survey_by_token(token)
    if survey.get("status") != "open":
        raise ValueError("问卷已关闭")
    session = validate_public_session(token, session_id)
    if session.get("status") != "running":
        raise ValueError("实验已结束")
    index = int(session.get("current_index", 0))
    sequence = session.get("sequence") or []
    if index >= len(sequence):
        raise ValueError("没有待回答的素材")
    current = sequence[index]

    filled = dict(answers or {})
    for question in get_schema(survey):
        if question.get("role") == "stimulus" and not filled.get(question["id"]):
            filled[question["id"]] = current.get("stimulus_id", "")
        elif question.get("role") == "rater" and not filled.get(question["id"]):
            filled[question["id"]] = session.get("participant_code", "")

    from . import survey_meta  # 延迟导入，避免 survey_meta -> surveys 循环

    record = survey_meta.build_response_record(
        survey, filled, origin="local", session_id=session_id,
        watch_seconds=watch_seconds, strict=True,
    )
    survey_meta.set_client_ip_meta(record, client_ip)
    record["submitted_at"] = _now()
    with transaction(write=True) as conn:
        current_survey = load_survey(survey["id"], conn=conn)
        if current_survey.get("status") != "open":
            raise ValueError("问卷已关闭")
        if current_survey.get("schema_hash") != survey.get("schema_hash"):
            raise ValueError("问卷题目已更新，请重新加载后提交")
        session = load_session(session_id, conn=conn)
        if int(session["current_index"]) != index:
            raise ValueError("会话进度已更新，请刷新后继续")
        advance_session_record(session)
        survey_db.save_responses(conn, survey["id"], [record], submit_index=index)
        survey_db.save_session(conn, session)
    return {"session": public_session(session), "response_id": record["response_id"]}
