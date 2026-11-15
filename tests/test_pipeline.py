import shutil
import unittest
from pathlib import Path

import numpy as np

from eeg_emostudio.data.features import compute_de_features
from eeg_emostudio.demo import make_synthetic_raw
from eeg_emostudio.pipeline import build_features_from_raw
from eeg_emostudio.training.trainer import TrainConfig, run_loso


class PipelineTests(unittest.TestCase):
    def test_de_shape(self):
        rng = np.random.default_rng(1)
        epochs = rng.normal(size=(3, 4, 400))
        features, starts = compute_de_features(epochs, fs=200, window_s=1.0, step_s=0.5)
        self.assertEqual(features.shape[0], 3)
        self.assertEqual(features.shape[2], 4)
        self.assertEqual(features.shape[3], 5)
        self.assertGreater(features.shape[1], 0)
        self.assertTrue(np.isfinite(features).all())

    def test_raw_to_features_to_training(self):
        temp_path = Path(__file__).resolve().parent.parent / "artifacts" / "_test_tmp"
        if temp_path.exists():
            shutil.rmtree(temp_path)
        temp_path.mkdir(parents=True)
        try:
            raw = make_synthetic_raw(
                n_subjects=3, n_per_class=3, n_channels=4, n_classes=3, fs=100, seconds=4
            )
            np.savez_compressed(temp_path / "raw.npz", **raw)
            summary = build_features_from_raw(
                temp_path / "raw.npz", temp_path / "features.npz", window_s=1.0, step_s=1.0
            )
            self.assertEqual(summary["n_bands"], 5)
            from eeg_emostudio.data.manifest import load_features

            data = load_features(temp_path / "features.npz")
            config = TrainConfig(epochs=2, batch_size=8, patience=2, hidden=8, seed=0)
            result = run_loso(
                data["x"],
                data["y"],
                data["subjects"],
                model_name="dualview",
                config=config,
                class_names=data["class_names"],
            )
            self.assertIn("overall", result)
            self.assertEqual(result["n_subjects"], 3)
            self.assertGreaterEqual(result["overall"]["accuracy"], 0.0)
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
