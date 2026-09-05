# Local DuckDB warehouse

The canonical local research database is:

`data/warehouse/ai_alpha_research.duckdb`

It is rebuilt atomically from retained raw envelopes, standardized CSV tables, research inputs and audit reports. API secrets are never written to the database.

## Layers

- `raw_manifest`: source, entity, retrieval timestamp, content hash, raw file path and record count for every retained API envelope.
- Standardized tables: market, filings, PIT-safe annual and single-quarter fundamentals, earnings, developer activity, model usage, product-domain rankings and manually reviewed alternative observations.
- `feature_store` and `targets`: point-in-time research features and forward labels.
- `source_registry` and `data_dictionary`: source reliability and field semantics.
- `ingestion_log`: normalized execution records from `data/processed/*.json`.
- `quality_exceptions`: open failures plus explicitly retained research limitations.
- `factor_results`: current Factor Lab verdicts and full JSON payloads.
- `data_asset_registry`: one row per warehouse asset with layer, source path, row count and build timestamp.

## Build and inspect

```bash
python3 scripts/build_warehouse.py
python3 scripts/inspect_warehouse.py
```

The full daily research pipeline rebuilds the warehouse before hypothesis tests and again after results are generated. Factor Lab and the web export read their core tables from DuckDB, with CSV fallback only when the warehouse does not yet exist.

## Example read-only query

```bash
python3 - <<'PY'
import duckdb
con = duckdb.connect('data/warehouse/ai_alpha_research.duckdb', read_only=True)
print(con.execute('select table_name, row_count from data_asset_registry order by row_count desc').fetchall())
con.close()
PY
```

Storage integrity does not by itself prove economic validity. `quality_exceptions`, source tiers and each proxy's scope must still be considered before using a field in a backtest.

`fundamental_quarterly` prefers a directly disclosed three-month fact. When SEC Companyfacts supplies only six-month or nine-month cash-flow values it reconstructs the missing single quarter by cumulative difference; Q4 may be annual value minus nine-month value. The row retains `available_date`, `metric_derivations`, and `source_accessions`. Historical values repeated in later filings do not replace the earliest market-visible filing in this research table.
