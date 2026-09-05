# Development Runbook

## Scope

The research universe contains 20 AI value-chain companies with SEC-validated identifiers. The original five-company pilot remains available only for narrow connectivity checks.

The project has two coordinated tracks:

1. quantitative point-in-time company/date research;
2. a daily AI event-intelligence brief with explicit asset transmission and falsification conditions.

## Security

- Keep credentials only in `.env`.
- `.env` is ignored by Git.
- Clients never log request query strings containing API keys.
- Raw envelopes store content hashes, retrieval timestamps, and sanitized request metadata.

## Connectivity test

```bash
python3 scripts/smoke_test.py
```

The script calls each configured source once with NVDA, writes append-only JSON under `data/raw/`, and produces `data/processed/connectivity_report.json`.

Run dependency-free unit tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Pilot ingestion

```bash
python3 scripts/ingest_pilot.py --start 2024-10-01 --end 2026-09-01
```

Run a subset when preserving a vendor quota:

```bash
python3 scripts/ingest_pilot.py --sources sec github huggingface
```

Validate completeness and content hashes:

```bash
python3 scripts/validate_pilot.py
```

## Point-in-time rule

Raw retrieval time is not automatically the economic `available_at`. Normalization must preserve both source publication time and ingestion time. Vendor backfills remain new versions and never overwrite earlier snapshots.

## Next stage

After connectivity succeeds:

1. normalize Massive OHLCV into `market_daily`;
2. calculate target returns with an explicit next-tradable-close convention;
3. normalize SEC XBRL facts using a reviewed metric map;
4. build GitHub/Hugging Face adoption snapshots and historical release/activity features;
5. ingest Alpha Vantage earnings surprise as a free consensus-revision substitute;
6. calculate IC, Rank IC, grouped returns, long-short return, turnover, and drawdown.

Run the first standardized research pipeline after benchmark ingestion:

```bash
python3 scripts/ingest_benchmarks.py
python3 scripts/run_research_pipeline.py
```

Outputs are written to `data/standardized/`, `data/research/`, `research/results/`, and `research/reports/`. See `RESEARCH_METHODOLOGY.md` before interpreting any pilot statistic.

## Web platform

The presentation layer is a Next.js App Router application in `web/`. Python exports the research snapshot consumed by the dashboard.

```bash
# From the repository root, using Node.js 22
npm ci --prefix web
npm run dev
```

Open `http://localhost:3000`. Verify and run the production build:

```bash
npm run build
npm run start
```

To refresh the snapshot, run `python3 scripts/export_web_data.py` before building. The frontend reads `web/public/data/dashboard.json`; Python and provider API keys are not needed to build or run the website. Existing hash links such as `/#signals` remain supported.

See [web/README.md](web/README.md) for Vercel and Docker deployment, data updates, and the existing public redistribution restrictions.

## Daily AI tracking

See `DAILY_AI_TRACKING.md` for source hierarchy, materiality scoring, and event schema. The reusable scheduled-task prompt is `automation/daily_ai_brief_prompt.md`; the report layout is `templates/daily_ai_brief.md`.

Default schedule: 08:00 Asia/Shanghai every day. A local-project scheduled task requires the desktop app to remain running and the computer to be on. The workflow must explicitly report when no event clears the materiality threshold.
