"""Questionnaire sessions and the historical fixed-scale experiment API.

Current sessions and their playback cursor share the database with survey
responses. Fixed-scale answers remain available through their legacy routes.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    AUDIO_DIR,
    ROOT,
    SELECTION_CSV,
    VIDEO_DIR,
)
from .media import media_path
from .db import transaction
from . import survey_db

LIKERT_LABELS = {
    1: "非常低",
    2: "很低",
    3: "较低",
    4: "略低",
    5: "中等",
    6: "略高",
    7: "较高",
    8: "很高",
    9: "非常高",
}
DISCRETE_CHOICES = [
    {"value": "平静", "label": "平静 / 中性"},
    {"value": "悲伤", "label": "悲伤"},
    {"value": "恐惧", "label": "恐惧"},
    {"value": "快乐", "label": "快乐"},
    {"value": "其他", "label": "其他 / 说不清"},
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", value)[:64]


def _load_materials() -> list[dict[str, Any]]:
    if not SELECTION_CSV.exists():
        raise FileNotFoundError("尚未生成选材清单，请先在“材料选材”页运行选材")
    frame = pd.read_csv(SELECTION_CSV, encoding="utf-8-sig")
    frame = frame[frame["modality"].astype(str).str.lower() == "video"].copy()
    materials: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        stimulus = str(row["stimulus_id"])
        path = media_path("video", stimulus)
        if not path:
            continue
        materials.append(
            {
                "stimulus_id": stimulus,
                "modality": "video",
                "category": str(row.get("category", "")),
                "discrete_label": str(row.get("discrete_label", "")),
                "quality_score": float(row.get("quality_score", 0) or 0),
                "grade": str(row.get("grade", "")),
                "selection_rank": int(row.get("selection_rank", 9999) or 9999),
                "path": str(path.relative_to(ROOT)),
            }
        )
    return materials


def _balanced_sequence(materials: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Round-robin over the four affect quadrants, then by quality rank."""

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in materials:
        groups.setdefault(item["category"], []).append(item)
    for key in groups:
        groups[key].sort(key=lambda item: item["selection_rank"])
    ordered: list[dict[str, Any]] = []
    max_len = max((len(items) for items in groups.values()), default=0)
    for index in range(max_len):
        for category in ["HVHA", "HVLA", "LVHA", "LVLA"]:
            items = groups.get(category, [])
            if index < len(items):
                ordered.append(items[index])
    # Avoid adjacent trials with the same self-reported discrete emotion.
    # This keeps the four quadrants while reducing carry-over effects.
    if len(ordered) > 1:
        pool = ordered[:]
        ordered = []
        while pool:
            index = next(
                (
                    i
                    for i, item in enumerate(pool)
                    if not ordered or item["discrete_label"] != ordered[-1]["discrete_label"]
                ),
                0,
            )
            ordered.append(pool.pop(index))
    if limit > 0:
        ordered = ordered[:limit]
    return ordered


def create_session(
    participant_code: str,
    limit: int = 8,
    age: int | None = None,
    gender: str = "",
    consent: bool = True,
    note: str = "",
    sleep_hours: float | None = None,
    fatigue: int | None = None,
    mood: int | None = None,
) -> dict[str, Any]:
    code = re.sub(r"[^A-Za-z0-9_-]+", "", participant_code or "").strip()
    if not code:
        raise ValueError("请填写被试编号")
    if not consent:
        raise ValueError("需要确认知情同意")
    if limit < 1 or limit > 40:
        raise ValueError("本轮刺激数需在 1–40 之间")
    materials = _balanced_sequence(_load_materials(), limit)
    if not materials:
        raise ValueError("没有可用的视频刺激，请先运行材料选材")
    session_id = f"E{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
    session = {
        "id": session_id,
        "participant_code": code,
        "age": age,
        "gender": gender,
        "note": note[:500],
        "pre_session": {
            "age": age,
            "gender": gender,
            "sleep_hours": sleep_hours,
            "fatigue": fatigue,
            "mood": mood,
        },
        "consent": True,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "running",
        "current_index": 0,
        "sequence": materials,
        "responses": [],
        "protocol": {
            "modality": "video",
            "questionnaire": "SAM valence/arousal + discrete emotion + intensity/familiarity",
            "video_dir": str(VIDEO_DIR.relative_to(ROOT)),
        },
    }
    with transaction(write=True) as conn:
        survey_db.save_session(conn, session)
    return public_session(session)


