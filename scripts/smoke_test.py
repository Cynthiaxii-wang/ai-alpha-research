#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.clients import (  # noqa: E402
    AlphaVantageClient,
    GitHubClient,
    HuggingFaceClient,
    MassiveClient,
    OpenRouterClient,
    SECClient,
)
from ai_alpha_research.config import Settings  # noqa: E402
from ai_alpha_research.storage import write_raw_json  # noqa: E402
from ai_alpha_research.universe import load_pilot_universe  # noqa: E402


def payload_size(payload: object) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("results", "data", "quarterlyEarnings"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
        return len(payload)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Test configured API connectivity without exposing credentials.")
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["github", "huggingface", "massive", "alpha_vantage", "sec_submissions", "openrouter"],
        choices=["github", "huggingface", "massive", "alpha_vantage", "sec_submissions", "openrouter"],
    )
    args = parser.parse_args()
    settings = Settings.from_project_root(PROJECT_ROOT)
    company = load_pilot_universe(PROJECT_ROOT / "config" / "pilot_universe.csv")[0]
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=30)
    calls = {
        "github": lambda: GitHubClient(settings).public_repositories(company.github_owner, limit=10),
        "huggingface": lambda: HuggingFaceClient(settings).models(company.huggingface_author, limit=10),
        "massive": lambda: MassiveClient(settings).daily_bars(company.ticker, start, end),
        "alpha_vantage": lambda: AlphaVantageClient(settings).earnings(company.ticker),
        "sec_submissions": lambda: SECClient(settings).submissions(company.cik),
        "openrouter": lambda: OpenRouterClient(settings).models(),
    }
    report: dict[str, object] = {
        "pilot_company": company.ticker,
        "configured_variables": settings.configured_key_names(),
        "checks": {},
    }
    failed = False
    for source in args.sources:
        call = calls[source]
        try:
            payload = call()
            path = write_raw_json(
                PROJECT_ROOT,
                source=source,
                entity=company.ticker if source != "openrouter" else "models",
                payload=payload,
                request_metadata={"purpose": "connectivity_smoke_test"},
            )
            report["checks"][source] = {
                "status": "ok",
                "records_or_top_level_items": payload_size(payload),
                "raw_file": str(path.relative_to(PROJECT_ROOT)),
            }
        except Exception as exc:  # safe client exceptions redact credentials
            failed = True
            report["checks"][source] = {"status": "failed", "error": str(exc)}
    output_dir = PROJECT_ROOT / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "connectivity_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
