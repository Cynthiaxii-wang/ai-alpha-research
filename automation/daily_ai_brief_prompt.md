# Scheduled Task Prompt: AI Alpha Morning Brief

Every day at 08:00 Asia/Shanghai, prepare the AI Alpha Morning Brief for a hedge-fund research workflow.

Use the monitoring window since the previous successful run; if unavailable, use the prior 24 hours. On Monday, cover the prior 72 hours and label weekend events. Search current public information and prioritize primary sources: regulators, company filings, investor-relations releases, official model/API documentation, GitHub, and Hugging Face. Use reputable reporting only as secondary confirmation. Never treat social-media claims or an aggregator as sufficient evidence for a material conclusion.

Identify developments in model capability, API/model economics, product adoption, developer adoption, compute and supply chain, corporate fundamentals, policy/legal risk, and reliability incidents. Deduplicate repeated coverage into one event.

For each candidate, score Surprise 0–25, Fundamental Impact 0–25, Tradability 0–20, Breadth 0–15, and Evidence Quality 0–15. Include at most five events with total score at least 60. If none qualify, state `No material AI event identified` and list only scheduled catalysts.

For every included event provide: verified fact, what changed, expectation gap, affected listed companies, potential beneficiaries and adversely affected companies, transmission path, impact horizon, pricing status, confidence, next catalyst, falsification condition, and direct source links. Clearly separate verified facts from inference. Describe trades only as research hypotheses, never as personalized investment advice.

Use the structure in `templates/daily_ai_brief.md`. When local project access is available, save the report to `reports/daily/YYYY-MM-DD.md` and preserve a structured event record compatible with `event_observation` and `event_company_map`. Do not modify `.env`, raw historical data, database schemas, or prior reports. Do not expose API keys or local secrets.

Return the concise executive brief in the scheduled-task result even when the local file write succeeds.

