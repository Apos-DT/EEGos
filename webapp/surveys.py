"""Shareable questionnaire definitions built from the managed media library."""

from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .experiment import SESSIONS_DIR, public_session, submit_response
from .media import item_by_id, load_manifest, media_path
from .services import ROOT

SURVEYS_DIR = ROOT / "data" / "surveys"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _survey_path(survey_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "", survey_id)
    if not safe or safe != survey_id:
        raise ValueError("非法问卷 id")
    return SURVEYS_DIR / f"{safe}.json"


def _all() -> list[dict[str, Any]]:
    if not SURVEYS_DIR.exists():
        return []
    surveys = []
    for path in sorted(SURVEYS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            surveys.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return surveys


def _save(survey: dict[str, Any]) -> None:
    SURVEYS_DIR.mkdir(parents=True, exist_ok=True)
    survey["updated_at"] = _now()
    _survey_path(survey["id"]).write_text(json.dumps(survey, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _session_count(survey_id: str) -> int:
    if not SESSIONS_DIR.exists():
        return 0
    count = 0
    for path in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("survey_id") == survey_id:
                count += 1
        except Exception:
            continue
    return count


def _public(survey: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": survey["id"],
        "token": survey["token"],
        "title": survey["title"],
        "description": survey.get("description", ""),
        "status": survey.get("status", "open"),
        "created_at": survey["created_at"],
        "updated_at": survey.get("updated_at", survey["created_at"]),
        "n_materials": len(survey.get("materials", [])),
        "n_video": sum(1 for item in survey.get("materials", []) if item.get("modality") == "video"),
        "n_audio": sum(1 for item in survey.get("materials", []) if item.get("modality") == "audio"),
        "n_responses": _session_count(survey["id"]),
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
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise ValueError("请填写问卷标题")
    items = _material_items(material_ids or [])
    survey = {
        "id": f"Q{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}",
        "token": secrets.token_urlsafe(7),
        "title": title,
        "description": description.strip()[:1000],
        "created_at": _now(),
        "status": "open",
        "settings": {"require_code": require_code, "allow_multiple": allow_multiple},
        "materials": items,
    }
    _save(survey)
    return _public(survey)

def update_survey(
    survey_id: str,
    title: str,
    description: str,
    material_ids: list[str] | None = None,
) -> dict[str, Any]:
    survey = load_survey(survey_id)
    survey["title"] = title.strip() or survey["title"]
    survey["description"] = (description or "").strip()[:1000]
    if material_ids is not None:
        survey["materials"] = _material_items(material_ids)
    _save(survey)
    return _public(survey)

def _settings(survey: dict[str, Any]) -> dict[str, Any]:
    settings = survey.get("settings", {})
    return {
        "require_code": bool(settings.get("require_code", True)),
        "allow_multiple": bool(settings.get("allow_multiple", True)),
    }


def load_survey(survey_id: str) -> dict[str, Any]:
    path = _survey_path(survey_id)
    if not path.exists():
        raise FileNotFoundError("问卷不存在")
    return json.loads(path.read_text(encoding="utf-8"))


def survey_by_token(token: str) -> dict[str, Any]:
    for survey in _all():
        if survey.get("token") == token:
            return survey
    raise FileNotFoundError("问卷链接不存在")


def list_surveys() -> list[dict[str, Any]]:
    return [_public(survey) for survey in _all()]


def toggle_survey(survey_id: str) -> dict[str, Any]:
    survey = load_survey(survey_id)
    survey["status"] = "closed" if survey.get("status", "open") == "open" else "open"
    _save(survey)
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
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    (SESSIONS_DIR / f"{session_id}.json").write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return public_session(session)


def validate_public_session(token: str, session_id: str) -> dict[str, Any]:
    survey = survey_by_token(token)
    path = SESSIONS_DIR / f"{re.sub(r'[^A-Za-z0-9_-]+', '', session_id)}.json"
    if not path.exists():
        raise FileNotFoundError("会话不存在")
    session = json.loads(path.read_text(encoding="utf-8"))
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
    validate_public_session(token, session_id)
    return submit_response(session_id, data)
