"""Regression checks for Factor Lab neutralisation helpers and public payload."""
import json
import unittest
from pathlib import Path

from scripts.run_hypotheses import grouped_percentile_map, newey_west_mean_t_stat, ols_residuals


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

    def test_newey_west_t_stat_accounts_for_positive_serial_correlation(self):
        values = [0.01, 0.02, 0.03, 0.02, 0.01, -0.01, -0.02, -0.01, 0.01, 0.02]
        independent = newey_west_mean_t_stat(values, 0)
        overlapping = newey_west_mean_t_stat(values, 2)
        self.assertIsNotNone(independent)
        self.assertIsNotNone(overlapping)
        self.assertLess(abs(overlapping), abs(independent))

    def test_public_payload_contains_explanation_controls_and_long_horizons(self):
        payload = json.loads((ROOT / "web/public/data/dashboard.json").read_text(encoding="utf-8"))
        card = payload["hypotheses"]["factor_lab"]["return_prediction"][0]
        self.assertEqual(card["primary_horizon"], "60")
        self.assertEqual(set(card["horizons"]), {"20", "60", "120"})
        self.assertEqual(len(card["control_variants"]), 3)
        self.assertEqual(len(card["component_ablation"]), 4)
        self.assertEqual(len(card["signal_sources"]), 3)
        self.assertEqual(card["robustness"]["leave_one_company_out"]["count"], 38)
        self.assertGreater(card["robustness"]["leave_one_industry_out"]["count"], 1)
        self.assertNotIn("results", card["robustness"]["leave_one_company_out"])
        self.assertNotIn("results", card["robustness"]["leave_one_industry_out"])
        self.assertTrue(card["factor_definition"]["mechanisms"])
        self.assertTrue(card["factor_definition"]["failure_modes"])
        self.assertTrue(card["cumulative_20d"])
        self.assertGreater(card["backtest_scope"]["company_count"], 0)
        self.assertGreater(card["backtest_scope"]["cross_section_count"], 0)
        for horizon in ("20", "60", "120"):
            metrics = card["horizons"][horizon]
            self.assertIn("company_count", metrics)
            self.assertIn("rebalance_periods", metrics)
            self.assertIn("spread_t_stat", metrics)
            self.assertEqual(metrics["spread_t_stat"], metrics["spread_t_stat_hac"])
            self.assertIn("spread_t_stat_naive", metrics)
            self.assertIn("hac_lag", metrics)
            self.assertIn("spread_positive_rate", metrics)


if __name__ == "__main__":
    unittest.main()
