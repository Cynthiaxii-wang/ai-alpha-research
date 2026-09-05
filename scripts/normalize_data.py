#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.research_utils import latest_raw, load_envelope, parse_float, write_csv  # noqa: E402
from ai_alpha_research.universe import load_universe  # noqa: E402


EASTERN = ZoneInfo("America/New_York")
US_GAAP_METRIC_DEFINITIONS = {
    "revenue": {"unit": "USD", "tags": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]},
    "gross_profit": {"unit": "USD", "tags": ["GrossProfit"]},
    "operating_income": {"unit": "USD", "tags": ["OperatingIncomeLoss"]},
    "operating_cash_flow": {"unit": "USD", "tags": ["NetCashProvidedByUsedInOperatingActivities"]},
    "capex": {"unit": "USD", "tags": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]},
    "rd_expense": {"unit": "USD", "tags": ["ResearchAndDevelopmentExpense"]},
    "diluted_shares": {"unit": "shares", "tags": ["WeightedAverageNumberOfDilutedSharesOutstanding"]},
}
IFRS_METRIC_DEFINITIONS = {
    "revenue": {"unit": "TWD", "tags": ["Revenue", "RevenueFromContractsWithCustomers"]},
    "gross_profit": {"unit": "TWD", "tags": ["GrossProfit"]},
    "operating_income": {"unit": "TWD", "tags": ["ProfitLossFromOperatingActivities"]},
    "operating_cash_flow": {"unit": "TWD", "tags": ["CashFlowsFromUsedInOperatingActivities"]},
    "capex": {"unit": "TWD", "tags": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"]},
    "rd_expense": {"unit": "TWD", "tags": ["ResearchAndDevelopmentExpense"]},
    "diluted_shares": {"unit": "shares", "tags": ["AdjustedWeightedAverageShares", "WeightedAverageShares"]},
}
METRIC_DEFINITIONS_BY_NAMESPACE = {
    "us-gaap": US_GAAP_METRIC_DEFINITIONS,
    "ifrs-full": IFRS_METRIC_DEFINITIONS,
}


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def market_available_at(trade_date: date) -> str:
    return iso_utc(datetime.combine(trade_date, time(16, 15), tzinfo=EASTERN))


def earnings_available_at(reported_date: date, report_time: str) -> str:
    clock = time(8, 0) if report_time == "pre-market" else time(16, 15)
    return iso_utc(datetime.combine(reported_date, clock, tzinfo=EASTERN))


def normalize_market(tickers: list[str]) -> list[dict]:
    rows = []
    for ticker in tickers:
        envelope = load_envelope(latest_raw(PROJECT_ROOT, "massive", ticker))
        for item in envelope["payload"].get("results") or []:
            trade_date = datetime.fromtimestamp(item["t"] / 1000, tz=timezone.utc).date()
            rows.append({
                "ticker": ticker,
                "trade_date": trade_date.isoformat(),
                "open": item.get("o"),
                "high": item.get("h"),
                "low": item.get("l"),
                "close": item.get("c"),
                "volume": item.get("v"),
                "vwap": item.get("vw"),
                "transactions": item.get("n"),
                "adjusted": envelope["payload"].get("adjusted"),
                "available_at": market_available_at(trade_date),
                "source_retrieved_at": envelope["retrieved_at"],
                "source": "massive",
            })
    rows.sort(key=lambda row: (row["ticker"], row["trade_date"]))
    return rows


def normalize_unadjusted_market(tickers: list[str]) -> list[dict]:
    rows = []
    for ticker in tickers:
        envelope = load_envelope(latest_raw(PROJECT_ROOT, "massive_unadjusted", ticker))
        for item in envelope["payload"].get("results") or []:
            trade_date = datetime.fromtimestamp(item["t"] / 1000, tz=timezone.utc).date()
            rows.append({
                "ticker": ticker,
                "trade_date": trade_date.isoformat(),
                "close_unadjusted": item.get("c"),
                "available_at": market_available_at(trade_date),
                "source_retrieved_at": envelope["retrieved_at"],
                "source": "massive_unadjusted",
            })
    rows.sort(key=lambda row: (row["ticker"], row["trade_date"]))
    return rows


def normalize_earnings(tickers: list[str]) -> list[dict]:
    rows = []
    for ticker in tickers:
        envelope = load_envelope(latest_raw(PROJECT_ROOT, "alpha_vantage", ticker))
        for item in envelope["payload"].get("quarterlyEarnings") or []:
            reported_date = date.fromisoformat(item["reportedDate"])
            rows.append({
                "ticker": ticker,
                "fiscal_period_end": item.get("fiscalDateEnding"),
                "reported_date": reported_date.isoformat(),
                "report_time": item.get("reportTime") or "unknown",
                "reported_eps": parse_float(item.get("reportedEPS")),
                "estimated_eps": parse_float(item.get("estimatedEPS")),
                "surprise": parse_float(item.get("surprise")),
                "surprise_pct": parse_float(item.get("surprisePercentage")),
                "available_at": earnings_available_at(reported_date, item.get("reportTime") or "unknown"),
                "source_retrieved_at": envelope["retrieved_at"],
                "pit_status": "vendor_historical_estimate_snapshot_unverified",
                "source": "alpha_vantage",
            })
    rows.sort(key=lambda row: (row["ticker"], row["reported_date"]))
    return rows


def normalize_fundamentals(tickers: list[str]) -> list[dict]:
    rows = []
    for ticker in tickers:
        envelope = load_envelope(latest_raw(PROJECT_ROOT, "sec_companyfacts", ticker))
        namespaces = envelope["payload"].get("facts") or {}
        seen = set()
        for namespace, definitions in METRIC_DEFINITIONS_BY_NAMESPACE.items():
            facts = namespaces.get(namespace) or {}
            allowed_forms = {"10-K", "10-Q"} if namespace == "us-gaap" else {"20-F", "6-K"}
            for metric_name, definition in definitions.items():
                unit = definition["unit"]
                for tag_priority, tag in enumerate(definition["tags"]):
                    entries = ((((facts.get(tag) or {}).get("units") or {}).get(unit)) or [])
                    for entry in entries:
                        end = entry.get("end")
                        if entry.get("form") not in allowed_forms or not end or end < "2019-01-01":
                            continue
                        natural_key = (namespace, metric_name, tag, entry.get("accn"), entry.get("start"), end, entry.get("val"))
                        if natural_key in seen:
                            continue
                        seen.add(natural_key)
                        start = entry.get("start")
                        duration = (date.fromisoformat(end) - date.fromisoformat(start)).days if start and end else None
                        rows.append({
                            "ticker": ticker,
                            "metric_name": metric_name,
                            "taxonomy": namespace,
                            "xbrl_tag": tag,
                            "tag_priority": tag_priority,
                            "metric_value": entry.get("val"),
                            "unit": unit,
                            "start_date": start,
                            "period_end": end,
                            "duration_days": duration,
                            "fiscal_year": entry.get("fy"),
                            "fiscal_period": entry.get("fp"),
                            "form": entry.get("form"),
                            "accession_number": entry.get("accn"),
                            "filed_date": entry.get("filed"),
                            "available_date": entry.get("filed"),
                            "frame": entry.get("frame"),
                            "source_retrieved_at": envelope["retrieved_at"],
                            "source": "sec_edgar",
                        })
    rows.sort(key=lambda row: (row["ticker"], row["metric_name"], row["period_end"] or "", row["filed_date"] or ""))
    return rows


def build_annual_fundamentals(observations: list[dict]) -> list[dict]:
    selected = {}
    for row in observations:
        duration = int(row["duration_days"]) if row["duration_days"] not in (None, "") else 0
        if row["fiscal_period"] != "FY" or row["form"] not in {"10-K", "20-F"} or not 300 <= duration <= 430:
            continue
        key = (row["ticker"], row["metric_name"], row["period_end"])
        ordering = (row["filed_date"], int(row.get("tag_priority") or 0))
        if key not in selected or ordering < selected[key][0]:
            selected[key] = (ordering, row)
    by_period = defaultdict(dict)
    for (ticker, metric, period_end), (_, row) in selected.items():
        by_period[(ticker, period_end)][metric] = row
    output = []
    for (ticker, period_end), metrics in by_period.items():
        revenue = parse_float((metrics.get("revenue") or {}).get("metric_value"))
        ocf = parse_float((metrics.get("operating_cash_flow") or {}).get("metric_value"))
        capex = parse_float((metrics.get("capex") or {}).get("metric_value"))
        diluted_shares = parse_float((metrics.get("diluted_shares") or {}).get("metric_value"))
        free_cash_flow = ocf - capex if ocf is not None and capex is not None else None
        operating_dates = [
            metrics[name]["filed_date"]
            for name in ("revenue", "operating_cash_flow", "capex")
            if metrics.get(name) and metrics[name].get("filed_date")
        ]
        valuation_dates = operating_dates + ([metrics["diluted_shares"]["filed_date"]] if metrics.get("diluted_shares") and metrics["diluted_shares"].get("filed_date") else [])
        output.append({
            "ticker": ticker,
            "fiscal_year": date.fromisoformat(period_end).year,
            "period_end": period_end,
            "available_date": max(operating_dates) if operating_dates else None,
            "valuation_available_date": max(valuation_dates) if valuation_dates else None,
            "financial_currency": (metrics.get("revenue") or {}).get("unit"),
            "revenue": revenue,
            "gross_profit": parse_float((metrics.get("gross_profit") or {}).get("metric_value")),
            "operating_income": parse_float((metrics.get("operating_income") or {}).get("metric_value")),
            "operating_cash_flow": ocf,
            "capex": capex,
            "free_cash_flow": free_cash_flow,
            "rd_expense": parse_float((metrics.get("rd_expense") or {}).get("metric_value")),
            "diluted_shares": diluted_shares,
            "sales_per_diluted_share": revenue / diluted_shares if revenue is not None and diluted_shares else None,
            "fcf_per_diluted_share": free_cash_flow / diluted_shares if free_cash_flow is not None and diluted_shares else None,
            "pit_selection_rule": "earliest_filed_annual_value_across_standard_tags",
        })
    output.sort(key=lambda row: (row["ticker"], row["period_end"]))
    previous = {}
    for row in output:
        prior = previous.get(row["ticker"])
        for field in ("revenue", "capex", "free_cash_flow"):
            current = row[field]
            old = prior[field] if prior else None
            row[f"{field}_yoy"] = current / old - 1 if current is not None and old not in (None, 0) else None
        row["fcf_margin"] = row["free_cash_flow"] / row["revenue"] if row["free_cash_flow"] is not None and row["revenue"] else None
        row["capex_to_revenue"] = row["capex"] / row["revenue"] if row["capex"] is not None and row["revenue"] else None
        previous[row["ticker"]] = row
    return output


def prior_economic_quarter(rows: list[dict], row: dict) -> dict | None:
    """Return the closest period about one year earlier; SEC fy/fp is not a key."""
    current_end = date.fromisoformat(row["period_end"])
    options = [candidate for candidate in rows
        if 330 <= (current_end - date.fromisoformat(candidate["period_end"])).days <= 400]
    return min(options,
        key=lambda candidate: abs((current_end - date.fromisoformat(candidate["period_end"])).days - 365),
        default=None)


def build_quarterly_fundamentals(observations: list[dict]) -> list[dict]:
    """Build PIT-safe single-quarter flow metrics from SEC observations."""
    flow_metrics = {
        "revenue", "gross_profit", "operating_income",
        "operating_cash_flow", "capex", "rd_expense",
    }
    canonical = {}
    for row in observations:
        if row["metric_name"] not in flow_metrics or not row.get("start_date") or not row.get("period_end"):
            continue
        duration = int(row["duration_days"]) if row.get("duration_days") not in (None, "") else 0
        if not 70 <= duration <= 430:
            continue
        key = (row["ticker"], row["metric_name"], row["start_date"], row["period_end"], row["unit"])
        ordering = (row.get("filed_date") or "9999-12-31", int(row.get("tag_priority") or 0))
        if key not in canonical or ordering < canonical[key][0]:
            canonical[key] = (ordering, row)

    economic_rows = [item[1] for item in canonical.values()]
    by_start = defaultdict(list)
    for row in economic_rows:
        by_start[(row["ticker"], row["metric_name"], row["unit"], row["start_date"])].append(row)
    for rows in by_start.values():
        rows.sort(key=lambda item: (item["period_end"], int(item["duration_days"])))

    candidates = defaultdict(list)

    def quarter_label(row: dict, default: str | None = None) -> str | None:
        period = row.get("fiscal_period")
        if period in {"Q1", "Q2", "Q3"}:
            return period
        frame = row.get("frame") or ""
        for label in ("Q1", "Q2", "Q3", "Q4"):
            if frame.endswith(label):
                return label
        return default

    def add_candidate(row: dict, value: float, derivation: str, quarter: str | None,
                      source_rows: list[dict]) -> None:
        if quarter is None:
            return
        filed_dates = [item.get("filed_date") for item in source_rows if item.get("filed_date")]
        accessions = sorted({item.get("accession_number") for item in source_rows if item.get("accession_number")})
        candidates[(row["ticker"], row["metric_name"], row["period_end"])].append({
            "ticker": row["ticker"], "metric_name": row["metric_name"], "period_end": row["period_end"],
            "fiscal_year": row.get("fiscal_year"), "fiscal_quarter": quarter,
            "metric_value": value, "unit": row["unit"],
            "available_date": max(filed_dates) if filed_dates else None,
            "derivation": derivation, "source_accessions": "|".join(accessions),
        })

    # Prefer directly disclosed three-month values.
    for row in economic_rows:
        duration = int(row["duration_days"])
        if 70 <= duration <= 120:
            value = parse_float(row.get("metric_value"))
            if value is not None:
                default = "Q4" if row.get("fiscal_period") == "FY" else None
                add_candidate(row, value, "direct_quarter", quarter_label(row, default), [row])

    # Recover Q2/Q3 from YTD cumulative disclosures with a common start date.
    for rows in by_start.values():
        for index, current in enumerate(rows):
            duration = int(current["duration_days"])
            if not 150 <= duration <= 310:
                continue
            prior_options = [row for row in rows[:index] if 70 <= int(row["duration_days"]) < duration]
            if not prior_options:
                continue
            prior = prior_options[-1]
            current_value, prior_value = parse_float(current.get("metric_value")), parse_float(prior.get("metric_value"))
            if current_value is None or prior_value is None:
                continue
            default = "Q2" if duration <= 220 else "Q3"
            add_candidate(current, current_value - prior_value, "cumulative_difference", quarter_label(current, default), [prior, current])

        # Recover Q4 from annual less the nine-month cumulative value.
        annuals = [row for row in rows if 320 <= int(row["duration_days"]) <= 430]
        nine_months = [row for row in rows if 230 <= int(row["duration_days"]) <= 310]
        for annual_row in annuals:
            priors = [row for row in nine_months if row["period_end"] < annual_row["period_end"]]
            if not priors:
                continue
            prior = priors[-1]
            annual_value, prior_value = parse_float(annual_row.get("metric_value")), parse_float(prior.get("metric_value"))
            if annual_value is not None and prior_value is not None:
                add_candidate(annual_row, annual_value - prior_value, "annual_minus_nine_month", "Q4", [prior, annual_row])

    derivation_rank = {"direct_quarter": 0, "cumulative_difference": 1, "annual_minus_nine_month": 2}
    selected = {
        key: min(rows, key=lambda row: (derivation_rank[row["derivation"]], row.get("available_date") or "9999-12-31"))
        for key, rows in candidates.items()
    }
    by_period = defaultdict(dict)
    for (ticker, metric_name, period_end), row in selected.items():
        by_period[(ticker, period_end)][metric_name] = row

    output = []
    for (ticker, period_end), metrics in by_period.items():
        anchor = metrics.get("revenue") or next(iter(metrics.values()))
        revenue = parse_float((metrics.get("revenue") or {}).get("metric_value"))
        ocf = parse_float((metrics.get("operating_cash_flow") or {}).get("metric_value"))
        capex = parse_float((metrics.get("capex") or {}).get("metric_value"))
        free_cash_flow = ocf - capex if ocf is not None and capex is not None else None
        output.append({
            "ticker": ticker, "fiscal_year": anchor.get("fiscal_year"),
            "fiscal_quarter": anchor.get("fiscal_quarter"), "period_end": period_end,
            "available_date": max((row.get("available_date") for row in metrics.values() if row.get("available_date")), default=None),
            "financial_currency": anchor.get("unit"), "revenue": revenue,
            "gross_profit": parse_float((metrics.get("gross_profit") or {}).get("metric_value")),
            "operating_income": parse_float((metrics.get("operating_income") or {}).get("metric_value")),
            "operating_cash_flow": ocf, "capex": capex, "free_cash_flow": free_cash_flow,
            "rd_expense": parse_float((metrics.get("rd_expense") or {}).get("metric_value")),
            "fcf_margin": free_cash_flow / revenue if free_cash_flow is not None and revenue else None,
            "capex_to_revenue": capex / revenue if capex is not None and revenue else None,
            "metric_derivations": ";".join(f"{name}:{row['derivation']}" for name, row in sorted(metrics.items())),
            "source_accessions": "|".join(sorted({accession for row in metrics.values() for accession in row["source_accessions"].split("|") if accession})),
            "pit_selection_rule": "earliest_filed_economic_period; direct_quarter_preferred; cumulative_difference_fallback",
        })

    output.sort(key=lambda row: (row["ticker"], row["period_end"]))
    histories = defaultdict(list)
    for row in output:
        histories[row["ticker"]].append(row)
    for rows in histories.values():
        previous = None
        for row in rows:
            # SEC fy/fp labels are issuer-defined and occasionally repeated or
            # stale. Match the economic period near one year earlier instead.
            prior_year = prior_economic_quarter(rows, row)
            for field in ("revenue", "capex", "free_cash_flow"):
                current, old = row.get(field), prior_year.get(field) if prior_year else None
                row[f"{field}_yoy"] = current / old - 1 if current is not None and old not in (None, 0) else None
            row["revenue_qoq"] = row["revenue"] / previous["revenue"] - 1 if previous and row["revenue"] is not None and previous["revenue"] not in (None, 0) else None
            previous = row
        for index, row in enumerate(rows):
            prior_growth = rows[index - 1].get("revenue_yoy") if index else None
            row["revenue_growth_acceleration"] = row["revenue_yoy"] - prior_growth if row["revenue_yoy"] is not None and prior_growth is not None else None
    return output


def normalize_developer_snapshots(companies) -> list[dict]:
    rows = []
    for company in companies:
        if not company.github_owner and not company.huggingface_author:
            continue
        if not company.github_owner:
            continue
        github = load_envelope(latest_raw(PROJECT_ROOT, "github", company.ticker))
        repos = [repo for repo in github["payload"] if not repo.get("fork") and not repo.get("archived")][:50]
        as_of = datetime.fromisoformat(github["retrieved_at"])
        cutoff = as_of.timestamp() - 90 * 86400
        row = {
            "ticker": company.ticker,
            "snapshot_at": github["retrieved_at"],
            "github_repositories_returned": len(repos),
            "github_total_stars": sum(repo.get("stargazers_count") or 0 for repo in repos),
            "github_total_forks": sum(repo.get("forks_count") or 0 for repo in repos),
            "github_total_open_issues": sum(repo.get("open_issues_count") or 0 for repo in repos),
            "github_active_repos_90d": sum(
                datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00")).timestamp() >= cutoff
                for repo in repos if repo.get("pushed_at")
            ),
            "github_history_status": "current_snapshot_not_historical",
            "hf_models_returned": None,
            "hf_total_downloads_top50": None,
            "hf_total_likes_top50": None,
            "hf_history_status": "not_applicable" if not company.huggingface_author else "current_snapshot_not_historical",
        }
        if company.huggingface_author:
            hf = load_envelope(latest_raw(PROJECT_ROOT, "huggingface", company.ticker))
            models = sorted(hf["payload"], key=lambda model: model.get("downloads") or 0, reverse=True)[:50]
            row.update({
                "snapshot_at": max(github["retrieved_at"], hf["retrieved_at"]),
                "hf_models_returned": len(models),
                "hf_total_downloads_top50": sum(model.get("downloads") or 0 for model in models),
                "hf_total_likes_top50": sum(model.get("likes") or 0 for model in models),
            })
        rows.append(row)
    return rows


def normalize_openrouter() -> list[dict]:
    envelope = load_envelope(latest_raw(PROJECT_ROOT, "openrouter", "models"))
    rows = []
    for model in envelope["payload"].get("data") or []:
        pricing = model.get("pricing") or {}
        rows.append({
            "model_id": model.get("id"),
            "model_name": model.get("name"),
            "created_unix": model.get("created"),
            "context_length": model.get("context_length"),
            "prompt_usd_per_token": parse_float(pricing.get("prompt")),
            "completion_usd_per_token": parse_float(pricing.get("completion")),
            "cache_read_usd_per_token": parse_float(pricing.get("input_cache_read")),
            "snapshot_at": envelope["retrieved_at"],
            "pit_status": "current_third_party_snapshot",
        })
    return rows


def normalize_openrouter_usage() -> list[dict]:
    paths = sorted((PROJECT_ROOT / "data" / "raw" / "openrouter_usage").glob("*/rankings_daily_*.json"))
    if not paths:
        return []
    envelope = load_envelope(paths[-1])
    rows = []
    for item in envelope["payload"].get("data") or []:
        slug = item.get("model_permaslug") or ""
        rows.append({
            "usage_date": item.get("date"),
            "model_permaslug": slug,
            "provider": slug.split("/", 1)[0] if "/" in slug else slug,
            "total_tokens": item.get("total_tokens"),
            "available_at": envelope["retrieved_at"],
            "source_retrieved_at": envelope["retrieved_at"],
            "source": "openrouter_rankings",
            "scope": "openrouter_platform_top50_plus_other",
        })
    rows.sort(key=lambda row: (row["usage_date"] or "", row["provider"], row["model_permaslug"]))
    return rows


def normalize_cloudflare_product_ranks() -> list[dict]:
    with (PROJECT_ROOT / "config" / "ai_product_domains.csv").open(encoding="utf-8", newline="") as handle:
        products = {row["product_id"]: row for row in csv.DictReader(handle)}
    selected = {}
    for product_id, product in products.items():
        for path in sorted((PROJECT_ROOT / "data" / "raw" / "cloudflare_radar").glob(f"*/{product_id}_*.json")):
            envelope = load_envelope(path)
            payload = envelope.get("payload") or {}
            details = (payload.get("result") or {}).get("details_0") or {}
            ranges = ((payload.get("result") or {}).get("meta") or {}).get("dateRange") or []
            observation_date = str((ranges[-1] if ranges else {}).get("endTime") or envelope["retrieved_at"])[:10]
            row = {
                "product_id": product_id,
                "product_name": product["product_name"],
                "domain": product["domain"],
                "listed_ticker": product["listed_ticker"],
                "owner": product["owner"],
                "observation_date": observation_date,
                "rank": details.get("rank"),
                "rank_bucket": details.get("bucket"),
                "categories": json.dumps(details.get("categories") or [], ensure_ascii=False, separators=(",", ":")),
                "available_at": envelope["retrieved_at"],
                "source_retrieved_at": envelope["retrieved_at"],
                "source": "cloudflare_radar",
                "signal_scope": product["signal_scope"],
                "pit_status": "daily_snapshot_broad_web_attention_proxy",
            }
            key = (product_id, observation_date)
            if key not in selected or row["source_retrieved_at"] > selected[key]["source_retrieved_at"]:
                selected[key] = row
    return sorted(selected.values(), key=lambda row: (row["observation_date"], row["product_id"]))


def main() -> int:
    universe_path = PROJECT_ROOT / "config" / "research_universe.csv"
    if not universe_path.exists():
        universe_path = PROJECT_ROOT / "config" / "pilot_universe.csv"
    companies = load_universe(universe_path)
    company_tickers = [company.ticker for company in companies]
    with (PROJECT_ROOT / "config" / "benchmarks.csv").open(encoding="utf-8", newline="") as handle:
        benchmark_tickers = [row["ticker"] for row in csv.DictReader(handle)]
    market = normalize_market(company_tickers + benchmark_tickers)
    unadjusted_market = normalize_unadjusted_market(company_tickers)
    earnings = normalize_earnings(company_tickers)
    fundamentals = normalize_fundamentals(company_tickers)
    annual = build_annual_fundamentals(fundamentals)
    quarterly = build_quarterly_fundamentals(fundamentals)
    developer = normalize_developer_snapshots(companies)
    models = normalize_openrouter()
    openrouter_usage = normalize_openrouter_usage()
    product_ranks = normalize_cloudflare_product_ranks()
    root = PROJECT_ROOT / "data" / "standardized"
    write_csv(root / "market_daily.csv", market, list(market[0]))
    write_csv(root / "market_unadjusted_daily.csv", unadjusted_market, list(unadjusted_market[0]))
    write_csv(root / "earnings.csv", earnings, list(earnings[0]))
    write_csv(root / "fundamental_observations.csv", fundamentals, list(fundamentals[0]))
    write_csv(root / "fundamental_annual.csv", annual, list(annual[0]))
    write_csv(root / "fundamental_quarterly.csv", quarterly, list(quarterly[0]))
    write_csv(root / "developer_snapshot.csv", developer, list(developer[0]))
    write_csv(root / "openrouter_model_snapshot.csv", models, list(models[0]))
    if openrouter_usage:
        write_csv(root / "openrouter_usage_daily.csv", openrouter_usage, list(openrouter_usage[0]))
    if product_ranks:
        write_csv(root / "product_domain_rank_daily.csv", product_ranks, list(product_ranks[0]))
    print(f"market={len(market)} earnings={len(earnings)} fundamentals={len(fundamentals)} annual={len(annual)} quarterly={len(quarterly)} developer={len(developer)} models={len(models)} openrouter_usage={len(openrouter_usage)} product_ranks={len(product_ranks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
