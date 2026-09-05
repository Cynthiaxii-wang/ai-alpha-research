#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.clients import MassiveClient  # noqa: E402
from ai_alpha_research.config import Settings  # noqa: E402
from ai_alpha_research.storage import write_raw_json  # noqa: E402
from ai_alpha_research.universe import load_universe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest unadjusted closes for filing-basis valuation only.")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 10, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--tickers", nargs="+")
    args = parser.parse_args()
    universe = load_universe(PROJECT_ROOT / "config" / "research_universe.csv")
    if args.tickers:
        requested = {ticker.upper() for ticker in args.tickers}
        universe = [company for company in universe if company.ticker in requested]
    client = MassiveClient(Settings.from_project_root(PROJECT_ROOT))
    report = []
    for company in universe:
        try:
            payload = client.daily_bars(company.ticker, args.start, args.end, adjusted=False)
            path = write_raw_json(PROJECT_ROOT, source="massive_unadjusted", entity=company.ticker, payload=payload, request_metadata={"purpose": "filing_basis_valuation", "adjusted": False})
            report.append({"ticker": company.ticker, "status": "ok", "raw_file": str(path.relative_to(PROJECT_ROOT))})
            print(f"[massive_unadjusted] {company.ticker}: {path.relative_to(PROJECT_ROOT)}", flush=True)
        except Exception as exc:
            report.append({"ticker": company.ticker, "status": "failed", "error": str(exc)})
            print(f"[massive_unadjusted] {company.ticker}: FAILED - {exc}", file=sys.stderr, flush=True)
    path = PROJECT_ROOT / "data" / "processed" / "unadjusted_price_ingestion_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = sum(row["status"] != "ok" for row in report)
    print(f"completed={len(report) - failures} failed={failures}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
