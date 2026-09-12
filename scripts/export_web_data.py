#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.warehouse import read_table, warehouse_path  # noqa: E402
from ai_alpha_research.demand_chain import build_demand_chain
from ai_alpha_research.scoring import (  # noqa: E402
    FUNDAMENTAL_SCORE_VERSION,
    FUNDAMENTAL_WEIGHTS,
    MIN_SCORE_COVERAGE,
    MARKET_SCORE_VERSION,
    MARKET_WEIGHTS,
    STRONG_FUNDAMENTAL_THRESHOLD,
    STRONG_MARKET_THRESHOLD,
    classify_signal,
    weighted_score,
)

LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def read_csv(path: Path) -> list[dict]:
    if warehouse_path(PROJECT_ROOT).exists():
        table_name = {"research_universe": "company_master"}.get(path.stem, path.stem)
        try:
            return read_table(PROJECT_ROOT, table_name)
        except Exception as exc:
            if "does not exist" not in str(exc).lower():
                raise
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def median(values):
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    middle = len(clean) // 2
    return clean[middle] if len(clean) % 2 else (clean[middle - 1] + clean[middle]) / 2


def percentile_rank(values, value, higher_is_better=True):
    clean = sorted(item for item in values if item is not None)
    if value is None or not clean:
        return None
    if len(clean) == 1:
        result = 0.5
    else:
        below = sum(item < value for item in clean)
        equal = sum(item == value for item in clean)
        result = (below + (equal - 1) / 2) / (len(clean) - 1)
    return result if higher_is_better else 1 - result


def average(values):
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def normalize_event_brief(brief: dict) -> dict:
    """Export only the explicit v2 event clocks and source classification.

    The legacy field migration is narrow: old `publishedDate` already denoted
    the event date and old `publishedAt` already denoted the source timestamp.
    Missing event dates are never inferred from generation/retrieval metadata.
    """
    output = {**brief, "eventSchemaVersion": 2}
    if not output.get("brief_date"):
        try:
            output["brief_date"] = datetime.fromisoformat(output["asOf"].replace("Z", "+00:00")).astimezone(LOCAL_TZ).date().isoformat()
        except (KeyError, TypeError, ValueError):
            output["brief_date"] = None
    events = []
    for source in brief.get("events", []):
        event_date = source.get("event_date") or source.get("publishedDate")
        source_published_at = source.get("source_published_at") or source.get("publishedAt")
        if not event_date or not source_published_at:
            continue
        event = {key: value for key, value in source.items() if key not in {"publishedDate", "publishedAt"}}
        event["event_date"] = event_date
        event["source_published_at"] = source_published_at
        event["sourceType"] = source.get("sourceType") or ("media" if source.get("sourceTier") == "B" else "official")
        events.append(event)
    output["events"] = events
    output["eventCount"] = len(events)
    return output


def latest_raw_payload(source: str, ticker: str):
    paths = sorted((PROJECT_ROOT / "data" / "raw" / source).glob(f"*/{ticker}_*.json"))
    if not paths:
        return None, None
    envelope = json.loads(paths[-1].read_text(encoding="utf-8"))
    return envelope.get("payload"), envelope.get("retrieved_at")


