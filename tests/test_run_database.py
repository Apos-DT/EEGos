import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webapp import run_store
from webapp.db import transaction
from webapp.jobs import MAX_LOG_LINES, JobManager


class RunDatabaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        override = patch.dict(os.environ, {"EEG_DB_PATH": str(self.root / "test.sqlite3")})
        override.start()
        self.addCleanup(override.stop)

    def test_migration_does_not_duplicate_or_replay_logs(self):
        old_jobs = self.root / "jobs"
        old_jobs.mkdir()
        job_file = old_jobs / "j.json"
        observed_file = self.root / "observed.json"
        legacy = {"id": "j", "kind": "train", "title": "old", "status": "success",
                  "logs": ["start", "finish"], "params": {"epochs": 4}}
        job_file.write_text(json.dumps(legacy), encoding="utf-8")
        observed_file.write_text(json.dumps({str(self.root / "run"): {
            "started_at": "2026-11-23T09:00:00", "params": {"epochs": 3},
        }}), encoding="utf-8")
        original = job_file.read_bytes()
        run_store.migrate_legacy(old_jobs, observed_file)
        run_store.append_job_logs("j", [("2026-11-23T09:01:00", "verified")])
        run_store.migrate_legacy(old_jobs, observed_file)

        self.assertEqual(run_store.read_job("j")["logs"], ["start", "finish", "verified"])
        self.assertEqual(run_store.read_job("j")["params"], {"epochs": 4})
        self.assertEqual(len(run_store.list_observations()), 1)
        self.assertEqual(job_file.read_bytes(), original)

    def test_completed_job_and_full_log_survive_new_manager(self):
        first = JobManager(workers=1)
        self.addCleanup(first._executor.shutdown)

        def produce(job):
            for number in range(MAX_LOG_LINES + 3):
                first.log(job, f"log {number}")
            return {"kind": "train", "run_id": "run-one"}

        submitted = first.submit("train", "training fixture", produce, {"epochs": 5})
        first._executor.shutdown(wait=True)
        second = JobManager()
        self.addCleanup(second._executor.shutdown)
        loaded = second.get(submitted.id)
        self.assertEqual(loaded.status, "success")
        self.assertEqual(loaded.result["run_id"], "run-one")
        self.assertEqual(len(loaded.logs), MAX_LOG_LINES)
        self.assertTrue(loaded.logs[-1].startswith("[完成]"))
        with transaction() as conn:
            total = conn.execute("SELECT count(*) FROM job_logs WHERE job_id = ?", (submitted.id,)).fetchone()[0]
            self.assertEqual(total, MAX_LOG_LINES + 4)
        self.assertEqual(second.list()[0].id, submitted.id)

    def test_orphaned_job_is_recovered_after_restart(self):
        run_store.save_job({"id": "orphan", "kind": "train", "status": "queued"})
        restarted = JobManager()
        self.addCleanup(restarted._executor.shutdown)
        self.assertEqual(restarted.get("orphan").status, "interrupted")
        self.assertEqual(run_store.read_job("orphan")["status"], "interrupted")
