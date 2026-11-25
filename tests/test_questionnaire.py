"""问卷 schema、答卷元数据仓库与问卷星导入导出的单元/集成测试。

所有写盘都重定向到临时目录，不触碰 data/ 下的真实数据。
"""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from auth_client import WorkspaceClient

from webapp import record_store, survey_db
from webapp.db import transaction
import webapp.questionnaire as questionnaire
import webapp.survey_meta as survey_meta
import webapp.surveys as surveys
from webapp.main import app

WJX_HEADER = [
    "序号", "提交答卷时间", "所用时间", "来源", "来源详情", "来自IP", "总分",
    "1、您的姓名：", "2、视频编号:",
    "3、请为该视频使你实际产生的情绪效价（不愉快~愉快）打分:",
    "4、请为该视频使你实际产生的情绪唤醒度（平静~激烈）打分：",
    "5、观看该视频后，你是否形成了一种明确、突出的主导情绪？",
    "6、请选择该视频诱发你实际产生的主导情绪：",
    "7、主导情绪大约覆盖素材多长时间？",
    "8、视频诱发的主导情绪是否存在明显的情绪反转或多种情绪变化？",
    "9、在本次测试前，你对该视频的熟悉程度？",
    "10、在未观看完整电影/电视剧的情况下，你是否仍能理解该片段？",
    "11、播放过程中是否存在以下问题？可多选：",
    "12、是否存在未被上述问题涵盖，但明显影响情绪体验的因素？",
]

BASE_ROW = [
    "2026/8/10 12:32:09", "34秒", "微信", "N/A", "111.17.76.83(山东-济南)", "14",
    "张三", "1.mp4", "6", "5",
    "产生了较为清晰的主导情绪", "温馨/放松", "总时长75%以上",
    "主导情绪从头到尾基本稳定", "从未接触过", "基本完全理解", "没有问题", "没有",
]