def build_alternative_pulse(rows: list[dict], as_of: str) -> list[dict]:
    eligible = [row for row in rows if row.get("available_at", "")[:10] <= as_of]
    series = defaultdict(list)
    for row in eligible:
        value = number(row.get("metric_value"))
        if value is None:
            continue
        series[row["series_id"]].append({**row, "value": value})
    for observations in series.values():
        observations.sort(key=lambda row: row["observation_end"])

    def latest(series_id):
        observations = series.get(series_id, [])
        return observations[-1] if observations else None

    def prior(series_id, days):
        observations = series.get(series_id, [])
        if not observations:
            return None
        target = date.fromisoformat(observations[-1]["observation_end"]) - timedelta(days=days)
        candidates = [row for row in observations if date.fromisoformat(row["observation_end"]) <= target]
        return candidates[-1] if candidates else None

    cards = []
    capex = latest("csp_capex_top4")
    capex_prior = prior("csp_capex_top4", 330)
    if capex and capex_prior:
        cards.append({
            "id": "csp-capex", "eyebrow": "CAPITAL CYCLE", "title": "北美四大 CSP 季度 Capex",
            "value": f"${capex['value']:.1f}bn", "change": capex["value"] / capex_prior["value"] - 1,
            "changeLabel": "YoY", "asOf": capex["observation_end"], "quality": "IR COMPILED",
            "qualityTone": "medium", "note": "工作簿汇编自四家公司 IR。",
        })
    h100 = latest("gpu_rental_h100_usd_hour")
    h100_prior = prior("gpu_rental_h100_usd_hour", 30)
    if h100 and h100_prior:
        cards.append({
            "id": "h100-rental", "eyebrow": "COMPUTE ECONOMICS", "title": "H100 算力租赁价格",
            "value": f"${h100['value']:.2f}/h", "change": h100["value"] / h100_prior["value"] - 1,
            "changeLabel": "30D", "asOf": h100["observation_end"], "quality": "SOURCE GAP",
            "qualityTone": "low", "note": "序列完整但工作簿未记录供应商；暂只做市场热度参考。",
        })
    memory_ids = ["memory_spot_ddr5_16gb_2gx8", "memory_spot_ddr5_16gb_1gx16", "memory_spot_ddr4_8gb_1gx8", "memory_spot_ddr4_4gb_512mx8"]
    memory_changes = []
    memory_date = None
    for series_id in memory_ids:
        current, base = latest(series_id), prior(series_id, 30)
        if current and base:
            memory_changes.append(current["value"] / base["value"] - 1)
            memory_date = max(memory_date or current["observation_end"], current["observation_end"])
    if memory_changes:
        average_change = sum(memory_changes) / len(memory_changes)
        cards.append({
            "id": "memory-spot", "eyebrow": "SUPPLY CHAIN", "title": "DRAM 现货组合",
            "value": f"{average_change:+.1%}", "change": average_change, "changeLabel": "30D AVG",
            "asOf": memory_date, "quality": "UNIT GAP", "qualityTone": "low",
            "note": "四个 DDR4/DDR5 品种平均变化；价格单位与供应商待核验。",
        })
    chatgpt = latest("product_activity_chatgpt")
    if chatgpt:
        cards.append({
            "id": "chatgpt-activity", "eyebrow": "PRODUCT ADOPTION", "title": "ChatGPT 周活用户",
            "value": f"{chatgpt['value']:.0f}m", "change": None, "changeLabel": "WAU",
            "asOf": chatgpt["observation_end"], "quality": "OFFICIAL",
            "qualityTone": "high", "note": "900m 周活已与 OpenAI 2026-02-27 官方披露交叉核验。",
        })
    return cards


