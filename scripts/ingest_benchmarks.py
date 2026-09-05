#!/usr/bin/env python3
from __future__ import annotations

import csv
import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.clients import MassiveClient  # noqa: E402
from ai_alpha_research.config import Settings  # noqa: E402
from ai_alpha_research.storage import write_raw_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest benchmark price history.")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 10, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    settings = Settings.from_project_root(PROJECT_ROOT)
    with (PROJECT_ROOT / "config" / "benchmarks.csv").open(encoding="utf-8", newline="") as handle:
        benchmarks = list(csv.DictReader(handle))
    client = MassiveClient(settings)
    for benchmark in benchmarks:
        ticker = benchmark["ticker"]
        payload = client.daily_bars(ticker, args.start, args.end)
        path = write_raw_json(
            PROJECT_ROOT,
            source="massive",
            entity=ticker,
            payload=payload,
            request_metadata={"purpose": "benchmark_ingestion"},
        )
        print(f"[massive] {ticker}: {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
