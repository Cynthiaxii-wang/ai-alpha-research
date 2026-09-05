#!/usr/bin/env python3
from __future__ import annotations

import math
import statistics
import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.research_utils import parse_float, read_csv, write_csv  # noqa: E402
from ai_alpha_research.universe import load_universe  # noqa: E402


FEATURE_VERSION = "pilot_v1"
TARGET_VERSION = "next_close_entry_qqq_excess_v1"


def iso_date(value: str) -> date:
    return date.fromisoformat(value)


def forward_metrics(closes: list[float], index: int, horizon: int) -> tuple[float | None, float | None, float | None]:
    entry = index + 1
    end = entry + horizon
    if end >= len(closes):
        return None, None, None
    path = closes[entry : end + 1]
    total_return = path[-1] / path[0] - 1
    daily = [math.log(path[position] / path[position - 1]) for position in range(1, len(path))]
    future_vol = statistics.stdev(daily) * math.sqrt(252) if len(daily) >= 2 else None
    peak = path[0]
    max_drawdown = 0.0
    for value in path:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1)
    return total_return, future_vol, max_drawdown


def build_targets(market_rows: list[dict], company_tickers: list[str], benchmark: str) -> list[dict]:
    by_ticker = defaultdict(list)
    for row in market_rows:
        by_ticker[row["ticker"]].append(row)
    for rows in by_ticker.values():
        rows.sort(key=lambda row: row["trade_date"])
    benchmark_prices = {row["trade_date"]: parse_float(row["close"]) for row in by_ticker[benchmark]}
    output = []
    for ticker in company_tickers:
        rows = by_ticker[ticker]
        closes = [parse_float(row["close"]) for row in rows]
        for index, row in enumerate(rows):
            target = {
                "ticker": ticker,
                "target_date": row["trade_date"],
                "benchmark_ticker": benchmark,
                "target_version": TARGET_VERSION,
                "entry_rule": "next_trading_day_close",
                "ret_1d": None,
                "ret_5d": None,
                "ret_20d": None,
                "ret_60d": None,
                "ret_120d": None,
                "excess_return_20d": None,
                "excess_return_60d": None,
                "excess_return_120d": None,
                "future_vol_20d": None,
                "future_max_drawdown_20d": None,
                "target_available_at": None,
            }
            for horizon in (1, 5, 20, 60, 120):
                result, future_vol, max_drawdown = forward_metrics(closes, index, horizon)
                target[f"ret_{horizon}d"] = result
                if horizon == 20:
                    target["future_vol_20d"] = future_vol
                    target["future_max_drawdown_20d"] = max_drawdown
                end_index = index + 1 + horizon
                if result is not None:
                    start_date = rows[index + 1]["trade_date"]
                    end_date = rows[end_index]["trade_date"]
                    start_benchmark = benchmark_prices.get(start_date)
                    end_benchmark = benchmark_prices.get(end_date)
                    if start_benchmark and end_benchmark and horizon in (20, 60, 120):
                        target[f"excess_return_{horizon}d"] = result - (end_benchmark / start_benchmark - 1)
                    # The row-level timestamp records when the longest currently
                    # populated horizon became observable.  This keeps partially
                    # mature rows auditable instead of leaving their timestamp blank.
                    target["target_available_at"] = rows[end_index]["available_at"]
            output.append(target)
    return output


def add_feature(output: list[dict], ticker: str, feature_date: str, name: str, value, source_period_end: str | None, available_at: str, source: str) -> None:
    if value is None:
        return
    output.append({
        "ticker": ticker,
        "feature_date": feature_date,
        "feature_name": name,
        "feature_value": value,
        "feature_version": FEATURE_VERSION,
        "source_period_end": source_period_end,
        "source_max_available_at": available_at,
        "source": source,
    })


def market_features(market_rows: list[dict], company_tickers: list[str]) -> list[dict]:
    by_ticker = defaultdict(list)
    for row in market_rows:
        if row["ticker"] in company_tickers:
            by_ticker[row["ticker"]].append(row)
    output = []
    for ticker, rows in by_ticker.items():
        rows.sort(key=lambda row: row["trade_date"])
        closes = [parse_float(row["close"]) for row in rows]
        volumes = [parse_float(row["volume"]) for row in rows]
        for index, row in enumerate(rows):
            for horizon in (5, 20, 60):
                value = closes[index] / closes[index - horizon] - 1 if index >= horizon else None
                add_feature(output, ticker, row["trade_date"], f"momentum_{horizon}d", value, row["trade_date"], row["available_at"], "massive")
            if index >= 20:
                daily = [math.log(closes[pos] / closes[pos - 1]) for pos in range(index - 19, index + 1)]
                vol = statistics.stdev(daily) * math.sqrt(252)
                window = volumes[index - 19 : index + 1]
                volume_std = statistics.stdev(window)
                volume_z = (volumes[index] - statistics.fmean(window)) / volume_std if volume_std else 0.0
                add_feature(output, ticker, row["trade_date"], "realized_vol_20d", vol, row["trade_date"], row["available_at"], "massive")
                add_feature(output, ticker, row["trade_date"], "volume_z_20d", volume_z, row["trade_date"], row["available_at"], "massive")
    return output


