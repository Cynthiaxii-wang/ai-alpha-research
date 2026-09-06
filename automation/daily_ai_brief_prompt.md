# Scheduled Task Prompt: AI Alpha Morning Brief

Every day at 08:00 Asia/Shanghai, prepare the AI Alpha Morning Brief for a hedge-fund research workflow.

Use the monitoring window since the previous successful run; if unavailable, use the prior 24 hours. On Monday, cover the prior 72 hours and label weekend events. Search current public information and prioritize primary sources: regulators, company filings, investor-relations releases, official model/API documentation, GitHub, and Hugging Face. Use reputable reporting only as secondary confirmation. Never treat social-media claims or an aggregator as sufficient evidence for a material conclusion.

Identify developments in model capability, API/model economics, product adoption, developer adoption, compute and supply chain, corporate fundamentals, policy/legal risk, and reliability incidents. Deduplicate repeated coverage into one event.

For each candidate, score Surprise 0–25, Fundamental Impact 0–25, Tradability 0–20, Breadth 0–15, and Evidence Quality 0–15. Include at most five events with total score at least 60. If none qualify, state `No material AI event identified` and list only scheduled catalysts.

For every included event provide: verified fact, what changed, expectation gap, affected listed companies, potential beneficiaries and adversely affected companies, transmission path, impact horizon, pricing status, confidence, next catalyst, falsification condition, and direct source links. Clearly separate verified facts from inference. Describe trades only as research hypotheses, never as personalized investment advice.

Use the structure in `templates/daily_ai_brief.md`. When local project access is available, save the report to `reports/daily/YYYY-MM-DD.md` and preserve a structured event record compatible with `event_observation` and `event_company_map`. Do not modify `.env`, raw historical data, database schemas, or prior reports. Do not expose API keys or local secrets.

Return the concise executive brief in the scheduled-task result even when the local file write succeeds.

At the very end, append a machine-readable import block exactly between
`AI_ALPHA_IMPORT_V2_START` and `AI_ALPHA_IMPORT_V2_END`. It must be valid JSON,
must contain no Markdown inside the markers, and must use this contract:

```json
{
  "schemaVersion": "ai-alpha-gpt-brief-v2",
  "brief_date": "YYYY-MM-DD date of this morning brief in Asia/Shanghai",
  "asOf": "ISO-8601 timestamp with timezone",
  "events": [
    {
      "id": "stable-kebab-case-id",
      "event_date": "YYYY-MM-DD date when the described event actually occurred",
      "source_published_at": "source publication timestamp in ISO-8601 with timezone",
      "type": "event category",
      "sourceName": "publisher name",
      "sourceUrl": "direct HTTPS article, filing, or official-release URL",
      "supportingUrls": ["direct HTTPS corroborating URL"],
      "headline": "concise Chinese headline",
      "summary": "attributed Chinese fact summary",
      "whatChanged": "what changed versus the prior information set",
      "expectationGap": "what differs from expectations",
      "affectedCompanies": ["LISTED_TICKER"],
      "beneficiaries": ["LISTED_TICKER"],
      "adverselyAffected": ["LISTED_TICKER"],
      "impactPath": "adoption → consumption → compute → investment → monetization",
      "horizon": "expected observation horizon",
      "pricingStatus": "pricing assessment",
      "scoreComponents": {"surprise": 0, "fundamental": 0, "tradability": 0, "breadth": 0, "evidence": 0},
      "confidence": "高/中/低",
      "nextCatalyst": "dated or observable next check",
      "falsification": "condition that would invalidate the interpretation"
    }
  ]
}
```

The five score components retain their maxima of 25/25/20/15/15 and included
events must total at least 60. Use direct source URLs, never a ChatGPT page,
search-results page, tracking redirect, or homepage. A Reuters/Bloomberg/FT/WSJ
item must be explicitly attributed as reporting and must not be rewritten as an
issuer-confirmed fact. Do not place secrets, private paths, or personal data in
the import block.

`brief_date`, `event_date`, and `source_published_at` are different fields.
Never copy the brief generation time, page update time, sitemap `lastmod`, or
crawler retrieval time into either event date field. If the true event date or
source publication timestamp cannot be established from the source, exclude the
event from the import block and put it under unresolved leads instead.
