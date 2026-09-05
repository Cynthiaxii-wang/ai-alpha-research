#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
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


def save(root: Path, source: str, entity: str, payload: object) -> str:
    path = write_raw_json(
        root,
        source=source,
        entity=entity,
        payload=payload,
        request_metadata={"purpose": "pilot_ingestion"},
    )
    print(f"[{source}] {entity}: {path.relative_to(root)}")
    return str(path.relative_to(root))


def run_call(root: Path, report: list[dict[str, str]], source: str, entity: str, call) -> None:
    try:
        path = save(root, source, entity, call())
        report.append({"source": source, "entity": entity, "status": "ok", "raw_file": path})
    except Exception as exc:
        message = str(exc)
        report.append({"source": source, "entity": entity, "status": "failed", "error": message})
        print(f"[{source}] {entity}: FAILED - {message}", file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest raw pilot data for five AI companies.")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 10, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--tickers", nargs="+", help="Optional subset of pilot tickers.")
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["massive", "alpha_vantage", "sec", "github", "huggingface", "openrouter"],
        choices=["massive", "alpha_vantage", "sec", "github", "huggingface", "openrouter"],
    )
    args = parser.parse_args()
    settings = Settings.from_project_root(PROJECT_ROOT)
    universe = load_pilot_universe(PROJECT_ROOT / "config" / "pilot_universe.csv")
    if args.tickers:
        requested = {ticker.upper() for ticker in args.tickers}
        universe = [company for company in universe if company.ticker in requested]
    report: list[dict[str, str]] = []
    github = GitHubClient(settings)
    huggingface = HuggingFaceClient(settings)
    massive = MassiveClient(settings)
    alpha = AlphaVantageClient(settings)
    sec = SECClient(settings)
    if "openrouter" in args.sources:
        run_call(PROJECT_ROOT, report, "openrouter", "models", OpenRouterClient(settings).models)
    for company in universe:
        if "massive" in args.sources:
            run_call(PROJECT_ROOT, report, "massive", company.ticker, lambda c=company: massive.daily_bars(c.ticker, args.start, args.end))
        if "alpha_vantage" in args.sources:
            run_call(PROJECT_ROOT, report, "alpha_vantage", company.ticker, lambda c=company: alpha.earnings(c.ticker))
        if "sec" in args.sources:
            run_call(PROJECT_ROOT, report, "sec_submissions", company.ticker, lambda c=company: sec.submissions(c.cik))
            run_call(PROJECT_ROOT, report, "sec_companyfacts", company.ticker, lambda c=company: sec.company_facts(c.cik))
        if "github" in args.sources:
            run_call(PROJECT_ROOT, report, "github", company.ticker, lambda c=company: github.public_repositories(c.github_owner, limit=50))
        if "huggingface" in args.sources and company.huggingface_author:
            run_call(PROJECT_ROOT, report, "huggingface", company.ticker, lambda c=company: huggingface.models(c.huggingface_author, limit=50))
    output_dir = PROJECT_ROOT / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "pilot_ingestion_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok_count = sum(row["status"] == "ok" for row in report)
    failed_count = len(report) - ok_count
    print(f"completed={ok_count} failed={failed_count} report={report_path.relative_to(PROJECT_ROOT)}", flush=True)
    return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
