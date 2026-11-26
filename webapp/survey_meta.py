"""统一答卷仓库、元数据统计、质量诊断与问卷星 CSV 导入导出。

SQLite 保存问卷、答卷、会话、导入批次与暂存元数据。原始 CSV 副本仍留在
``data/survey_imports``，以便按批次和原始行号回查。

答卷记录同时保存「原始答案」与「按 role 归一化后的值」以及
``schema_version`` / ``schema_hash``，因此修改量表后旧答卷仍可追溯。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import secrets
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Iterable

from .questionnaire import (
    PLATFORM_OUTPUT_COLUMNS,
    SchemaError,
    hash_ip,
    infer_schema,
    normalize_schema,
    parse_platform_meta,
    schema_fingerprint,
    schema_for_survey,
    survey_kind,
    validate_answers,
    wjx_header,
)
from .config import IMPORTS_DIR, STAGING_DIR
from .surveys import _public, load_survey
from .record_store import managed
from . import record_store, survey_db
from .db import transaction


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "", value or "")[:80]
    if not cleaned:
        raise ValueError("非法标识")
    return cleaned


def _decode(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return data.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue
    raise SchemaError("无法识别 CSV 编码（尝试过 UTF-8 BOM / GB18030 / UTF-16）")


# ---------------------------------------------------------------------------
# 答卷记录
# ---------------------------------------------------------------------------


def build_response_record(
    survey: dict[str, Any],
    answers: dict[str, Any],
    *,
    origin: str = "local",
    platform: dict[str, Any] | None = None,
    batch_id: str = "",
    raw_row: int | None = None,
    session_id: str = "",
    watch_seconds: int = 0,
    strict: bool = True,
) -> dict[str, Any]:
    """构造一份统一答卷记录（不落盘）。"""

    schema = schema_for_survey(survey)
    if not schema:
        raise SchemaError("该问卷没有题目定义")
    kind = survey_kind(survey)
    clean, normalized, flags = validate_answers(schema, answers, kind=kind, strict=strict)

    by_role = {question["role"]: (question, normalized.get(question["id"])) for question in schema if question.get("role")}
    rater = by_role.get("rater", (None, None))[1] or ""
    stimulus_id = by_role.get("stimulus", (None, None))[1] or ""
    stimulus_raw = ""
    if "stimulus" in by_role:
        stimulus_raw = str(clean.get(by_role["stimulus"][0]["id"], "") or "")

    meta = dict(platform or {})
    record: dict[str, Any] = {
        "response_id": f"SR{uuid.uuid4().hex[:10]}",
        "survey_id": survey["id"],
        "schema_version": int(survey.get("schema_version", 1) or 1),
        "schema_hash": survey.get("schema_hash") or schema_fingerprint(schema),
        "origin": origin,
        "batch_id": batch_id,
        "raw_row": raw_row,
        "session_id": session_id,
        "submitted_at": meta.get("submitted_at") or _now(),
        "serial_no": meta.get("serial_no"),
        "duration_s": meta.get("duration_s"),
        "source": meta.get("source") or ("问卷星导入" if origin == "import" else "本地系统"),
        "source_detail": meta.get("source_detail") or "直接访问",
        "ip_region": meta.get("ip_region", ""),
        "ip_hash": meta.get("ip_hash", ""),
        "total_score": meta.get("total_score"),
        "participant_code": rater,
        "rater": rater,
        "stimulus_id": stimulus_id,
        "stimulus_raw": stimulus_raw,
        "watch_seconds": int(watch_seconds or 0),
        "answers": clean,
        "normalized": normalized,
        "flags": flags,
        "valid": not any(
            flag.startswith(("missing:", "invalid:")) or flag == "duplicate" for flag in flags
        ),
        "created_at": _now(),
    }
    return record


def append_responses(survey_id: str, records: Iterable[dict[str, Any]]) -> int:
    with transaction(write=True) as conn:
        return survey_db.save_responses(conn, survey_id, records)


def append_response(record: dict[str, Any]) -> dict[str, Any]:
    append_responses(record["survey_id"], [record])
    return record


@managed("responses", id_key="response_id", title_key="display_name")
def iter_responses(survey_id: str) -> list[dict[str, Any]]:
    return survey_db.list_responses(survey_id)


def response_table(survey_id: str, limit: int = 200) -> dict[str, Any]:
    total, rows = survey_db.recent_responses(survey_id, max(1, min(limit, 5000)))
    return {
        "total": total,
        "responses": record_store.decorate_rows("responses", rows, "response_id", "display_name"),
    }


def total_responses() -> int:
    """Count all responses for the dashboard."""
    return survey_db.count_responses()


def get_response(survey_id: str, response_id: str) -> dict[str, Any] | None:
    record = survey_db.get_response(survey_id, response_id)
    if record is None:
        return None
    rows = record_store.decorate_rows("responses", [record], "response_id", "display_name")
    return rows[0] if rows else None


@managed("responses", id_key="response_id", title_key="display_name")
def responses_for_session(survey_id: str, session_id: str) -> list[dict[str, Any]]:
    """Read responses via the session index and preserve submission order."""
    return survey_db.list_responses(survey_id, session_id)


def record_schema(survey, record):
    current = schema_for_survey(survey)
    if record.get("schema_hash") == survey.get("schema_hash", schema_fingerprint(current)):
        return current
    for version in survey.get("schema_history") or []:
        if record.get("schema_hash") == version.get("schema_hash"):
            return version["schema"]
    if not record.get("schema_hash") and int(record.get("schema_version", 1)) == int(survey.get("schema_version", 1)):
        return current
    raise SchemaError("答卷量表版本缺失，无法安全解释题目")


def current_records(survey):
    fingerprint = survey.get("schema_hash") or schema_fingerprint(schema_for_survey(survey))
    return [r for r in iter_responses(survey["id"])
            if r.get("schema_hash") == fingerprint or
            (not r.get("schema_hash") and r.get("schema_version", 1) == survey.get("schema_version", 1))]


def response_detail(survey_id: str, response_id: str) -> dict[str, Any]:
    """单份答卷 + 题目定义，供后台「查看答卷」逐题展开。

    题目定义随答卷一起返回，页面才能显示题干、题型与字段角色；答卷本身
    已带 schema_version / schema_hash，改过量表后仍可对照当时的版本。
    """

    record = get_response(survey_id, response_id)
    if record is None:
        raise FileNotFoundError("答卷不存在")
    survey = load_survey(survey_id)
    return {
        "response": record,
        "schema": record_schema(survey, record),
        "survey": {
            "id": survey["id"],
            "title": survey.get("title", ""),
            "kind": survey_kind(survey),
        },
    }


# ---------------------------------------------------------------------------
# 元数据统计与质量诊断
# ---------------------------------------------------------------------------


def _numeric(records: list[dict[str, Any]], role: str) -> list[float]:
    values: list[float] = []
    for record in records:
        value = (record.get("normalized") or {}).get(role)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return values


def _role_key(survey: dict[str, Any], role: str) -> str | None:
    return next((q["id"] for q in schema_for_survey(survey) if q.get("role") == role), None)


def survey_metadata(survey_id: str) -> dict[str, Any]:
    """问卷层 + 答卷层 + 题目层元数据汇总。"""

    survey = load_survey(survey_id)
    schema = schema_for_survey(survey)
    records = current_records(survey)
    valid = [record for record in records if record.get("valid")]
    raters = {record.get("rater") for record in valid if record.get("rater")}
    stimuli = {record.get("stimulus_id") for record in valid if record.get("stimulus_id")}
    times = sorted(record.get("submitted_at", "") for record in records if record.get("submitted_at"))

    questions: list[dict[str, Any]] = []
    for question in schema:
        qid = question["id"]
        answered = sum(1 for record in records if (record.get("answers") or {}).get(qid) not in (None, "", []))
        entry: dict[str, Any] = {
            "id": qid,
            "title": question["title"],
            "type": question["type"],
            "role": question.get("role", ""),
            "required": question.get("required", True),
            "min": question.get("min", 1), "max": question.get("max", 9),
            "answered": answered,
            "answer_rate": round(100 * answered / len(records), 1) if records else 0,
        }
        if question["type"] in {"single", "multiple"}:
            counter: Counter[str] = Counter()
            for record in records:
                value = (record.get("answers") or {}).get(qid)
                for part in (value if isinstance(value, list) else re.split(r"[┋|]", str(value or ""))):
                    if part.strip():
                        counter[part.strip()] += 1
            entry["distribution"] = counter.most_common(12)
        elif question["type"] == "rating":
            values = [float(value) for record in records
                      if isinstance((record.get("normalized") or {}).get(qid), (int, float))
                      for value in [(record.get("normalized") or {}).get(qid)]]
            entry["mean"] = round(statistics.fmean(values), 3) if values else None
            entry["sd"] = round(statistics.pstdev(values), 3) if len(values) > 1 else None
            entry["distribution"] = sorted(Counter(int(value) for value in values).items())
        questions.append(entry)

    by_origin = Counter(record.get("origin", "local") for record in records)
    by_batch = Counter(record.get("batch_id") for record in records if record.get("batch_id"))
    return {
        "survey": _public(survey),
        "schema_version": int(survey.get("schema_version", 1) or 1),
        "schema_hash": survey.get("schema_hash") or (schema_fingerprint(schema) if schema else ""),
        "schema_history": survey.get("schema_history", []),
        "statistics_scope": "current_schema",
        "n_all_versions": survey_db.count_responses(survey_id),
        "kind": survey_kind(survey),
        "origin": survey.get("origin", {}),
        "n_questions": len(schema),
        "questions": questions,
        "n_responses": len(records),
        "n_valid": len(valid),
        "n_invalid": len(records) - len(valid),
        "n_raters": len(raters),
        "n_stimuli": len(stimuli),
        "by_origin": dict(by_origin),
        "by_batch": dict(by_batch),
        "first_submitted_at": times[0] if times else None,
        "last_submitted_at": times[-1] if times else None,
        "imports": [import_detail(batch_id) for batch_id in by_batch if import_detail(batch_id)],
    }


def _affect_map(survey, groups):
    schema = schema_for_survey(survey)
    questions = [[q for q in schema if q.get("role") == role and q["type"] == "rating"]
                 for role in ("valence", "arousal")]
    if any(len(matches) != 1 for matches in questions):
        return None
    valence, arousal = (matches[0] for matches in questions)
    fingerprint = survey.get("schema_hash") or schema_fingerprint(schema)
    axes = [{key: question[key] for key in ("min", "max")} for question in (valence, arousal)]
    points = []
    for stimulus, records in groups.items():
        pairs = []
        for record in records:
            if not record.get("valid") or record.get("schema_hash") != fingerprint:
                continue
            values = record.get("normalized") or {}
            pair = [values.get(q["id"]) for q in (valence, arousal)]
            if all(type(value) in (int, float) and axis["min"] <= value <= axis["max"]
                   for value, axis in zip(pair, axes)):
                pairs.append(pair)
        if pairs:
            x, y = (statistics.fmean(scores) for scores in zip(*pairs))
            points.append({"stimulus_id": stimulus, "valence": x, "arousal": y, "n": len(pairs)})
    return {"valence": axes[0], "arousal": axes[1], "points": points}


def quality_report(survey_id: str) -> dict[str, Any]:
    """数据质量诊断：重复、直线作答、无效评分、逐素材覆盖率。

    规则与 ``eeg_emostudio.audit.survey`` 保持一致（同一评分者×刺激保留
    首次；效价与唤醒 SD 均 < 1.0 判为直线作答），但这里只打标记、不删除
    任何行，保证每条异常都能回溯到原始行号。
    """

    survey = load_survey(survey_id)
    records = current_records(survey)
    valence_key = _role_key(survey, "valence")
    arousal_key = _role_key(survey, "arousal")
    issues_key = _role_key(survey, "issues")

    seen: set[tuple[str, str]] = set()
    duplicates: list[dict[str, Any]] = []
    for record in records:
        key = (record.get("rater", ""), record.get("stimulus_id", ""))
        if all(key) and key in seen:
            duplicates.append({
                "response_id": record.get("response_id"),
                "rater": key[0], "stimulus_id": key[1], "raw_row": record.get("raw_row"),
            })
        elif all(key):
            seen.add(key)

    by_rater: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("rater"):
            by_rater[record["rater"]].append(record)
    rater_rows: list[dict[str, Any]] = []
    for rater, group in by_rater.items():
        def sd(key: str | None) -> float | None:
            if not key:
                return None
            values = [float(v) for item in group
                      if isinstance((item.get("normalized") or {}).get(key), (int, float))
                      for v in [(item.get("normalized") or {}).get(key)]]
            return statistics.pstdev(values) if len(values) > 1 else None
        v_sd, a_sd = sd(valence_key), sd(arousal_key)
        straight = v_sd is not None and a_sd is not None and v_sd < 1.0 and a_sd < 1.0
        rater_rows.append({
            "rater": rater, "n_ratings": len(group),
            "valence_sd": round(v_sd, 3) if v_sd is not None else None,
            "arousal_sd": round(a_sd, 3) if a_sd is not None else None,
            "straightline_suspect": straight,
        })
    rater_rows.sort(key=lambda item: item["n_ratings"], reverse=True)

    by_stimulus: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("stimulus_id"):
            by_stimulus[record["stimulus_id"]].append(record)
    coverage: list[dict[str, Any]] = []
    for stimulus_id, group in by_stimulus.items():
        def mean_of(key: str | None) -> float | None:
            if not key:
                return None
            values = [float(v) for item in group
                      if isinstance((item.get("normalized") or {}).get(key), (int, float))
                      for v in [(item.get("normalized") or {}).get(key)]]
            return round(statistics.fmean(values), 3) if values else None
        problem = 0
        if issues_key:
            for item in group:
                value = (item.get("normalized") or {}).get(issues_key)
                if isinstance(value, dict) and value.get("severity", 0) > 0:
                    problem += 1
        coverage.append({
            "stimulus_id": stimulus_id,
            "n_raters": len({item.get("rater") for item in group if item.get("rater")}),
            "valence_mean": mean_of(valence_key),
            "arousal_mean": mean_of(arousal_key),
            "problem_rate": round(problem / len(group), 3) if group else 0,
        })
    coverage.sort(key=lambda item: (-item["n_raters"], item["stimulus_id"]))

    invalid_ratings = sum(
        1 for record in records
        if (valence_key and (record.get("normalized") or {}).get(valence_key) is None)
        or (arousal_key and (record.get("normalized") or {}).get(arousal_key) is None)
    )
    return {
        "n_responses": len(records),
        "n_valid": sum(1 for record in records if record.get("valid")),
        "n_duplicates": len(duplicates),
        "duplicates": duplicates[:50],
        "n_straightline_raters": sum(1 for row in rater_rows if row["straightline_suspect"]),
        "rater_table": rater_rows,
        "invalid_ratings": invalid_ratings,
        "n_stimuli_covered": len(by_stimulus),
        "stimulus_coverage": coverage,
        "affect_map": _affect_map(survey, by_stimulus),
        "mean_valence": round(statistics.fmean(_numeric(records, valence_key)), 3) if valence_key and _numeric(records, valence_key) else None,
        "mean_arousal": round(statistics.fmean(_numeric(records, arousal_key)), 3) if arousal_key and _numeric(records, arousal_key) else None,
    }


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------


def _wjx_value(record: dict[str, Any], question: dict[str, Any], answers: dict[str, Any]) -> str:
    value = answers.get(question["id"], "")
    if isinstance(value, (list, tuple)):
        return "┋".join(str(item) for item in value)
    if isinstance(value, (dict,)):
        return str(value.get("text", ""))
    return str(value or "")


def export_wjx_csv(survey_id: str) -> str:
    """导出问卷星兼容 CSV（7 个平台列 + 题目列，表头带题号前缀）。

    调用方应以 UTF-8 BOM 编码写盘/下载，与问卷星导出保持一致。
    """

    survey = load_survey(survey_id)
    schema = schema_for_survey(survey)
    if not schema:
        raise SchemaError("该问卷没有题目定义，无法导出")
    records = sorted(current_records(survey), key=lambda item: item.get("serial_no") or 0)
    buffer = io.StringIO()
    headers = PLATFORM_OUTPUT_COLUMNS + [wjx_header(question, index) for index, question in enumerate(schema, start=1)]
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for position, record in enumerate(records, start=1):
        answers = record.get("answers") or {}
        ip_display = f"{record.get('ip_hash', '')}({record.get('ip_region')})" if record.get("ip_hash") else ""
        duration = record.get("duration_s")
        writer.writerow([
            record.get("serial_no") or position,
            record.get("submitted_at", ""),
            f"{int(duration)}秒" if isinstance(duration, (int, float)) else "",
            record.get("source", ""),
            record.get("source_detail", ""),
            ip_display,
            record.get("total_score") if record.get("total_score") is not None else "",
        ] + [_wjx_value(record, question, answers) for question in schema])
    return buffer.getvalue()


def export_clean_csv(survey_id: str) -> str:
    """导出分析用宽表：元数据列 + 每个 role 一列归一化值。"""

    survey = load_survey(survey_id)
    schema = schema_for_survey(survey)
    versions = [schema] + [v["schema"] for v in survey.get("schema_history") or []]
    roles = list(dict.fromkeys(q["role"] for version in versions for q in version if q.get("role")))
    fields = [
        "response_id", "survey_id", "schema_version", "origin", "batch_id", "raw_row",
        "submitted_at", "duration_s", "source", "ip_region", "ip_hash",
        "rater", "stimulus_id", "stimulus_raw", "valid", "flags",
    ] + [f"n_{role}" for role in roles]
    records = iter_responses(survey_id)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    role_keys = {question["role"]: question["id"] for question in schema if question.get("role")}
    for record in records:
        normalized = record.get("normalized") or {}
        row: dict[str, Any] = {key: record.get(key) for key in fields}
        row["flags"] = ";".join(record.get("flags") or [])
        own_keys = {q["role"]: q["id"] for q in record_schema(survey, record) if q.get("role")}
        for role in roles:
            value = normalized.get(own_keys.get(role))
            row[f"n_{role}"] = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
        writer.writerow(row)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# 历史问卷星 CSV 导入（两步：预览 → 提交）
# ---------------------------------------------------------------------------


def _guess_kind(filename: str) -> str:
    text = filename.lower()
    if "音乐" in filename or "歌曲" in filename or "music" in text or "audio" in text:
        return "audio"
    return "video"


def preview_import(data: bytes, filename: str, kind: str = "") -> dict[str, Any]:
    """解析上传的问卷星 CSV，推断 schema 并暂存，返回字段映射预览。"""

    if not data:
        raise SchemaError("上传内容为空")
    text, encoding = _decode(data)
    reader = csv.DictReader(io.StringIO(text))
    columns = list(reader.fieldnames or [])
    if not columns:
        raise SchemaError("CSV 没有表头")
    if len(set(columns)) != len(columns):
        raise SchemaError("CSV 存在重复列名，请先整理后再导入")
    rows = list(reader)
    if not rows:
        raise SchemaError("CSV 没有数据行")
    resolved_kind = kind if kind in {"video", "audio"} else _guess_kind(filename)
    schema, platform_map = infer_schema(columns, rows, resolved_kind)

    token = secrets.token_urlsafe(12)
    stage = {
        "token": token, "filename": filename, "encoding": encoding,
        "kind": resolved_kind, "schema": schema, "platform_map": platform_map,
        "columns": columns, "n_rows": len(rows),
        "sha256": hashlib.sha256(data).hexdigest(),
        "created_at": _now(),
    }
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    source = STAGING_DIR / f"{token}.csv"
    with source.open("xb") as handle:
        handle.write(data)
    try:
        with transaction(write=True) as conn:
            survey_db.save_staging(conn, stage)
    except Exception:
        source.unlink(missing_ok=True)
        raise
    preview_questions = []
    for index, question in enumerate(schema, start=1):
        column = question.get("source_column", "")
        samples = [str(row.get(column, "")).strip() for row in rows[:3] if str(row.get(column, "")).strip()]
        preview_questions.append({
            "index": index, "id": question["id"], "title": question["title"],
            "type": question["type"], "role": question.get("role", ""),
            "options": question.get("options", []), "source_column": column,
            "samples": samples[:3],
        })
    return {
        "staging_id": token,
        "filename": filename,
        "encoding": encoding,
        "kind": resolved_kind,
        "n_rows": len(rows),
        "n_columns": len(columns),
        "sha256": hashlib.sha256(data).hexdigest(),
        "platform_map": platform_map,
        "questions": preview_questions,
        "sample_rows": [{key: str(value)[:60] for key, value in row.items()} for row in rows[:3]],
    }


def _load_staging(staging_id: str, conn) -> tuple[dict[str, Any], bytes, str]:
    token = _safe(staging_id)
    if token != staging_id:
        raise SchemaError("非法导入暂存标识")
    meta = survey_db.get_staging(conn, token)
    source_path = STAGING_DIR / f"{token}.csv"
    if meta is None or not source_path.is_file():
        raise SchemaError("导入暂存已过期，请重新上传")
    source = source_path.read_bytes()
    if hashlib.sha256(source).hexdigest() != meta["sha256"]:
        raise SchemaError("暂存 CSV 校验失败，请重新上传")
    text, _ = _decode(source)
    return meta, source, text


def commit_import(
    staging_id: str,
    survey_id: str = "",
    title: str = "",
    description: str = "",
    mark_duplicates: bool = True,
) -> dict[str, Any]:
    """把暂存的问卷星 CSV 落成统一答卷，并登记导入批次。"""

    created_source = None
    try:
        with transaction(write=True) as conn:
            meta, source, text = _load_staging(staging_id, conn)
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            schema = normalize_schema(meta["schema"])
            platform_map = meta["platform_map"]
            kind = meta["kind"]

            from .surveys import create_survey_from_import  # local import: 避免模块装配期循环

            if survey_id:
                survey = load_survey(survey_id, conn=conn)
                if survey.get("origin", {}).get("type") == "wjx_import":
                    # 导入到已有归档问卷时沿用其 schema；字段不一致则显式报错
                    if schema_fingerprint(schema) != survey.get("schema_hash"):
                        raise SchemaError("该问卷的题目结构与上传 CSV 不一致，请新建归档问卷")
            else:
                survey = create_survey_from_import(
                    title=title or f"历史问卷导入 · {meta['filename']}",
                    description=description,
                    kind=kind,
                    schema=schema,
                    source_filename=meta["filename"], conn=conn,
                )

            records: list[dict[str, Any]] = []
            seen: set[tuple[str, str]] = set()
            duplicate_count = 0
            for index, row in enumerate(rows, start=2):
                answers = {question["id"]: row.get(question.get("source_column", ""), "") for question in schema}
                platform = parse_platform_meta(row, platform_map)
                record = build_response_record(
                    survey, answers, origin="import", platform=platform,
                    batch_id="", raw_row=index, strict=False,
                )
                key = (record.get("rater", ""), record.get("stimulus_id", ""))
                if mark_duplicates and all(key):
                    if key in seen:
                        record["flags"].append("duplicate")
                        record["valid"] = False
                        duplicate_count += 1
                    else:
                        seen.add(key)
                records.append(record)

            batch_id = f"IMP{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
            for record in records:
                record["batch_id"] = batch_id
            written = survey_db.save_responses(conn, survey["id"], records)
            batch = {
                "batch_id": batch_id,
                "survey_id": survey["id"],
                "filename": meta["filename"],
                "encoding": meta["encoding"],
                "kind": kind,
                "sha256": meta["sha256"],
                "schema_hash": survey.get("schema_hash"),
                "schema_version": survey.get("schema_version"),
                "column_map": platform_map,
                "n_rows": len(rows),
                "n_written": written,
                "n_valid": sum(1 for record in records if record["valid"]),
                "n_duplicates": duplicate_count,
                "n_invalid": sum(1 for record in records if not record["valid"]) - duplicate_count,
                "created_at": _now(),
            }
            survey_db.save_import(conn, batch)
            conn.execute("DELETE FROM survey_import_staging WHERE token=?", (staging_id,))
            IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
            target = IMPORTS_DIR / f"{batch_id}.source.csv"
            with target.open("xb") as handle:
                created_source = target
                handle.write(source)
    except Exception:
        if created_source is not None:
            created_source.unlink(missing_ok=True)
        raise
    try:
        (STAGING_DIR / f"{staging_id}.csv").unlink(missing_ok=True)
    except OSError:
        # The token was consumed in SQLite, so cleanup can safely be retried.
        pass
    return {"batch": batch, "survey": _public(survey)}


@managed("imports", id_key="batch_id", title_key="filename")
def list_imports() -> list[dict[str, Any]]:
    return survey_db.list_imports()


def import_detail(batch_id: str) -> dict[str, Any] | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", batch_id):
        return None
    return survey_db.get_import(batch_id)


def set_client_ip_meta(record: dict[str, Any], client_ip: str) -> None:
    """本地提交时记录脱敏后的来源信息（不保存原始 IP）。"""

    region, digest = hash_ip(client_ip)
    if digest:
        record["ip_region"] = region
        record["ip_hash"] = digest
