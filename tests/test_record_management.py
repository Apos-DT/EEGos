import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from webapp import record_resources as resources, record_store as store, services
from webapp.config import invalidate
from webapp.main import app
from webapp.routers import records


class RecordManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        mocked = patch.object(store, "STORE_DIR", self.root / "record_management")
        mocked.start(); self.addCleanup(mocked.stop)
        self.client = TestClient(app)
        self.rows = [{"id": "sample/一", "name": "原始名称", "accuracy": .51, "survey_id": "test-survey"},
                     {"id": "sample-two", "name": "另一个名称", "accuracy": .6, "survey_id": "test-survey"}]
        self.source = self.root / "source.json"
        self.source.write_text(json.dumps(self.rows), encoding="utf-8")
        self.original_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        mocked = patch.object(resources, "source_rows", return_value=(self.rows, "id", "name"))
        mocked.start(); self.addCleanup(mocked.stop)
        self.addCleanup(invalidate)

    def change(self, method="PATCH", resource="media", revision=0, **fields):
        endpoint = "item" if method == "PATCH" else fields.pop("operation", "delete")
        return self.client.request(method, f"/api/records/{resource}/{endpoint}", json={
            "id": "sample/一", "revision": revision, **fields,
        })

    def test_edit_query_delete_restore_for_every_resource(self):
        for resource in resources.RESOURCES:
            with self.subTest(resource=resource), patch("webapp.training_monitor.snapshot", return_value={"tasks": []}):
                response = self.change(resource=resource, title="新名称", notes="复现实验", tags=["基线", "基线", " EEG "])
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["metadata"]["tags"], ["基线", "EEG"])
                query = self.client.get(f"/api/records/{resource}", params={"q": "复现实验"}).json()
                self.assertEqual(query["total"], 1)
                self.assertEqual(query["items"][0]["title"], "新名称")
                self.assertEqual(self.change("POST", resource, 1).status_code, 200)
                self.assertEqual(self.client.get(f"/api/records/{resource}").json()["total"], 1)
                trash = self.client.get(f"/api/records/{resource}?view=trash").json()
                self.assertEqual(trash["total"], 1)
                self.assertEqual(self.change("POST", resource, 2, operation="restore").status_code, 200)
                self.assertEqual(self.client.get(f"/api/records/{resource}").json()["total"], 2)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original_hash)
        self.assertEqual(self.rows[0]["accuracy"], .51)

    def test_conflicting_edits_do_not_overwrite_newer_metadata(self):
        self.assertEqual(self.change(title="第一个修改").status_code, 200)
        self.assertEqual(self.change(title="过期修改").status_code, 409)
        current = self.client.get("/api/records/media/item", params={"id": "sample/一"}).json()
        self.assertEqual(current["title"], "第一个修改")
        self.assertEqual(len(store.snapshot()["events"]), 1)

    def test_patch_preserves_unspecified_fields_and_rejects_metric_changes(self):
        self.change(notes="keep notes", tags=["keep tag"])
        self.assertEqual(self.change(revision=1, title="new name").status_code, 200)
        meta = store.metadata("media", "sample/一")
        self.assertEqual(meta["notes"], "keep notes")
        self.assertEqual(meta["tags"], ["keep tag"])
        self.assertEqual(self.change(revision=2, accuracy=.99).status_code, 422)

    def test_pagination_clamps_after_filtering_and_handles_empty_results(self):
        data = self.client.get("/api/records/media?page=999&page_size=1").json()
        self.assertEqual((data["page"], data["pages"], len(data["items"])), (2, 2, 1))
        data = self.client.get("/api/records/media?q=no-such-record&page=999").json()
        self.assertEqual((data["total"], data["page"], data["items"]), (0, 1, []))
        self.assertEqual(self.client.get("/api/records/media?page_size=1000").status_code, 422)

    def test_management_api_uses_existing_access_guard(self):
        with patch("webapp.main.ACCESS_TOKEN", "record-test-token"):
            self.assertEqual(self.client.get("/api/records/media").status_code, 401)
            self.assertEqual(self.client.get("/api/records/media", headers={"x-access-token":"record-test-token"}).status_code, 200)

    def test_missing_records_and_unknown_resources_cannot_be_written(self):
        response = self.client.patch("/api/records/media/item", json={"id": "../../outside", "revision": 0})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get("/api/records/not-registered").status_code, 404)
        self.assertFalse((store.STORE_DIR / "state.json").exists())

    def test_running_task_cannot_be_trashed(self):
        self.rows[0]["status"] = "running"
        self.assertEqual(self.change("POST", "jobs").status_code, 409)
        self.assertEqual(self.change("POST", "eeg_runs").status_code, 409)
        self.assertFalse((store.STORE_DIR / "state.json").exists())

    def test_corrupt_store_is_not_silently_replaced(self):
        store.STORE_DIR.mkdir()
        path = store.STORE_DIR / "state.json"
        path.write_text("broken storage", encoding="utf-8")
        self.assertEqual(self.change(title="new").status_code, 503)
        self.assertEqual(path.read_text(encoding="utf-8"), "broken storage")

    def test_managed_views_filter_trash_and_keep_sources_unchanged(self):
        self.change(title="显示名称", notes="备注")
        rows = store.decorate_rows("media", self.rows)
        self.assertEqual(rows[0]["name"], "显示名称")
        self.assertEqual(self.rows[0]["name"], "原始名称")
        self.change("POST", revision=1)
        self.assertEqual(len(store.decorate_rows("media", self.rows)), 1)
        with store.including_deleted():
            self.assertEqual(len(store.decorate_rows("media", self.rows)), 2)

    def test_existing_experiment_views_update_after_metadata_changes(self):
        experiments = self.root / "experiments"
        run = experiments / "run-one"
        run.mkdir(parents=True)
        metrics = run / "metrics.json"
        metrics.write_text(json.dumps({"model":"DDA-UDDA", "setting":"loso", "overall":{"accuracy":.5}}))
        original = metrics.read_bytes()
        with patch.object(services, "EXPERIMENTS_DIR", experiments), patch.object(services, "ARTIFACTS", self.root):
            invalidate()
            self.assertEqual(services.list_experiments()[0]["label"], "run-one")
            store.update("experiments", "run-one", {"title":"Readable name"}, 0)
            self.assertEqual(services.list_experiments()[0]["label"], "Readable name")
            store.update("experiments", "run-one", {"deleted_at":"2026-11-20"}, 1)
            self.assertEqual(services.list_experiments(), [])
            store.update("experiments", "run-one", {"deleted_at":None}, 2)
            self.assertEqual(len(services.list_experiments()), 1)
        self.assertEqual(metrics.read_bytes(), original)

    def test_trashed_survey_public_link_is_disabled_until_restore(self):
        from webapp import surveys
        fixture = {"id":"test-survey", "token":"public-test-token"}
        with patch.object(surveys, "_all", return_value=[fixture]):
            self.assertEqual(surveys.survey_by_token("public-test-token"), fixture)
            store.update("surveys", fixture["id"], {"deleted_at":"2026-11-20"}, 0)
            with self.assertRaises(FileNotFoundError):
                surveys.survey_by_token("public-test-token")
            store.update("surveys", fixture["id"], {"deleted_at":None}, 1)
            self.assertEqual(surveys.survey_by_token("public-test-token"), fixture)

    def test_uploads_validate_features_and_preserve_document_downloads(self):
        processed = self.root / "processed"
        with patch.object(records, "PROCESSED_DIR", processed):
            bad = self.client.post("/api/records/features/upload?filename=bad.npz", content=b"bad")
            self.assertEqual(bad.status_code, 422)
            self.assertEqual(list(processed.glob("*.npz")), [])
            buffer = io.BytesIO()
            np.savez(buffer, x=np.ones((2, 3, 5)), y=np.array([0, 1]), subjects=np.array(["S01", "S02"]))
            good = self.client.post("/api/records/features/upload?filename=features.npz", content=buffer.getvalue())
            self.assertEqual(good.status_code, 200)
            self.assertEqual(len(list(processed.glob("*.npz"))), 1)
            buffer = io.BytesIO()
            np.savez(buffer, x=np.ones((2, 3, 5)), y=np.array([0]), subjects=np.array(["S01", "S02"]))
            self.assertEqual(self.client.post("/api/records/features/upload?filename=wrong.npz", content=buffer.getvalue()).status_code, 422)
            self.assertEqual(len(list(processed.glob("*.npz"))), 1)
        document = self.client.post("/api/records/documents/upload?filename=notes.txt", content=b"research notes")
        self.assertEqual(document.status_code, 200)
        url = f"/api/records/documents/file/{document.json()['id']}"
        self.assertEqual(self.client.get(url).content, b"research notes")
        self.assertEqual(self.client.get("/api/records/documents/file/../../outside").status_code, 404)


if __name__ == "__main__":
    unittest.main()
