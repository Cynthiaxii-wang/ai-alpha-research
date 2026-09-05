# AI Alpha Research Data Foundation v2

这是面向对冲基金研究的 AI 公司 point-in-time 数据底座，已跑通：

`Raw Data → Standardized Tables → Features & Targets → Hypothesis Tests → Research Findings`

## Next.js 网站

网站位于 `web/`，使用 Next.js App Router，可部署到 Vercel 或 Node.js / Docker 环境。

```bash
# Node.js 22；在项目根目录运行
npm ci --prefix web
npm run dev
# 生产构建与启动
npm run build
npm run start
```

本地地址：`http://localhost:3000`。部署时将 Vercel Root Directory 设为 `web`。
完整步骤、目录说明和数据发布限制见 [web/README.md](web/README.md)。

## 当前已完成

- 20 家 AI 价值链公司，CIK 由 SEC 官方 ticker 映射生成。
- 2024-10-01 起的日频行情和 QQQ 基准。
- SEC 10-K/10-Q 基本面、Alpha Vantage 盈利事件、GitHub/Hugging Face/OpenRouter 数据。
- OpenRouter 2025-01-01 起的日频模型 Token 排名历史，以及 Cloudflare Radar AI 产品域名快照。
- 调整价用于收益率，未调整价配同期稀释股数用于 filing-basis P/S 和 P/FCF。
- 1D/5D/20D/60D Targets、QQQ excess return、future volatility 和 drawdown。
- GitHub 带日期 commits/releases 事件表与月度活动 Features，保留截断标记。
- H1/H2/H3 探索性检验与自动质量审计。
- 每日 08:00 Asia/Shanghai 的 AI 大事晨报规则、来源表、模板和自动化 prompt。
- 支持将分析师 AI 跟踪 Excel 快照导入为标准化另类数据，默认只用于描述性看板。

## 关键文件

- `data_dictionary_v1.csv`：字段级数据字典。
- `database_schema_v1.md` / `schema_v1.sql`：数据关系与 PostgreSQL DDL。
- `RESEARCH_METHODOLOGY.md`：PIT、价格、估值和代理变量口径。
- `data/research/feature_store.csv` / `targets.csv`：研究输入与标签。
- `research/results/hypothesis_results.json`：机器可读假设结果。
- `research/reports/expanded_research_findings.md`：人类可读研究结论。
- `data/research/research_quality_report.json`：全链路质量审计。
- `data/warehouse/ai_alpha_research.duckdb`：统一的本地研究数据库与数据血缘清单。
- `WAREHOUSE.md`：DuckDB 表层、构建、查询与审计说明。
- `DAILY_AI_TRACKING.md`：每日 AI 事件跟踪体系。

## 复现

```bash
python3 scripts/bootstrap_universe.py
python3 scripts/ingest_research_universe.py
python3 scripts/ingest_unadjusted_prices.py
python3 scripts/ingest_github_history.py
python3 scripts/ingest_alternative_usage.py
python3 scripts/normalize_github_history.py
python3 scripts/run_research_pipeline.py
python3 scripts/inspect_warehouse.py
python3 scripts/import_tracking_workbook.py --input /path/to/AI_tracking.xlsx
python3 scripts/export_web_data.py
```

API 密钥只保存在本地 `.env`，该文件已被 `.gitignore` 排除。

## 研究红线

- 任何研究查询必须满足 `available_at <= decision_timestamp`。
- `period_end` 与 `available_at` 不得混用。
- 当前 GitHub 自动选库只是公司开源活动代理，不是纯 AI 产品采用数据。
- OpenRouter Token 仅代表该平台内的模型流量，跨提供商 Token 口径不可直接等同；Cloudflare Radar 是网页关注度代理，不是用户数。
- Alpha Vantage 历史估值 EPS 尚未被独立验证为机构级 PIT consensus。
- 当前结果是 hypothesis screening，不是可部署 alpha 策略。