def load_session(session_id: str, *, conn=None) -> dict[str, Any]:
    if not session_id or _safe_id(session_id) != session_id:
        raise ValueError("非法 session id")
    if conn is not None:
        session = survey_db.get_session(conn, session_id)
    else:
        with transaction() as db:
            session = survey_db.get_session(db, session_id)
    if session is None:
        raise FileNotFoundError("实验会话不存在")
    return session


def public_session(session: dict[str, Any]) -> dict[str, Any]:
    sequence = session.get("sequence", [])
    index = int(session.get("current_index", 0))
    current = sequence[index] if index < len(sequence) and session.get("status") == "running" else None
    # 新版自定义量表答卷单独存储，不写进 session.responses；
    # 进度必须按 session_id 回查，否则提交后进度条一直停在 0/N。
    answered = len(session.get("responses", []))
    if session.get("survey_id"):
        try:
            from . import survey_meta  # 延迟导入，避免 survey_meta -> surveys -> experiment 循环

            answered = len(
                survey_meta.responses_for_session(str(session["survey_id"]), session["id"])
            )
        except Exception:
            pass
    payload = {
        "id": session["id"],
        "participant_code": session["participant_code"],
        "status": session["status"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "current_index": index,
        "total": len(sequence),
        "answered": answered,
        "current": None,
        "progress": round(100 * index / len(sequence), 1) if sequence else 0,
        # 新版问卷会话携带归属问卷，前端据此直达该轮答卷；旧版会话留空。
        "survey_id": session.get("survey_id", ""),
        "survey_title": session.get("survey_title", ""),
    }
    if current:
        media_type = "audio" if str(current.get("modality", "video")) == "audio" else "video"
        token = session.get("survey_token")
        media_url = (
            f"/q/{token}/media/{session['id']}?v={index}"
            if token
            else f"/experiment/media/{session['id']}?v={index}"
        )
        payload["current"] = {
            "stimulus_id": current["stimulus_id"],
            "modality": media_type,
            "category": current.get("category", ""),
            "discrete_label": current.get("discrete_label", ""),
            "quality_score": current.get("quality_score", 0),
            "index": index + 1,
            "total": len(sequence),
            "media_type": media_type,
            "video_url": media_url,
            "media_url": media_url,
        }
    return payload


def video_for_session(session_id: str) -> Path:
    session = load_session(session_id)
    index = int(session.get("current_index", 0))
    if session.get("status") != "running" or index >= len(session["sequence"]):
        raise FileNotFoundError("当前没有待播放视频")
    item = session["sequence"][index]
    modality = str(item.get("modality", "video"))
    path = media_path(modality, str(item["stimulus_id"]))
    if path is None:
        relative = item.get("path")
        path = (ROOT / relative).resolve() if relative else None
    if path is None or not path.exists():
        raise FileNotFoundError("素材文件不在管理目录")
    return path


def submit_response(session_id: str, data: dict[str, Any]) -> dict[str, Any]:
    with transaction(write=True) as conn:
        session = load_session(session_id, conn=conn)
        if session.get("status") != "running":
            raise ValueError("实验已结束")
        index = int(session["current_index"])
        if index >= len(session["sequence"]):
            raise ValueError("没有待回答的刺激")
        current = session["sequence"][index]
        val = int(data.get("valence", 0))
        arousal = int(data.get("arousal", 0))
        intensity = int(data.get("intensity", 0))
        familiarity = int(data.get("familiarity", 0))
        if not 1 <= val <= 9 or not 1 <= arousal <= 9:
            raise ValueError("效价/唤醒评分需在 1–9 之间")
        if not 1 <= intensity <= 5 or not 1 <= familiarity <= 5:
            raise ValueError("情绪强度/熟悉度需在 1–5 之间")
        discrete = str(data.get("discrete", "")).strip()
        if discrete not in {item["value"] for item in DISCRETE_CHOICES}:
            raise ValueError("请选择主导情绪")
        response = {
            "response_id": f"R{len(session['responses']) + 1:04d}",
            "stimulus_id": current["stimulus_id"],
            "stimulus_index": index + 1,
            "category": current["category"],
            "expected_discrete": current["discrete_label"],
            "valence": val,
            "arousal": arousal,
            "discrete": discrete,
            "intensity": intensity,
            "familiarity": familiarity,
            "previous_viewed": bool(data.get("previous_viewed", False)),
            "watch_seconds": max(0, int(data.get("watch_seconds", 0) or 0)),
            "note": str(data.get("note", ""))[:500],
            "answered_at": _now(),
        }
        session["responses"].append(response)
        advance_session_record(session)
        survey_db.save_session(conn, session)
    return public_session(session)


def advance_session_record(session: dict[str, Any]) -> None:
    """Advance an in-memory session loaded in the caller's write transaction."""
    if session.get("status") != "running":
        raise ValueError("实验已结束")
    index = int(session["current_index"])
    if index >= len(session["sequence"]):
        raise ValueError("没有待回答的刺激")
    session["current_index"] = index + 1
    session["updated_at"] = _now()
    if session["current_index"] >= len(session["sequence"]):
        session["status"] = "completed"
        session["completed_at"] = session["updated_at"]


def abort_session(session_id: str) -> dict[str, Any]:
    with transaction(write=True) as conn:
        session = load_session(session_id, conn=conn)
        if session.get("status") == "running":
            session["status"] = "aborted"
            session["aborted_at"] = session["updated_at"] = _now()
            survey_db.save_session(conn, session)
    return public_session(session)


def list_sessions() -> list[dict[str, Any]]:
    return [public_session(session) for session in survey_db.list_sessions()]


def summary() -> dict[str, Any]:
    raw_sessions = survey_db.list_sessions()
    sessions = [public_session(session) for session in raw_sessions]
    all_responses = [response for session in raw_sessions for response in session["responses"]]
    completed = [item for item in sessions if item["status"] == "completed"]
    valence = [float(item["valence"]) for item in all_responses if item.get("valence")]
    arousal = [float(item["arousal"]) for item in all_responses if item.get("arousal")]
    counts: dict[str, int] = {}
    for item in all_responses:
        counts[str(item.get("discrete", "未知"))] = counts.get(str(item.get("discrete", "未知")), 0) + 1
    straightline = sum(1 for item in all_responses if item.get("valence") == item.get("arousal"))
    previous = sum(1 for item in all_responses if item.get("previous_viewed"))
    intensities = [float(item["intensity"]) for item in all_responses if item.get("intensity")]
    familiarities = [float(item["familiarity"]) for item in all_responses if item.get("familiarity")]
    return {
        "sessions": len(sessions),
        "completed_sessions": len(completed),
        "participants": len({item["participant_code"] for item in sessions}),
        "responses": len(all_responses),
        "completion_rate": round(100 * len(completed) / len(sessions), 1) if sessions else 0,
        "mean_valence": round(sum(valence) / len(valence), 2) if valence else None,
        "mean_arousal": round(sum(arousal) / len(arousal), 2) if arousal else None,
        "discrete_counts": counts,
        "straightline": straightline,
        "previous_viewed": previous,
        "mean_intensity": round(sum(intensities) / len(intensities), 2) if intensities else None,
        "mean_familiarity": round(sum(familiarities) / len(familiarities), 2) if familiarities else None,
        "latest_sessions": sessions[:8],
    }


def responses_payload(limit: int = 200) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for session in survey_db.list_sessions():
        for response in session["responses"]:
            rows.append(
                {
                    "session_id": session["id"],
                    "participant_code": session["participant_code"],
                    "status": session["status"],
                    **response,
                }
            )
    rows.sort(key=lambda item: item.get("answered_at", ""), reverse=True)
    return {"summary": summary(), "responses": rows[:limit], "total": len(rows)}


def responses_csv() -> str:
    rows = responses_payload(limit=100000)["responses"]
    fields = [
        "session_id", "participant_code", "status", "response_id", "stimulus_index",
        "stimulus_id", "category", "expected_discrete", "valence", "arousal",
        "discrete", "intensity", "familiarity", "previous_viewed", "watch_seconds",
        "note", "answered_at",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
