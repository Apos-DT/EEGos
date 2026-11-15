import unittest

import numpy as np

from eeg_emostudio.data.splits import assert_no_subject_leakage, loso_splits, subject_dependent_split


class SplitTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(0)
        self.subjects = np.repeat([f"S{i:02d}" for i in range(4)], 20)
        self.y = np.tile(np.repeat(np.arange(4), 5), 4)
        self.x = rng.normal(size=(len(self.y), 4, 3)).astype(np.float32)

    def test_loso_has_no_subject_leakage(self):
        folds = loso_splits(self.y, self.subjects, val_fraction=0.2, seed=1)
        self.assertEqual(len(folds), 4)
        for fold in folds:
            assert_no_subject_leakage(fold, self.subjects)
            self.assertTrue(len(fold["train_idx"]) > 0)
            self.assertTrue(len(fold["val_idx"]) > 0)
            self.assertTrue(len(fold["test_idx"]) > 0)

    def test_each_sample_is_held_out_once(self):
        folds = loso_splits(self.y, self.subjects, seed=2)
        held_out = np.concatenate([fold["test_idx"] for fold in folds])
        self.assertEqual(len(held_out), len(self.subjects))
        self.assertEqual(len(set(held_out.tolist())), len(self.subjects))

    def test_subject_dependent_split_covers_all_samples(self):
        split = subject_dependent_split(self.y, self.subjects, seed=3)
        all_idx = np.concatenate(list(split.values()))
        self.assertEqual(sorted(all_idx.tolist()), list(range(len(self.y))))


if __name__ == "__main__":
    unittest.main()