def event_trade_date(reported_date: date, report_time: str, trading_dates: list[date]) -> date | None:
    if report_time == "pre-market":
        position = bisect_left(trading_dates, reported_date)
    else:
        position = bisect_right(trading_dates, reported_date)
    return trading_dates[position] if position < len(trading_dates) else None


def earnings_features(rows: list[dict], market_rows: list[dict], company_tickers: list[str]) -> list[dict]:
    dates_by_ticker = defaultdict(list)
    for row in market_rows:
        if row["ticker"] in company_tickers:
            dates_by_ticker[row["ticker"]].append(iso_date(row["trade_date"]))
    output = []
    for row in rows:
        if row["ticker"] not in company_tickers or row["reported_date"] < "2024-09-01":
            continue
        feature_date = event_trade_date(iso_date(row["reported_date"]), row["report_time"], dates_by_ticker[row["ticker"]])
        if not feature_date:
            continue
        add_feature(output, row["ticker"], feature_date.isoformat(), "earnings_surprise", parse_float(row["surprise"]), row["fiscal_period_end"], row["available_at"], "alpha_vantage_unverified_pit")
        add_feature(output, row["ticker"], feature_date.isoformat(), "earnings_surprise_pct", parse_float(row["surprise_pct"]), row["fiscal_period_end"], row["available_at"], "alpha_vantage_unverified_pit")
    return output


def next_trading_date(after: date, trading_dates: list[date]) -> date | None:
    position = bisect_right(trading_dates, after)
    return trading_dates[position] if position < len(trading_dates) else None


def fundamental_features(rows: list[dict], market_rows: list[dict], company_tickers: list[str]) -> list[dict]:
    dates_by_ticker = defaultdict(list)
    for row in market_rows:
        if row["ticker"] in company_tickers:
            dates_by_ticker[row["ticker"]].append(iso_date(row["trade_date"]))
    output = []
    fields = ("revenue_yoy", "capex_yoy", "free_cash_flow_yoy", "fcf_margin", "capex_to_revenue")
    for row in rows:
        if row["ticker"] not in company_tickers or not row["available_date"]:
            continue
        feature_date = next_trading_date(iso_date(row["available_date"]), dates_by_ticker[row["ticker"]])
        if not feature_date:
            continue
        for field in fields:
            add_feature(output, row["ticker"], feature_date.isoformat(), field, parse_float(row[field]), row["period_end"], row["available_date"] + "T23:59:59Z", "sec_edgar")
    return output


def valuation_features(annual_rows: list[dict], unadjusted_market_rows: list[dict], company_tickers: list[str]) -> list[dict]:
    """Build daily filing-aware P/S and P/FCF from SEC per-share fundamentals."""
    annual_by_ticker = defaultdict(list)
    for row in annual_rows:
        # Filing-basis valuation is only comparable when the filing currency
        # matches the USD-listed security basis.  TWD IFRS fundamentals remain
        # useful for growth/margin analysis but not for the ADR P/S proxy.
        if row["ticker"] in company_tickers and row.get("valuation_available_date") and row.get("financial_currency", "USD") == "USD":
            annual_by_ticker[row["ticker"]].append(row)
    for rows in annual_by_ticker.values():
        rows.sort(key=lambda row: row["valuation_available_date"])

    output = []
    for market in unadjusted_market_rows:
        ticker = market["ticker"]
        if ticker not in company_tickers:
            continue
        candidates = annual_by_ticker.get(ticker, [])
        available_dates = [row["valuation_available_date"] for row in candidates]
        position = bisect_right(available_dates, market["trade_date"]) - 1
        if position < 0:
            continue
        annual = candidates[position]
        price = parse_float(market["close_unadjusted"])
        sales_per_share = parse_float(annual.get("sales_per_diluted_share"))
        fcf_per_share = parse_float(annual.get("fcf_per_diluted_share"))
        available_at = market["available_at"]
        if price is not None and sales_per_share and sales_per_share > 0:
            add_feature(output, ticker, market["trade_date"], "price_to_sales_filing_basis", price / sales_per_share, annual["period_end"], available_at, "massive_unadjusted_sec_edgar")
        if price is not None and fcf_per_share and fcf_per_share > 0:
            add_feature(output, ticker, market["trade_date"], "price_to_fcf_filing_basis", price / fcf_per_share, annual["period_end"], available_at, "massive_unadjusted_sec_edgar")
    return output


