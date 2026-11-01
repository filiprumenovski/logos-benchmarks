"""Tests of the latency summary. Run: python3 -m unittest discover eval"""
import json
import tempfile
import unittest
from pathlib import Path

import latency


class Percentile(unittest.TestCase):
    def test_linear_interpolation(self):
        v = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(latency.percentile(v, 0.5), 2.5)
        self.assertAlmostEqual(latency.percentile(v, 0.99), 3.97)
        self.assertEqual(latency.percentile(v, 1.0), 4.0)
        self.assertEqual(latency.percentile([7.0], 0.5), 7.0)


class Summary(unittest.TestCase):
    def test_synthetic_replay(self):
        rows = [{"e2e_us": 500.0 * (i + 1), "search_us": 500.0, "exact": i != 3, "decision_match": True, "fire": i % 2 == 0}
                for i in range(100)]
        rows[50]["e2e_us"] = 90000.0  # one decision over the 80 ms budget
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            p.write_text("".join(json.dumps(r) + "\n" for r in rows))
            out = latency.summarize(p)
        self.assertEqual(out["decisions"], 100)
        self.assertEqual(out["over_80_ms"], 1)
        self.assertEqual(out["over_5_ms"], 90)  # 5.5 to 50 ms, and the 90 ms decision
        self.assertEqual(out["exact_rows"], 99)
        self.assertEqual(out["decisions_matching_reference"], 100)
        self.assertEqual(out["triggers"], 50)
        self.assertEqual(out["e2e_ms"]["max"], 90.0)
        self.assertEqual(out["stage_median_ms"]["search"], 0.5)

    def test_missing_decision_flag_is_not_counted_as_a_match(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            p.write_text(json.dumps({"e2e_us": 1500.0, "exact": True}) + "\n")
            self.assertIsNone(latency.summarize(p)["decisions_matching_reference"])


if __name__ == "__main__":
    unittest.main()
