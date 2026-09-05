#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.research_utils import load_envelope, write_csv  # noqa: E402


def month_end(value: str) -> str:
    observed = date.fromisoformat(value[:10])
    if observed.month == 12:
        following = date(observed.year + 1, 1, 1)
    else:
        following = date(observed.year, observed.month + 1, 1)
    return date.fromordinal(following.toordinal() - 1).isoformat()


def month_ends_between(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start[:10]).replace(day=1)
    final = date.fromisoformat(end[:10]).replace(day=1)
    output = []
    while current <= final:
        output.append(month_end(current.isoformat()))
        current = date(current.year + (current.month == 12), 1 if current.month == 12 else current.month + 1, 1)
    return output


def main() -> int:
    report_path = PROJECT_ROOT / "data" / "processed" / "github_history_ingestion_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    events = []
    monthly = defaultdict(lambda: {"commits": 0, "releases": 0})
    metadata = {}
    for item in report:
        if item["status"] != "ok":
            continue
        ticker = item["ticker"]
        metadata[ticker] = item
        seen_sha = set()
        for relative in item["commit_files"]:
            envelope = load_envelope(PROJECT_ROOT / relative)
            for commit in envelope["payload"]:
                sha = commit.get("sha")
                if sha in seen_sha:
                    continue
                seen_sha.add(sha)
                committed_at = (((commit.get("commit") or {}).get("committer") or {}).get("date"))
                if not committed_at:
                    continue
                events.append({"ticker": ticker, "repo": item["repo"], "event_type": "commit", "event_id": sha, "event_at": committed_at, "source_retrieved_at": envelope["retrieved_at"], "proxy_scope": "selected_company_open_source_repository"})
                monthly[(ticker, month_end(committed_at))]["commits"] += 1
        envelope = load_envelope(PROJECT_ROOT / item["release_file"])
        for release in envelope["payload"]:
            released_at = release.get("published_at") or release.get("created_at")
            if not released_at or not item["since"][:10] <= released_at[:10] <= item["until"][:10]:
                continue
            events.append({"ticker": ticker, "repo": item["repo"], "event_type": "release", "event_id": release.get("id"), "event_at": released_at, "source_retrieved_at": envelope["retrieved_at"], "proxy_scope": "selected_company_open_source_repository"})
            monthly[(ticker, month_end(released_at))]["releases"] += 1
    events.sort(key=lambda row: (row["event_at"], row["ticker"], row["event_type"]))
    monthly_rows = []
    for ticker, item in sorted(metadata.items()):
        for period_end in month_ends_between(item["since"], item["until"]):
            counts = monthly[(ticker, period_end)]
            monthly_rows.append({
                "ticker": ticker,
                "repo": item["repo"],
                "month_end": period_end,
                "commit_count": counts["commits"],
                "release_count": counts["releases"],
                "history_complete_within_window": item["commit_history_complete_within_window"],
                "selection_rule": item["selection_rule"],
                "factor_hypothesis": "dated_company_open_source_activity_may_lead_product_or_earnings_signals",
            })
    root = PROJECT_ROOT / "data" / "standardized"
    write_csv(root / "github_activity_events.csv", events, list(events[0]))
    write_csv(root / "developer_monthly_activity.csv", monthly_rows, list(monthly_rows[0]))
    print(f"events={len(events)} monthly_rows={len(monthly_rows)} companies={len(metadata)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
