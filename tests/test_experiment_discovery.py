import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from auth_client import WorkspaceClient

from webapp import services
from webapp.config import invalidate
from webapp.main import app


class ExperimentDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.experiments = self.root / "experiments"
        self.experiments.mkdir()
        mocked_db = patch.dict(os.environ, {"EEG_DB_PATH": str(self.root / "test.sqlite3")})
        mocked_db.start()
        self.addCleanup(mocked_db.stop)
        for name, value in (("ARTIFACTS", self.root), ("EXPERIMENTS_DIR", self.experiments)):
            mocked = patch.object(services, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        invalidate("experiments")
        self.addCleanup(invalidate, "experiments")
        self.client = WorkspaceClient(app)

    def write_metrics(self, run, accuracy):
        (run / "metrics.json").write_text(json.dumps({
            "model": "DDA-UDDA", "setting": "loso",
            "overall": {"accuracy": accuracy},
        }), encoding="utf-8")

    def test_finished_run_appears_after_list_was_read_during_training(self):
        run = self.experiments / "new-dda-run"
        run.mkdir()
        self.assertEqual(self.client.get("/api/experiments").json()["count"], 0)

        self.write_metrics(run, .5)
        payload = self.client.get("/api/experiments").json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["experiments"][0]["id"], run.name)
        self.assertIn(run.name, self.client.get("/experiments").text)

        (run / "report.html").write_text("<p>Training report</p>", encoding="utf-8")
        record = self.client.get("/api/experiments").json()["experiments"][0]
        self.assertTrue(record["has_report"])
        self.assertEqual(self.client.get(record["report_url"]).status_code, 200)

        self.write_metrics(run, .61234)
        record = self.client.get("/api/experiments").json()["experiments"][0]
        self.assertEqual(record["accuracy"], .61234)
        self.assertEqual(self.client.get(f"/api/experiments/{run.name}").json()["overall"]["accuracy"], .61234)
        (run / "metrics.json").unlink()
        self.assertEqual(self.client.get("/api/experiments").json()["count"], 0)

    def test_demo_metrics_are_watched_outside_experiments_directory(self):
        demo = self.root / "demo"
        demo.mkdir()
        self.assertEqual(services.list_experiments(), [])
        self.write_metrics(demo, .8)
        record = services.list_experiments()[0]
        self.assertEqual(record["id"], "demo")
        self.assertTrue(record["is_demo"])
