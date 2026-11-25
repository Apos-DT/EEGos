from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
from auth_client import WorkspaceClient

from webapp.main import app


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = WorkspaceClient(app)

    def test_pages_render(self):
        for path in ["/", "/surveys", "/survey-data", "/surveys/new", "/media", "/eeg", "/audit", "/selection", "/datasets", "/training", "/experiments", "/documents", "/system"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("EmoStudio", response.text)

    def test_surveys_render_legacy_rows_without_record_metadata(self):
        legacy = {"id":"legacy", "title":"Legacy survey", "status":"open",
                  "description":"", "n_materials":1, "n_questions":3, "n_responses":2,
                  "n_video":1, "n_audio":0, "schema_version":1,
                  "created_at":"2026-11-16", "updated_at":"2026-11-16", "public_path":"/q/legacy"}
        with patch("webapp.routers.survey.list_surveys", return_value=[legacy]):
            response = self.client.get("/surveys")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Legacy survey", response.text)

    def test_legacy_experiment_pages_redirect(self):
        """旧版现场实验与统计页已下线，统一收敛到问卷数据页。"""

        for path in ["/experiment", "/responses"]:
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response.headers["location"], "/survey-data")
        home = self.client.get("/").text
        self.assertNotIn("现场实验（旧版）", home)
        self.assertIn("/survey-data", home)

    def test_core_apis(self):
        for path in ["/api/health", "/api/overview", "/api/audit", "/api/selection", "/api/datasets", "/api/experiments", "/api/docs", "/api/experiment/sessions", "/api/experiment/responses", "/api/media", "/api/surveys", "/api/eeg/uploads"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIsInstance(response.json(), dict)

    def test_document_download_scope(self):
        self.assertEqual(self.client.get("/files/docx/02").status_code, 200)
        self.assertEqual(self.client.get("/files/pdf/02").status_code, 200)
        self.assertEqual(self.client.get("/files/docx/99").status_code, 404)
        self.assertEqual(self.client.get("/files/audit/../../etc/passwd").status_code, 404)

    def test_invalid_training_request_rejected(self):
        response = self.client.post(
            "/api/train/run",
            json={
                "dataset_id": "missing",
                "model": "dualview",
                "setting": "loso",
                "epochs": 1,
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_non_eeg_catalog_ids_cannot_start_eeg_jobs(self):
        sources = self.client.get("/api/datasets/catalog").json()["datasets"]
        excluded = {row["id"] for row in sources if row["eeg_preparation"] == "no_eeg"}
        self.assertTrue({"meld", "emorynlp", "noxi", "iemocap"} <= excluded)
        with patch("webapp.routers.datasets.manager.submit") as submit:
            for source_id in excluded:
                with self.subTest(source=source_id):
                    response = self.client.post("/api/features/run", json={"raw_id": source_id})
                    self.assertEqual(response.status_code, 404)
                    response = self.client.post("/api/train/run", json={"dataset_id": source_id})
                    self.assertEqual(response.status_code, 404)
        submit.assert_not_called()

    def test_eeg_raw_upload_checks_modality_and_arrays_before_save(self):
        arrays = {
            "x": np.ones((2, 3, 200), dtype=np.float32),
            "y": [0, 1], "subjects": ["S1", "S2"], "fs": 200,
        }

        def upload(filename="trial.npz", confirmed=True, **overrides):
            body = BytesIO()
            np.savez_compressed(body, **{**arrays, **overrides})
            return self.client.post("/api/raw/upload", content=body.getvalue(), params={
                "filename": filename, "eeg_confirmed": confirmed,
            })

        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw_dir = root / "raw"
            with patch("webapp.routers.datasets.ROOT", root), patch("webapp.routers.datasets.RAW_DIR", raw_dir):
                self.assertEqual(upload(filename="annotations.csv").status_code, 400)
                self.assertEqual(upload(confirmed=False).status_code, 400)
                self.assertEqual(upload(modality="audio").status_code, 400)
                self.assertEqual(upload(feature_names=["DE"]).status_code, 400)
                self.assertEqual(upload(y=[0]).status_code, 400)
                self.assertFalse(raw_dir.exists())

                response = upload()
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue((raw_dir / "trial.npz").is_file())
                response = upload(filename="declared.npz", modality="EEG", confirmed=False)
                self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()
