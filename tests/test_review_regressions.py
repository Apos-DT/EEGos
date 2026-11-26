"""Regression cases identified during the system review."""
import csv
import io
import unittest
from unittest.mock import patch

import numpy as np

from eeg_emostudio.data.splits import loso_splits, subject_dependent_split, trial_groups
from webapp import questionnaire, survey_meta, surveys
from test_questionnaire import RepositoryTests as RepositoryFixture


class SurveyReviewTests(RepositoryFixture):
    def test_retry_returns_original_receipt_after_completion(self):
        _, survey_id = self._import()
        survey = surveys.load_survey(survey_id)
        survey["status"] = "open"
        survey["schema"] = questionnaire.normalize_schema([
            {"id": "rating", "type": "rating", "title": "评分", "min": 0, "max": 10}
        ])
        survey["schema_hash"] = questionnaire.schema_fingerprint(survey["schema"])
        surveys._save(survey)
        self._seed_session({
            "id": "RETRY", "survey_id": survey_id, "survey_token": survey["token"],
            "participant_code": "P1", "status": "running", "current_index": 0,
            "sequence": [{"stimulus_id": "1.mp4", "modality": "video"}],
            "responses": [], "created_at": "2026-11-27", "updated_at": "2026-11-27",
        })
        arguments = dict(expected_index=0, schema_hash=survey["schema_hash"])
        first = surveys.submit_schema_answers(survey["token"], "RETRY", {"rating": "0"}, **arguments)
        second = surveys.submit_schema_answers(survey["token"], "RETRY", {"rating": "0"}, **arguments)
        self.assertEqual(first["response_id"], second["response_id"])
        self.assertEqual(second["session"]["current_index"], 1)
        with self.assertRaises(ValueError):
            surveys.submit_schema_answers(survey["token"], "RETRY", {"rating": "10"}, **arguments)

    def test_retired_roles_are_preserved_in_export(self):
        _, survey_id = self._import()
        before = surveys.load_survey(survey_id)
        questions = [dict(q) for q in before["schema"]]
        questions[2]["role"] = "intensity"
        surveys.update_survey(survey_id, "改版", "", schema=questions)
        metadata = survey_meta.survey_metadata(survey_id)
        self.assertEqual(metadata["n_responses"], 0)
        rows = list(csv.DictReader(io.StringIO(survey_meta.export_clean_csv(survey_id))))
        self.assertTrue(rows)
        self.assertEqual(rows[0]["n_intensity"], "")
        self.assertTrue(rows[0]["n_valence"])

    def test_scale_endpoints_and_empty_values(self):
        for low, high in [(0, 10), (1, 5), (1, 9)]:
            question = {"type": "rating", "min": low, "max": high}
            for value in [low, high]:
                self.assertEqual(questionnaire.normalize_answer(question, str(value)), value)
            self.assertIsNone(questionnaire.normalize_answer(question, ""))
            self.assertIsNone(questionnaire.normalize_answer(question, str(high + 1)))

    def test_database_search_can_reach_oldest_of_5001_responses(self):
        from webapp import survey_db
        from webapp.db import transaction
        _, survey_id = self._import()
        survey = surveys.load_survey(survey_id)
        records = [survey_meta.build_response_record(survey, {}, strict=False) for _ in range(5001)]
        records[0]["rater"] = "oldest-unique-rater"
        with transaction(write=True) as conn:
            survey_db.save_responses(conn, survey_id, records)
        result = survey_db.query_responses(survey_id, query="oldest-unique-rater")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["responses"][0]["response_id"], records[0]["response_id"])


class SplitReviewTests(unittest.TestCase):
    def test_subject_dependent_cli_finishes_with_report_and_checkpoint(self):
        import json
        import tempfile
        from pathlib import Path
        import torch
        from eeg_emostudio.cli import main
        from eeg_emostudio.data.manifest import write_feature_dataset
        from eeg_emostudio.models.registry import build_model
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subjects = np.repeat(["S1", "S2", "S3"], 60)
            trials = np.tile(np.repeat(np.arange(12).astype(str), 5), 3)
            y = np.tile(np.repeat(np.tile([0, 1], 6), 5), 3)
            x = np.random.default_rng(4).normal(size=(180, 4, 5))
            write_feature_dataset(root / "input.npz", x, y, subjects,
                                  trial_ids=trials, class_names=["a", "b"])
            output = root / "run"
            self.assertEqual(main(["train", "--data", str(root / "input.npz"),
                "--out", str(output), "--model", "mlp", "--epochs", "1",
                "--setting", "subject-dependent", "--device", "cpu"]), 0)
            self.assertTrue((output / "report.html").exists())
            self.assertEqual(json.loads((output / "run_meta.json").read_text())["status"], "success")
            checkpoint = torch.load(output / "checkpoint.pt", weights_only=True)
            model = build_model("mlp", checkpoint["n_channels"], checkpoint["n_features"],
                                checkpoint["n_classes"], hidden=checkpoint["config"]["hidden"],
                                dropout=checkpoint["config"]["dropout"])
            model.load_state_dict(checkpoint["state_dict"])
            model.eval()
            indices = checkpoint["split_indices"]["test_idx"]
            transformed = (x[indices] - np.asarray(checkpoint["scaler"]["mean"])) / np.asarray(checkpoint["scaler"]["std"])
            with torch.no_grad():
                predictions = model(torch.tensor(transformed, dtype=torch.float32)).argmax(1).numpy()
            with np.load(output / "test_predictions.npz") as stored:
                np.testing.assert_array_equal(predictions, stored["y_pred"])

    def test_windows_are_grouped_and_loso_validation_holds_subjects(self):
        subjects = np.repeat(["S1", "S2", "S3"], 60)
        trials = np.tile(np.repeat(np.arange(12).astype(str), 5), 3)
        labels = np.tile(np.repeat(np.tile([0, 1], 6), 5), 3)
        split = subject_dependent_split(labels, subjects, trial_ids=trials)
        groups = trial_groups(subjects, trial_ids=trials)
        sets = [set(groups[indices]) for indices in split.values()]
        self.assertFalse(sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
        for fold in loso_splits(labels, subjects, trial_ids=trials):
            self.assertFalse(set(subjects[fold["train_idx"]]) & set(subjects[fold["val_idx"]]))

    def test_historic_subject_dependent_metrics_are_indexed(self):
        from pathlib import Path
        from webapp.services import _experiment_info
        info = _experiment_info(Path("old-run"), {"setting": "subject-dependent",
            "test_metrics": {"accuracy": 0.5, "macro_f1": 0.4}}, {})
        self.assertEqual(info["accuracy"], 0.5)

    def test_backup_restore_preserves_database_and_files(self):
        import sqlite3
        from contextlib import closing
        import tempfile
        from pathlib import Path
        from scripts.backup_workspace import backup, restore, verify
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            database = data / "workspace.sqlite3"
            with closing(sqlite3.connect(database)) as conn:
                conn.execute("CREATE TABLE samples(id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO samples VALUES (1)")
                conn.commit()
            (data / "report.txt").write_text("test report", encoding="utf-8")
            backup(database, {"data": data}, root / "backup")
            restore(root / "backup", root / "restored")
            verify(root / "restored")
            with closing(sqlite3.connect(root / "restored/database.sqlite3")) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM samples").fetchone()[0], 1)
            self.assertEqual((root / "restored/data/report.txt").read_text(), "test report")


# unittest discovery should only inherit the fixture through the concrete class.
del RepositoryFixture
