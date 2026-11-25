import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webapp import dashboard, record_store, survey_db
from webapp.db import transaction
from webapp.questionnaire import schema_fingerprint, schema_for_survey


class DashboardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {"EEG_DB_PATH": str(self.root / "dashboard.sqlite3")})
        environment.start()
        self.addCleanup(environment.stop)
        patches = (
            patch.object(dashboard, "SEED_IV_DIR", self.root),
            patch.object(record_store, "STORE_DIR", self.root),
            patch.object(dashboard.services, "_count_eeg_files", return_value=0),
            patch.object(dashboard.services, "sync_experiments", return_value="fixture"),
            patch.object(dashboard.services, "list_feature_datasets", return_value=[]),
        )
        for replacement in patches:
            replacement.start()
            self.addCleanup(replacement.stop)

    def add_run(self, run_id, model, dataset, accuracy, *, f1=None, demo=False, metadata=None, protocol=None):
        details = {
            "id": run_id, "label": run_id, "model": model, "n_samples": 1080, "n_subjects": 15,
            "setting": "loso", "setting_label": "LOSO", "created_at": "2026-11-23T18:40:00+08:00",
            "report_url": "", "is_demo": demo,
        }
        overall = {"accuracy": accuracy}
        if f1 is not None:
            overall["macro_f1"] = f1
        metrics = {"overall": overall, "protocol": protocol or {}}
        with transaction(write=True) as conn:
            conn.execute("""
                INSERT INTO experiment_runs (
                    scope, run_id, output_path, artifact_signature, model, setting, dataset,
                    created_at, is_demo, summary_json, metrics_json, metadata_json
                ) VALUES ('fixture', ?, '', 'fixture', ?, 'loso', ?, ?, ?, ?, ?, ?)
            """, (run_id, model, dataset, details["created_at"], demo, json.dumps(details), json.dumps(metrics),
                  json.dumps(metadata or {})))

    def test_dataset_scope_and_real_benchmark(self):
        self.add_run("dda", "DDA-UDDA", "SEED-IV", 0.5, f1=0.5064,
                     protocol={"selection_uses_target_test_accuracy": True})
        self.add_run("demo", "demo", None, 0.9, f1=0.99, demo=True)
        self.add_run("seediv_trial_mlp_loso", "mlp", None, 0.4278, f1=0.4291)
        self.add_run("known-path", "mlp", str(self.root / "signal.npz"), 0.4)
        self.add_run("named", "model", "DEAP", 0.2, f1=0.3)
        self.add_run("deleted", "DDA-SDDA", "SEED-IV", 0.9, f1=0.9)
        record_store.update("experiments", "deleted", {"deleted_at": "2026-11-23"}, 0)
        features = [
            {"id": "experiment-trials", "name": "SEED-IV trials", "source": "SEED-IV",
             "path": dashboard._LEGACY_FEATURES[("seediv_trial_mlp_loso", "mlp", 1080)], "kind": "processed"},
            {"id": "custom-input", "name": "Local input", "source": "自定义",
             "path": str(self.root / "signal.npz"), "kind": "processed"},
        ]
        with patch.object(dashboard.services, "list_feature_datasets", return_value=features):
            seed = dashboard.get_dashboard_context("SEED_IV")
            self.assertEqual(seed["dataset"], "seed-iv")
            self.assertEqual({run["id"] for run in seed["runs"]}, {"dda", "seediv_trial_mlp_loso"})
            self.assertEqual(seed["benchmark"]["score"], 0.5064)
            self.assertEqual(seed["benchmark"]["metric"], "macro_f1")
            self.assertIn("按目标测试集选模", seed["benchmark"]["label"])
            self.assertEqual(seed["phase"]["best_loso"]["id"], "seediv_trial_mlp_loso")
            self.assertEqual(seed["phase"]["best_loso"]["modalities"], ["EEG"])
            self.assertIsNone(seed["phase"]["gain"])
            self.assertEqual(seed["ablation"], [])
            custom = dashboard.get_dashboard_context("feature:custom-input")
            self.assertEqual(custom["phase"]["feature_sets"], 1)
            self.assertEqual([run["dataset_label"] for run in custom["runs"]], ["Local input"])
            self.assertIsNone(custom["runs"][0]["macro_f1"])
            self.assertEqual(dashboard.get_dashboard_context("DEAP")["runs"][0]["dataset"], "source:deap")
            self.assertEqual(dashboard.get_dashboard_context("meld")["runs"], [])
            self.assertEqual(dashboard.get_dashboard_context("unknown")["runs"], [])

    def test_questionnaire_versions_and_explicit_collection_batch(self):
        original = schema_for_survey({
            "schema": [{"id": "valence", "title": "效价", "type": "rating", "role": "valence", "min": 1, "max": 9}],
        })
        survey = {
            "id": "survey", "title": "试采集", "token": "fixture", "created_at": "2026-11-25",
            "schema_version": 2, "schema": [{**original[0], "max": 5}],
            "schema_history": [{"version": 1, "schema_hash": schema_fingerprint(original), "schema": original}],
            "materials": [{"stimulus_id": "movie.mp4", "modality": "video"}],
            "collection_batch_id": "2026Q4", "collection_batch_name": "自采 2026Q4",
        }
        session = {
            "id": "session", "survey_id": survey["id"], "participant_code": "S00", "status": "aborted",
            "sequence": survey["materials"], "created_at": "2026-11-25T09:00:00",
        }
        legacy = {
            "id": "separate", "participant_code": "S01", "status": "completed",
            "created_at": "2026-11-25T08:00:00", "responses": [{"valence": 1}],
        }
        response = {"response_id": "verified", "session_id": session["id"], "schema_version": 1,
                    "schema_hash": schema_fingerprint(original), "normalized": {"valence": 8}}
        with transaction(write=True) as conn:
            survey_db.save_survey(conn, survey)
            survey_db.save_session(conn, session)
            survey_db.save_session(conn, legacy)
            survey_db.save_responses(conn, survey["id"], [
                response,
                {**response, "response_id": "deleted", "normalized": {"valence": 1}},
                {**response, "response_id": "different_scale", "schema_version": 2, "normalized": {"valence": 5}},
                {**response, "response_id": "invalid", "valid": False},
            ])
        record_store.update("responses", "deleted", {"deleted_at": "2026-11-25"}, 0)
        data = dashboard.get_dashboard_context("batch:2026Q4")
        self.assertIn({"id": "batch:2026Q4", "label": "自采 2026Q4"}, data["dataset_options"])
        self.assertEqual(data["phase"]["responses"], 3)
        self.assertEqual(data["phase"]["stimuli"], 1)
        self.assertEqual(data["session_status"], {"completed": 0, "running": 0, "interrupted": 1})
        self.assertEqual(data["label_distribution"]["total"], 1)
        self.assertEqual(data["label_distribution"]["positive"], 1)
        self.assertEqual(data["sessions"][0]["modalities"], ["量表"])
        self.assertEqual(data["sessions"][0]["stimuli"], ["视频刺激"])
        self.assertFalse(next(mode for mode in data["modalities"] if mode["label"] == "Video")["ready"])
        self.assertEqual(dashboard.get_dashboard_context()["label_distribution"]["negative"], 1)
        self.assertEqual(dashboard.get_dashboard_context("seed-iv")["sessions"], [])

    def test_ablation_requires_identical_evaluation_id(self):
        metadata = {"ablation_group": "matched", "evaluation_id": "same-subjects-and-trials"}
        self.add_run("eeg", "EEG model", "SEED-IV", 0.43, metadata={**metadata, "modalities": ["EEG"]})
        self.add_run("face", "Video model", "SEED-IV", 0.41, metadata={**metadata, "modalities": ["Face"]})
        fusion = {**metadata, "modalities": ["EEG", "Face"], "fusion": "FLF"}
        self.add_run("different-evaluation", "Fusion", "SEED-IV", 0.52,
                     metadata={**fusion, "evaluation_id": "different-trials"})
        self.assertEqual(dashboard.get_dashboard_context()["ablation"], [])
        self.add_run("matched-evaluation", "Fusion", "SEED-IV", 0.54, metadata=fusion)
        data = dashboard.get_dashboard_context("seed-iv")
        self.assertEqual([row["value"] for row in data["ablation"]], [0.43, 0.41, 0.54])
        self.assertAlmostEqual(data["phase"]["gain"], 0.11)
