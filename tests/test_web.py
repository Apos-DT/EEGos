import unittest

from fastapi.testclient import TestClient

from webapp.main import app


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_pages_render(self):
        for path in ["/", "/surveys", "/survey-data", "/surveys/new", "/media", "/eeg", "/audit", "/selection", "/datasets", "/training", "/experiments", "/documents", "/system"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("EEG-EmoStudio", response.text)

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


if __name__ == "__main__":
    unittest.main()
