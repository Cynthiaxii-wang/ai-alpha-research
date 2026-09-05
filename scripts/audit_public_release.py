"""Read-only data checks; write a separate release gate, never certify authenticity."""
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ai_alpha_research.research_utils import latest_raw, load_envelope, parse_float


def close(a, b):
    return a is not None and b is not None and abs(a-b) <= max(1e-8, abs(b)*1e-10)


def main():
    with (ROOT / 'data/standardized/fundamental_quarterly.csv').open() as f:
        quarterly = list(csv.DictReader(f))
    periods = defaultdict(set)
    for r in quarterly:
        periods[(r['ticker'], r['fiscal_year'], r['fiscal_quarter'])].add(r['period_end'])
    conflicts = [dict(ticker=k[0], fiscal_year=k[1], fiscal_quarter=k[2],
                      period_ends=sorted(v)) for k, v in periods.items() if len(v) > 1]
    with (ROOT / 'data/standardized/market_daily.csv').open() as f:
        market = list(csv.DictReader(f))
    price_errors = []
    for r in market:
        try:
            o,h,l,c,v = (float(r[k]) for k in ['open','high','low','close','volume'])
            if not (0 < l <= min(o,c) <= max(o,c) <= h and v >= 0):
                price_errors.append({'ticker':r['ticker'],'date':r['trade_date']})
        except (ValueError, TypeError):
            price_errors.append({'ticker':r['ticker'],'date':r['trade_date']})
    # Confirm every standardized market row is present in the exact retained
    # vendor response, not only internally plausible OHLCV.
    raw_market = {}
    raw_files = {}
    for ticker in sorted({r['ticker'] for r in market}):
        path = latest_raw(ROOT, 'massive', ticker)
        envelope = load_envelope(path)
        raw_files[ticker] = str(path.relative_to(ROOT))
        for item in envelope['payload'].get('results') or []:
            day = datetime.fromtimestamp(item['t']/1000, tz=timezone.utc).date().isoformat()
            raw_market[(ticker, day)] = item
    raw_mismatches = []
    vendor_fields = {'open':'o','high':'h','low':'l','close':'c','volume':'v','vwap':'vw','transactions':'n'}
    for row in market:
        raw = raw_market.get((row['ticker'], row['trade_date']))
        mismatched = [field for field, vendor in vendor_fields.items()
            if raw is None or not close(parse_float(row.get(field)), parse_float(raw.get(vendor)))]
        if mismatched:
            raw_mismatches.append({'ticker':row['ticker'],'date':row['trade_date'],'fields':mismatched})
    yoy_mismatches = []
    by_ticker = defaultdict(list)
    for row in quarterly:
        by_ticker[row['ticker']].append(row)
    for rows in by_ticker.values():
        for row in rows:
            end = datetime.fromisoformat(row['period_end']).date()
            options = [r for r in rows if 330 <= (end-datetime.fromisoformat(r['period_end']).date()).days <= 400]
            prior = min(options, key=lambda r:abs((end-datetime.fromisoformat(r['period_end']).date()).days-365), default=None)
            for field in ('revenue','capex','free_cash_flow'):
                current, old = parse_float(row.get(field)), parse_float(prior.get(field)) if prior else None
                expected = current/old-1 if current is not None and old not in (None,0) else None
                actual = parse_float(row.get(field+'_yoy'))
                if (expected is None) != (actual is None) or (expected is not None and not close(actual, expected)):
                    yoy_mismatches.append({'ticker':row['ticker'],'period_end':row['period_end'],'field':field})
    brief = json.loads((ROOT / 'data/processed/daily_ai_brief.json').read_text())
    event_dates = [dict(id=e.get('id'),publishedDate=e.get('publishedDate'),publishedAt=e.get('publishedAt'))
                   for e in brief.get('events',[]) if e.get('publishedDate') and e.get('publishedAt')
                   and e['publishedDate'] != e['publishedAt'][:10]]
    report = {
        'checked_at':datetime.now(timezone.utc).isoformat(),
        'release_status':'blocked_for_public_redistribution',
        'scope':'Local lineage/consistency checks plus a separate licensing gate; not a guarantee of investment accuracy',
        'quarterly_issuer_label_conflicts_warning':conflicts,
        'quarterly_yoy_mismatches':yoy_mismatches,
        'market_rows_checked':len(market), 'market_ohlcv_errors':price_errors,
        'market_raw_response_mismatches':raw_mismatches,
        'market_raw_files_by_ticker':raw_files,
        'event_date_discrepancies_to_review':event_dates,
        'required_before_publication':[
            'Verify representative price and financial figures against original provider/filing sources',
            'Replace Massive-derived display/analytics or obtain Massive written redistribution permission',
            'Confirm public display rights for internship workbook-derived data',
            'Freeze reviewed source/code/data snapshot and rerun publication checks'],
    }
    output = ROOT / 'data/research/public_release_audit.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(f'fiscal_label_warnings={len(conflicts)} yoy_errors={len(yoy_mismatches)} market_errors={len(price_errors)} raw_mismatches={len(raw_mismatches)} event_date_reviews={len(event_dates)}')
    print(f'release_status={report["release_status"]}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
