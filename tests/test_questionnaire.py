"""问卷 schema、答卷元数据仓库与问卷星导入导出的单元/集成测试。

所有写盘都重定向到临时目录，不触碰 data/ 下的真实数据。
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import webapp.experiment as experiment
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
        self.saved: list[tuple[object, str, object]] = []

        def patch(module, name, value):
            self.saved.append((module, name, getattr(module, name)))
            setattr(module, name, value)

        patch(surveys, "SURVEYS_DIR", root / "surveys")
        patch(surveys, "RESPONSES_DIR", root / "responses")
        patch(surveys, "SESSIONS_DIR", root / "sessions")
        patch(experiment, "SESSIONS_DIR", root / "sessions")
        patch(survey_meta, "RESPONSES_DIR", root / "responses")
        patch(survey_meta, "IMPORTS_DIR", root / "imports")
        patch(survey_meta, "STAGING_DIR", root / "imports" / "_staging")

    def tearDown(self):
        for module, name, value in reversed(self.saved):
            setattr(module, name, value)
        self.tmp.cleanup()

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
        surveys.toggle_survey(survey_id)  # archived → open
        survey = surveys.load_survey(survey_id)
        session = {
            "id": "ETEST01", "survey_id": survey_id, "survey_token": survey["token"],
            "participant_code": "P01", "status": "running", "current_index": 0,
            "sequence": [{"stimulus_id": "3.mp4", "modality": "video", "category": "HVHA"}],
            "responses": [], "created_at": "2026-11-15T21:00:00", "updated_at": "2026-11-15T21:00:00",
        }
        surveys.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        (surveys.SESSIONS_DIR / "ETEST01.json").write_text(
            json.dumps(session, ensure_ascii=False), encoding="utf-8"
        )
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

    def test_web_endpoints(self):
        client = TestClient(app)
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


if __name__ == "__main__":
    unittest.main()
