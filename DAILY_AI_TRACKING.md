# Daily AI Event Tracking System

## Objective

The daily track complements the quantitative company-date research foundation. It answers four questions every morning:

1. What materially changed in AI during the latest monitoring window?
2. Was the change surprising relative to prior expectations?
3. Which listed assets are exposed, through what transmission path, and over what horizon?
4. What evidence or future observation would confirm or falsify the trade hypothesis?

This is not a general AI-news digest. Events are reported only when they may change technology capability, adoption, cost, company fundamentals, market expectations, regulation, or supply-chain demand.

## Default schedule

- Run time: 08:00 Asia/Shanghai every day.
- Monitoring window: since the previous successful run; use the prior 24 hours if no checkpoint exists.
- Monday run: cover the prior 72 hours and label weekend events.
- Output: scheduled-task inbox summary plus `reports/daily/YYYY-MM-DD.md` when local project access is available.
- If no event clears the threshold, explicitly report `No material AI event identified` rather than filling space with low-value news.

## Event taxonomy

| Category | Examples | Fundamental transmission |
|---|---|---|
| Model capability | frontier model, reasoning, multimodal, agent capability | model competition, application capability, inference demand |
| Model/API economics | API price, caching, latency, throughput, context | application unit economics, cloud margin, inference demand elasticity |
| Product adoption | users, paid conversion, enterprise deployment, API usage | revenue growth, retention, monetization |
| Developer adoption | GitHub, Hugging Face, package downloads, integrations | ecosystem strength and future product adoption |
| Compute/supply chain | GPU, HBM, networking, foundry, data center, power | orders, capex, margins, bottlenecks |
| Corporate fundamentals | earnings, guidance, capex, contracts, M&A | estimates, cash flow, valuation |
| Policy/legal | export controls, copyright, safety, privacy, antitrust | market access, cost, business-model risk |
| Reliability/risk | outage, security incident, model withdrawal, benchmark issue | adoption risk, liability, trust, multiple compression |

## Source hierarchy

1. Tier A: regulator, exchange, company filing, official company/model/API announcement.
2. Tier B: platform-generated primary data such as GitHub and Hugging Face.
3. Tier C: reputable wire or specialist reporting with direct attribution.
4. Tier D: aggregator, social media, anonymous claim, or unverified benchmark.

Tier D may generate a monitoring lead but cannot independently support a published trading conclusion. A non-official material claim should have either two independent credible sources or one directly attributed primary document.

## Materiality score

Each candidate event receives a 0–100 score:

| Component | Weight | Question |
|---|---:|---|
| Surprise | 25 | How different is the fact from prior public expectations? |
| Fundamental impact | 25 | Can it change revenue, margins, capex, cash flow, or competitive position? |
| Tradability | 20 | Is there a clear listed-asset mapping and plausible catalyst window? |
| Breadth | 15 | How many companies or value-chain layers are affected? |
| Evidence quality | 15 | How direct, attributable, and independently verifiable is the evidence? |

Rules:

- `score >= 80`: urgent top event;
- `60 <= score < 80`: include in the morning brief;
- `40 <= score < 60`: store in the event database but normally omit from the executive brief;
- `score < 40`: discard or retain only as an unverified lead.

The score is an analyst triage device, not a return forecast.

## Required event record

- `event_id`
- `event_time`
- `first_seen_at`
- `available_at`
- `event_type`
- `source_tier`
- `source_name`
- `source_url`
- `headline`
- `fact_summary`
- `what_changed`
- `expectation_gap`
- `affected_companies`
- `beneficiaries`
- `adversely_affected`
- `transmission_path`
- `impact_horizon`
- `pricing_status`
- `materiality_score`
- `confidence_score`
- `next_catalyst`
- `falsification_condition`
- `duplicate_cluster_id`

## Morning brief structure

1. One-sentence overnight regime summary.
2. Up to five material events ranked by score.
3. Long, short, pair, and hedge mapping as research hypotheses—not recommendations.
4. What appears priced, partially priced, or unpriced.
5. Today’s scheduled catalysts.
6. Data-quality warnings and unresolved claims.
7. Direct source links.

## Research integration

Daily events are stored separately from the feature store. Only lagged, versioned event features may enter a backtest, for example:

- material event count over 5D/20D;
- positive/negative surprise score;
- event breadth;
- official-source share;
- model-price change;
- product-launch intensity;
- event-to-earnings lag.

All event-derived features must use `available_at <= decision_cutoff_at` and a versioned taxonomy.

# Free manual ChatGPT import

The project can import a ChatGPT-generated morning brief without an OpenAI API
key. This is intentionally a controlled copy workflow rather than unattended
access to a private ChatGPT conversation.

1. Keep `automation/daily_ai_brief_prompt.md` in the ChatGPT tracking task so
   each report ends with an `ai-alpha-gpt-brief-v2` JSON block.
2. Double-click `scripts/start_gpt_brief_import.command`, or run:

   ```bash
   /usr/bin/python3 scripts/serve_gpt_brief_import.py
   ```

3. Paste the whole ChatGPT report into the local page and select
   **核验、导入并发布**.

The service binds only to `127.0.0.1`. The original paste is retained under
`data/raw/gpt_manual_import/` for local lineage and is ignored by Git. The
importer requires a fresh source timestamp, a direct HTTPS link from an approved
primary or reputable secondary domain, complete materiality components, and a
score of at least 60. It rejects suspected secrets and deduplicates by source
URL. Tier B reporting is explicitly labeled as attributed reporting rather than
issuer confirmation.

The event schema keeps three clocks separate: `brief_date` is the Shanghai date
of the morning brief, `event_date` is when the underlying event occurred, and
`source_published_at` is the source's own publication timestamp. The importer
does not accept a date-only source timestamp and rejects an exact substitution
of the brief generation time. Sitemap `lastmod`, retrieval time and dashboard
generation time are never event dates.

After a successful import, the existing research pipeline rebuilds the local
warehouse and public dashboard. The existing publication gate then commits and
pushes only `web/public/data/dashboard.json`; a failed import, failed research
check, or failed release gate cannot trigger a push. Results and any commit hash
are written to `data/processed/gpt_brief_import_report.json` and shown in the
local page.
