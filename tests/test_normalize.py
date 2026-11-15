import unittest

from eeg_emostudio.audit.normalize import (
    canonical_stimulus_id,
    normalize_rater,
    parse_clock_seconds,
    parse_issue_cell,
    parse_rating,
)


class NormalizeTests(unittest.TestCase):
    def test_canonical_ids_and_known_typo(self):
        self.assertEqual(canonical_stimulus_id("12.mp4", "video"), "12.mp4")
        self.assertEqual(canonical_stimulus_id("388.mp4", "video"), "38.mp4")
        self.assertEqual(canonical_stimulus_id("118mp3", "audio"), "118.mp3")
        self.assertIsNone(canonical_stimulus_id("0.mp4", "video"))
        self.assertIsNone(canonical_stimulus_id("abc", "video"))

    def test_rating_anchors(self):
        self.assertEqual(parse_rating("非常不愉快"), 1.0)
        self.assertEqual(parse_rating("非常愉快"), 9.0)
        self.assertEqual(parse_rating("非常平静"), 1.0)
        self.assertEqual(parse_rating("非常激烈"), 9.0)
        self.assertEqual(parse_rating("7"), 7.0)
        self.assertIsNone(parse_rating("11"))
        self.assertIsNone(parse_rating(""))

    def test_clock_and_excel_fraction(self):
        self.assertAlmostEqual(parse_clock_seconds("1:43"), 103.0)
        self.assertAlmostEqual(parse_clock_seconds("01:10:00"), 4200.0)
        self.assertAlmostEqual(parse_clock_seconds(0.5), 43200.0)
        self.assertIsNone(parse_clock_seconds("bad"))

    def test_issue_union_and_contradiction(self):
        severity, tags, contradictory = parse_issue_cell("没有问题┋画面模糊")
        self.assertAlmostEqual(severity, 0.8 * 0.9, places=4)
        self.assertIn("模糊", tags)
        self.assertTrue(contradictory)

    def test_rater_name_cleanup(self):
        self.assertEqual(normalize_rater("张涵博·"), "张涵博")
        self.assertEqual(normalize_rater(" 张 涵 博 "), "张涵博")


if __name__ == "__main__":
    unittest.main()
