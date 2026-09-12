import csv
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UniverseScopeTests(unittest.TestCase):
    def test_core_dashboard_and_extended_backtest_scopes_are_separate(self):
        with (ROOT / "config" / "research_universe.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        research = [row for row in rows if (row.get("include_in_research") or "true").lower() == "true"]
        dashboard = [row for row in rows if (row.get("include_in_dashboard") or "true").lower() == "true"]
        self.assertEqual(len(research), 40)
        self.assertEqual(len(dashboard), 20)
        self.assertTrue(all(row["ticker"] in {item["ticker"] for item in research} for row in dashboard))


if __name__ == "__main__":
    unittest.main()