def developer_features(rows: list[dict]) -> list[dict]:
    output = []
    fields = (
        "github_repositories_returned", "github_total_stars", "github_total_forks",
        "github_total_open_issues", "github_active_repos_90d", "hf_models_returned",
        "hf_total_downloads_top50", "hf_total_likes_top50",
    )
    for row in rows:
        feature_date = row["snapshot_at"][:10]
        for field in fields:
            add_feature(output, row["ticker"], feature_date, field, parse_float(row[field]), feature_date, row["snapshot_at"], "github_huggingface_snapshot")
    return output


def developer_monthly_features(rows: list[dict], market_rows: list[dict], company_tickers: list[str]) -> list[dict]:
    dates_by_ticker = defaultdict(list)
    for row in market_rows:
        if row["ticker"] in company_tickers:
            dates_by_ticker[row["ticker"]].append(iso_date(row["trade_date"]))
    histories = defaultdict(list)
    for row in rows:
        if row["history_complete_within_window"].lower() == "true":
            histories[row["ticker"]].append(row)
    output = []
    for ticker, history in histories.items():
        history.sort(key=lambda row: row["month_end"])
        for index, row in enumerate(history):
            feature_date = next_trading_date(iso_date(row["month_end"]), dates_by_ticker[ticker])
            if not feature_date:
                continue
            commits = parse_float(row["commit_count"]) or 0.0
            releases = parse_float(row["release_count"]) or 0.0
            add_feature(output, ticker, feature_date.isoformat(), "github_selected_repo_commits_1m", commits, row["month_end"], row["month_end"] + "T23:59:59Z", "github_dated_history")
            add_feature(output, ticker, feature_date.isoformat(), "github_selected_repo_releases_1m", releases, row["month_end"], row["month_end"] + "T23:59:59Z", "github_dated_history")
            if index >= 3:
                baseline = statistics.fmean(parse_float(prior["commit_count"]) or 0.0 for prior in history[index - 3:index])
                change = math.log1p(commits) - math.log1p(baseline)
                add_feature(output, ticker, feature_date.isoformat(), "github_selected_repo_commit_change_3m", change, row["month_end"], row["month_end"] + "T23:59:59Z", "github_dated_history")
    return output


def deduplicate_features(rows: list[dict]) -> list[dict]:
    """Keep the newest observation known on a feature date for each natural key."""
    selected = {}
    for row in rows:
        key = (row["ticker"], row["feature_date"], row["feature_name"], row["feature_version"])
        ordering = (row["source_max_available_at"] or "", row["source_period_end"] or "")
        if key not in selected or ordering > selected[key][0]:
            selected[key] = (ordering, row)
    return [item[1] for item in selected.values()]


def main() -> int:
    standardized = PROJECT_ROOT / "data" / "standardized"
    market = read_csv(standardized / "market_daily.csv")
    earnings = read_csv(standardized / "earnings.csv")
    annual = read_csv(standardized / "fundamental_annual.csv")
    unadjusted_market = read_csv(standardized / "market_unadjusted_daily.csv")
    developer = read_csv(standardized / "developer_snapshot.csv")
    developer_monthly_path = standardized / "developer_monthly_activity.csv"
    developer_monthly = read_csv(developer_monthly_path) if developer_monthly_path.exists() else []
    universe_path = PROJECT_ROOT / "config" / "research_universe.csv"
    if not universe_path.exists():
        universe_path = PROJECT_ROOT / "config" / "pilot_universe.csv"
    company_tickers = [company.ticker for company in load_universe(universe_path)]
    targets = build_targets(market, company_tickers, "QQQ")
    features = market_features(market, company_tickers)
    features.extend(earnings_features(earnings, market, company_tickers))
    features.extend(fundamental_features(annual, market, company_tickers))
    features.extend(valuation_features(annual, unadjusted_market, company_tickers))
    features.extend(developer_features(developer))
    features.extend(developer_monthly_features(developer_monthly, market, company_tickers))
    features = deduplicate_features(features)
    features.sort(key=lambda row: (row["feature_date"], row["ticker"], row["feature_name"]))
    research = PROJECT_ROOT / "data" / "research"
    write_csv(research / "targets.csv", targets, list(targets[0]))
    write_csv(research / "feature_store.csv", features, list(features[0]))
    print(f"targets={len(targets)} features={len(features)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