def make_wjx_csv() -> bytes:
    rows = [
        BASE_ROW,
        [BASE_ROW[0].replace("12:32:09", "12:40:09")] + BASE_ROW[1:],  # 同人同素材 → 重复
        ["2026/8/10 13:01:11", "41秒", "链接", "直接访问", "106.118.217.208(河北-衡水)", "16",
         "李四", "2.mp4", "非常不愉快", "非常激烈",
         "产生了非常清晰、突出的主导情绪", "恐惧/不安", "总时长75%以上",
         "主导情绪从头到尾基本稳定", "从未接触过", "基本完全理解",
         "画面模糊┋音画不同步", "有，请说明〖音频不清晰〗"],
        ["2026/8/10 13:09:05", "38秒", "链接", "直接访问", "106.118.217.208(河北-衡水)", "15",
         "李四", "388.mp4", "8", "2",
         "产生了较为清晰的主导情绪", "激昂", "约占总时长50%-75%",
         "有一定波动，但主导情绪不变", "隐约见过或听过", "大部分能够理解", "没有问题", "没有"],
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(WJX_HEADER)
    for index, row in enumerate(rows, start=1):
        writer.writerow([index] + row)
    return buffer.getvalue().encode("utf-8-sig")


class SchemaTests(unittest.TestCase):
    def test_default_schema_has_all_roles(self):
        schema = questionnaire.default_schema("video")
        self.assertEqual(len(schema), 12)
        self.assertEqual(
            [item["role"] for item in schema],
            ["rater", "stimulus", "valence", "arousal", "clarity", "emotion",
             "coverage", "stability", "familiarity", "comprehension", "issues", "other"],
        )
        self.assertEqual(questionnaire.default_schema("audio")[1]["title"], "音乐歌曲编号:")

    def test_fingerprint_is_stable_and_sensitive(self):
        schema = questionnaire.default_schema("video")
        first = questionnaire.schema_fingerprint(schema)
        self.assertEqual(first, questionnaire.schema_fingerprint(questionnaire.normalize_schema(schema)))
        changed = json.loads(json.dumps(schema))
        changed[0]["title"] = "改过的题干"
        self.assertNotEqual(first, questionnaire.schema_fingerprint(changed))

    def test_validate_answers_rejects_missing_and_accepts_anchors(self):
        schema = questionnaire.default_schema("video")
        answers = {item["id"]: "1" for item in schema}
        for item in schema:
            if item["type"] == "single":
                answers[item["id"]] = item["options"][0]
            elif item["type"] == "multiple":
                answers[item["id"]] = [item["options"][0]]
        answers["q3"] = "非常不愉快"
        answers["q4"] = "非常激烈"
        clean, normalized, flags = questionnaire.validate_answers(schema, answers, strict=True)
        self.assertEqual(normalized["q3"], 1.0)
        self.assertEqual(normalized["q4"], 9.0)
        self.assertEqual(normalized["q2"], "1.mp4")
        self.assertEqual(flags, [])
        self.assertEqual(clean["q3"], "非常不愉快")

        broken = dict(answers)
        del broken["q6"]
        with self.assertRaises(questionnaire.SchemaError):
            questionnaire.validate_answers(schema, broken, strict=True)

    def test_issue_and_stimulus_normalisation(self):
        schema = questionnaire.default_schema("video")
        self.assertEqual(
            questionnaire.normalize_answer(schema[1], "388.mp4", "video"), "38.mp4"
        )
        issue = questionnaire.normalize_answer(schema[10], "画面模糊┋音画不同步")
        self.assertIsInstance(issue, dict)
        self.assertGreater(issue["severity"], 0)
        # classify_issue 会把原始选项映射为标准问题标签
        self.assertIn("模糊", issue["tags"])
        self.assertIn("不同步", issue["tags"])

    def test_infer_schema_from_wjx_header(self):
        reader = csv.DictReader(io.StringIO(make_wjx_csv().decode("utf-8-sig")))
        rows = list(reader)
        schema, platform_map = questionnaire.infer_schema(WJX_HEADER, rows)
        self.assertEqual(len(schema), 12)
        self.assertEqual([q["type"] for q in schema][:4], ["text", "text", "rating", "rating"])
        self.assertEqual(schema[10]["type"], "multiple")
        self.assertEqual(schema[11]["type"], "textarea")
        # 「来源」不得抢走「来源详情」
        self.assertEqual(platform_map["source"], "来源")
        self.assertEqual(platform_map["source_detail"], "来源详情")
        self.assertEqual(platform_map["ip"], "来自IP")

    def test_ip_is_pseudonymised(self):
        region, digest = questionnaire.hash_ip("111.17.76.83(山东-济南)")
        self.assertEqual(region, "山东-济南")
        self.assertEqual(len(digest), 12)
        self.assertNotIn("111.17", digest)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.enterContext(patch.dict(os.environ, {"EEG_DB_PATH": str(root / "test.sqlite3")}))
        self.enterContext(patch.object(record_store, "STORE_DIR", root / "record_management"))
        for name, path in {
            "SURVEYS_DIR": root / "surveys", "RESPONSES_DIR": root / "responses",
            "SESSIONS_DIR": root / "sessions", "IMPORTS_DIR": root / "imports",
            "STAGING_DIR": root / "imports" / "_staging",
        }.items():
            self.enterContext(patch.object(survey_db, name, path))
        self.enterContext(patch.object(survey_meta, "IMPORTS_DIR", root / "imports"))
        self.enterContext(patch.object(survey_meta, "STAGING_DIR", root / "imports" / "_staging"))

    @staticmethod
    def _seed_session(session):
        with transaction(write=True) as conn:
            survey_db.save_session(conn, session)

    def _import(self) -> tuple[dict, str]:
        preview = survey_meta.preview_import(make_wjx_csv(), "情绪诱发情况评估（视频）.csv")
        result = survey_meta.commit_import(preview["staging_id"], title="测试归档问卷")
        return result["batch"], result["survey"]["id"]

    def test_import_metadata_quality_and_export_roundtrip(self):
        batch, survey_id = self._import()
        self.assertEqual(batch["n_rows"], 4)
        self.assertEqual(batch["n_written"], 4)
        self.assertEqual(batch["n_valid"], 3)
        self.assertEqual(batch["n_duplicates"], 1)

        metadata = survey_meta.survey_metadata(survey_id)
        self.assertEqual(metadata["n_responses"], 4)
        self.assertEqual(metadata["n_raters"], 2)
        self.assertEqual(metadata["n_stimuli"], 3)  # 1.mp4 / 2.mp4 / 388.mp4→38.mp4
        self.assertEqual(metadata["n_questions"], 12)
        self.assertEqual(metadata["schema_version"], 1)

        quality = survey_meta.quality_report(survey_id)
        self.assertEqual(quality["n_duplicates"], 1)
        self.assertEqual(quality["invalid_ratings"], 0)
        self.assertGreater(quality["stimulus_coverage"][0]["n_raters"], 0)
        self.assertIsNotNone(quality["mean_valence"])

        exported = list(csv.reader(io.StringIO(survey_meta.export_wjx_csv(survey_id))))
        self.assertEqual(exported[0], WJX_HEADER)
        self.assertEqual(len(exported), 5)
        self.assertEqual(exported[1][7], "张三")

        clean = list(csv.reader(io.StringIO(survey_meta.export_clean_csv(survey_id))))
        self.assertIn("n_valence", clean[0])
        self.assertIn("raw_row", clean[0])
        self.assertEqual(len(clean), 5)

        batches = survey_meta.list_imports()
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["batch_id"], batch["batch_id"])
        self.assertEqual(survey_meta.import_detail(batch["batch_id"])["sha256"], batch["sha256"])

    def test_records_keep_schema_version_and_raw_row(self):
        _, survey_id = self._import()
        records = survey_meta.iter_responses(survey_id)
        self.assertEqual(sorted(item["raw_row"] for item in records), [2, 3, 4, 5])
        self.assertTrue(all(item["schema_version"] == 1 for item in records))
        self.assertTrue(all(item["schema_hash"] for item in records))
        self.assertTrue(all("111.17" not in str(item.get("ip_hash", "")) for item in records))
        duplicate = [item for item in records if "duplicate" in item["flags"]]
        self.assertEqual(len(duplicate), 1)
        self.assertFalse(duplicate[0]["valid"])

    def test_schema_update_creates_version_history(self):
        _, survey_id = self._import()
        original = surveys.load_survey(survey_id)
        new_schema = json.loads(json.dumps(original["schema"]))
        new_schema[0]["title"] = "请填写你的编号"
        result = surveys.update_survey(survey_id, original["title"], "", schema=new_schema)
        self.assertEqual(result["schema_version"], 2)
        updated = surveys.load_survey(survey_id)
        self.assertEqual(len(updated["schema_history"]), 1)
        self.assertEqual(updated["schema_history"][0]["version"], 1)
        self.assertEqual(updated["schema"][0]["title"], "请填写你的编号")

    def test_local_schema_answers_are_recorded_with_metadata(self):
        _, survey_id = self._import()
        # 归档问卷按产品规则不可重新开放（另见 test_archived_survey_cannot_be_published）；
        # 这里仅构造一份「已发布的本地问卷」夹具，用于验证答卷元数据落盘。
        survey = surveys.load_survey(survey_id)
        survey["status"] = "open"
        surveys._save(survey)
        session = {
            "id": "ETEST01", "survey_id": survey_id, "survey_token": survey["token"],
            "participant_code": "P01", "status": "running", "current_index": 0,
            "sequence": [{"stimulus_id": "3.mp4", "modality": "video", "category": "HVHA"}],
            "responses": [], "created_at": "2026-11-15T21:00:00", "updated_at": "2026-11-15T21:00:00",
        }
        self._seed_session(session)
        answers = {
            "q1": "P01", "q2": "3.mp4", "q3": "7", "q4": "6",
            "q5": "产生了较为清晰的主导情绪", "q6": "愉快", "q7": "总时长75%以上",
            "q8": "主导情绪从头到尾基本稳定", "q9": "从未接触过", "q10": "基本完全理解",
            "q11": ["没有问题"], "q12": "没有",
        }
        result = surveys.submit_schema_answers(
            survey["token"], "ETEST01", answers, client_ip="127.0.0.1", watch_seconds=42
        )
        self.assertEqual(result["session"]["status"], "completed")
        records = survey_meta.iter_responses(survey_id)
        self.assertEqual(len(records), 5)
        local = [item for item in records if item["origin"] == "local"][0]
        self.assertEqual(local["stimulus_id"], "3.mp4")
        self.assertEqual(local["watch_seconds"], 42)
        self.assertEqual(local["ip_hash"], questionnaire.hash_ip("127.0.0.1")[1])
        self.assertEqual(local["schema_version"], 1)
        self.assertTrue(local["valid"])

    def test_archived_survey_cannot_be_published(self):
        """历史导入问卷是归档证据，不能被 toggle 成可填写的在线问卷。"""
        _, survey_id = self._import()
        survey = surveys.load_survey(survey_id)
        self.assertEqual(survey["status"], "archived")
        with self.assertRaisesRegex(ValueError, "不可重新开放"):
            surveys.toggle_survey(survey_id)
        self.assertEqual(surveys.load_survey(survey_id)["status"], "archived")
        with self.assertRaisesRegex(ValueError, "不接受新答卷"):
            surveys.start_response(survey["token"], "P01")

        client = WorkspaceClient(app, raise_server_exceptions=False)
        self.assertEqual(client.get(f"/q/{survey['token']}").status_code, 404)
        self.assertEqual(client.get(f"/api/public/surveys/{survey['token']}").status_code, 404)
        page = client.get("/surveys").text
        self.assertIn("历史导入归档", page)
        self.assertNotIn("重新开放", page)
        self.assertNotIn("copy-link", page)
        self.assertNotIn("toggle-survey", page)

    def test_kind_is_persisted_on_edit(self):
        """切换视频/音乐量表后 kind 必须落盘，否则刺激编号按旧模态归一化。"""
        _, survey_id = self._import()
        surveys.update_survey(
            survey_id, "音乐版问卷", "", schema=questionnaire.default_schema("audio"), kind="audio"
        )
        survey = surveys.load_survey(survey_id)
        self.assertEqual(survey["kind"], "audio")
        self.assertEqual(surveys.infer_kind(survey), "audio")
        self.assertEqual(survey_meta.survey_metadata(survey_id)["kind"], "audio")
        record = survey_meta.build_response_record(survey, {"q2": "3"}, strict=False)
        self.assertEqual(record["normalized"]["q2"], "3.mp3")

        client = WorkspaceClient(app, raise_server_exceptions=False)
        self.assertEqual(
            client.put(f"/api/surveys/{survey_id}", json={
                "title": "切回视频版", "schema": questionnaire.default_schema("video"), "kind": "video",
            }).status_code, 200
        )
        self.assertEqual(surveys.load_survey(survey_id)["kind"], "video")

    def test_schema_survey_rejects_legacy_response_channel(self):
        """带 schema 的问卷不能走旧固定量表通道，避免答卷分裂在两处。"""
        _, survey_id = self._import()
        survey = surveys.load_survey(survey_id)
        survey["status"] = "open"
        surveys._save(survey)
        with self.assertRaisesRegex(ValueError, "自定义量表"):
            surveys.public_submit(survey["token"], "ENOSESSION", {})

    def test_legacy_survey_uses_schema_fallback_everywhere(self):
        """无 schema 的旧问卷在统计与导出侧也必须拿到一致的默认量表。"""
        survey_db.SURVEYS_DIR.mkdir(parents=True, exist_ok=True)
        legacy = {
            "id": "QLEGACY", "token": "legacytok", "title": "旧版问卷", "description": "",
            "created_at": "2026-01-01T00:00:00", "status": "open",
            "settings": {}, "materials": [],
        }
        (survey_db.SURVEYS_DIR / "QLEGACY.json").write_text(
            json.dumps(legacy, ensure_ascii=False), encoding="utf-8"
        )
        survey_db.migrate_legacy()
        self.assertEqual(len(surveys.get_schema(legacy)), 12)
        self.assertEqual(survey_meta.survey_metadata("QLEGACY")["n_questions"], 12)
        record = survey_meta.build_response_record(legacy, {"q2": "1.mp4"}, strict=False)
        self.assertEqual(record["normalized"]["q2"], "1.mp4")
        self.assertIn("1、", survey_meta.export_wjx_csv("QLEGACY"))

        client = WorkspaceClient(app, raise_server_exceptions=False)
        self.assertEqual(client.get("/api/surveys/QLEGACY/responses.csv").status_code, 200)
        self.assertEqual(client.get("/api/surveys/QLEGACY/metadata").status_code, 200)

    def test_legacy_migration_is_atomic_and_preserves_originals(self):
        """A broken line does not import a partial history, and retries do not restore old state."""
        for directory in (survey_db.SURVEYS_DIR, survey_db.SESSIONS_DIR, survey_db.RESPONSES_DIR):
            directory.mkdir(parents=True)
        survey = {"id": "QLEGACY", "token": "legacy", "title": "历史问卷",
                  "created_at": "2026-01-01T00:00:00", "status": "open"}
        session = {"id": "ELEGACY", "survey_id": "QLEGACY", "participant_code": "P01",
                   "status": "completed", "created_at": "2026-01-01T00:00:00",
                   "updated_at": "2026-01-01T00:00:00", "current_index": 1,
                   "responses": [{"response_id": "R0001", "valence": 7}]}
        answer = {"response_id": "SRLEGACY", "survey_id": "QLEGACY", "session_id": "ELEGACY",
                  "submitted_at": "2026-01-01T00:00:00", "answers": {"q1": "P01"}}
        survey_path = survey_db.SURVEYS_DIR / "QLEGACY.json"
        session_path = survey_db.SESSIONS_DIR / "ELEGACY.json"
        answer_path = survey_db.RESPONSES_DIR / "QLEGACY.jsonl"
        survey_path.write_text(json.dumps(survey), encoding="utf-8")
        session_path.write_text(json.dumps(session), encoding="utf-8")
        valid_line = json.dumps(answer) + "\n"
        answer_path.write_text(valid_line + "{broken\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "第 2 行"):
            survey_db.migrate_legacy()
        self.assertEqual(survey_db.list_surveys(), [])
        self.assertEqual(survey_db.list_sessions(), [])

        answer_path.write_text(valid_line, encoding="utf-8")
        survey_db.migrate_legacy()
        self.assertEqual(survey_db.list_sessions()[0]["responses"][0]["valence"], 7)
        self.assertEqual(survey_meta.get_response("QLEGACY", "SRLEGACY")["answers"], {"q1": "P01"})
        self.assertEqual(surveys.toggle_survey("QLEGACY")["status"], "closed")
        record_store.update("responses", "SRLEGACY", {"deleted_at": "2026-01-02"}, 0)
        survey_db.migrate_legacy()
        self.assertEqual(surveys.load_survey("QLEGACY")["status"], "closed")
        self.assertEqual(survey_meta.response_table("QLEGACY")["total"], 0)
        self.assertEqual(survey_meta.total_responses(), 0)
        self.assertEqual(json.loads(survey_path.read_text(encoding="utf-8"))["status"], "open")
        self.assertEqual(answer_path.read_text(encoding="utf-8"), valid_line)

    def test_web_endpoints(self):
        client = WorkspaceClient(app)
        self.assertEqual(client.get("/survey-data").status_code, 200)
        templates = client.get("/api/questionnaire/templates").json()
        self.assertEqual(len(templates["templates"]["video"]), 12)

        preview = client.post(
            "/api/surveys/import/preview?filename=%E8%A7%86%E9%A2%91%E9%97%AE%E5%8D%B7.csv",
            content=make_wjx_csv(),
            headers={"Content-Type": "application/octet-stream"},
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        staging_id = preview.json()["preview"]["staging_id"]
        committed = client.post("/api/surveys/import/commit", json={
            "staging_id": staging_id, "title": "HTTP 导入测试",
        })
        self.assertEqual(committed.status_code, 200, committed.text)
        survey_id = committed.json()["batch"]["survey_id"]
        batch_id = committed.json()["batch"]["batch_id"]

        base = f"/api/surveys/{survey_id}"
        for path in [f"{base}/schema", f"{base}/metadata", f"{base}/quality", f"{base}/responses"]:
            response = client.get(path)
            self.assertEqual(response.status_code, 200, path)
        csv_response = client.get(f"{base}/responses.csv")
        self.assertEqual(csv_response.status_code, 200)
        self.assertTrue(csv_response.content.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(client.get(f"/api/surveys/imports/{batch_id}/source.csv").status_code, 200)
        self.assertEqual(client.get("/api/surveys/imports").json()["imports"][0]["batch_id"], batch_id)
        self.assertIn("HTTP 导入测试", client.get("/surveys").text)

    def _open_survey_with_session(self, survey_id: str, stimuli: list[str]) -> tuple[str, str]:
        """构造可填写问卷与本地会话，返回 (token, session_id)。"""

        survey = surveys.load_survey(survey_id)
        survey["status"] = "open"
        surveys._save(survey)
        session_id = "ESESSION01"
        session = {
            "id": session_id, "survey_id": survey_id, "survey_token": survey["token"],
            "survey_title": survey["title"], "participant_code": "P01",
            "status": "running", "current_index": 0,
            "sequence": [
                {"stimulus_id": name, "modality": "video", "category": "HVHA"} for name in stimuli
            ],
            "responses": [],
            "created_at": "2026-11-16T00:00:00", "updated_at": "2026-11-16T00:00:00",
        }
        self._seed_session(session)
        return survey["token"], session_id

    @staticmethod
    def _answers(rater: str, stimulus: str) -> dict:
        return {
            "q1": rater, "q2": stimulus, "q3": "7", "q4": "6",
            "q5": "产生了较为清晰的主导情绪", "q6": "愉快", "q7": "总时长75%以上",
            "q8": "主导情绪从头到尾基本稳定", "q9": "从未接触过", "q10": "基本完全理解",
            "q11": ["没有问题"], "q12": "没有",
        }

    def test_response_detail_repository(self):
        """单份答卷可定位、可带题目定义读取，会话过滤不串数据。"""

        _, survey_id = self._import()
        records = survey_meta.iter_responses(survey_id)
        target = records[0]
        self.assertIsNotNone(survey_meta.get_response(survey_id, target["response_id"]))
        self.assertIsNone(survey_meta.get_response(survey_id, "SRNOTEXIST"))
        detail = survey_meta.response_detail(survey_id, target["response_id"])
        self.assertEqual(detail["survey"]["id"], survey_id)
        self.assertEqual(len(detail["schema"]), 12)
        self.assertEqual(detail["response"]["answers"], target["answers"])
        with self.assertRaises(FileNotFoundError):
            survey_meta.response_detail(survey_id, "SRNOTEXIST")
        self.assertEqual(survey_meta.total_responses(), 4)
        self.assertEqual(survey_meta.responses_for_session(survey_id, "EUNKNOWN"), [])

    def test_sqlite_answers_advance_session_progress(self):
        """新版答卷不写 session.responses，进度仍须按独立答卷表正确累加。"""

        _, survey_id = self._import()
        token, session_id = self._open_survey_with_session(survey_id, ["1.mp4", "2.mp4"])
        first = surveys.submit_schema_answers(token, session_id, self._answers("P01", "1.mp4"))
        self.assertEqual(first["session"]["answered"], 1)
        self.assertEqual(first["session"]["total"], 2)
        self.assertEqual(first["session"]["status"], "running")
        second = surveys.submit_schema_answers(token, session_id, self._answers("P01", "2.mp4"))
        self.assertEqual(second["session"]["answered"], 2)
        self.assertEqual(second["session"]["status"], "completed")
        self.assertEqual(len(survey_meta.responses_for_session(survey_id, session_id)), 2)
        self.assertEqual(survey_meta.total_responses(), 6)

    def test_online_response_rolls_back_when_cursor_cannot_be_saved(self):
        _, survey_id = self._import()
        token, session_id = self._open_survey_with_session(survey_id, ["1.mp4"])
        with patch.object(survey_db, "save_session", side_effect=OSError("simulated write failure")):
            with self.assertRaises(OSError):
                surveys.submit_schema_answers(token, session_id, self._answers("P01", "1.mp4"))
        self.assertEqual(survey_meta.responses_for_session(survey_id, session_id), [])
        self.assertEqual(surveys.validate_public_session(token, session_id)["current_index"], 0)

    def test_csv_commit_can_retry_once_after_rollback(self):
        source = make_wjx_csv()
        stage = survey_meta.preview_import(source, "rollback.csv")
        token = stage["staging_id"]
        with patch.object(survey_db, "save_import", side_effect=OSError("simulated write failure")):
            with self.assertRaises(OSError):
                survey_meta.commit_import(token)
        self.assertEqual(survey_db.list_surveys(), [])
        self.assertEqual(survey_meta.total_responses(), 0)
        self.assertEqual(survey_meta.list_imports(), [])
        result = survey_meta.commit_import(token)
        csv_path = survey_meta.IMPORTS_DIR / f"{result['batch']['batch_id']}.source.csv"
        self.assertEqual(csv_path.read_bytes(), source)
        with self.assertRaisesRegex(questionnaire.SchemaError, "暂存已过期"):
            survey_meta.commit_import(token)

    def test_response_detail_api_and_legacy_redirects(self):
        """详情 API、本轮结果 API 与旧版页面重定向形成完整可达链路。"""

        _, survey_id = self._import()
        token, session_id = self._open_survey_with_session(survey_id, ["1.mp4"])
        submitted = surveys.submit_schema_answers(token, session_id, self._answers("P01", "1.mp4"))
        response_id = submitted["response_id"]
        client = WorkspaceClient(app, raise_server_exceptions=False)

        detail = client.get(f"/api/surveys/{survey_id}/responses/{response_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(len(detail.json()["schema"]), 12)
        self.assertEqual(detail.json()["response"]["answers"]["q6"], "愉快")
        self.assertEqual(
            client.get(f"/api/surveys/{survey_id}/responses/SRMissing").status_code, 404
        )

        result = client.get(f"/api/public/surveys/{token}/sessions/{session_id}/result")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(result.json()["responses"]), 1)
        self.assertEqual(len(result.json()["schema"]), 12)
        self.assertEqual(
            client.get(f"/api/public/surveys/{token}/sessions/EWRONG/result").status_code, 404
        )

        legacy = client.get("/responses", follow_redirects=False)
        self.assertEqual(legacy.status_code, 302)
        self.assertEqual(legacy.headers["location"], "/survey-data")
        redirect = client.get(f"/experiment?session={session_id}", follow_redirects=False)
        self.assertEqual(redirect.status_code, 302)
        location = redirect.headers["location"]
        self.assertIn(f"survey_id={survey_id}", location)
        self.assertIn(f"response_id={response_id}", location)
        self.assertIn("tab=responses", location)
        page = client.get(location).text
        self.assertIn("答卷明细", page)
        self.assertIn("responseDetail", page)

        old_session = {
            "id": "ELEGACY", "participant_code": "X", "status": "completed",
            "current_index": 0, "sequence": [], "responses": [],
            "created_at": "2026-11-15T00:00:00", "updated_at": "2026-11-15T00:00:00",
        }
        self._seed_session(old_session)
        self.assertEqual(
            client.get("/experiment?session=ELEGACY", follow_redirects=False).headers["location"],
            "/survey-data",
        )


if __name__ == "__main__":
    unittest.main()
