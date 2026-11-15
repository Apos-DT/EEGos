import unittest

from fastapi.testclient import TestClient

from webapp.main import app


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_pages_render(self):
        for path in ["/", "/experiment", "/surveys", "/surveys/new", "/media", "/responses", "/eeg", "/audit", "/selection", "/datasets", "/training", "/experiments", "/documents", "/system"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("EEG-EmoStudio", response.text)

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
