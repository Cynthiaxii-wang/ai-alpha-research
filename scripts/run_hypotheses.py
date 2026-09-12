#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import statistics
import sys
import calendar
import csv
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.research_utils import mean, parse_float, pearson, read_csv, spearman  # noqa: E402
from ai_alpha_research.universe import load_universe  # noqa: E402
from ai_alpha_research.warehouse import read_table, warehouse_path  # noqa: E402


def research_rows(table_name: str, fallback: Path) -> list[dict]:
    if warehouse_path(PROJECT_ROOT).exists():
        return read_table(PROJECT_ROOT, table_name)
    return read_csv(fallback)


def percentile_map(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: item[1])
    if len(ordered) == 1:
        return {ordered[0][0]: 0.5}
    return {ticker: index / (len(ordered) - 1) for index, (ticker, _) in enumerate(ordered)}


def grouped_percentile_map(values: dict[str, float], groups: dict[str, str]) -> dict[str, float]:
    output = {}
    grouped = defaultdict(dict)
    for ticker, value in values.items():
        grouped[groups.get(ticker, "unclassified")][ticker] = value
    for rows in grouped.values():
        output.update(percentile_map(rows))
    return output


def ols_residuals(values: dict[str, float], controls: list[dict[str, float]]) -> dict[str, float]:
    """Return cross-sectional OLS residuals using a tiny ridge for singular ranks."""
    tickers = [ticker for ticker in values if all(ticker in control for control in controls)]
    if len(tickers) < len(controls) + 4:
        return {}
    width = len(controls) + 1
    matrix = [[0.0 for _ in range(width)] for _ in range(width)]
    vector = [0.0 for _ in range(width)]
    rows = []
    for ticker in tickers:
        x = [1.0] + [control[ticker] for control in controls]
        y = values[ticker]
        rows.append((ticker, x, y))
        for i in range(width):
            vector[i] += x[i] * y
            for j in range(width):
                matrix[i][j] += x[i] * x[j]
    for i in range(1, width):
        matrix[i][i] += 1e-8
    augmented = [matrix[i] + [vector[i]] for i in range(width)]
    for column in range(width):
        pivot = max(range(column, width), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            return {}
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(width):
            if row == column:
                continue
            multiplier = augmented[row][column]
            augmented[row] = [
                augmented[row][position] - multiplier * augmented[column][position]
                for position in range(width + 1)
            ]
    beta = [augmented[index][-1] for index in range(width)]
    return {
        ticker: y - sum(beta[position] * x[position] for position in range(width))
        for ticker, x, y in rows
    }


def fundamental_dislocation_test(features: list[dict], targets: list[dict], stages: dict[str, str]) -> dict:
    """Test raw, within-stage and controlled versions of the Signal Monitor gap."""
    histories = defaultdict(list)
    momentum_by_date = defaultdict(dict)
    momentum_60d_by_date = defaultdict(dict)
    for row in features:
        value = parse_float(row["feature_value"])
        if value is None:
            continue
        if row["feature_name"] in {"revenue_yoy", "fcf_margin", "price_to_sales_filing_basis", "realized_vol_20d"}:
            histories[(row["ticker"], row["feature_name"])].append(
                (row["feature_date"], row.get("source_period_end"), value)
            )
        elif row["feature_name"] == "momentum_20d":
            momentum_by_date[row["feature_date"]][row["ticker"]] = value
        elif row["feature_name"] == "momentum_60d":
            momentum_60d_by_date[row["feature_date"]][row["ticker"]] = value
    for rows in histories.values():
        rows.sort()
    target_map = {(row["ticker"], row["target_date"]): row for row in targets}
    minimum_cross_section = max(15, math.ceil(len(stages) * 0.60))
    eligible_dates = sorted(
        day for day, values in momentum_by_date.items()
        if len(values) >= minimum_cross_section
        and len(momentum_60d_by_date.get(day, {})) >= minimum_cross_section
    )
    rebalance_dates = eligible_dates[::20]
    samples = []

    def latest(ticker: str, name: str, day: str):
        matches = [item for item in histories.get((ticker, name), []) if item[0] <= day]
        return matches[-1][2] if matches else None

    def latest_change(ticker: str, name: str, day: str):
        matches = [item for item in histories.get((ticker, name), []) if item[0] <= day]
        return matches[-1][2] - matches[-2][2] if len(matches) >= 2 else None

    def latest_yoy_change(ticker: str, name: str, day: str):
        matches = [item for item in histories.get((ticker, name), []) if item[0] <= day and item[1]]
        if not matches:
            return None
        current = matches[-1]
        current_end = date.fromisoformat(current[1])
        candidates = [item for item in matches[:-1]
            if 330 <= (current_end - date.fromisoformat(item[1])).days <= 400]
        prior = min(candidates,
            key=lambda item: abs((current_end - date.fromisoformat(item[1])).days - 365),
            default=None)
        return current[2] - prior[2] if prior else None

    for day in rebalance_dates:
        momentum = momentum_by_date[day]
        momentum_60d = momentum_60d_by_date[day]
        revenue = {ticker: latest(ticker, "revenue_yoy", day) for ticker in momentum}
        revenue_acceleration = {ticker: latest_change(ticker, "revenue_yoy", day) for ticker in momentum}
        fcf = {ticker: latest(ticker, "fcf_margin", day) for ticker in momentum}
        fcf_delta = {ticker: latest_yoy_change(ticker, "fcf_margin", day) for ticker in momentum}
        complete = [
            ticker for ticker in momentum
            if ticker in momentum_60d and revenue[ticker] is not None
            and revenue_acceleration[ticker] is not None and fcf[ticker] is not None
            and fcf_delta[ticker] is not None and (ticker, day) in target_map
        ]
        if len(complete) < minimum_cross_section:
            continue
        complete_values = {ticker: revenue[ticker] for ticker in complete}
        revenue_rank = percentile_map(complete_values)
        acceleration_rank = percentile_map({ticker: revenue_acceleration[ticker] for ticker in complete})
        fcf_rank = percentile_map({ticker: fcf[ticker] for ticker in complete})
        fcf_delta_rank = percentile_map({ticker: fcf_delta[ticker] for ticker in complete})
        market_20_rank = percentile_map({ticker: momentum[ticker] for ticker in complete})
        market_60_rank = percentile_map({ticker: momentum_60d[ticker] for ticker in complete})
        stage_revenue_rank = grouped_percentile_map(complete_values, stages)
        stage_acceleration_rank = grouped_percentile_map({ticker: revenue_acceleration[ticker] for ticker in complete}, stages)
        stage_fcf_rank = grouped_percentile_map({ticker: fcf[ticker] for ticker in complete}, stages)
        stage_fcf_delta_rank = grouped_percentile_map({ticker: fcf_delta[ticker] for ticker in complete}, stages)
        stage_market_20_rank = grouped_percentile_map({ticker: momentum[ticker] for ticker in complete}, stages)
        stage_market_60_rank = grouped_percentile_map({ticker: momentum_60d[ticker] for ticker in complete}, stages)
        raw_gap = {
            ticker: (
                0.375 * revenue_rank[ticker]
                + 0.3125 * acceleration_rank[ticker]
                + 0.3125 * (fcf_rank[ticker] + fcf_delta_rank[ticker]) / 2
                - (0.60 * market_20_rank[ticker] + 0.40 * market_60_rank[ticker])
            ) for ticker in complete
        }
        stage_gap = {
            ticker: (
                0.375 * stage_revenue_rank[ticker]
                + 0.3125 * stage_acceleration_rank[ticker]
                + 0.3125 * (stage_fcf_rank[ticker] + stage_fcf_delta_rank[ticker]) / 2
                - (0.60 * stage_market_20_rank[ticker] + 0.40 * stage_market_60_rank[ticker])
            ) for ticker in complete
        }
        valuation = {ticker: latest(ticker, "price_to_sales_filing_basis", day) for ticker in complete}
        volatility = {ticker: latest(ticker, "realized_vol_20d", day) for ticker in complete}
        controlled_tickers = [ticker for ticker in complete if valuation[ticker] is not None and volatility[ticker] is not None]
        valuation_rank = grouped_percentile_map({ticker: valuation[ticker] for ticker in controlled_tickers}, stages)
        volatility_rank = grouped_percentile_map({ticker: volatility[ticker] for ticker in controlled_tickers}, stages)
        controlled_gap = ols_residuals(stage_gap, [valuation_rank, volatility_rank])
        cross_section = []
        for ticker in complete:
            target = target_map[(ticker, day)]
            row = {
                "ticker": ticker, "date": day, "stage": stages.get(ticker, "unclassified"),
                "raw_gap": raw_gap[ticker], "stage_gap": stage_gap[ticker],
                "controlled_gap": controlled_gap.get(ticker),
            }
            for horizon in (20, 60, 120):
                row[f"ret{horizon}"] = parse_float(target.get(f"excess_return_{horizon}d"))
            samples.append(row)
            cross_section.append(row)
        for horizon in (20, 60, 120):
            stage_returns = defaultdict(list)
            for row in cross_section:
                if row[f"ret{horizon}"] is not None:
                    stage_returns[row["stage"]].append(row[f"ret{horizon}"])
            stage_means = {stage: mean(values) for stage, values in stage_returns.items()}
            for row in cross_section:
                value = row[f"ret{horizon}"]
                row[f"controlled_ret{horizon}"] = value - stage_means[row["stage"]] if value is not None and row["stage"] in stage_means else None

    def summarize_variant(score_key: str, controlled_return: bool = False) -> dict:
        date_ics = {20: [], 60: [], 120: []}
        group_values = {20: defaultdict(list), 60: defaultdict(list), 120: defaultdict(list)}
        date_spreads = {20: [], 60: [], 120: []}
        by_date = defaultdict(list)
        for row in samples:
            if row.get(score_key) is not None:
                by_date[row["date"]].append(row)
        for day, rows in sorted(by_date.items()):
            for horizon in (20, 60, 120):
                return_key = f"controlled_ret{horizon}" if controlled_return else f"ret{horizon}"
                mature = [row for row in rows if row.get(return_key) is not None]
                if len(mature) < 8:
                    continue
                ic = spearman([row[score_key] for row in mature], [row[return_key] for row in mature])
                if ic is not None:
                    date_ics[horizon].append((day, ic))
                ordered = sorted(mature, key=lambda row: row[score_key])
                size = len(ordered)
                dated_groups = defaultdict(list)
                for index, row in enumerate(ordered):
                    quintile = min(5, math.floor(index * 5 / size) + 1)
                    value = row[return_key]
                    dated_groups[quintile].append(value)
                for quintile, values in dated_groups.items():
                    group_values[horizon][quintile].append(mean(values))
                q1, q5 = mean(dated_groups[1]), mean(dated_groups[5])
                if q1 is not None and q5 is not None:
                    date_spreads[horizon].append({"date": day, "spread": q5 - q1})
        horizon_results = {}
        for horizon in (20, 60, 120):
            return_key = f"controlled_ret{horizon}" if controlled_return else f"ret{horizon}"
            mature = [row for row in samples if row.get(score_key) is not None and row.get(return_key) is not None]
            ics = [value for _, value in date_ics[horizon] if value is not None]
            groups = [mean(group_values[horizon].get(group, [])) for group in range(1, 6)]
            spreads = [item["spread"] for item in date_spreads[horizon]]
            # Equal-weight rebalance dates. This makes the headline spread,
            # its t-stat and the Q1/Q5 chart use the same aggregation rule.
            top_bottom = mean(spreads)
            spread_std = statistics.stdev(spreads) if len(spreads) >= 2 else None
            spread_t_stat = (
                statistics.fmean(spreads) / (spread_std / math.sqrt(len(spreads)))
                if spread_std not in (None, 0) else None
            )
            monotonic_steps = sum(
                groups[index] is not None and groups[index - 1] is not None and groups[index] >= groups[index - 1]
                for index in range(1, 5)
            )
            horizon_results[str(horizon)] = {
                "sample_size": len(mature), "rank_ic": mean(ics),
                "company_count": len({row["ticker"] for row in mature}),
                "ic_stability": sum(value > 0 for value in ics) / len(ics) if ics else None,
                "hit_rate": mean(1.0 if row[score_key] * row[return_key] > 0 else 0.0 for row in mature if row[score_key] != 0),
                "top_bottom_spread": top_bottom, "group_returns": groups,
                "bottom_quintile_return": groups[0], "top_quintile_return": groups[4],
                "monotonic_steps": monotonic_steps, "rebalance_periods": len(ics),
                "spread_t_stat": spread_t_stat,
                "spread_positive_rate": sum(value > 0 for value in spreads) / len(spreads) if spreads else None,
            }
        cumulative = 1.0
        cumulative_series = []
        peak = 1.0
        max_drawdown = 0.0
        for item in date_spreads[20]:
            cumulative *= 1 + item["spread"]
            peak = max(peak, cumulative)
            max_drawdown = min(max_drawdown, cumulative / peak - 1)
            cumulative_series.append({"date": item["date"], "value": cumulative - 1, "periodSpread": item["spread"]})
        return {"horizons": horizon_results, "period_spreads": date_spreads, "cumulative_20d": cumulative_series, "max_drawdown_20d": max_drawdown}

    variants = {
        "raw_cross_chain": summarize_variant("raw_gap"),
        "within_stage": summarize_variant("stage_gap"),
        "controlled": summarize_variant("controlled_gap", controlled_return=True),
    }
    horizon_results = variants["within_stage"]["horizons"]
    primary_ic_rows = []
    by_date = defaultdict(list)
    for row in samples:
        if row.get("stage_gap") is not None and row.get("ret20") is not None:
            by_date[row["date"]].append(row)
    for day, rows in sorted(by_date.items()):
        if len(rows) >= 8:
            value = spearman([row["stage_gap"] for row in rows], [row["ret20"] for row in rows])
            if value is not None:
                primary_ic_rows.append((day, value))
    quarterly = defaultdict(list)
    for day, value in primary_ic_rows:
        if value is not None:
            quarter = f"{day[:4]}Q{(int(day[5:7]) - 1) // 3 + 1}"
            quarterly[quarter].append(value)
    ic_series = [{"period": period, "value": mean(values)} for period, values in sorted(quarterly.items())]
    primary = horizon_results["60"]
    rank_ic = primary["rank_ic"]
    stability = primary["ic_stability"]
    effective_periods = primary["rebalance_periods"]
    if effective_periods < 24 or rank_ic is None:
        verdict = "Needs Data"
    elif rank_ic >= 0.08 and stability is not None and stability >= 0.60:
        verdict = "Validated"
    elif rank_ic > 0 and stability is not None and stability >= 0.50:
        verdict = "Promising"
    elif rank_ic <= -0.05:
        verdict = "Rejected"
    else:
        verdict = "Weak"
    conclusion = (
        f"同层中性Gap的60日 Rank IC 为 {rank_ic:+.2f}，正向 IC 期占比 {stability:.0%}；"
        f"Q5减Q1的60日平均超额收益为 {primary['top_bottom_spread']:+.1%}。"
        if rank_ic is not None and stability is not None and primary["top_bottom_spread"] is not None
        else "当前成熟样本不足，暂不能判断定价错位是否具有稳定收益预测能力。"
    )
    return {
        "experiment_id": "R1",
        "name": "Fundamental Dislocation Factor",
        "category": "Return Prediction",
        "verdict": verdict,
        "primary_horizon": "60",
        "horizons": horizon_results,
        "ic_time_series": ic_series,
        "cumulative_20d": variants["within_stage"]["cumulative_20d"],
        "max_drawdown_20d": variants["within_stage"]["max_drawdown_20d"],
        "control_variants": [
            {"id": "raw", "name": "原始全链Gap", "description": "全样本统一排名，仅控制QQQ市场收益", "horizons": variants["raw_cross_chain"]["horizons"]},
            {"id": "stage", "name": "同层中性Gap", "description": "基本面与价格均在上游/中游/下游内部排名", "horizons": variants["within_stage"]["horizons"]},
            {"id": "controlled", "name": "估值与波动率控制", "description": "同层Gap剔除P/S和20日波动率暴露，未来收益再做同层中性", "horizons": variants["controlled"]["horizons"]},
        ],
        "factor_definition": {
            "formula": "Live Fundamental = 30%增长 + 25%增长加速 + 25%现金流质量 + 20% EPS预期修正；Market = 60% 20D + 40% 60D同层价格分位；Gap = Fundamental − Market",
            "backtest_formula": "历史PIT回测尚无EPS Revision序列，因此将其余三维重新归一为：37.5%增长 + 31.25%增长加速 + 31.25%现金流质量；FCF Margin变化按去年同财季计算。",
            "question": "基本面仍强、但近期相对价格表现弱的公司，是否会在信息扩散后获得未来超额收益？",
            "mechanisms": ["财报信息扩散慢于短期资金流", "指数、仓位或风险冲击造成非基本面抛售", "基本面持续兑现后触发估值修复"],
            "failure_modes": ["滞后财务数据尚未反映订单或指引恶化", "高质量公司仍可能处于估值压缩周期", "所谓错位可能是市场提前识别了基本面拐点"],
        },
        "backtest_scope": {
            "start_date": min((row["date"] for row in samples), default=None),
            "end_date": max((row["date"] for row in samples), default=None),
            "rebalance_rule": "每20个交易日", "entry_rule": "信号日后的下一交易日收盘", "benchmark": "QQQ超额收益",
            "company_count": primary.get("company_count"), "cross_section_count": primary.get("rebalance_periods"),
        },
        "conclusion": conclusion,
        "next_action": "继续扩展历史区间与公司数，加入交易成本、规模和更细行业控制；当前结果只能用于证伪或生成研究问题。",
        "method": "每20个交易日重建横截面；历史核心分数使用Revenue YoY、Revenue增长加速度、FCF Margin及其同财季同比变化，市场分数合并20D/60D动量；主结果使用同层Gap，次日收盘入场并观察20D/60D/120D相对QQQ收益。控制版本进一步剔除P/S、20日波动率及同层共同收益。",
    }


def token_usage_summary(rows: list[dict]) -> dict:
    daily_total = defaultdict(float)
    provider_daily = defaultdict(float)
    models = set()
    for row in rows:
        usage_date = row.get("usage_date")
        provider = row.get("provider")
        tokens = parse_float(row.get("total_tokens"))
        if not usage_date or tokens is None:
            continue
        daily_total[usage_date] += tokens
        if provider and provider != "other":
            provider_daily[(provider, usage_date)] += tokens
            models.add(row.get("model_permaslug"))
    shares = defaultdict(list)
    for (provider, usage_date), tokens in provider_daily.items():
        total = daily_total.get(usage_date)
        if total:
            shares[provider].append((usage_date, tokens / total))
    latest_day = max(daily_total, default=None)
    leaders = []
    if latest_day:
        for provider, values in shares.items():
            latest = next((share for day, share in reversed(sorted(values)) if day == latest_day), None)
            if latest is not None:
                leaders.append((provider, latest))
    leaders.sort(key=lambda item: item[1], reverse=True)
    return {
        "sample_size": sum(len(values) for values in shares.values()),
        "coverage_days": len(daily_total),
        "start_date": min(daily_total, default=None),
        "end_date": latest_day,
        "provider_count": len(shares),
        "model_count": len(models),
        "leading_provider": leaders[0][0] if leaders else None,
        "leading_share": leaders[0][1] if leaders else None,
    }


def calendar_quarter_key(value: str) -> int:
    observed = date.fromisoformat(value[:10])
    return observed.year * 4 + (observed.month - 1) // 3


def capex_conversion_quarterly_test(quarterly: list[dict], companies) -> dict:
    """Pooled lead/lag screen using PIT-safe single-quarter SEC values."""
    bucket_by_ticker = {company.ticker: company.value_chain_bucket for company in companies}

    def segment(ticker: str) -> str:
        bucket = bucket_by_ticker.get(ticker, "")
        if bucket in {"cloud_platform", "cloud_model_platform"}:
            return "Cloud"
        if bucket == "foundry":
            return "Foundry"
        if bucket in {"compute", "memory", "networking", "semiconductor_networking"}:
            return "Semiconductor"
        return "Other"

    by_ticker = defaultdict(list)
    for row in quarterly:
        by_ticker[row["ticker"]].append(row)
    samples = defaultdict(list)
    for ticker, rows in by_ticker.items():
        rows.sort(key=lambda row: row["period_end"])
        for index, current in enumerate(rows):
            capex_growth = parse_float(current.get("capex_yoy"))
            if capex_growth is None:
                continue
            for lag in (1, 2):
                if index + lag >= len(rows):
                    continue
                future = rows[index + lag]
                samples[(lag, "revenue")].append({
                    "ticker": ticker, "segment": segment(ticker), "x": capex_growth,
                    "y": parse_float(future.get("revenue_yoy")), "period_key": calendar_quarter_key(current["period_end"]),
                })
                samples[(lag, "fcf")].append({
                    "ticker": ticker, "segment": segment(ticker), "x": capex_growth,
                    "y": parse_float(future.get("fcf_margin")), "period_key": calendar_quarter_key(current["period_end"]),
                })

    def summarize(rows: list[dict], minimum_cross_section: int = 5) -> dict:
        complete = [row for row in rows if row["y"] is not None]
        by_period = defaultdict(list)
        for row in complete:
            by_period[row["period_key"]].append(row)
        period_ics = []
        for period_key, period_rows in sorted(by_period.items()):
            if len(period_rows) < minimum_cross_section:
                continue
            value = spearman([row["x"] for row in period_rows], [row["y"] for row in period_rows])
            if value is not None:
                period_ics.append({"period_key": period_key, "rank_ic": value, "sample_size": len(period_rows)})
        return {
            "sample_size": len(complete),
            "company_count": len({row["ticker"] for row in complete}),
            "rank_ic": mean(item["rank_ic"] for item in period_ics),
            "ic_stability": mean(1.0 if item["rank_ic"] > 0 else 0.0 for item in period_ics),
            "period_count": len(period_ics),
            "period_ics": period_ics,
            "pooled_rank_correlation": spearman([row["x"] for row in complete], [row["y"] for row in complete]),
            "pooled_pearson": pearson([row["x"] for row in complete], [row["y"] for row in complete]),
        }

    lead_lag = {
        f"+{lag}Q_{target}": summarize(samples[(lag, target)])
        for lag in (1, 2) for target in ("revenue", "fcf")
    }
    segment_results = {}
    for segment_name in ("Cloud", "Semiconductor", "Foundry"):
        segment_results[segment_name] = {
            f"+{lag}Q_revenue": summarize([row for row in samples[(lag, "revenue")] if row["segment"] == segment_name], 3)
            for lag in (1, 2)
        }
    primary = lead_lag["+1Q_revenue"]
    ic = primary["rank_ic"]
    if primary["sample_size"] < 50 or ic is None:
        verdict = "Needs Data"
    elif ic >= 0.08 and primary["ic_stability"] is not None and primary["ic_stability"] >= 0.55:
        verdict = "Promising"
    elif ic <= -0.05:
        verdict = "Rejected"
    else:
        verdict = "Weak"
    return {
        "status": "quarterly_lead_lag_complete",
        "verdict": verdict,
        "sample_size": primary["sample_size"],
        "company_count": primary["company_count"],
        "lead_lag": lead_lag,
        "segment_results": segment_results,
        "warning": "Primary Rank IC is the mean of calendar-quarter cross-sectional ICs; pooled correlations are retained only as diagnostics. Uses total company capex, not disclosed AI-only capex; industry and macro effects are not yet controlled.",
    }


def token_to_cloud_revenue_test(token_rows: list[dict], quarterly: list[dict], companies) -> dict:
    """Calendar-quarter pilot: OpenRouter token growth leads cloud-cohort revenue growth."""
    daily_total = defaultdict(float)
    for row in token_rows:
        value = parse_float(row.get("total_tokens"))
        if value is not None and row.get("usage_date"):
            daily_total[row["usage_date"]] += value
    quarter_tokens = defaultdict(float)
    quarter_last_day = {}
    for day, value in daily_total.items():
        key = calendar_quarter_key(day)
        quarter_tokens[key] += value
        quarter_last_day[key] = max(quarter_last_day.get(key, day), day)
    complete_quarters = {}
    for key, value in quarter_tokens.items():
        year, quarter_zero = divmod(key, 4)
        end_month = (quarter_zero + 1) * 3
        quarter_end = date(year, end_month, calendar.monthrange(year, end_month)[1]).isoformat()
        if quarter_last_day[key] >= quarter_end:
            complete_quarters[key] = value
    token_growth = {}
    for key in sorted(complete_quarters):
        prior = complete_quarters.get(key - 1)
        if prior:
            token_growth[key] = complete_quarters[key] / prior - 1

    cloud_tickers = {
        company.ticker for company in companies
        if company.value_chain_bucket in {"cloud_platform", "cloud_model_platform"}
    }
    revenue_by_quarter = defaultdict(list)
    for row in quarterly:
        value = parse_float(row.get("revenue_yoy"))
        if row.get("ticker") in cloud_tickers and value is not None:
            revenue_by_quarter[calendar_quarter_key(row["period_end"])].append(value)
    cloud_revenue_growth = {key: statistics.median(values) for key, values in revenue_by_quarter.items()}

    lead_lag = {}
    for lag in (1, 2):
        pairs = [(growth, cloud_revenue_growth[key + lag]) for key, growth in token_growth.items() if key + lag in cloud_revenue_growth]
        lead_lag[f"+{lag}Q_revenue"] = {
            "sample_size": len(pairs),
            "rank_ic": spearman([x for x, _ in pairs], [y for _, y in pairs]),
            "pearson": pearson([x for x, _ in pairs], [y for _, y in pairs]),
        }
    return {
        "status": "pilot_lead_lag_complete",
        "verdict": "Needs Data",
        "sample_size": lead_lag["+1Q_revenue"]["sample_size"],
        "lead_lag": lead_lag,
        "complete_token_quarters": len(complete_quarters),
        "cloud_company_count": len(cloud_tickers),
        "warning": "OpenRouter is one platform and total-company revenue is not cloud-segment revenue. The quarterly time-series sample is too short for inference.",
    }


def value_chain_transmission_test(quarterly: list[dict], companies) -> dict:
    """Test whether CSP capex growth leads upstream semiconductor revenue growth."""
    bucket = {company.ticker: company.value_chain_bucket for company in companies}
    cloud = {ticker for ticker, value in bucket.items() if value in {"cloud_platform", "cloud_model_platform"}}
    upstream = {ticker for ticker, value in bucket.items() if value in {"compute", "memory", "networking", "semiconductor_networking"}}
    cloud_capex = defaultdict(list)
    upstream_revenue = defaultdict(list)
    for row in quarterly:
        period = calendar_quarter_key(row["period_end"])
        if row["ticker"] in cloud:
            value = parse_float(row.get("capex_yoy"))
            if value is not None:
                cloud_capex[period].append(value)
        if row["ticker"] in upstream:
            value = parse_float(row.get("revenue_yoy"))
            if value is not None:
                upstream_revenue[period].append(value)
    capex_series = {period: statistics.median(values) for period, values in cloud_capex.items()}
    revenue_series = {period: statistics.median(values) for period, values in upstream_revenue.items()}
    horizons = {}
    for lag in (0, 1, 2):
        pairs = [(value, revenue_series[period + lag]) for period, value in capex_series.items() if period + lag in revenue_series]
        horizons[f"+{lag}Q"] = {
            "sample_size": len(pairs),
            "rank_ic": spearman([x for x, _ in pairs], [y for _, y in pairs]),
            "pearson": pearson([x for x, _ in pairs], [y for _, y in pairs]),
        }
    primary = horizons["+1Q"]
    verdict = "Promising" if primary["sample_size"] >= 16 and primary["rank_ic"] is not None and primary["rank_ic"] >= 0.20 else "Weak" if primary["sample_size"] >= 12 else "Needs Data"
    return {
        "name": "CSP Capex → Upstream Revenue",
        "verdict": verdict,
        "signal": "Median YoY capex growth of MSFT AMZN GOOGL and ORCL",
        "target": "Median YoY revenue growth of NVDA AMD AVGO MU and ANET",
        "horizons": horizons,
        "conclusion": (
            f"CSP Capex增长对上游收入增长的+1Q时序Rank相关为 {primary['rank_ic']:+.2f}，样本为{primary['sample_size']}个季度。"
            if primary["rank_ic"] is not None else "现有季度数据不足以判断CSP Capex对上游收入的领先关系。"
        ),
        "warning": "This is an aggregate time-series screen. Total company capex and total company revenue are proxies; macro cycles and common trends are not controlled.",
    }


def factor_lab_payload(h1: dict, h2: dict, h3: dict, dislocation: dict, token_usage: dict, token_lead_lag: dict, product_ranks: list[dict]) -> dict:
    adoption_ic = h1["rank_ic_activity_change_vs_next_earnings_surprise"]
    capex_ic = h2["lead_lag"]["+1Q_revenue"]["rank_ic"]
    composite_ic = h3["rank_ic_20d"]
    radar_counts = defaultdict(int)
    for row in product_ranks:
        radar_counts[row.get("product_id")] += 1
    radar_depth = min(radar_counts.values()) if radar_counts else 0
    return {
        "fundamental_prediction": [
            {
                "experiment_id": "F1", "name": "AI Adoption Factor", "category": "Fundamental Prediction",
                "verdict": "Weak" if h1["sample_size"] >= 50 else "Needs Data", "primary_horizon": "Next earnings",
                "metrics": {"rank_ic": adoption_ic, "ic_stability": None, "hit_rate": None, "sample_size": h1["sample_size"], "top_bottom_spread": None},
                "ic_time_series": [], "group_returns": [], "lead_lag": [],
                "conclusion": "当前开源活动代理与下一次盈利意外的相关性接近零，不能视为产品采用率。",
                "monitoring_metrics": [
                    {"label": "Radar 产品", "value": str(len({row.get('product_id') for row in product_ranks}))},
                    {"label": "每产品快照", "value": str(radar_depth)},
                ],
                "factor_definition": {
                    "formula": "Adoption Change = log(1 + 当月Commit) − log(1 + 前3个月平均Commit)",
                    "question": "开发者开源活动的加速，是否领先下一次盈利变化？",
                    "mechanisms": ["开发采用可能领先商业采购", "生态活跃度可能降低产品获客成本"],
                    "failure_modes": ["开源仓库不等于付费产品使用", "公司选择性开源会改变Commit口径"],
                },
                "next_action": "每日积累Radar域名排名；Google Trends获批后补充五年产品搜索历史。", "method": h1["signal_definition"] + "；Cloudflare Radar仅作为广义网页关注度代理。",
            },
            {
                "experiment_id": "F2", "name": "Capex Conversion Factor", "category": "Fundamental Prediction",
                "verdict": h2["verdict"], "primary_horizon": "+1Q",
                "metrics": {"rank_ic": capex_ic, "ic_stability": h2["lead_lag"]["+1Q_revenue"]["ic_stability"], "hit_rate": None, "sample_size": h2["sample_size"], "top_bottom_spread": None},
                "ic_time_series": [], "group_returns": [],
                "lead_lag": [
                    {"label": "+1Q Revenue", "value": h2["lead_lag"]["+1Q_revenue"]["rank_ic"]},
                    {"label": "+2Q Revenue", "value": h2["lead_lag"]["+2Q_revenue"]["rank_ic"]},
                    {"label": "+1Q FCF Margin", "value": h2["lead_lag"]["+1Q_fcf"]["rank_ic"]},
                    {"label": "+2Q FCF Margin", "value": h2["lead_lag"]["+2Q_fcf"]["rank_ic"]},
                ],
                "segment_results": h2["segment_results"],
                "factor_definition": {
                    "formula": "Capex YoY(t) → Revenue YoY / FCF Margin(t+1Q, t+2Q)",
                    "question": "本期资本开支增长，能否转化为未来收入增长和现金流？",
                    "mechanisms": ["新增算力形成可售云容量", "基础设施投资向芯片、网络和存储收入传导"],
                    "failure_modes": ["总Capex包含非AI投资", "建设周期、利用率和折旧可能延迟或侵蚀回报"],
                },
                "conclusion": f"季度总Capex增长对下一季度收入增长的平均横截面 Rank IC 为 {capex_ic:+.2f}，正向季度占比 {h2['lead_lag']['+1Q_revenue']['ic_stability']:.0%}（{h2['sample_size']}个公司季度）。" if capex_ic is not None and h2["lead_lag"]["+1Q_revenue"]["ic_stability"] is not None else "季度样本不足，暂不能判断Capex转化效率。",
                "next_action": "补充CSP云收入与AI专属Capex，加入行业和宏观控制。", "method": h2["warning"],
            },
            {
                "experiment_id": "F3", "name": "Token Usage Factor", "category": "Fundamental Prediction",
                "verdict": "Needs Data", "primary_horizon": "+1Q / +2Q",
                "metrics": {"rank_ic": token_lead_lag["lead_lag"]["+1Q_revenue"]["rank_ic"], "ic_stability": None, "hit_rate": None, "sample_size": token_lead_lag["sample_size"], "top_bottom_spread": None},
                "ic_time_series": [], "group_returns": [], "lead_lag": [
                    {"label": "+1Q Revenue", "value": token_lead_lag["lead_lag"]["+1Q_revenue"]["rank_ic"]},
                    {"label": "+2Q Revenue", "value": token_lead_lag["lead_lag"]["+2Q_revenue"]["rank_ic"]},
                ],
                "monitoring_metrics": [
                    {"label": "历史区间", "value": f"{token_usage['start_date'] or '—'} → {token_usage['end_date'] or '—'}"},
                    {"label": "覆盖天数", "value": str(token_usage["coverage_days"])},
                    {"label": "Provider数", "value": str(token_usage["provider_count"])},
                    {"label": "最新领先", "value": f"{token_usage['leading_provider'] or '—'} {token_usage['leading_share']:.1%}" if token_usage["leading_share"] is not None else "—"},
                ],
                "factor_definition": {
                    "formula": "OpenRouter Token周度增长(t) → Cloud Revenue YoY(t+1Q, t+2Q)",
                    "question": "模型调用量变化，是否领先云平台收入兑现？",
                    "mechanisms": ["Token消费直接占用推理算力", "调用量扩张可能先于季度财报披露"],
                    "failure_modes": ["OpenRouter并非全市场", "模型迁移、降价和缓存会切断Token与收入关系"],
                },
                "conclusion": f"已完成Token增长对Cloud公司收入的+1Q/+2Q试算，但+1Q只有{token_lead_lag['sample_size']}个完整季度配对，不能据此判断预测能力。",
                "next_action": "继续积累季度历史，并以公司披露的Cloud/AI分部收入替代总收入。",
                "method": "OpenRouter Top 50模型每日Token总量，历史起于2025-01-01；仅代表OpenRouter平台，不代表全市场，跨Provider Token口径不可机械比较。",
            },
        ],
        "return_prediction": [
            dislocation,
            {
                "experiment_id": "R2", "name": "EPS Revision Factor", "category": "Return Prediction",
                "verdict": "Needs Data", "primary_horizon": "20D / 60D",
                "metrics": {"rank_ic": None, "ic_stability": None, "hit_rate": None, "sample_size": 0, "top_bottom_spread": None},
                "ic_time_series": [], "group_returns": [], "lead_lag": [],
                "factor_definition": {
                    "formula": "EPS Revision 30D = 当前一致预期EPS ÷ 30日前一致预期EPS − 1",
                    "question": "分析师盈利预期上调，是否领先未来20D/60D超额收益？",
                    "mechanisms": ["盈利信息逐步进入卖方模型", "连续上调可能强化机构配置"],
                    "failure_modes": ["修正可能已被价格提前交易", "缺乏可靠PIT共识历史会产生回看偏差"],
                },
                "conclusion": "当前可监测30D一致预期修正，但每日point-in-time历史刚开始积累。", "next_action": "持续每日归档后再进入历史收益检验。", "method": "Next-quarter EPS estimate change over trailing 30 days.",
            },
            {
                "experiment_id": "R3", "name": "Fundamental + Valuation Factor", "category": "Return Prediction",
                "verdict": "Rejected" if composite_ic is not None and composite_ic < -0.05 else "Weak", "primary_horizon": "20D",
                "metrics": {"rank_ic": composite_ic, "ic_stability": None, "hit_rate": None, "sample_size": h3["sample_size_20d"], "top_bottom_spread": (h3["composite_qualified_mean_excess_20d"] - h3["composite_comparison_mean_excess_20d"]) if h3["composite_qualified_mean_excess_20d"] is not None and h3["composite_comparison_mean_excess_20d"] is not None else None},
                "ic_time_series": [], "group_returns": [], "lead_lag": [],
                "factor_definition": {
                    "formula": "正EPS Surprise + 正Revenue增长 + 正FCF Margin + P/S不高于当日中位数",
                    "question": "盈利超预期、质量较好且估值较低的组合，是否获得未来20D超额收益？",
                    "mechanisms": ["盈利兑现与合理估值共同降低预期落差", "多条件交集可能过滤低质量便宜股"],
                    "failure_modes": ["EPS历史共识并非已验证PIT数据", "二元阈值会丢失强弱程度并造成样本不稳"],
                },
                "conclusion": "现有惊喜+基本面+估值规则未显示稳定的20日超额收益。", "next_action": "移除历史共识污染，改用正式EPS Revision并做行业中性化。", "method": h3["composite_rule"],
            },
        ],
    }


def developer_activity_to_earnings_test(monthly: list[dict], earnings: list[dict]) -> dict:
    histories = defaultdict(list)
    for row in monthly:
        if row["history_complete_within_window"].lower() != "true":
            continue
        histories[row["ticker"]].append((row["month_end"], parse_float(row["commit_count"]) or 0.0))
    for rows in histories.values():
        rows.sort()
    samples = []
    for event in earnings:
        surprise = parse_float(event["surprise_pct"])
        prior = [(period_end, count) for period_end, count in histories.get(event["ticker"], []) if period_end < event["reported_date"]]
        if surprise is None or len(prior) < 4:
            continue
        current = prior[-1][1]
        baseline = sum(count for _, count in prior[-4:-1]) / 3
        activity_change = math.log1p(current) - math.log1p(baseline)
        samples.append({"ticker": event["ticker"], "reported_date": event["reported_date"], "activity_change": activity_change, "surprise_pct": surprise})
    return {
        "status": "exploratory_complete_history_subset",
        "sample_size": len(samples),
        "company_count": len({row["ticker"] for row in samples}),
        "rank_ic_activity_change_vs_next_earnings_surprise": spearman([row["activity_change"] for row in samples], [row["surprise_pct"] for row in samples]),
        "pearson_activity_change_vs_next_earnings_surprise": pearson([row["activity_change"] for row in samples], [row["surprise_pct"] for row in samples]),
        "signal_definition": "log1p(last complete month commits) minus log1p(mean commits in preceding three complete months)",
        "scope_warning": "Only uncensored selected-repository histories are used; this is a company open-source activity proxy, not direct AI product adoption.",
    }


def earnings_surprise_test(features: list[dict], targets: list[dict]) -> dict:
    target_map = {(row["ticker"], row["target_date"]): row for row in targets}
    valuation = {}
    fundamental_history = defaultdict(list)
    ps_by_date = defaultdict(list)
    for row in features:
        key = (row["ticker"], row["feature_date"])
        value = parse_float(row["feature_value"])
        if row["feature_name"] == "price_to_sales_filing_basis" and value is not None:
            valuation[key] = value
            ps_by_date[row["feature_date"]].append(value)
        elif row["feature_name"] in {"revenue_yoy", "fcf_margin"} and value is not None:
            fundamental_history[(row["ticker"], row["feature_name"])].append((row["feature_date"], value))
    for history in fundamental_history.values():
        history.sort()

    def latest_value(ticker: str, name: str, feature_date: str):
        matches = [value for observed, value in fundamental_history.get((ticker, name), []) if observed <= feature_date]
        return matches[-1] if matches else None

    samples = []
    for row in features:
        if row["feature_name"] != "earnings_surprise_pct":
            continue
        target = target_map.get((row["ticker"], row["feature_date"]))
        if not target:
            continue
        signal = parse_float(row["feature_value"])
        ret20 = parse_float(target["excess_return_20d"])
        ret60 = parse_float(target["excess_return_60d"])
        if signal is not None and ret20 is not None:
            ps = valuation.get((row["ticker"], row["feature_date"]))
            date_values = sorted(ps_by_date.get(row["feature_date"], []))
            ps_median = date_values[len(date_values) // 2] if date_values else None
            revenue_yoy = latest_value(row["ticker"], "revenue_yoy", row["feature_date"])
            fcf_margin = latest_value(row["ticker"], "fcf_margin", row["feature_date"])
            qualified = (
                signal > 0
                and revenue_yoy is not None and revenue_yoy > 0
                and fcf_margin is not None and fcf_margin > 0
                and ps is not None and ps_median is not None and ps <= ps_median
            )
            samples.append({"ticker": row["ticker"], "date": row["feature_date"], "signal": signal, "ret20": ret20, "ret60": ret60, "ps": ps, "revenue_yoy": revenue_yoy, "fcf_margin": fcf_margin, "qualified": qualified})
    xs20 = [row["signal"] for row in samples]
    ys20 = [row["ret20"] for row in samples]
    sixty = [row for row in samples if row["ret60"] is not None]
    positive = [row for row in samples if row["signal"] >= 0]
    negative = [row for row in samples if row["signal"] < 0]
    valuation_samples = [row for row in samples if row["ps"] is not None]
    composite = [row for row in samples if row["qualified"]]
    comparison = [row for row in samples if row["ps"] is not None and row["revenue_yoy"] is not None and row["fcf_margin"] is not None and not row["qualified"]]
    return {
        "status": "exploratory_test_complete",
        "pit_warning": "Alpha Vantage historical estimated EPS snapshots are not independently verified as point-in-time consensus history.",
        "sample_size_20d": len(samples),
        "sample_size_60d": len(sixty),
        "pearson_20d": pearson(xs20, ys20),
        "rank_ic_20d": spearman(xs20, ys20),
        "rank_ic_60d": spearman([row["signal"] for row in sixty], [row["ret60"] for row in sixty]),
        "positive_surprise_mean_excess_20d": mean(row["ret20"] for row in positive),
        "negative_surprise_mean_excess_20d": mean(row["ret20"] for row in negative),
        "positive_count": len(positive),
        "negative_count": len(negative),
        "valuation_coverage_count": len(valuation_samples),
        "composite_qualified_count": len(composite),
        "composite_qualified_mean_excess_20d": mean(row["ret20"] for row in composite),
        "composite_comparison_count": len(comparison),
        "composite_comparison_mean_excess_20d": mean(row["ret20"] for row in comparison),
        "composite_rule": "positive EPS surprise + positive latest revenue growth + positive latest FCF margin + filing-basis P/S at or below same-day universe median",
        "valuation_warning": "Filing-basis P/S is a free-data proxy and may retain residual split/restatement convention differences.",
    }


def capex_conversion_test(annual: list[dict]) -> dict:
    by_ticker = defaultdict(list)
    for row in annual:
        by_ticker[row["ticker"]].append(row)
    samples = []
    for ticker, rows in by_ticker.items():
        rows.sort(key=lambda row: row["period_end"])
        for current, future in zip(rows, rows[1:]):
            capex_growth = parse_float(current["capex_yoy"])
            next_revenue_growth = parse_float(future["revenue_yoy"])
            next_fcf_margin = parse_float(future["fcf_margin"])
            if capex_growth is not None and next_revenue_growth is not None:
                samples.append({
                    "ticker": ticker,
                    "period_end": current["period_end"],
                    "capex_growth": capex_growth,
                    "next_revenue_growth": next_revenue_growth,
                    "next_fcf_margin": next_fcf_margin,
                })
    fcf_samples = [row for row in samples if row["next_fcf_margin"] is not None]
    return {
        "status": "descriptive_small_sample_complete",
        "sample_size": len(samples),
        "capex_growth_vs_next_revenue_growth_pearson": pearson(
            [row["capex_growth"] for row in samples], [row["next_revenue_growth"] for row in samples]
        ),
        "capex_growth_vs_next_revenue_growth_rank_ic": spearman(
            [row["capex_growth"] for row in samples], [row["next_revenue_growth"] for row in samples]
        ),
        "capex_growth_vs_next_fcf_margin_rank_ic": spearman(
            [row["capex_growth"] for row in fcf_samples], [row["next_fcf_margin"] for row in fcf_samples]
        ),
        "warning": "Total capex is used because company-disclosed AI capex is not consistently separable; Pearson and rank results diverge, indicating outlier sensitivity, and the annual sample remains too small for inference.",
    }


def fmt(value) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def write_report(results: dict, path: Path) -> None:
    h1 = results["H1_developer_adoption_to_earnings"]
    h2 = results["H2_capex_conversion"]
    h3 = results["H3_fundamental_surprise_valuation"]
    text = f"""# Expanded Research Findings v2

Generated: {results['generated_at']}

## Executive conclusion

The pipeline now produces standardized point-in-time-aware tables, market and valuation features, next-close-entry targets, and reproducible diagnostics across the expanded AI value-chain universe. This remains hypothesis screening, not evidence of a deployable alpha strategy.

## H1 — Developer adoption → earnings surprise

**Status:** {h1['status']}

Dated GitHub history is tested only where the selected repository's commit window is complete and uncensored. Current stars/downloads are still not backfilled.

- Sample size: {h1['sample_size']}
- Companies represented: {h1['company_count']}
- Rank IC(activity change, next earnings surprise): {fmt(h1['rank_ic_activity_change_vs_next_earnings_surprise'])}
- Pearson(activity change, next earnings surprise): {fmt(h1['pearson_activity_change_vs_next_earnings_surprise'])}

This is a selected-repository open-source activity proxy, not direct AI product adoption or company-wide developer usage.

## H2 — Capex growth → revenue/FCF conversion

**Status:** {h2['status']}

- Sample size: {h2['sample_size']}
- Rank IC(capex growth, +1Q revenue growth): {fmt(h2['lead_lag']['+1Q_revenue']['rank_ic'])}
- Rank IC(capex growth, +2Q revenue growth): {fmt(h2['lead_lag']['+2Q_revenue']['rank_ic'])}
- Rank IC(capex growth, +1Q FCF margin): {fmt(h2['lead_lag']['+1Q_fcf']['rank_ic'])}
- Rank IC(capex growth, +2Q FCF margin): {fmt(h2['lead_lag']['+2Q_fcf']['rank_ic'])}

Interpretation is descriptive only. Total capex is not equivalent to AI capex, and the pooled quarterly sample does not yet control for industry or macro effects.

## H3 — Fundamental improvement + earnings surprise + valuation

**Status:** {h3['status']}

The free-data version now combines earnings surprise, latest filed revenue growth and FCF margin, and filing-basis P/S. Historical consensus estimates remain vendor-unverified.

- 20D event sample: {h3['sample_size_20d']}
- 20D Rank IC: {fmt(h3['rank_ic_20d'])}
- 60D Rank IC: {fmt(h3['rank_ic_60d'])}
- Positive-surprise mean 20D excess return: {fmt(h3['positive_surprise_mean_excess_20d'])}
- Negative-surprise mean 20D excess return: {fmt(h3['negative_surprise_mean_excess_20d'])}
- Valuation-covered event sample: {h3['valuation_coverage_count']}
- Composite-qualified events: {h3['composite_qualified_count']}
- Composite-qualified mean 20D excess return: {fmt(h3['composite_qualified_mean_excess_20d'])}
- Comparable but non-qualified events: {h3['composite_comparison_count']}
- Non-qualified mean 20D excess return: {fmt(h3['composite_comparison_mean_excess_20d'])}

The Alpha Vantage historical estimated-EPS field is not independently verified as a true archived consensus snapshot, so this result is exploratory and must not be presented as a clean PIT backtest.

## What can be claimed

- The free-source ingestion and standardization pipeline works.
- Market Targets are reproducible with an explicit next-close entry convention and QQQ benchmark.
- SEC annual fundamentals use the earliest filed 10-K/20-F value across approved standard tags for each period.
- Developer/model snapshots and dated GitHub histories retain explicit scope and censoring status.

## What cannot yet be claimed

- That developer adoption predicts returns.
- That the pilot factors generate robust alpha.
- That total capex isolates AI investment.
- That the earnings-estimate history is institutional-quality PIT consensus.
- That the current universe and short history provide enough breadth for production portfolio construction.

## Required next evidence

1. Accumulate daily GitHub/Hugging Face/model-price snapshots.
2. Replace the automatic repository proxy with a manually reviewed AI-repository asset map and add stargazer histories.
3. Add delisted/renamed identifiers and survivorship-bias controls where relevant.
4. Compare the free filing-basis valuation proxy with an institutional PIT market-cap source when available.
5. Re-run with sector controls, transaction costs, turnover, and subperiod stability tests.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    features = research_rows("feature_store", PROJECT_ROOT / "data" / "research" / "feature_store.csv")
    targets = research_rows("targets", PROJECT_ROOT / "data" / "research" / "targets.csv")
    annual = research_rows("fundamental_annual", PROJECT_ROOT / "data" / "standardized" / "fundamental_annual.csv")
    quarterly_path = PROJECT_ROOT / "data" / "standardized" / "fundamental_quarterly.csv"
    quarterly = research_rows("fundamental_quarterly", quarterly_path) if quarterly_path.exists() else []
    earnings = research_rows("earnings", PROJECT_ROOT / "data" / "standardized" / "earnings.csv")
    monthly = research_rows("developer_monthly_activity", PROJECT_ROOT / "data" / "standardized" / "developer_monthly_activity.csv")
    usage_path = PROJECT_ROOT / "data" / "standardized" / "openrouter_usage_daily.csv"
    token_rows = research_rows("openrouter_usage_daily", usage_path) if usage_path.exists() else []
    radar_path = PROJECT_ROOT / "data" / "standardized" / "product_domain_rank_daily.csv"
    product_ranks = research_rows("product_domain_rank_daily", radar_path) if radar_path.exists() else []
    companies = load_universe(PROJECT_ROOT / "config" / "research_universe.csv")
    h1 = developer_activity_to_earnings_test(monthly, earnings)
    h2 = capex_conversion_quarterly_test(quarterly, companies)
    h3 = earnings_surprise_test(features, targets)
    with (PROJECT_ROOT / "config" / "research_universe.csv").open(encoding="utf-8", newline="") as handle:
        stages = {row["ticker"]: row.get("primary_stage") or "unclassified" for row in csv.DictReader(handle)}
    dislocation = fundamental_dislocation_test(features, targets, stages)
    token_usage = token_usage_summary(token_rows)
    token_lead_lag = token_to_cloud_revenue_test(token_rows, quarterly, companies)
    chain_transmission = value_chain_transmission_test(quarterly, companies)
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe": [company.ticker for company in companies],
        "benchmark": "QQQ",
        "H1_developer_adoption_to_earnings": h1,
        "H2_capex_conversion": h2,
        "F3_token_to_cloud_revenue": token_lead_lag,
        "value_chain_transmission": chain_transmission,
        "H3_fundamental_surprise_valuation": h3,
        "factor_lab": factor_lab_payload(h1, h2, h3, dislocation, token_usage, token_lead_lag, product_ranks),
    }
    result_path = PROJECT_ROOT / "research" / "results" / "hypothesis_results.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(results, PROJECT_ROOT / "research" / "reports" / "expanded_research_findings.md")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
