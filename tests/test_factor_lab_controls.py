"""Regression checks for Factor Lab neutralisation helpers and public payload."""
import json
import unittest
from pathlib import Path

from scripts.run_hypotheses import grouped_percentile_map, ols_residuals


ROOT = Path(__file__).resolve().parents[1]


class FactorLabControlTests(unittest.TestCase):
    def test_percentiles_are_computed_within_stage(self):
        values = {"U1": 10, "U2": 20, "D1": 100, "D2": 200}
        stages = {"U1": "upstream", "U2": "upstream", "D1": "downstream", "D2": "downstream"}
        ranked = grouped_percentile_map(values, stages)
        self.assertEqual(ranked, {"U1": 0.0, "U2": 1.0, "D1": 0.0, "D2": 1.0})

    def test_ols_residual_removes_control_exposure(self):
        control = {f"T{i}": float(i) for i in range(8)}
        values = {ticker: 2.0 + 3.0 * value for ticker, value in control.items()}
        residuals = ols_residuals(values, [control])
        self.assertEqual(set(residuals), set(values))
        self.assertLess(max(abs(value) for value in residuals.values()), 1e-6)

    def test_public_payload_contains_explanation_controls_and_long_horizons(self):
        payload = json.loads((ROOT / "web/public/data/dashboard.json").read_text(encoding="utf-8"))
        card = payload["hypotheses"]["factor_lab"]["return_prediction"][0]
        self.assertEqual(card["primary_horizon"], "60")
        self.assertEqual(set(card["horizons"]), {"20", "60", "120"})
        self.assertEqual(len(card["control_variants"]), 3)
        self.assertTrue(card["factor_definition"]["mechanisms"])
        self.assertTrue(card["factor_definition"]["failure_modes"])
        self.assertTrue(card["cumulative_20d"])


if __name__ == "__main__":
    unittest.main()
