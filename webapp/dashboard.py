"""Build the Dashboard from indexed experiment, survey and dataset records."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from . import dataset_catalog, media, record_store, services, survey_db
from .config import ROOT, SEED_IV_DIR
from .db import transaction
from .questionnaire import schema_fingerprint, schema_for_survey


# These two pre-index runs are explicitly documented in docs/16_SEED_IV数据接入报告.md.
_LEGACY_FEATURES = {
    ("seediv_trial_mlp_loso", "mlp", 1080): "data/processed/seed_iv_de_LDS_trial.npz",
    ("seediv_trial_dualview_loso", "dualview", 1080): "data/processed/seed_iv_de_LDS_trial.npz",
}


def _key(value):
    return "".join(char for char in str(value or "").casefold() if char.isalnum())


def _source_id(value, options):
    key = _key(value)
    if key == "seedivraw":
        key = "seediv"
    return next((source_id for source_id, name in options.items()
                 if key in {_key(source_id), _key(name)}), "")


def _path(value):
    return (ROOT / Path(value)).resolve()


def _score(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
        return float(value)
    return None


def _feature_rows():
    rows = []
    for feature in services.list_feature_datasets():
        if feature["kind"] == "demo":
            continue
        manifest = feature.get("manifest_path")
        extra = {}
        if manifest:
            try:
                value = json.loads(_path(manifest).read_text(encoding="utf-8-sig")).get("extra")
                if isinstance(value, dict):
                    extra = value
            except (OSError, ValueError, AttributeError):
                pass
        rows.append({**feature, "extra": extra})
    return rows


def _modality_labels(values):
    if not isinstance(values, (list, tuple)):
        return []
    names = {
        "eeg": "EEG", "video": "Video", "视频": "Video", "face": "Face", "面部视频": "Face",
        "audio": "Audio", "音频": "Audio", "ecg": "ECG", "gsr": "GSR", "eda": "GSR",
        "gsrecg": "GSR/ECG", "text": "Text", "文本": "Text", "eyetracking": "眼动", "眼动": "眼动",
    }
    return list(dict.fromkeys(names.get(_key(value), value.strip())
                              for value in values if isinstance(value, str) and value.strip()))


def _batch_id(value):
    value = str(value or "").strip()
    return f"batch:{value}" if value else ""


def _record_scope(record, options):
    batch = _batch_id(record.get("collection_batch_id"))
    source = _source_id(record.get("dataset_id") or record.get("dataset"), options)
    return {batch, source} - {""}


def _explicit_dataset_name(value):
    if not isinstance(value, str):
        return ""
    name = value.strip()
    if not name or len(name) > 100 or any(char in name for char in "/\\:."):
        return ""
    return name


def _runs(options, features):
    scope = services.sync_experiments()
    eeg_inputs = {_path(row["path"]): row for row in features}
    eeg_ids = {row["id"]: row for row in features}
    with transaction() as conn:
        rows = conn.execute("""
            SELECT e.summary_json, e.metadata_json, e.metrics_json,
                   e.dataset, COALESCE(m.title, '') AS title
            FROM experiment_runs e
            LEFT JOIN record_metadata m ON m.resource = 'experiments' AND m.record_id = e.run_id
            WHERE e.scope = ? AND COALESCE(m.deleted_at, '') = ''
            ORDER BY e.created_at DESC, e.run_id DESC
            """, (scope,)).fetchall()
    runs = []
    for row in rows:
        summary = json.loads(row["summary_json"])
        meta = json.loads(row["metadata_json"])
        metrics = json.loads(row["metrics_json"])
        legacy = (summary["id"], summary["model"], summary["n_samples"])
        source = row["dataset"] or metrics.get("dataset") or _LEGACY_FEATURES.get(legacy, "")
        feature = eeg_ids.get(meta.get("feature_id") or meta.get("dataset_id"))
        if not feature and isinstance(source, str) and source.lower().endswith(".npz"):
            feature = eeg_inputs.get(_path(source))
        dataset = _source_id(feature.get("source") if feature else source, options)
        if not dataset:
            dataset = _source_id(meta.get("dataset_id"), options)
        if not dataset and not feature and not summary["is_demo"]:
            name = _explicit_dataset_name(source)
            if name:
                dataset = f"source:{_key(name)}"
                options.setdefault(dataset, name)
        dataset_label = options[dataset] if dataset else ""
        if feature and not dataset_label:
            dataset_label = feature["name"]
        elif not dataset_label and source and isinstance(source, str):
            dataset_label = Path(source.replace("\\", "/")).name
        algorithm = str(meta.get("algorithm") or "").upper()
        is_transfer = (
            algorithm in {"UDDA", "SDDA"} and meta.get("external_engine") == "JC-Journal-Club/DDA"
        ) or str(summary.get("model", "")).upper() in {"DDA-UDDA", "DDA-SDDA"}
        modalities = _modality_labels(meta.get("modalities") or metrics.get("modalities"))
        if not modalities and (feature or (is_transfer and dataset == "seed-iv")):
            modalities = ["EEG"]
        fusion = meta.get("fusion_strategy") or meta.get("fusion") or metrics.get("fusion_strategy")
        fusion = fusion if isinstance(fusion, str) and len(modalities) > 1 else None
        category = "transfer" if is_transfer else (
            "fusion" if fusion else "unimodal" if len(modalities) == 1 else "unknown"
        )
        overall = metrics.get("overall") or {}
        protocol = metrics.get("protocol") or {}
        parameters = meta.get("parameters") or {}
        feature_info = feature.get("extra", {}) if feature else {}
        dataset_info = meta.get("dataset_info") or {}
        feature_name = dataset_info.get("feature") or feature_info.get("feature_key") or feature_info.get("feature")
        feature_label = "DE 特征" if _key(feature_name).startswith("de") else (
            "PSD 特征" if _key(feature_name).startswith("psd") else ""
        )
        if not feature_label and "DE computed" in feature_info.get("units", ""):
            feature_label = "DE 特征"
        caveats = []
        fold_count = len(metrics.get("folds") or [])
        expected_dda_folds = {"loso": 45, "cross-session": 3}.get(summary["setting"])
        if is_transfer and expected_dda_folds and fold_count < expected_dda_folds:
            caveats.append("部分折")
        elif parameters.get("max_folds") or parameters.get("target_subject"):
            caveats.append("部分折")
        elif summary["setting"] == "loso" and 0 < fold_count < (summary.get("n_subjects") or 0):
            caveats.append("部分折")
        if isinstance(protocol, dict) and protocol.get("selection_uses_target_test_accuracy"):
            caveats.append("按目标测试集选模")
        run_scope = _record_scope(meta, options) | ({dataset} if dataset else set())
        if feature:
            run_scope.add(f"feature:{feature['id']}")
        runs.append({
            **summary,
            "label": row["title"] or summary["label"],
            "created_at": meta.get("submitted_at") or summary["created_at"],
            "modalities": modalities,
            "fusion": fusion,
            "category": category,
            "dataset": dataset,
            "dataset_label": dataset_label or ("合成演示" if summary["is_demo"] else "来源未记录"),
            "feature_label": feature_label,
            "dataset_scopes": sorted(run_scope),
            "accuracy": _score(overall.get("accuracy")),
            "macro_f1": _score(overall.get("macro_f1")),
            "caveats": caveats,
            "ablation_group": meta.get("ablation_group"),
            "evaluation_id": meta.get("evaluation_id"),
        })
    return sorted(runs, key=lambda run: (run["created_at"], run["id"]), reverse=True)


def _comparison(runs):
    evidence = [run for run in runs if not run["is_demo"]]
    loso = [run for run in evidence if run["setting"] == "loso" and run["accuracy"] is not None]
    qualified = [run for run in loso if not run["caveats"]]
    best_loso = max(qualified or loso, key=lambda run: run["accuracy"], default=None)
    reference = max(
        (run for run in loso if run["macro_f1"] is not None),
        key=lambda run: run["macro_f1"], default=None,
    )
    benchmark = None
    if reference:
        label = "本地 LOSO Macro-F1 最高记录"
        if reference["caveats"]:
            label += " · " + "、".join(reference["caveats"])
        benchmark = {"label": label, "metric": "macro_f1", "score": reference["macro_f1"]}
    groups = defaultdict(dict)
    for run in evidence:
        if (not run["dataset"] or not run["ablation_group"] or not run["evaluation_id"]
                or run["accuracy"] is None or run["caveats"]):
            continue
        group = (run["dataset"], run["setting"], run["ablation_group"], run["evaluation_id"])
        modes = frozenset("Video" if m == "Face" else m for m in run["modalities"])
        groups[group].setdefault(modes, run)
    expected = [frozenset(["EEG"]), frozenset(["Video"]), frozenset(["EEG", "Video"])]
    matched = next((group for group in groups.values() if set(expected) <= group.keys()
                    and group[expected[-1]]["fusion"]), {})
    ablation = []
    gain = None
    if matched:
        ablation = [
            {"label": label, "value": matched[mode]["accuracy"]}
            for label, mode in zip(("仅 EEG", "仅视频", "EEG + 视频"), expected)
        ]
        if best_loso and matched[expected[-1]]["id"] == best_loso["id"]:
            gain = ablation[-1]["value"] - ablation[0]["value"]
    return best_loso, benchmark, ablation, gain


def _label(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 1 <= value <= 9:
        return "negative" if value < 5 else "positive" if value > 5 else "neutral"
    return None


def _valence_by_version(survey):
    schema = schema_for_survey(survey)
    current_version = int(survey.get("schema_version") or 1)
    revisions = [(current_version, survey.get("schema_hash") or schema_fingerprint(schema), schema)]
    revisions.extend((item["version"], item["schema_hash"], item["schema"])
                     for item in survey.get("schema_history") or [])
    valid_questions = {}
    for version, fingerprint, questions in revisions:
        valence = [q["id"] for q in questions if q.get("role") == "valence"
                   and q.get("type") == "rating" and (q.get("min"), q.get("max")) == (1, 9)]
        if len(valence) == 1:
            valid_questions[version] = (fingerprint, valence[0])
    return valid_questions


def _stimulus_counts(surveys, legacy_sessions):
    clips = set()
    paradigms = set()
    for survey in surveys:
        groups = survey.get("materials") or []
        if groups:
            paradigms.add(schema_fingerprint(schema_for_survey(survey)))
        for material in groups:
            identifier = material.get("stimulus_id") or material.get("filename") or material.get("id")
            if identifier:
                clips.add((material.get("modality", "video"), identifier))
    for session in legacy_sessions:
        if session.get("sequence"):
            paradigms.add("legacy-sam")
        for material in session.get("sequence") or []:
            identifier = material.get("stimulus_id") or material.get("filename") or material.get("id")
            if identifier:
                clips.add((material.get("modality", "video"), identifier))
    return Counter(modality for modality, _ in clips), len(paradigms)


def _acquisition(selected, options, surveys, raw_sessions):
    statuses = dict.fromkeys(("completed", "running", "interrupted"), 0)
    distribution = dict.fromkeys(("positive", "neutral", "negative", "total"), 0)
    distribution["scope"] = "有效问卷及旧版量表的 1–9 效价评分，5 为中性"
    removed_surveys = record_store.metadata_index("surveys")
    removed_responses = record_store.metadata_index("responses")
    active_surveys = {survey["id"]: survey for survey in surveys
                      if not removed_surveys.get(survey["id"], {}).get("deleted_at")}
    survey_scopes = {key: _record_scope(survey, options) for key, survey in active_surveys.items()}
    session_scopes = {session["id"]: _record_scope(session, options) for session in raw_sessions}
    answered = Counter()
    linked_sessions = set()
    associated_surveys = set()
    responses = 0
    for survey_id, survey in active_surveys.items():
        versions = _valence_by_version(survey)
        for record in survey_db.list_responses(survey_id):
            if removed_responses.get(record["response_id"], {}).get("deleted_at"):
                continue
            session_id = record.get("session_id")
            record_scopes = (
                survey_scopes[survey_id] | session_scopes.get(session_id, set()) | _record_scope(record, options)
                | ({_batch_id(record["batch_id"])} if record.get("batch_id") else set())
            )
            if selected and selected not in record_scopes:
                continue
            associated_surveys.add(survey_id)
            if session_id:
                linked_sessions.add(session_id)
                answered[session_id] += 1
            responses += 1
            version = versions.get(int(record.get("schema_version") or 1))
            if not record.get("valid", True) or not version:
                continue
            fingerprint, question = version
            if record.get("schema_hash") and record["schema_hash"] != fingerprint:
                continue
            label = _label((record.get("normalized") or {}).get(question))
            if label:
                distribution[label] += 1
    sessions = []
    legacy = []
    for session in raw_sessions:
        survey_id = session.get("survey_id") or ""
        if survey_id and survey_id not in active_surveys:
            continue
        session_id = session["id"]
        scopes = survey_scopes.get(survey_id, set()) | session_scopes[session_id]
        if selected and selected not in scopes and session_id not in linked_sessions:
            continue
        sequence = session.get("sequence") or []
        legacy_responses = [item for item in session.get("responses") or []
                            if not removed_responses.get(item.get("response_id"), {}).get("deleted_at")]
        responses += len(legacy_responses)
        for response in legacy_responses:
            if not response.get("valid", True):
                continue
            label = _label(response.get("valence"))
            if label:
                distribution[label] += 1
        if not survey_id:
            legacy.append(session)
        else:
            associated_surveys.add(survey_id)
        status = session["status"]
        statuses[status if status in {"completed", "running"} else "interrupted"] += 1
        stimuli = list(dict.fromkeys("音频刺激" if item.get("modality") == "audio" else "视频刺激"
                                     for item in sequence))
        modalities = _modality_labels(session.get("captured_modalities")) + ["量表"]
        sessions.append({
            "id": session_id, "survey_id": survey_id, "status": status,
            "survey_title": removed_surveys.get(survey_id, {}).get("title") or (
                active_surveys.get(survey_id, {}).get("title") or session.get("survey_title") or ""
            ),
            "participant_code": session["participant_code"], "created_at": session["created_at"],
            "total": len(sequence), "answered": answered[session_id] + len(legacy_responses),
            "modalities": modalities, "stimuli": stimuli,
        })
    distribution["total"] = sum(distribution[key] for key in ("positive", "neutral", "negative"))
    related_surveys = [
        survey for key, survey in active_surveys.items()
        if not selected or key in associated_surveys or selected in survey_scopes[key]
    ]
    stimuli, paradigms = _stimulus_counts(related_surveys, legacy)
    return sessions, statuses, distribution, responses, stimuli, paradigms


def _feature_types(features):
    types = set()
    for row in features:
        extra = row["extra"]
        key = _key(extra.get("feature") or extra.get("feature_key"))
        if key.startswith("de") or (row["source"] == "SEED-IV raw" and "DE computed" in extra.get("units", "")):
            types.add("DE")
        elif key.startswith("psd"):
            types.add("PSD")
    return [{"label": label, "ready": label in types} for label in ("DE", "PSD", "视觉", "声学")]


def _modalities(raw_count, features, sessions, stimuli, seed_raw):
    captured = {modality for session in sessions for modality in session["modalities"]}
    eeg_available = bool(raw_count or features or "EEG" in captured)
    eeg_detail = (
        "SEED-IV 原始文件 200 Hz" if seed_raw else
        "已有 EEG 文件或采集记录" if eeg_available else "当前范围暂无 EEG 记录"
    )
    video_detail = (
        "已登记视频采集" if {"Video", "Face"} & captured else
        "已有视频刺激素材，暂无采集记录" if stimuli["video"] else "当前范围暂无视频采集记录"
    )
    audio_detail = (
        "已登记音频采集" if "Audio" in captured else
        "已有音频刺激素材，暂无采集记录" if stimuli["audio"] else "当前范围暂无音频采集记录"
    )
    physiology = bool({"GSR", "ECG", "GSR/ECG"} & captured)
    rows = [
        ("EEG", eeg_available, eeg_detail),
        ("Video", bool({"Video", "Face"} & captured), video_detail),
        ("Audio", "Audio" in captured, audio_detail),
        ("GSR/ECG", physiology, "已登记生理信号采集" if physiology else "当前范围暂无采集记录"),
    ]
    return [{"label": label, "ready": ready, "detail": detail + "；实时设备状态未接入"}
            for label, ready, detail in rows]


def get_dashboard_context(dataset: str = "") -> dict:
    """Collect data for a catalog dataset or an explicitly linked acquisition batch."""
    catalog = dataset_catalog.list_source_datasets()
    options = {source["id"]: source["name"] for source in catalog}
    surveys = survey_db.list_surveys()
    raw_sessions = survey_db.list_sessions()
    imports = record_store.decorate_rows("imports", survey_db.list_imports(), "batch_id", "filename")
    batches = {_batch_id(batch["batch_id"]): batch.get("filename") or batch["batch_id"] for batch in imports}
    for record in [*surveys, *raw_sessions]:
        if batch_id := record.get("collection_batch_id"):
            batches[_batch_id(batch_id)] = record.get("collection_batch_name") or str(batch_id)

    features = _feature_rows()
    feature_options = {
        f"feature:{feature['id']}": feature["name"] for feature in features
        if not _source_id(feature["source"], options)
    }
    runs = _runs(options, features)
    for run in runs:
        for scope in run["dataset_scopes"]:
            if scope.startswith("batch:"):
                batches.setdefault(scope, scope.removeprefix("batch:"))

    selected = _source_id(dataset, options) or dataset.strip()
    if selected:
        runs = [run for run in runs if selected in run["dataset_scopes"]]
        features = [feature for feature in features if selected in {
            _source_id(feature["source"], options), f"feature:{feature['id']}",
        }]
    sessions, statuses, distribution, responses, stimuli, paradigms = _acquisition(
        selected, options, surveys, raw_sessions,
    )
    seed_raw = sum(path.is_file() for path in (SEED_IV_DIR / "eeg_raw_data").glob("*/*.mat")) \
        if selected in {"", "seed-iv"} else 0
    raw_count = services._count_eeg_files() if not selected else seed_raw
    best_loso, benchmark, ablation, gain = _comparison(runs)
    fusion_runs = [run for run in runs if run["fusion"] and not run["is_demo"] and not run["caveats"]
                   and run["accuracy"] is not None]
    best_fusion = max(fusion_runs, key=lambda run: run["accuracy"], default=None)
    return {
        "dataset": selected,
        "dataset_options": [
            {"id": value, "label": label} for value, label in {**options, **batches, **feature_options}.items()
        ],
        "runs": runs,
        "sessions": sessions[:5],
        "session_status": statuses,
        "label_distribution": distribution,
        "modalities": _modalities(raw_count, features, sessions, stimuli, seed_raw),
        "phase": {
            "stimuli": sum(stimuli.values()), "video_stimuli": stimuli["video"], "audio_stimuli": stimuli["audio"],
            "paradigms": paradigms, "responses": responses, "sessions": len(sessions), "trigger_rate": None,
            "raw_files": raw_count, "feature_sets": len(features), "feature_types": _feature_types(features),
            "runs": sum(not run["is_demo"] for run in runs),
            "best_fusion": best_fusion["fusion"] if best_fusion else None, "best_loso": best_loso, "gain": gain,
        },
        "benchmark": benchmark,
        "ablation": ablation,
    }


def _recent_questionnaires():
    surveys = record_store.decorate_rows("surveys", survey_db.list_surveys(), title_key="title")
    response_metadata = record_store.metadata_index("responses")
    sessions = survey_db.list_sessions()
    by_survey = defaultdict(list)
    for session in sessions:
        by_survey[session.get("survey_id")].append(session)
    valid_responses = 0
    rows = []
    for survey in surveys:
        responses = [row for row in survey_db.list_responses(survey["id"])
                     if not response_metadata.get(row["response_id"], {}).get("deleted_at")]
        related_sessions = by_survey[survey["id"]]
        responses.extend(row for session in related_sessions for row in session.get("responses") or []
                         if not response_metadata.get(row.get("response_id"), {}).get("deleted_at"))
        valid_responses += sum(bool(row.get("valid", True)) for row in responses)
        dates = [survey.get("updated_at") or survey["created_at"]]
        dates.extend(row.get("submitted_at") or row.get("answered_at") or "" for row in responses)
        dates.extend(session.get("updated_at") or session["created_at"] for session in related_sessions)
        rows.append({
            "id": survey["id"], "title": survey["title"], "updated_at": max(dates),
            "n_responses": len(responses), "status": survey.get("status", "open"),
        })
    # Historical acquisition sessions precede questionnaire definitions and still
    # belong to the collection total. Their responses must only be counted once.
    valid_responses += sum(
        bool(row.get("valid", True))
        for session in by_survey[None] + by_survey[""]
        for row in session.get("responses") or []
        if not response_metadata.get(row.get("response_id"), {}).get("deleted_at")
    )
    rows.sort(key=lambda row: (row["updated_at"], row["id"]), reverse=True)
    return len(surveys), valid_responses, rows[:2]


def _representative_runs(runs):
    eligible = [run for run in runs if not run["is_demo"] and run["setting"] == "loso"
                and run["accuracy"] is not None]
    chosen = eligible[:4]
    names = {"dgcnn": "DGCNN", "dualview": "DualView", "mlp": "MLP"}
    result = []
    for run in chosen[:4]:
        description = [run["dataset_label"], run.get("feature_label"), run["setting_label"]]
        details = [run["id"], run["created_at"], *run["caveats"]]
        result.append({
            **run, "model_label": names.get(str(run["model"]).casefold(), run["model"]),
            "subtitle": " · ".join(part for part in description if part),
            "details": " · ".join(part for part in details if part),
        })
    return result


def get_dashboard_overview() -> dict:
    """Return a global overview with separate corpus and EEG preparation counts."""
    catalog = dataset_catalog.list_source_datasets()
    options = {source["id"]: source["name"] for source in catalog}
    features = _feature_rows()
    runs = _runs(options, features)
    real_runs = [run for run in runs if not run["is_demo"] and run["accuracy"] is not None]
    best = max(real_runs, key=lambda run: run["accuracy"], default=None)
    shown_runs = _representative_runs(runs)
    survey_count, valid_responses, recent_surveys = _recent_questionnaires()
    library = media.library_payload()
    statuses = {
        "available": "已就位", "annotations": "标注就位", "access_required": "待授权",
        "unverified": "待校验", "partial": "下载未完成", "missing": "未就位",
    }
    datasets = [{
        "id": source["id"], "name": source["name"], "modalities": source["modalities"],
        "has_eeg": "EEG" in source["modalities"],
        "status": statuses.get(source["local_status"], "待核查"),
        "status_detail": source["structure"],
    } for source in catalog]
    caveats = list(dict.fromkeys(note for run in shown_runs for note in run["caveats"]))
    comparison_note = "展示最近 4 次跨被试实验。"
    if caveats:
        comparison_note += "DDA 记录含" + "、".join(caveats) + "，具体条件见报告。"
    return {
        "surveys": survey_count, "valid_responses": valid_responses,
        "media_total": len(library["items"]), "media_formal": library["selected_count"],
        "media_quadrants": [category for category in ("HVHA", "HVLA", "LVHA", "LVLA")
                            if any(item.get("category") == category for item in library["items"])],
        "dataset_count": len(datasets), "eeg_dataset_count": sum(row["has_eeg"] for row in datasets),
        "other_dataset_count": sum(not row["has_eeg"] for row in datasets),
        "raw_files": sum(path.is_file() for path in (SEED_IV_DIR / "eeg_raw_data").glob("*/*.mat")),
        "feature_sets": sum(_source_id(feature["source"], options) == "seed-iv" for feature in features),
        "run_count": len(real_runs), "best_accuracy": best["accuracy"] if best else None,
        "best_accuracy_caveats": best["caveats"] if best else [],
        "report_count": sum(bool(run.get("report_url")) for run in runs),
        "report_demo_count": sum(bool(run.get("report_url")) and run["is_demo"] for run in runs),
        "datasets": datasets, "recent_surveys": recent_surveys,
        "runs": shown_runs, "comparison_note": comparison_note,
    }
