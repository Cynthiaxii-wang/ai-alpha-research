#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.research_utils import parse_float, read_csv  # noqa: E402
from ai_alpha_research.universe import load_universe  # noqa: E402


def duplicate_count(rows: list[dict], fields: tuple[str, ...]) -> int:
    counts = Counter(tuple(row[field] for field in fields) for row in rows)
    return sum(count - 1 for count in counts.values() if count > 1)


def main() -> int:
    standardized = PROJECT_ROOT / "data" / "standardized"
    research = PROJECT_ROOT / "data" / "research"
    market = read_csv(standardized / "market_daily.csv")
    earnings = read_csv(standardized / "earnings.csv")
    fundamentals = read_csv(standardized / "fundamental_observations.csv")
    annual = read_csv(standardized / "fundamental_annual.csv")
    quarterly = read_csv(standardized / "fundamental_quarterly.csv")
    developer = read_csv(standardized / "developer_snapshot.csv")
    features = read_csv(research / "feature_store.csv")
    targets = read_csv(research / "targets.csv")
    companies = [company.ticker for company in load_universe(PROJECT_ROOT / "config" / "research_universe.csv")]
    dates = defaultdict(set)
    for row in market:
        dates[row["ticker"]].add(row["trade_date"])
    qqq_dates = dates["QQQ"]
    failures = []
    company_date_mismatches = {ticker: len(dates[ticker] ^ qqq_dates) for ticker in companies}
    if any(company_date_mismatches.values()):
        failures.append("company_benchmark_date_mismatch")
    duplicate_checks = {
        "market_ticker_date": duplicate_count(market, ("ticker", "trade_date")),
        "target_ticker_date_version": duplicate_count(targets, ("ticker", "target_date", "target_version")),
        "feature_ticker_date_name_version": duplicate_count(features, ("ticker", "feature_date", "feature_name", "feature_version")),
        "quarterly_ticker_period_end": duplicate_count(quarterly, ("ticker", "period_end")),
    }
    if any(duplicate_checks.values()):
        failures.append("duplicate_primary_key")
    feature_date_violations = [
        row for row in features
        if row["source_max_available_at"] and row["source_max_available_at"][:10] > row["feature_date"]
    ]
    if feature_date_violations:
        failures.append("feature_available_after_feature_date")
    mature_20d = sum(parse_float(row["ret_20d"]) is not None for row in targets)
    mature_60d = sum(parse_float(row["ret_60d"]) is not None for row in targets)
    missing_qqq_excess = sum(
        parse_float(row["ret_20d"]) is not None and parse_float(row["excess_return_20d"]) is None
        for row in targets
    )
    if missing_qqq_excess:
        failures.append("mature_target_missing_benchmark_return")
    mature_20d_missing_available_at = sum(
        parse_float(row["ret_20d"]) is not None and not row["target_available_at"]
        for row in targets
    )
    if mature_20d_missing_available_at:
        failures.append("mature_target_missing_available_at")
    annual_tickers = {row["ticker"] for row in annual}
    fundamental_coverage_missing = sorted(set(companies) - annual_tickers)
    quarterly_tickers = {row["ticker"] for row in quarterly}
    quarterly_coverage_missing = sorted(set(companies) - quarterly_tickers)
    quarterly_timing_violations = sum(
        bool(row.get("available_date")) and row["available_date"] < row["period_end"]
        for row in quarterly
    )
    quarterly_negative_core_values = sum(
        (parse_float(row.get("revenue")) is not None and parse_float(row.get("revenue")) < 0)
        or (parse_float(row.get("capex")) is not None and parse_float(row.get("capex")) < 0)
        for row in quarterly
    )
    if quarterly_timing_violations or quarterly_negative_core_values:
        failures.append("quarterly_fundamental_integrity")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not failures else "fail",
        "status_scope": "engineering_integrity_checks_only",
        "research_readiness": "exploratory_only",
        "failures": failures,
        "row_counts": {
            "market_daily": len(market),
            "earnings": len(earnings),
            "fundamental_observations": len(fundamentals),
            "fundamental_annual": len(annual),
            "fundamental_quarterly": len(quarterly),
            "developer_snapshot": len(developer),
            "feature_store": len(features),
            "targets": len(targets),
        },
        "duplicate_checks": duplicate_checks,
        "company_benchmark_date_mismatches": company_date_mismatches,
        "feature_available_date_violations": len(feature_date_violations),
        "mature_targets": {"20d": mature_20d, "60d": mature_60d},
        "mature_20d_missing_qqq_excess": missing_qqq_excess,
        "mature_20d_missing_available_at": mature_20d_missing_available_at,
        "fundamental_coverage_missing": fundamental_coverage_missing,
        "quarterly_fundamental_coverage_missing": quarterly_coverage_missing,
        "quarterly_available_date_violations": quarterly_timing_violations,
        "quarterly_negative_revenue_or_capex": quarterly_negative_core_values,
        "known_research_limitations": [
            "Twenty-company research universe and short history remain too limited for production inference.",
            "Alpha Vantage historical estimated EPS is not independently verified as archived PIT consensus.",
            "Developer/model adoption begins with a 2026-09-02 current snapshot.",
            "Total capex is not a clean AI-capex measure.",
            "Filing-basis P/S and P/FCF are free-data proxies with residual split/restatement convention risk.",
            "TSM IFRS/TWD fundamentals are normalized for growth and margin analysis but excluded from the USD ADR valuation proxy.",
            "TSM currently lacks sufficiently structured quarterly 6-K facts in SEC Companyfacts; quarterly lead-lag tests cover 19 US filers.",
            "Engineering PASS does not mean institutional-grade data or validated investment alpha.",
            "Daily overlapping forward-return labels are not independent observations.",
            "Automatically selected GitHub repositories are company open-source proxies and require analyst review.",
        ],
    }
    path = research / "research_quality_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
