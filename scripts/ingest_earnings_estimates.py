#!/usr/bin/env python3
"""Collect current Alpha Vantage earnings-estimate and revision snapshots."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_alpha_research.config import Settings  # noqa: E402
from ai_alpha_research.http import get_json  # noqa: E402
from ai_alpha_research.storage import write_raw_json  # noqa: E402
from ai_alpha_research.universe import load_universe  # noqa: E402


def main() -> int:
    settings = Settings.from_project_root(ROOT)
    universe = load_universe(ROOT / "config" / "research_universe.csv")
    report = []
    for company in universe:
        try:
            payload = get_json(
                "https://www.alphavantage.co/query",
                params={"function": "EARNINGS_ESTIMATES", "symbol": company.ticker, "apikey": settings.alpha_vantage_api_key},
            )
            if not isinstance(payload, dict) or "estimates" not in payload:
                message = payload.get("Information") or payload.get("Note") or "missing estimates"
                raise RuntimeError(message)
            path = write_raw_json(
                ROOT, source="alpha_vantage_estimates", entity=company.ticker, payload=payload,
                request_metadata={"function": "EARNINGS_ESTIMATES", "purpose": "signal_monitor"},
            )
            report.append({"ticker": company.ticker, "status": "ok", "rows": len(payload["estimates"]), "raw_file": str(path.relative_to(ROOT))})
            print(f"[estimate] {company.ticker}: {len(payload['estimates'])} rows", flush=True)
        except Exception as exc:
            raw_error = str(exc)
            rate_limited = "rate limit" in raw_error.lower() or "frequency" in raw_error.lower()
            safe_error = "Alpha Vantage daily rate limit reached" if rate_limited else "Alpha Vantage request failed"
            report.append({"ticker": company.ticker, "status": "failed", "error": safe_error})
            print(f"[estimate] {company.ticker}: FAILED - {safe_error}", file=sys.stderr, flush=True)
            if rate_limited:
                break
    output = ROOT / "data" / "processed" / "earnings_estimates_ingestion_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = sum(row["status"] == "ok" for row in report)
    print(f"completed={ok} failed={len(report)-ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
