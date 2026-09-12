import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ai_alpha_research.scoring import classify_signal, weighted_score


class ScoringTests(unittest.TestCase):
    def test_missing_component_is_reweighted_not_zero_filled(self):
        result = weighted_score({"growth": 0.8, "quality": None}, {"growth": 0.5, "quality": 0.5})
        self.assertAlmostEqual(result["score"], 0.8)
        self.assertAlmostEqual(result["coverage"], 0.5)
        self.assertEqual(result["effective_weights"], {"growth": 1.0})

    def test_complete_weighted_score(self):
        result = weighted_score({"a": 1.0, "b": 0.0}, {"a": 0.75, "b": 0.25})
        self.assertAlmostEqual(result["score"], 0.75)
        self.assertAlmostEqual(result["coverage"], 1.0)

    def test_signal_classification_enforces_coverage_and_quadrants(self):
        self.assertEqual(classify_signal(0.9, 0.1, 0.6)[0], "Data gap")
        self.assertEqual(classify_signal(0.9, 0.1, 1.0)[0], "Fundamental dislocation")
        self.assertEqual(classify_signal(0.9, 0.8, 1.0)[0], "Momentum")
        self.assertEqual(classify_signal(0.3, 0.8, 1.0)[0], "Expectation risk")
        self.assertEqual(classify_signal(0.3, 0.2, 1.0)[0], "Deteriorating")


if __name__ == "__main__":
    unittest.main()
