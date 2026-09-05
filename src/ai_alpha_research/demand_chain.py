"""Observed demand-chain evidence; no inferred conversion between unrelated panels."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import math


def numeric(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        return None


def build_demand_chain(products, usage, alternative, quarterly, cutoff):
    cutoff_dt = timestamp(cutoff)
    if cutoff_dt is None:
        raise ValueError('Explicit evidence cutoff required')
    def eligible(rows, field='available_at'):
        return [r for r in rows if timestamp(r.get(field)) is not None and timestamp(r[field]) <= cutoff_dt]

    # Resolve versions by availability, not file order. Keep each observed date.
    def versions(rows, keys, available='available_at'):
        result = {}
        for row in eligible(rows, available):
            key = tuple(row.get(k) for k in keys)
            if key not in result or timestamp(row[available]) > timestamp(result[key][available]):
                result[key] = row
        return list(result.values())

    adoption = []
    by_product = defaultdict(list)
    for row in versions(products, ['product_id', 'observation_date']):
        by_product[row['product_id']].append(row)
    for key, rows in sorted(by_product.items()):
        rows.sort(key=lambda r: r['observation_date'])
        last = rows[-1]
        rank = numeric(last.get('rank'))
        adoption.append({'id': key, 'name': last['product_name'], 'value': rank,
            'bucket': last.get('rank_bucket'), 'unit': '域名排名' if rank else '排名区间',
            'date': last['observation_date'], 'availableAt': last['available_at'],
            'source': 'Cloudflare Radar', 'url': 'https://radar.cloudflare.com/domains/domain/' + last['domain'],
            'table': 'product_domain_rank_daily', 'samples': len(rows),
            'scope': 'DNS 关注度；不代表活跃用户或付费转化',
            'tickers': [last['listed_ticker']] if last.get('listed_ticker') else []})

    daily = defaultdict(float)
    model_days = defaultdict(dict)
    usage_rows = versions(usage, ['usage_date', 'model_permaslug'])
    for row in usage_rows:
        value = numeric(row.get('total_tokens'))
        if value is not None and value >= 0 and row['usage_date'] < cutoff_dt.date().isoformat():
            daily[row['usage_date']] += value
            model_days[row['usage_date']][row['model_permaslug']] = value
    days = sorted(daily)
    consumption = {'value': None, 'change': None, 'series': [], 'coverage': 0, 'otherShare': None}
    if days:
        end = date.fromisoformat(days[-1])
        recent = [(end - timedelta(days=i)).isoformat() for i in range(7)]
        previous = [(end - timedelta(days=i)).isoformat() for i in range(7, 14)]
        complete = all(d in daily for d in recent + previous)
        total = sum(daily[d] for d in recent if d in daily)
        prior = sum(daily[d] for d in previous if d in daily)
        consumption.update(value=total if all(d in daily for d in recent) else None,
            change=total / prior - 1 if complete and prior > 0 else None,
            date=days[-1], coverage=sum(d in daily for d in recent + previous),
            otherShare=sum(model_days[d].get('other', 0) for d in recent) / total if total else None,
            series=[{'date': d, 'value': daily[d]} for d in days[-28:]],
            availableAt=max((r['available_at'] for r in usage_rows), default=None))
    consumption.update(source='OpenRouter', url='https://openrouter.ai/rankings',
        table='openrouter_usage_daily', unit='Tokens / 7个完整UTC日',
        scope='Top 50 + other；跨模型Tokenizer不同，份额和总量仅为平台观察指标')

    compute = []
    rentals = defaultdict(list)
    for row in versions(alternative, ['series_id', 'observation_end']):
        if row.get('metric_name') == 'gpu_rental_price' and row.get('unit') == 'USD_per_hour':
            if numeric(row.get('metric_value')) is not None:
                rentals[row['series_id']].append(row)
    for key, rows in sorted(rentals.items()):
        rows.sort(key=lambda r: r['observation_end'])
        last = rows[-1]
        target = date.fromisoformat(last['observation_end']) - timedelta(days=30)
        previous = [r for r in rows if 0 <= (target - date.fromisoformat(r['observation_end'])).days <= 7]
        base = previous[-1] if previous else None
        base_value = numeric(base['metric_value']) if base else None
        value = numeric(last['metric_value'])
        compute.append({'id': key, 'name': key.removeprefix('gpu_rental_').removesuffix('_usd_hour').upper(),
            'value': value, 'change': value / base_value - 1 if base_value and base_value > 0 else None,
            'baseDate': base['observation_end'] if base else None,
            'date': last['observation_end'], 'availableAt': last['available_at'],
            'ageDays': (cutoff_dt.date() - date.fromisoformat(last['observation_end'])).days,
            'unit': 'USD / GPU小时', 'source': last.get('source_name'), 'url': last.get('source_url'),
            'table': 'manual_alternative_observations', 'sheet': last.get('workbook_sheet'),
            'cell': last.get('workbook_cell'), 'pitStatus': last.get('pit_status'),
            'scope': '租价反映供需共同作用；工作簿历史仅作当前观察，不推算GPU利用率',
            'tickers': ['NVDA'],
            'series': [{'date': r['observation_end'], 'value': numeric(r['metric_value'])} for r in rows[-60:]]})

    # Same company / same fiscal quarter comparisons only. No mixed date median.
    cohort = ['MSFT', 'AMZN', 'GOOGL', 'ORCL']
    financial = defaultdict(list)
    for row in versions(quarterly, ['ticker', 'period_end'], 'available_date'):
        if row.get('ticker') in cohort:
            financial[row['ticker']].append(row)
    companies = []
    for ticker in cohort:
        rows = sorted(financial[ticker], key=lambda r: r['period_end'])
        if not rows:
            continue
        last = rows[-1]
        last_end = date.fromisoformat(last['period_end'])
        prior_options = [r for r in rows[:-1]
            if 330 <= (last_end - date.fromisoformat(r['period_end'])).days <= 400]
        prior = min(prior_options,
            key=lambda r: abs((last_end - date.fromisoformat(r['period_end'])).days - 365),
            default=None)
        rev, capex, fcf = (numeric(last.get(k)) for k in ['revenue', 'capex', 'free_cash_flow'])
        ry, cy = numeric(last.get('revenue_yoy')), numeric(last.get('capex_yoy'))
        margin = fcf / rev if rev and rev > 0 and fcf is not None else None
        prior_margin = numeric(prior.get('fcf_margin')) if prior else None
        delta = margin - prior_margin if margin is not None and prior_margin is not None else None
        gap = cy - ry if cy is not None and ry is not None else None
        flag = '投入领先收入，现金流承压' if gap is not None and gap > .10 and delta is not None and delta < -.02 else '收入增长且现金流率改善' if ry is not None and ry > 0 and delta is not None and delta > .02 else '继续跟踪投入兑现'
        companies.append({'ticker': ticker, 'date': last['period_end'], 'availableAt': last['available_date'],
            'capexGrowth': cy, 'revenueGrowth': ry, 'fcfMargin': margin, 'fcfMarginYoYDelta': delta,
            'investmentRevenueGap': gap, 'capexIntensity': capex / rev if rev and rev > 0 and capex is not None else None,
            'flag': flag, 'table': 'fundamental_quarterly', 'source': 'SEC Companyfacts',
            'accessions': last.get('source_accessions'), 'scope': '公司总口径；现金流变化按去年同财季比较'})
    watch = [{'title': c['ticker'] + '：' + c['flag'], 'ticker': c['ticker'],
              'detail': '同一财季的Capex增速、收入增速与FCF率同比变化', 'date': c['date']} for c in companies if c['flag'] != '继续跟踪投入兑现']
    return {'version': 'demand_chain_v1', 'cutoff': cutoff, 'adoption': adoption,
        'consumption': consumption, 'compute': compute, 'companies': companies, 'watch': watch,
        'links': [
            {'from': 'Adoption', 'to': 'Consumption', 'status': '待形成同产品历史', 'evidence': '域名排名与OpenRouter覆盖不同用户，当前不能计算采用→消耗转化率。', 'next': '持续积累同一产品的活跃用户、留存和请求量。'},
            {'from': 'Consumption', 'to': 'Compute', 'status': '观察供需，不做弹性推断', 'evidence': 'Token日频与GPU租价可以观察趋势，但租价缺少利用率和机型工作负载配对。', 'next': '补充GPU小时、利用率、缓存与推理效率。'},
            {'from': 'Compute', 'to': 'Investment', 'status': '待补订单与交付', 'evidence': '租价和季度Capex频率及主体不同，目前没有可归因的传导系数。', 'next': '补充服务器订单、交付日期和采购公司映射。'},
            {'from': 'Investment', 'to': 'Monetization', 'status': '已做同公司同财季扫描', 'evidence': '比较Capex与收入增速差、FCF率同比变化；点击公司查看市场错位。', 'next': '以Cloud/AI分部收入替代总收入，并在Factor Lab验证滞后窗口。'}]}
