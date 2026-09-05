#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.clients import GitHubClient  # noqa: E402
from ai_alpha_research.config import Settings  # noqa: E402
from ai_alpha_research.research_utils import latest_raw, load_envelope  # noqa: E402
from ai_alpha_research.storage import write_raw_json  # noqa: E402
from ai_alpha_research.universe import load_universe  # noqa: E402


def select_repo(payload: list[dict]) -> dict | None:
    eligible = [repo for repo in payload if not repo.get("fork") and not repo.get("archived")]
    return max(eligible, key=lambda repo: repo.get("stargazers_count") or 0) if eligible else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect dated GitHub commit/release history for a transparent company OSS proxy.")
    parser.add_argument("--since", default="2024-10-01T00:00:00Z")
    parser.add_argument("--until", default=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--tickers", nargs="+")
    args = parser.parse_args()
    companies = load_universe(PROJECT_ROOT / "config" / "research_universe.csv")
    if args.tickers:
        requested = {ticker.upper() for ticker in args.tickers}
        companies = [company for company in companies if company.ticker in requested]
    report_path = PROJECT_ROOT / "data" / "processed" / "github_history_ingestion_report.json"
    client = GitHubClient(Settings.from_project_root(PROJECT_ROOT))
    report = []
    for company in companies:
        if not company.github_owner:
            report.append({"ticker": company.ticker, "status": "not_applicable", "reason": "no_verified_github_owner"})
            continue
        try:
            repo = select_repo(load_envelope(latest_raw(PROJECT_ROOT, "github", company.ticker))["payload"])
            if not repo:
                report.append({"ticker": company.ticker, "status": "not_applicable", "reason": "no_eligible_repository"})
                continue
            full_name = repo["full_name"]
            commit_files = []
            total_commits = 0
            history_complete = False
            for page in range(1, args.max_pages + 1):
                payload = client.commits(full_name, since=args.since, until=args.until, page=page)
                path = write_raw_json(PROJECT_ROOT, source="github_commits", entity=f"{company.ticker}_{page}", payload=payload, request_metadata={"repo": full_name, "since": args.since, "until": args.until, "page": page})
                commit_files.append(str(path.relative_to(PROJECT_ROOT)))
                total_commits += len(payload)
                if len(payload) < 100:
                    history_complete = True
                    break
            releases = client.releases(full_name)
            release_path = write_raw_json(PROJECT_ROOT, source="github_releases", entity=company.ticker, payload=releases, request_metadata={"repo": full_name, "limit": 100})
            report.append({
                "ticker": company.ticker,
                "status": "ok",
                "repo": full_name,
                "selection_rule": "highest_starred_nonfork_nonarchived_among_50_most_recently_updated_owner_repos",
                "since": args.since,
                "until": args.until,
                "commit_count_collected": total_commits,
                "commit_history_complete_within_window": history_complete,
                "commit_files": commit_files,
                "release_file": str(release_path.relative_to(PROJECT_ROOT)),
            })
            print(f"[github_history] {company.ticker} {full_name}: commits={total_commits} complete={history_complete} releases={len(releases)}", flush=True)
        except Exception as exc:
            report.append({"ticker": company.ticker, "status": "failed", "error": str(exc)})
            print(f"[github_history] {company.ticker}: FAILED - {exc}", file=sys.stderr, flush=True)
    if args.tickers and report_path.exists():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        replaced = {row["ticker"] for row in report}
        report = [row for row in previous if row["ticker"] not in replaced] + report
    report.sort(key=lambda row: row["ticker"])
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = sum(row["status"] == "failed" for row in report)
    print(f"ok={sum(row['status'] == 'ok' for row in report)} not_applicable={sum(row['status'] == 'not_applicable' for row in report)} failed={failures}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
