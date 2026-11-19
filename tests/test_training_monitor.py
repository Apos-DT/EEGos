import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import webapp.training_monitor as monitor


class TrainingMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.experiments = self.root / "experiments"
        self.jobs = self.root / "jobs"
        self.experiments.mkdir(); self.jobs.mkdir()
        self.out = self.experiments / "run with spaces"
        self.out.mkdir()
        self.patches = [patch.object(monitor, "ROOT", self.root), patch.object(monitor, "ARTIFACTS", self.root),
            patch.object(monitor, "EXPERIMENTS_DIR", self.experiments), patch.object(monitor, "WEB_JOBS_DIR", self.jobs),
            patch.object(monitor.manager, "list", return_value=[]),
            patch.object(monitor, "gpu_snapshot", return_value={"available":False,"devices":[]})]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.reset_cache)
        self.reset_cache()

    def reset_cache(self):
        monitor._cache = {}; monitor._cache_at = 0

    def proc(self, pid, parent=0):
        return {"ProcessId":pid,"ParentProcessId":parent,"started_at":"2026-11-20T00:00:00+08:00",
                "CommandLine":f'python run_seed4_dda.py --output-dir "{self.out}" --epochs 600 --max-folds 45'}

    def save(self, path, data):
        path.write_text(json.dumps(data),encoding="utf-8")

    def test_wrapper_deduplicated_and_legacy_progress_unknown(self):
        with patch.object(monitor, "processes", return_value=[self.proc(1),self.proc(2,1)]):
            result=monitor.snapshot()
        self.assertEqual(result["active_count"],1)
        task=result["tasks"][0]
        self.assertEqual(task["pid"],2)
        self.assertEqual(task["progress"]["total_folds"],45)
        self.assertIsNone(task["progress"]["fraction"])
        self.assertFalse(result["gpu"]["available"])

    def test_observed_worker_exit_is_not_left_running(self):
        with patch.object(monitor,"processes",return_value=[self.proc(1)]): monitor.snapshot()
        self.reset_cache()
        with patch.object(monitor,"processes",return_value=[]): result=monitor.snapshot()
        self.assertEqual(result["active_count"],0)
        self.assertEqual(result["tasks"][0]["status"],"interrupted")

    def test_completed_sidecar_overrides_stale_running_job(self):
        self.save(self.jobs/"j.json",{"id":"j","kind":"external_reproduction","status":"running","runtime":{"output":str(self.out)}})
        self.save(self.out/"run_meta.json",{"status":"success","finished_at":"2026-11-20T00:02:00+08:00"})
        with patch.object(monitor,"processes",return_value=[]): result=monitor.snapshot()
        self.assertEqual(result["tasks"][0]["status"],"success")
        self.assertEqual(result["active_count"],0)

    def test_new_fold_does_not_inherit_previous_epoch(self):
        self.save(self.out/"progress.json",{"planned_folds":3,"folds":[{"fold":1}]})
        self.save(self.out/"heartbeat.json",{"fold":2,"epoch":None,"event":"fold_started","at":"2026-11-20T00:02:00+08:00"})
        (self.out/"timeline.jsonl").write_text(json.dumps({"event":"epoch_evaluated","epoch":600})+"\n"+json.dumps({"event":"fold_started","fold":2}),encoding="utf-8")
        progress=monitor._progress(self.out,{"algorithm":"UDDA","epochs":600},"running")
        self.assertIsNone(progress["epoch"])
        self.assertEqual(progress["current_fold"],2)
        self.assertAlmostEqual(progress["fraction"],1/3)


if __name__ == "__main__": unittest.main()
