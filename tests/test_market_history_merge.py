import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts import normalize_data


def bar(day: str, close: float) -> dict:
    stamp = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1000)
    return {"t": stamp, "o": close, "h": close, "l": close, "c": close, "v": 1}


class MarketHistoryMergeTests(unittest.TestCase):
    def test_short_refresh_does_not_truncate_long_backfill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "data/raw/massive/2026-09-10/TEST_1.json"
            new = root / "data/raw/massive/2026-09-11/TEST_2.json"
            old.parent.mkdir(parents=True)
            new.parent.mkdir(parents=True)
            old.write_text(json.dumps({"retrieved_at": "2026-09-10T00:00:00Z", "payload": {"adjusted": True, "results": [bar("2020-01-02", 10), bar("2026-09-10", 20)]}}))
            new.write_text(json.dumps({"retrieved_at": "2026-09-11T00:00:00Z", "payload": {"adjusted": True, "results": [bar("2026-09-10", 21)]}}))
            original = normalize_data.PROJECT_ROOT
            normalize_data.PROJECT_ROOT = root
            try:
                rows = normalize_data.normalize_market(["TEST"])
            finally:
                normalize_data.PROJECT_ROOT = original
            self.assertEqual([row["trade_date"] for row in rows], ["2020-01-02", "2026-09-10"])
            self.assertEqual(rows[-1]["close"], 21)
            self.assertEqual(rows[-1]["source_retrieved_at"], "2026-09-11T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