def main() -> int:
    config = read_csv(PROJECT_ROOT / "config" / "research_universe.csv")
    # Keep the public product focused while allowing a broader research-only
    # universe to improve cross-sectional tests.
    config = [
        row for row in config
        if str(row.get("include_in_dashboard") or "true").strip().lower() == "true"
    ]
    market = read_csv(PROJECT_ROOT / "data" / "standardized" / "market_daily.csv")
    annual = read_csv(PROJECT_ROOT / "data" / "standardized" / "fundamental_annual.csv")
    quarterly = read_csv(PROJECT_ROOT / "data" / "standardized" / "fundamental_quarterly.csv")
    earnings = read_csv(PROJECT_ROOT / "data" / "standardized" / "earnings.csv")
    developer = read_csv(PROJECT_ROOT / "data" / "standardized" / "developer_snapshot.csv")
    features = read_csv(PROJECT_ROOT / "data" / "research" / "feature_store.csv")
    hypotheses = json.loads((PROJECT_ROOT / "research" / "results" / "hypothesis_results.json").read_text(encoding="utf-8"))
    quality = json.loads((PROJECT_ROOT / "data" / "research" / "research_quality_report.json").read_text(encoding="utf-8"))
    alternative_path = PROJECT_ROOT / "data" / "standardized" / "manual_alternative_observations.csv"
    alternative = read_csv(alternative_path) if alternative_path.exists() else []
    product_rank_path = PROJECT_ROOT / "data" / "standardized" / "product_domain_rank_daily.csv"
    product_ranks = read_csv(product_rank_path) if product_rank_path.exists() else []

    market_by_ticker = defaultdict(list)
    for row in market:
        market_by_ticker[row["ticker"]].append(row)
    for rows in market_by_ticker.values():
        rows.sort(key=lambda row: row["trade_date"])
    market_as_of = max((row["trade_date"] for row in market), default="")

    latest_annual = {}
    annual_history = defaultdict(list)
    for row in annual:
        if row["available_date"] > market_as_of:
            continue
        annual_history[row["ticker"]].append(row)
        if row["ticker"] not in latest_annual or row["available_date"] > latest_annual[row["ticker"]]["available_date"]:
            latest_annual[row["ticker"]] = row
    for rows in annual_history.values():
        rows.sort(key=lambda row: (row.get("period_end", ""), row.get("available_date", "")))
    latest_quarterly = {}
    quarterly_history = defaultdict(list)
    for row in quarterly:
        if row.get("available_date", "") > market_as_of:
            continue
        quarterly_history[row["ticker"]].append(row)
        if row["ticker"] not in latest_quarterly or row["available_date"] > latest_quarterly[row["ticker"]]["available_date"]:
            latest_quarterly[row["ticker"]] = row
    for rows in quarterly_history.values():
        rows.sort(key=lambda row: (row.get("period_end", ""), row.get("available_date", "")))
    latest_earnings = {}
    for row in earnings:
        if row["reported_date"] > market_as_of:
            continue
        if row["ticker"] not in latest_earnings or row["reported_date"] > latest_earnings[row["ticker"]]["reported_date"]:
            latest_earnings[row["ticker"]] = row
    developer_by_ticker = {row["ticker"]: row for row in developer}
    wanted_features = {"momentum_20d", "momentum_60d", "realized_vol_20d", "price_to_sales_filing_basis", "price_to_fcf_filing_basis"}
    latest_features = {}
    ps_history = defaultdict(list)
    for row in features:
        if row["feature_name"] == "price_to_sales_filing_basis":
            value = number(row.get("feature_value"))
            if value is not None and row.get("feature_date", "") <= market_as_of:
                ps_history[row["ticker"]].append((row["feature_date"], value))
        if row["feature_name"] not in wanted_features:
            continue
        key = (row["ticker"], row["feature_name"])
        if key not in latest_features or row["feature_date"] > latest_features[key]["feature_date"]:
            latest_features[key] = row

    qqq_rows = market_by_ticker["QQQ"]
    qqq = {row["trade_date"]: number(row["close"]) for row in qqq_rows}
    qqq_momentum_20d = None
    if len(qqq_rows) >= 21:
        current, base = number(qqq_rows[-1]["close"]), number(qqq_rows[-21]["close"])
        qqq_momentum_20d = current / base - 1 if current and base else None
    qqq_momentum_60d = None
    if len(qqq_rows) >= 61:
        current, base = number(qqq_rows[-1]["close"]), number(qqq_rows[-61]["close"])
        qqq_momentum_60d = current / base - 1 if current and base else None
    companies = []
    price_series = {}
    for item in config:
        ticker = item["ticker"]
        rows = market_by_ticker[ticker]
        latest = rows[-1] if rows else {}
        close = number(latest.get("close"))
        momentum = number((latest_features.get((ticker, "momentum_20d")) or {}).get("feature_value"))
        momentum_60d = number((latest_features.get((ticker, "momentum_60d")) or {}).get("feature_value"))
        fundamental = latest_quarterly.get(ticker, latest_annual.get(ticker, {}))
        history = quarterly_history.get(ticker, annual_history.get(ticker, []))
        prior_fundamental = history[-2] if len(history) >= 2 else {}
        prior_year_fundamental = None
        if fundamental.get("period_end"):
            current_end = date.fromisoformat(fundamental["period_end"])
            candidates = [row for row in history[:-1] if row.get("period_end") and 330 <= (current_end - date.fromisoformat(row["period_end"])).days <= 400]
            prior_year_fundamental = min(candidates, key=lambda row: abs((current_end - date.fromisoformat(row["period_end"])).days - 365), default=None)
        event = latest_earnings.get(ticker, {})
        dev = developer_by_ticker.get(ticker, {})
        ps = number((latest_features.get((ticker, "price_to_sales_filing_basis")) or {}).get("feature_value"))
        revenue_yoy = number(fundamental.get("revenue_yoy"))
        capex_yoy = number(fundamental.get("capex_yoy"))
        fcf_margin = number(fundamental.get("fcf_margin"))
        prior_revenue_yoy = number(prior_fundamental.get("revenue_yoy"))
        prior_capex_yoy = number(prior_fundamental.get("capex_yoy"))
        prior_fcf_margin = number((prior_year_fundamental or {}).get("fcf_margin"))
        revenue_acceleration = number(fundamental.get("revenue_growth_acceleration"))
        if revenue_acceleration is None:
            revenue_acceleration = revenue_yoy - prior_revenue_yoy if revenue_yoy is not None and prior_revenue_yoy is not None else None
        fcf_margin_delta = fcf_margin - prior_fcf_margin if fcf_margin is not None and prior_fcf_margin is not None else None
        cloud_bucket = item["value_chain_bucket"] in {"cloud_platform", "cloud_model_platform"}
        core_kpi_label = "Company Capex YoY" if cloud_bucket else "Company Revenue YoY"
        core_kpi_value = capex_yoy if cloud_bucket else revenue_yoy
        prior_core_kpi = prior_capex_yoy if cloud_bucket else prior_revenue_yoy
        core_kpi_delta = core_kpi_value - prior_core_kpi if core_kpi_value is not None and prior_core_kpi is not None else None
        surprise = number(event.get("surprise_pct"))
        estimates_payload, estimates_retrieved_at = latest_raw_payload("alpha_vantage_estimates", ticker)
        estimate_rows = (estimates_payload or {}).get("estimates") or []
        future_estimates = [row for row in estimate_rows if row.get("date", "") >= market_as_of]
        quarterly_estimates = [row for row in future_estimates if "quarter" in str(row.get("horizon", "")).lower()]
        selected_estimate = min(quarterly_estimates or future_estimates, key=lambda row: row.get("date", "9999-12-31"), default={})
        current_eps_estimate = number(selected_estimate.get("eps_estimate_average"))
        prior_30d_eps_estimate = number(selected_estimate.get("eps_estimate_average_30_days_ago"))
        eps_revision_30d = current_eps_estimate / prior_30d_eps_estimate - 1 if current_eps_estimate is not None and prior_30d_eps_estimate not in (None, 0) else None
        companies.append({
            "ticker": ticker,
            "name": item["company_name"],
            "bucket": item["value_chain_bucket"],
            "focus": item["product_focus"],
            "primaryStage": item.get("primary_stage") or "midstream",
            "secondarySegment": item.get("secondary_segment") or item["value_chain_bucket"],
            "secondaryExposure": item.get("secondary_exposure"),
            "upstreamDependencies": item.get("upstream_dependencies"),
            "downstreamCustomers": item.get("downstream_customers"),
            "lastDate": latest.get("trade_date"),
            "close": close,
            "momentum20d": momentum,
            "momentum60d": momentum_60d,
            "benchmarkMomentum20d": qqq_momentum_20d,
            "benchmarkMomentum60d": qqq_momentum_60d,
            "excess20d": momentum - qqq_momentum_20d if momentum is not None and qqq_momentum_20d is not None else None,
            "excess60d": momentum_60d - qqq_momentum_60d if momentum_60d is not None and qqq_momentum_60d is not None else None,
            "volatility20d": number((latest_features.get((ticker, "realized_vol_20d")) or {}).get("feature_value")),
            "revenueYoY": revenue_yoy,
            "revenueAcceleration": revenue_acceleration,
            "capexYoY": capex_yoy,
            "fcfMargin": fcf_margin,
            "fcfMarginDelta": fcf_margin_delta,
            "coreKpiLabel": core_kpi_label,
            "coreKpiValue": core_kpi_value,
            "coreKpiDelta": core_kpi_delta,
            "priceToSales": ps,
            "priceToFcf": number((latest_features.get((ticker, "price_to_fcf_filing_basis")) or {}).get("feature_value")),
            "earningsSurprisePct": surprise,
            "epsRevision30d": eps_revision_30d,
            "epsRevisionStatus": "current_vendor_revision_snapshot" if eps_revision_30d is not None else "awaiting_point_in_time_consensus_history",
            "epsRevisionHorizon": selected_estimate.get("horizon"),
            "epsRevisionPeriod": selected_estimate.get("date"),
            "epsRevisionAnalystCount": number(selected_estimate.get("eps_estimate_analyst_count")),
            "epsRevisionRetrievedAt": estimates_retrieved_at,
            "earningsDate": event.get("reported_date"),
            "githubStars": number(dev.get("github_total_stars")),
            "hfDownloads": number(dev.get("hf_total_downloads_top50")),
            "signalScore": None,
            "signalLabel": "Pending",
            "signalCoverage": 0.0,
            "fundamentalPeriodEnd": fundamental.get("period_end"),
            "fundamentalAvailableDate": fundamental.get("available_date"),
        })
        recent = rows[-120:]
        if recent:
            stock_base = number(recent[0]["close"])
            qqq_base = qqq.get(recent[0]["trade_date"])
            price_series[ticker] = [
                {
                    "date": row["trade_date"],
                    "stock": round(number(row["close"]) / stock_base * 100, 2) if stock_base else None,
                    "benchmark": round(qqq.get(row["trade_date"]) / qqq_base * 100, 2) if qqq_base and qqq.get(row["trade_date"]) else None,
                }
                for row in recent
            ]

    metric_specs = {
        "revenuePercentile": ("revenueYoY", True),
        "revenueAccelerationPercentile": ("revenueAcceleration", True),
        "fcfPercentile": ("fcfMargin", True),
        "fcfDeltaPercentile": ("fcfMarginDelta", True),
        "epsRevisionPercentile": ("epsRevision30d", True),
        "surprisePercentile": ("earningsSurprisePct", True),
        "marketPercentile": ("excess20d", True),
        "market60Percentile": ("excess60d", True),
        "valuationPercentile": ("priceToSales", False),
    }
    for output_name, (input_name, higher_is_better) in metric_specs.items():
        population = [company[input_name] for company in companies]
        for company in companies:
            company[output_name] = percentile_rank(population, company[input_name], higher_is_better)

    # Preserve the cross-chain view, then rebuild the signal percentiles inside
    # upstream / midstream / downstream peer groups.  This prevents software,
    # cloud and semiconductor economics from sharing one mechanical distribution.
    for company in companies:
        company["crossChainFundamentalPercentile"] = average([company["revenuePercentile"], company["fcfPercentile"]])
        company["crossChainMarketPercentile"] = company["marketPercentile"]
    stage_groups = defaultdict(list)
    for company in companies:
        stage_groups[company["primaryStage"]].append(company)
    for stage_rows in stage_groups.values():
        for output_name, (input_name, higher_is_better) in metric_specs.items():
            population = [company[input_name] for company in stage_rows]
            for company in stage_rows:
                company[output_name] = percentile_rank(population, company[input_name], higher_is_better)
                company["peerGroupSize"] = len(stage_rows)

    for company in companies:
        history = sorted(ps_history.get(company["ticker"], []))
        values = [value for _, value in history]
        company["valuationHistoryPercentile"] = percentile_rank(values, company["priceToSales"], True)
        company["valuationHistoryStart"] = history[0][0] if history else None
        company["growthAdjustedValuation"] = (
            company["priceToSales"] / (company["revenueYoY"] * 100)
            if company["priceToSales"] is not None and company["revenueYoY"] is not None and company["revenueYoY"] > 0
            else None
        )

    for company in companies:
        fundamental_components = {
            "growth": company["revenuePercentile"],
            "acceleration": company["revenueAccelerationPercentile"],
            "cash_quality": average([company["fcfPercentile"], company["fcfDeltaPercentile"]]),
            "expectations": company["epsRevisionPercentile"],
        }
        fundamental_result = weighted_score(fundamental_components, FUNDAMENTAL_WEIGHTS)
        market_components = {
            "excess_20d": company["marketPercentile"],
            "excess_60d": company["market60Percentile"],
        }
        market_result = weighted_score(market_components, MARKET_WEIGHTS)
        company["fundamentalPercentile"] = fundamental_result["score"]
        company["fundamentalScoreVersion"] = FUNDAMENTAL_SCORE_VERSION
        company["fundamentalScoreCoverage"] = fundamental_result["coverage"]
        company["fundamentalEffectiveWeights"] = fundamental_result["effective_weights"]
        company["fundamentalComponents"] = {
            name: round(value * 100) if value is not None else None
            for name, value in fundamental_components.items()
        }
        company["marketCompositePercentile"] = market_result["score"]
        company["marketScoreVersion"] = MARKET_SCORE_VERSION
        company["marketScoreCoverage"] = market_result["coverage"]
        company["marketComponents"] = {
            name: round(value * 100) if value is not None else None
            for name, value in market_components.items()
        }
        fundamental = company["fundamentalPercentile"]
        valuation = company["valuationPercentile"]
        market_signal = company["marketCompositePercentile"]
        excess = company["excess20d"]
        coverage = company["fundamentalScoreCoverage"]
        setup, reason = classify_signal(fundamental, market_signal, coverage)

        risks = []
        if valuation is not None and valuation < 0.25:
            risks.append("relative valuation stretched")
        if company["fcfMargin"] is not None and company["fcfMargin"] < 0:
            risks.append("negative FCF margin")
        if company["earningsSurprisePct"] is not None and company["earningsSurprisePct"] < 0:
            risks.append("latest earnings miss")
        if company["volatility20d"] is not None and company["volatility20d"] > 0.50:
            risks.append("high realized volatility")
        company["researchSetup"] = setup
        company["setupReason"] = reason
        company["setupRisk"] = ", ".join(risks) if risks else "No single mechanical red flag; catalyst and source review still required."
        company["fundamentalScore"] = round(fundamental * 100) if fundamental is not None else None
        company["marketScore"] = round(market_signal * 100) if market_signal is not None else None
        company["signalScore"] = company["fundamentalScore"]
        company["signalCoverage"] = coverage
        company["signalLabel"] = setup
        company["fundamentalPriceGap"] = (
            round((fundamental - market_signal) * 100)
            if fundamental is not None and market_signal is not None else None
        )
        company["crossChainGap"] = (
            round((company["crossChainFundamentalPercentile"] - company["crossChainMarketPercentile"]) * 100)
            if company["crossChainFundamentalPercentile"] is not None and company["crossChainMarketPercentile"] is not None else None
        )
        company["actionCategory"] = (
            "Opportunity" if setup == "Fundamental dislocation" else
            "Momentum" if setup == "Momentum" else
            "Risk" if setup in {"Expectation risk", "Deteriorating"} else "Watch"
        )
        company["valuationLabel"] = "估值较低" if valuation is not None and valuation >= 0.67 else "估值偏高" if valuation is not None and valuation <= 0.33 else "估值中性" if valuation is not None else "估值缺失"
        company["trend"] = "Accelerating" if company["coreKpiDelta"] is not None and company["coreKpiDelta"] >= 0.05 else "Decelerating" if company["coreKpiDelta"] is not None and company["coreKpiDelta"] <= -0.05 else "Stable"
        company["flagConclusion"] = reason

    # Signal change is based on dated platform snapshots, not inferred from a static
    # earnings observation. The first run establishes an honest baseline; later daily
    # runs can identify entries, exits and changes in dislocation magnitude.
    signal_history_path = PROJECT_ROOT / "data" / "processed" / "signal_monitor_history.json"
    signal_history = {"snapshots": []}
    if signal_history_path.exists():
        try:
            signal_history = json.loads(signal_history_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    snapshots = [item for item in signal_history.get("snapshots", []) if item.get("asOfDate") != market_as_of]
    prior_snapshot = max(
        (item for item in snapshots if item.get("asOfDate", "") < market_as_of),
        key=lambda item: item.get("asOfDate", ""), default=None,
    )
    prior_companies = (prior_snapshot or {}).get("companies", {})
    actionable = {"Fundamental dislocation", "Expectation risk"}
    for company in companies:
        previous = prior_companies.get(company["ticker"])
        current_setup = company["researchSetup"]
        current_gap = company["fundamentalPriceGap"]
        if not previous:
            change = "Baseline"
        elif previous.get("setup") != current_setup and current_setup in actionable:
            change = "NEW"
        elif previous.get("setup") in actionable and current_setup not in actionable:
            change = "Exited"
        elif previous.get("gap") is None or current_gap is None:
            change = "Unchanged"
        else:
            magnitude_change = abs(current_gap) - abs(previous["gap"])
            change = "Strengthening" if magnitude_change >= 5 else "Weakening" if magnitude_change <= -5 else "Unchanged"
        company["signalChange"] = change
    snapshots.append({
        "asOfDate": market_as_of,
        "companies": {company["ticker"]: {"setup": company["researchSetup"], "gap": company["fundamentalPriceGap"]} for company in companies},
    })
    signal_history_path.parent.mkdir(parents=True, exist_ok=True)
    signal_history_path.write_text(json.dumps({"snapshots": sorted(snapshots, key=lambda item: item["asOfDate"])[-120:]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    brief_path = PROJECT_ROOT / "data" / "processed" / "daily_ai_brief.json"
    daily_brief = json.loads(brief_path.read_text(encoding="utf-8")) if brief_path.exists() else {
        "status": "ready", "headline": "每日 AI 事件采集就绪",
        "summary": "今日事件将按来源、重要性与产业链影响进行整理。",
        "brief_date": None, "scheduledTime": "08:00 Asia/Shanghai", "verifiedCount": 0, "events": [],
    }
    daily_brief = normalize_event_brief(daily_brief)
    event_map = defaultdict(list)
    for event in daily_brief.get("events", []):
        for ticker in event.get("affectedCompanies", []):
            event_map[ticker].append(event)
    for company in companies:
        company_events = event_map.get(company["ticker"], [])
        company["eventCount"] = len(company_events)
        company["latestCatalyst"] = company_events[0]["headline"] if company_events else None

    queue_priority = {
        "Fundamental dislocation": 0,
        "Expectation risk": 1,
        "Deteriorating": 2,
        "Momentum": 3,
        "Data gap": 4,
    }
    research_queue = sorted(
        companies,
        key=lambda company: (
            queue_priority[company["researchSetup"]],
            -(abs(company["fundamentalPriceGap"]) if company["fundamentalPriceGap"] is not None else -1),
        ),
    )[:6]
    research_queue = [{
        "ticker": company["ticker"], "name": company["name"], "setup": company["researchSetup"],
        "reason": company["setupReason"], "risk": company["setupRisk"], "excess20d": company["excess20d"],
        "nextCheck": "Read latest filing / earnings transcript and verify the next dated catalyst.",
    } for company in research_queue]

    bucket_summaries = []
    grouped_companies = defaultdict(list)
    for company in companies:
        grouped_companies[company["bucket"]].append(company)
    for bucket, rows in grouped_companies.items():
        median_delta = median([row["coreKpiDelta"] for row in rows])
        bucket_summaries.append({
            "bucket": bucket,
            "companyCount": len(rows),
            "medianExcess20d": median([row["excess20d"] for row in rows]),
            "medianRevenueYoY": median([row["revenueYoY"] for row in rows]),
            "medianFcfMargin": median([row["fcfMargin"] for row in rows]),
            "coreKpiLabel": rows[0]["coreKpiLabel"],
            "medianCoreKpi": median([row["coreKpiValue"] for row in rows]),
            "medianCoreKpiDelta": median_delta,
            "trend": "Accelerating" if median_delta is not None and median_delta >= 0.05 else "Decelerating" if median_delta is not None and median_delta <= -0.05 else "Stable",
        })

    stage_labels = {
        "upstream": ("上游", "芯片、代工、存储与数据中心网络"),
        "midstream": ("中游", "云、模型、数据与开发基础设施"),
        "downstream": ("下游", "企业、创意与生产力应用"),
    }
    stage_summaries = []
    for stage in ("upstream", "midstream", "downstream"):
        rows = [company for company in companies if company["primaryStage"] == stage]
        acceleration = median([row["revenueAcceleration"] for row in rows])
        stage_summaries.append({
            "stage": stage, "name": stage_labels[stage][0], "description": stage_labels[stage][1],
            "companyCount": len(rows), "medianExcess20d": median([row["excess20d"] for row in rows]),
            "medianFundamentalScore": median([row["fundamentalScore"] for row in rows]),
            "opportunityCount": sum(row["actionCategory"] == "Opportunity" for row in rows),
            "trend": "Accelerating" if acceleration is not None and acceleration >= 0.03 else "Decelerating" if acceleration is not None and acceleration <= -0.03 else "Stable",
        })

    segment_summaries = []
    grouped_segments = defaultdict(list)
    for company in companies:
        grouped_segments[(company["primaryStage"], company["secondarySegment"])].append(company)
    for (stage, segment), rows in grouped_segments.items():
        delta = median([row["coreKpiDelta"] for row in rows])
        segment_summaries.append({
            "stage": stage, "segment": segment, "companyCount": len(rows),
            "coreKpiLabel": rows[0]["coreKpiLabel"], "medianCoreKpi": median([row["coreKpiValue"] for row in rows]),
            "medianExcess20d": median([row["excess20d"] for row in rows]),
            "trend": "Accelerating" if delta is not None and delta >= 0.05 else "Decelerating" if delta is not None and delta <= -0.05 else "Stable",
        })

    latest_product_rank = {}
    for row in product_ranks:
        product_id = row.get("product_id")
        if product_id and (product_id not in latest_product_rank or row.get("observation_date", "") > latest_product_rank[product_id].get("observation_date", "")):
            latest_product_rank[product_id] = row
    private_entities = [
        {
            "id": "openai", "name": "OpenAI", "ownership": "Private", "primaryStage": "midstream",
            "secondarySegment": "model_labs", "focus": "Foundation models API and ChatGPT",
            "secondaryExposure": "Consumer and enterprise AI applications", "linkedPublicCompanies": ["MSFT"],
            "productSignal": latest_product_rank.get("chatgpt", {}).get("rank"),
            "productSignalLabel": "ChatGPT global domain rank" if latest_product_rank.get("chatgpt", {}).get("rank") else "ChatGPT rank bucket",
            "productSignalBucket": latest_product_rank.get("chatgpt", {}).get("rank_bucket"),
        },
        {
            "id": "anthropic", "name": "Anthropic", "ownership": "Private", "primaryStage": "midstream",
            "secondarySegment": "model_labs", "focus": "Claude models API and enterprise agents",
            "secondaryExposure": "Enterprise AI applications", "linkedPublicCompanies": ["AMZN", "GOOGL"],
            "productSignal": latest_product_rank.get("claude", {}).get("rank"),
            "productSignalLabel": "Claude global domain rank" if latest_product_rank.get("claude", {}).get("rank") else "Claude rank bucket",
            "productSignalBucket": latest_product_rank.get("claude", {}).get("rank_bucket"),
        },
    ]
    chain_test = hypotheses.get("value_chain_transmission") or {}
    token_test = hypotheses.get("F3_token_to_cloud_revenue") or {}
    transmission_tests = [
        {
            "id": "csp-to-upstream", "path": "中游 CSP Capex → 上游芯片/网络收入",
            "verdict": chain_test.get("verdict", "Needs Data"), "conclusion": chain_test.get("conclusion"),
            "sampleSize": ((chain_test.get("horizons") or {}).get("+1Q") or {}).get("sample_size"),
            "leadLag": [
                {"label": "同期", "value": ((chain_test.get("horizons") or {}).get("+0Q") or {}).get("rank_ic")},
                {"label": "+1Q", "value": ((chain_test.get("horizons") or {}).get("+1Q") or {}).get("rank_ic")},
                {"label": "+2Q", "value": ((chain_test.get("horizons") or {}).get("+2Q") or {}).get("rank_ic")},
            ],
        },
        {
            "id": "tokens-to-cloud", "path": "模型 Token 使用 → 中游云平台收入",
            "verdict": token_test.get("verdict", "Needs Data"),
            "conclusion": f"现有+1Q只有{token_test.get('sample_size', 0)}个完整季度配对，暂不形成投资结论。",
            "sampleSize": token_test.get("sample_size"),
            "leadLag": [
                {"label": "+1Q", "value": ((token_test.get("lead_lag") or {}).get("+1Q_revenue") or {}).get("rank_ic")},
                {"label": "+2Q", "value": ((token_test.get("lead_lag") or {}).get("+2Q_revenue") or {}).get("rank_ic")},
            ],
        },
    ]
    payload = {
        "demandChain": build_demand_chain(product_ranks, read_csv(PROJECT_ROOT / "data" / "standardized" / "openrouter_usage_daily.csv"), alternative, quarterly, datetime.now(timezone.utc).isoformat()),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "asOfDate": market_as_of,
        "marketAsOfDate": market_as_of,
        "fundamentalAsOfDate": max((row.get("available_date") or "" for row in latest_quarterly.values()), default=""),
        "briefGeneratedAt": daily_brief.get("generatedAt"),
        "platform": {"name": "AI Alpha Research", "version": "Framework v0.1", "benchmark": "QQQ"},
        "universeScope": {
            "dashboardCompanies": len(companies),
            "backtestCompanies": len(hypotheses.get("universe") or []),
            "policy": "核心公司用于页面监测；扩展公司仅用于横截面回测与稳健性检验。",
        },
        "signalMethod": {
            "fundamentalVersion": FUNDAMENTAL_SCORE_VERSION,
            "fundamentalWeights": FUNDAMENTAL_WEIGHTS,
            "marketVersion": MARKET_SCORE_VERSION,
            "marketWeights": MARKET_WEIGHTS,
            "minimumCoverage": MIN_SCORE_COVERAGE,
            "strongFundamentalThreshold": STRONG_FUNDAMENTAL_THRESHOLD,
            "strongMarketThreshold": STRONG_MARKET_THRESHOLD,
        },
        "companies": companies,
        "priceSeries": price_series,
        "hypotheses": hypotheses,
        "quality": quality,
        "dailyBrief": daily_brief,
        "alternativePulse": build_alternative_pulse(alternative, market_as_of),
        "researchQueue": research_queue,
        "bucketSummaries": bucket_summaries,
        "stageSummaries": stage_summaries,
        "segmentSummaries": segment_summaries,
        "privateEntities": private_entities,
        "transmissionTests": transmission_tests,
        "sourceRegistry": [
            {"dataset": "日频行情", "provider": "Massive", "status": "回测与监测", "tone": "high", "use": "收益率、波动率、相对 QQQ 表现", "limit": "以交易日收盘时间作为数据可用时点。"},
            {"dataset": "财务数据", "provider": "SEC Companyfacts", "status": "回测与横截面比较", "tone": "high", "use": "收入、Capex、FCF、毛利率与估值", "limit": "按 SEC 文件提交日期进入研究表。"},
            {"dataset": "业绩数据", "provider": "Alpha Vantage", "status": "事件研究", "tone": "medium", "use": "实际 EPS、预期 EPS 与盈利意外", "limit": "历史共识数据按归档来源继续交叉检查。"},
            {"dataset": "开发者数据", "provider": "GitHub / Hugging Face", "status": "当前快照", "tone": "medium", "use": "开源活跃度、仓库覆盖与模型下载", "limit": "后续增加历史回填与产品级映射。"},
            {"dataset": "AI 另类数据", "provider": "AI 跟踪工作簿 + 官方数据", "status": "市场监测", "tone": "low", "use": "CSP Capex、算力租赁、内存价格与产品活跃度", "limit": "逐项补充发布时间与原始来源。"},
        ],
    }
    output = PROJECT_ROOT / "web" / "public" / "data" / "dashboard.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"companies={len(companies)} price_series={len(price_series)} output={output.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
