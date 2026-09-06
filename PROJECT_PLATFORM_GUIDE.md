# AI Alpha Research 项目与页面完整说明

> 文档版本：v1.1  
> 平台版本：Framework v0.1  
> 文档基准日：2026-09-05  
> 当前网页数据生成时间：2026-09-05（从现有数据库导出，不代表所有来源已重新抓取）  
> 当前市场数据截至：2026-09-03  
> 当前财务可用数据截至：2026-09-01  
> 本文描述的是当前真实实现，不把计划接入的数据写成已接入数据。

---

### v1.1 更新与页面索引

新增「AI 需求兑现链」，将产品采用、Token消耗、GPU租价、资本投入与收入/现金流对照组织成五个观察环节。新增模块的完整口径见第17节。

| 侧栏入口 | 研究分工 | 本文位置 |
|---|---|---|
| 01 Overview | 今日事件与市场概览 | 第5节 |
| 02 AI Value Chain | 上中下游产业位置与景气 | 第6节 |
| 03 Signal Monitor | 公司级基本面与定价错位 | 第7节 |
| 04 Factor Lab | 历史基本面/收益预测检验 | 第8节 |
| 05 AI 需求兑现链 | 另类数据证据与投入兑现观察 | 第17节 |
| Company Drawer | 点击公司打开的详情，不是独立侧栏页 | 第9节 |

本次已完成数据库导出、网页构建、三个计算回归测试，以及五个环节切换、来源展开、公司详情与 Factor Lab 跳转的浏览器检查。上述验证确认工程功能，不构成对供应商原始数字或投资预测能力的全面认证。

## 1. 项目是什么

AI Alpha Research 是一个面向对冲基金股票研究的 AI 产业研究原型。它不是单纯的新闻看板，也不是把若干 AI 股票放在同一张表里，而是把以下五个环节连成一条可审计的研究链路：

```text
原始数据
→ 标准化数据表
→ Features 与 Targets
→ 假设检验
→ 研究结论与公司研究队列
```

平台要回答五个问题：

1. AI 产业链的景气发生在上游、中游还是下游？
2. 景气如何从应用需求向云和芯片反向验证，又如何从资本开支向供给与应用传导？
3. 同一产业链环节中，哪家公司基本面更强？
4. 哪家公司出现了“基本面强、股价弱”或“基本面弱、股价强”的定价错位？
5. 这些信号在历史上是否真的能够预测未来基本面或未来超额收益？

当前版本是三天 MVP 研究底座，定位为 `exploratory research`。它能够完成数据采集、标准化、时间可用性控制、公司横截面比较和初步因子检验，但不等同于已经验证的可交易策略。

### 1.1 当前研究范围

- 研究对象：20 家 AI 产业链上市公司。
- 非上市观察对象：OpenAI、Anthropic。
- 股票基准：QQQ，即 Invesco QQQ ETF，用作纳斯达克 100 风格基准。
- 市场数据：2024-10-01 至 2026-09-03。
- 主要预测窗口：1D、5D、20D、60D、120D。
- 主要研究频率：市场数据日频，基本面季度/年度，开发者数据月频或快照，AI 事件日频。
- 当前研究状态：工程检查通过；投资研究结论仍为探索性。

### 1.2 当前明确不做什么

- 不把工程检查 `PASS` 写成因子已经有效。
- 不把 20 家公司、约两年行情得出的统计结果包装成机构级证据。
- 不在样本不足时使用随机森林、神经网络等复杂模型。
- 不把 GitHub stars、Hugging Face downloads、Cloudflare 域名排名直接等同于付费用户或收入。
- 不把总资本开支直接等同于 AI 专属资本开支。
- 不把供应商今天回填的历史数据自动视为当时市场已知数据。
- 不输出自动交易指令；页面信号用于安排研究优先级。

---

## 2. 系统架构与数据流

### 2.1 四层存储

| 层级 | 位置 | 作用 |
|---|---|---|
| Raw | `data/raw/` | 保存 API 原始 JSON envelope、抓取时间、请求信息和内容哈希 |
| Standardized | `data/standardized/` | 统一股票代码、日期、单位、字段和时间语义 |
| Research | `data/research/` | 保存 Feature Store、Targets 和质量报告 |
| Warehouse | `data/warehouse/ai_alpha_research.duckdb` | 将标准化表、研究表、来源、血缘、日志和异常统一到一个数据库 |

网页不直接读取各个 API，而是读取：

```text
web/public/data/dashboard.json
```

该文件由 `scripts/export_web_data.py` 从 DuckDB/标准化数据和研究结果中生成。这样页面数字与研究底稿共享同一套计算口径。

### 2.2 为什么保留 Raw 数据

每个 API 原始文件都保留以下信息：

- `source`：来自哪个服务。
- `entity`：对应哪个公司、代码、模型或数据对象。
- `retrieved_at`：系统什么时候抓取。
- `content_sha256`：内容哈希，用于判断原始内容是否被覆盖或变更。
- `request_metadata`：请求参数和范围。
- `payload`：供应商返回的原始内容。

数据库中的 `raw_manifest` 只是这些原始文件的索引。任何页面数字出现争议时，可以沿着标准化表、抓取日志和 raw file 回到供应商的原始响应。

### 2.3 Point-in-time 原则

系统区分四类日期：

| 字段 | 含义 |
|---|---|
| `period_end` / `observation_end` | 经济事实对应的报告期或测量窗口结束日 |
| `event_time` | 事件实际发生或公开发布的时间 |
| `available_at` / `available_date` | 市场最早能够使用该信息的时间 |
| `feature_date` | 系统形成研究特征的决策日期 |

研究查询的硬约束是：

```text
source.available_at <= decision_cutoff_at
```

例如 2026 年 6 月 30 日结束的财季，并不代表 6 月 30 日市场已经知道财务结果。数据只能从公司向 SEC 提交报告的日期起进入研究。

### 2.4 收益标签的交易时点

- 日频特征在相关交易日收盘后可得。
- 默认在下一交易日收盘价进入标签窗口。
- 20D 标签是在入场后第 20 个交易日收盘退出。
- QQQ 超额收益使用完全相同的入场日和退出日。
- 样本末端未来窗口尚未走完时，Target 保持空值，不能填 0。

---

## 3. 当前数据资产总览

以下数量来自当前实际标准化文件和质量报告。

| 数据资产 | 当前行数 | 覆盖范围 | 主要来源 | 用途 |
|---|---:|---|---|---|
| `market_daily` | 10,143 | 2024-10-01—2026-09-03 | Massive | 复权 OHLCV、收益率、波动率、QQQ 超额收益 |
| `market_unadjusted_daily` | 9,620 | 2024-10-01—2026-09-01 | Massive | 未复权价格，配合 SEC 每股基本面做估值代理 |
| `fundamental_observations` | 10,638 | 报告期 2019—2026 | SEC EDGAR | 最底层 XBRL 财务事实与申报血缘 |
| `fundamental_annual` | 146 | 2019—2026 | SEC EDGAR | 年度收入、Capex、FCF、利润率与估值分母 |
| `fundamental_quarterly` | 568 | 2019—2026 | SEC EDGAR | 单季度基本面、增长、加速度和 Capex 转化 |
| `earnings` | 1,537 | 1996-03-14—2026-09-02 | Alpha Vantage | 实际 EPS、预期 EPS和盈利意外 |
| `github_activity_events` | 12,814 | 按仓库历史 | GitHub | commit/release 事件 |
| `developer_monthly_activity` | 456 | 按完整月份聚合 | GitHub | 开发者活动变化特征 |
| `developer_snapshot` | 19 | 当前快照 | GitHub/Hugging Face | stars、forks、issues、模型下载与 likes |
| `openrouter_model_snapshot` | 421 | 当前目录快照 | OpenRouter | 模型目录、上下文长度与 API 标价 |
| `openrouter_usage_daily` | 31,059 | 2025-01-01—2026-09-03 | OpenRouter Rankings | Top 50 模型日 Token 使用代理 |
| `product_domain_rank_daily` | 9 | 2026-08-31—2026-09-04 | Cloudflare Radar | AI 产品网页关注度快照 |
| `manual_alternative_observations` | 12,962 | 主要为 2020—2026 | AI Tracking Workbook | CSP Capex、内存、算力、产品采用等候选另类数据 |
| `events` | 3 | 当前晨报窗口 | 公司官方来源等 | 已核验 AI 重大事件 |
| `feature_store` | 64,948 | 2024-10-01—2026-09-03 | 多源派生 | 所有研究特征 X |
| `targets` | 9,660 | 2024-10-01—2026-09-03 | Massive 派生 | 未来收益、超额收益、波动率与回撤 Y |

当前成熟的 20D Targets 为 9,240 条，成熟的 60D Targets 为 8,440 条。成熟 20D 样本中缺失 QQQ 超额收益的数量为 0。

---

## 4. 数据来源、可靠性和使用边界

### 4.1 SEC EDGAR / Companyfacts

- 官方入口：[SEC EDGAR APIs](https://www.sec.gov/edgar/sec-api-documentation)
- 当前等级：Tier A，第一方监管披露。
- 成本：免费。
- 当前用途：收入、毛利、营业利润、经营现金流、Capex、研发费用、稀释股数、申报日期与财务血缘。
- 为什么可靠：来源是上市公司正式提交给 SEC 的 10-K、10-Q、20-F 和结构化 XBRL 数据。
- 使用限制：公司自定义 XBRL tag 需要标准化；同一指标可能存在多个 tag、多个单位和重述版本。
- PIT 处理：采用最早公开申报日期作为 `available_date`，后续重述不得覆盖原值。
- 特殊情况：TSM 使用 IFRS/TWD 数据做增速和利润率；由于 ADR 与本币口径问题，不进入当前美元估值代理。TSM 的季度 6-K Companyfacts 结构不足，因此季度领先滞后检验目前覆盖 19 家美国申报公司。

### 4.2 Massive Stocks

- 官方接口：[Massive Custom Bars OHLC](https://www.massive.com/docs/rest/stocks/aggregates/custom-bars)
- 当前等级：Tier B，专业市场数据 API。
- 成本：当前使用免费层。
- 当前接口：`/v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}`。
- 当前用途：日频开高低收、成交量、VWAP、成交笔数、复权/未复权价格。
- 页面作用：QQQ 20D 收益、公司 20D 动量、20D excess、120 日相对走势图、未来收益 Targets。
- PIT 处理：以对应交易日收盘后作为 `available_at`。
- 使用限制：免费历史范围可能短于完整周期；复权约定和历史回填需要持续与交易所/其他数据源交叉核验。

### 4.3 Alpha Vantage

- 官方文档：[Alpha Vantage API Documentation](https://www.alphavantage.co/documentation/)
- 当前等级：Tier D / backup；可用于事件与交叉检查，不作为机构级历史共识的最终来源。
- 成本：免费层，存在每日调用限制。
- 当前用途：历史实际 EPS、供应商提供的 estimated EPS、surprise、surprise percentage；当前 next-quarter EPS estimate 与 30 天前快照字段。
- 页面作用：公司详情中的 Latest EPS surprise；Signal Monitor 的 EPS Rev 30D 在有可用快照时展示。
- 关键限制：历史 estimated EPS 尚未独立验证为当时真正可见的一致预期快照，因此不能直接宣称其为严格 PIT consensus。
- 处理方式：相关字段标注 `vendor_historical_estimate_snapshot_unverified`；EPS Revision Factor 在历史快照积累完成前保持 `Needs Data`。

### 4.4 GitHub

- 官方文档：[GitHub REST API](https://docs.github.com/en/rest)
- Commits：[REST API endpoints for commits](https://docs.github.com/en/rest/commits/commits)
- Releases：[REST API endpoints for releases](https://docs.github.com/en/rest/releases/releases)
- 当前等级：Tier B。
- 当前用途：公司相关公开仓库、stars、forks、open issues、commit 日期、release 日期、近 90 天活跃仓库数。
- 页面作用：公司详情的 GitHub stars snapshot；Factor Lab 的 AI Adoption Factor 输入之一。
- 有效解释：反映选定公开仓库的开发活动、发布节奏和开源生态关注度。
- 不能解释：不能直接代表付费客户、API 调用、企业部署或公司整体 AI 收入。
- 关键限制：自动选库可能包含与 AI 主产品关系较弱的仓库；需要分析师复核产品级映射。

### 4.5 Hugging Face Hub

- 官方 API：[Hugging Face HfApi](https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api)
- 当前等级：Tier B。
- 当前用途：公司/组织公开模型数量、Top 50 模型 downloads、likes。
- 页面作用：公司详情中的 HF downloads snapshot。
- 有效解释：开源模型的可见度和下载活动代理。
- 不能解释：下载不等于真实推理调用、付费 API 使用、企业合同或活跃用户。
- PIT 限制：downloads 和 likes 是当前累计快照；若没有每天持续归档，不能把今天看到的累计数回填到过去。

### 4.6 OpenRouter Models 与 Rankings

- 模型目录：[OpenRouter Models API](https://openrouter.ai/docs/guides/overview/models)
- 日排名数据：[Daily token totals for top 50 models](https://openrouter.ai/docs/api/api-reference/datasets/get-rankings-daily)
- 当前等级：模型目录 Tier D；历史 Rankings Tier B/conditional。
- 当前用途：模型 ID、提供商、上下文长度、prompt/completion 单 Token 价格；2025-01-01 起 Top 50 模型每日总 Token。
- 页面/因子作用：Token Usage Factor、模型采用监测、Provider 份额和模型价格背景。
- 有效解释：OpenRouter 平台内真实 Token 处理量。
- 关键限制：只覆盖 OpenRouter 流量；不同 Provider 使用自己的 tokenizer，跨 Provider Token 数不可机械等价；私有请求可能不进入公开统计。
- 当前样本：31,059 行、609 天、46 个 Provider；最新领先 Provider 信息由当次数据快照计算。

### 4.7 Cloudflare Radar

- 官方方法：[Cloudflare Radar Domain Ranking](https://developers.cloudflare.com/radar/investigate/domain-ranking-datasets/)
- 单域名接口：[Get domain rank details](https://developers.cloudflare.com/api/resources/radar/subresources/ranking/subresources/domain/methods/get/)
- 当前等级：Tier B/conditional。
- 当前用途：ChatGPT、Claude 等 AI 产品域名的全球 rank 或 rank bucket。
- 页面作用：AI Value Chain 中 OpenAI/Anthropic 的产品关注度节点；Factor Lab 中 AI Adoption Factor 的当前覆盖信息。
- 有效解释：基于 Cloudflare 1.1.1.1 DNS 查询形成的网页关注度代理。
- 不能解释：不是 DAU、MAU、订阅用户、付费席位、Token 使用或收入。
- 当前历史限制：目前主要是当前快照，需要每日积累后才能形成趋势。

### 4.8 AI Tracking Workbook

- 原始文件：用户提供的 `AI跟踪体系20260831.xlsx`。
- 当前等级：Tier C/conditional。
- 当前标准化结果：`manual_alternative_observations` 12,962 行。
- 潜在内容：CSP Capex、算力租赁、GPU/服务器、内存价格、云与应用采用、产业链手工跟踪指标。
- 当前用途：Overview 的另类数据脉冲和候选因子研究；没有完整来源与发布时间的数据只用于描述性监测。
- 关键限制：部分 Sheet 的原始来源、单位、发布日期和历史可得时间不完整。
- 入回测条件：必须逐项补齐 `source_url`、`available_at`、单位、频率、原始表格位置和 PIT 状态。

### 4.9 Company Investor Relations

- 当前等级：Tier A。
- 来源：各公司 Investor Relations、财报、财报电话会材料、官方博客与正式新闻稿。
- 当前用途：每日 AI 事件、AI 收入、AI Capex、产品采用、订单和管理层指引的人工验证。
- 关键限制：公司间术语不同，必须按公司建立解析规则，不能把“AI revenue”“AI-related revenue”“accelerated computing”等口径直接横比。

---

## 5. 页面一：Overview

Overview 是每天打开平台后的研究入口，目标是用一个首屏回答“市场环境如何、今天发生了什么、先研究谁”。

### 5.1 市场与研究概览

#### 纳斯达克 100 基准（QQQ）

- 展示内容：QQQ 过去 20 个交易日收益率。
- 来源：`market_daily`，供应商 Massive。
- 计算：`QQQ 当日收盘价 / QQQ 第 20 个交易日前收盘价 - 1`。
- 作用：判断当前 AI 股票表现是否只是纳斯达克整体 beta。
- 限制：QQQ 不是纯 AI 指数，也没有做风格或行业中性化。

#### 跑赢基准的公司

- 展示内容：20 家公司中 `excess20d > 0` 的公司数量。
- `excess20d = 公司 momentum20d - QQQ momentum20d`。
- 作用：观察 AI 股票上涨是否有广度，而不是仅由少数龙头驱动。

#### 中位超额收益

- 展示内容：20 家公司 20D excess 的横截面中位数。
- 使用中位数的原因：减少 PLTR、CRM 等极端涨跌对整体结论的影响。

#### 今日事件

- 展示内容：`daily_ai_brief.events` 中通过核验和重要性阈值的事件数量。
- 来源：正式事件表与晨报 JSON。
- 不是简单新闻条数；重复报道应聚为同一事件。

### 5.2 首要研究对象

- 数据来自 `researchQueue[0]`。
- 排序先看研究情景优先级，再看 `|Fundamental–Price Gap|`。
- 当前优先顺序：Fundamental dislocation → Expectation risk → Deteriorating → Momentum → Data gap。
- 点击后打开 Company Drawer。
- 作用：把看板转化为具体研究任务，而不是停留在展示数字。

### 5.3 今日核心事件

字段包括：

| 页面元素 | 数据字段 | 含义 |
|---|---|---|
| 来源与日期 | `sourceName`, `publishedDate` | 事件的第一方/可靠来源和发布日期 |
| 标题 | `headline` | 经整理后的事实标题 |
| 摘要 | `summary` | 事件发生了什么 |
| 投资含义 | `whatChanged` | 与此前预期相比改变了什么 |
| 关联公司 | `affectedCompanies` | 可能受影响的上市研究对象 |
| 官方原文 | `sourceUrl` | 可回到原始出处核验 |

事件不能只说明“发布了新模型”，还要说明价格、能力、分发渠道、云平台关系、Capex 或收入传导路径发生了什么变化。

### 5.4 四个工程指标

- `Research universe`：公司数量，目前为 20。
- `Feature table rows`：Feature Store 行数，目前为 64,948。
- `20D forward labels`：成熟 20D 标签数量，目前为 9,240。
- `Feature timing violations`：源数据最晚可用时间晚于特征决策时点的数量，目前为 0。

最后一个指标只能证明时间检查未发现违规，不能证明经济逻辑正确。

### 5.5 另类数据脉冲

仅在存在可展示数据时出现。每张卡片包含指标名称、值、变化、数据质量、观察日和说明。来源主要是 AI Tracking Workbook 和官方补充数据。

`quality` 用于区分：

- 已核验并有可用日期；
- 当前快照；
- 来源/时间不完整；
- 仅用于市场背景。

### 5.6 今日 AI 产业重要事件

当事件数量超过 1 时显示多卡片列表，包括来源等级、事实摘要、产业链传导逻辑、关联代码和原文链接。当前标准化 `events` 表有 3 条事件记录。

### 5.7 今天先看什么

展示最多 6 家公司，包括代码、名称、研究情景、解释和 20D vs QQQ。点击任意公司打开 Company Drawer。

### 5.8 Research Status

Overview 右下角是三个研究假设的简版状态：

- H1：Developer activity → Earnings。
- H2：Capex growth → Conversion。
- H3：Fundamentals + Surprise + Valuation → Return。

这里只用于快速提示，完整统计解释以 Factor Lab 为准。

---

## 6. 页面二：AI Value Chain

AI Value Chain 的任务不是做股票分类，而是回答“AI 产业的钱流向哪里、需求如何验证、哪个环节出现景气变化”。

### 6.1 双向传导逻辑

```text
资本与供给：上游基础设施 → 中游平台与模型 → 下游应用与变现
需求验证：下游应用与变现 → 中游平台与模型 → 上游基础设施
```

前向链路用于跟踪芯片、存储、网络和云 Capex 如何形成模型和应用供给；反向链路用于检查应用使用与变现能否支撑云需求和芯片订单。

### 6.2 一级环节

| 一级环节 | 公司数 | 当前内容 |
|---|---:|---|
| 上游基础设施 | 6 | 芯片、晶圆代工、存储与数据中心网络 |
| 中游平台与模型 | 10 | 云平台、模型、数据平台和开发基础设施 |
| 下游应用与变现 | 4 | 企业 AI、创意与生产力应用 |

每个一级环节展示：

- 公司数；
- 基本面得分中位数；
- 20D 超额收益中位数；
- Fundamental Dislocation 数量；
- 景气趋势：加速、稳定或放缓。

一级环节趋势由该环节公司 `revenueAcceleration` 的中位数判断：大于等于 +3ppt 为 Accelerating，小于等于 -3ppt 为 Decelerating，中间为 Stable。

### 6.3 二级环节与公司

| 一级环节 | 二级环节 | 当前公司/实体 | 当前核心 KPI |
|---|---|---|---|
| 上游 | AI 计算芯片 | NVDA、AMD | Company Revenue YoY |
| 上游 | 定制芯片与网络 | AVGO | Company Revenue YoY |
| 上游 | 晶圆代工 | TSM | Company Revenue YoY |
| 上游 | 存储与 HBM | MU | Company Revenue YoY |
| 上游 | 数据中心网络 | ANET | Company Revenue YoY |
| 中游 | 云计算平台 | MSFT、AMZN、ORCL | Company Capex YoY |
| 中游 | 云与模型平台 | GOOGL | Company Capex YoY |
| 中游 | 基础模型 | META | Company Revenue YoY |
| 中游 | 非上市模型实验室 | OpenAI、Anthropic | Cloudflare 产品 rank/rank bucket |
| 中游 | 数据平台 | SNOW、MDB、ESTC | Company Revenue YoY |
| 中游 | 开发与推理基础设施 | NET、DDOG | Company Revenue YoY |
| 下游 | 企业 AI 应用 | PLTR、CRM、NOW | Company Revenue YoY |
| 下游 | 创意与生产力应用 | ADBE | Company Revenue YoY |

当前“Company Revenue/Capex”仍是公司总口径，不是纯 AI 分部 KPI。未来应按环节升级为 Data Center Revenue、HBM Revenue、AI Networking Revenue、Cloud Revenue、Token Usage、AI ARR 等更纯净指标。

### 6.4 每张公司卡片

- Ticker 与公司名。
- 环节核心 KPI 及最新同比值。
- 估值位置标签。
- Research Setup。
- 20D Excess。

公司排序优先展示 Fundamental Dislocation，再展示风险/恶化/动量，同时参考 Gap 绝对值。

### 6.5 OpenAI 与 Anthropic

两家公司属于非上市实体，因此：

- 放在中游“非上市模型实验室”；
- 不进入股票横截面排名；
- 不进入收益回测；
- 通过关联上市公司映射产业链影响。

当前映射：

- OpenAI → MSFT；同时有下游消费者和企业应用暴露。
- Anthropic → AMZN、GOOGL；同时有企业 AI 应用暴露。

当前产品信号：ChatGPT 显示 Cloudflare 全球域名 rank；Claude 在无精确 Top 100 排名时显示 rank bucket。这些数字是网页关注度，不是用户数。

### 6.6 产业链传导检验

#### CSP Capex → 上游芯片/网络收入

- X：MSFT、AMZN、GOOGL、ORCL 等 CSP 公司季度 Capex YoY 中位数。
- Y：NVDA、AMD、AVGO、MU、ANET 等上游公司季度 Revenue YoY 中位数。
- 方法：时间序列 Spearman Rank correlation。
- 当前结果：同期约 +0.65；+1Q 约 +0.69；+2Q 约 +0.60；+1Q 样本 26 个季度。
- 当前 Verdict：Promising。
- 正确解释：CSP Capex 与下一季度上游收入增速在当前样本中存在较强同向排序关系。
- 不能解释：尚未控制共同趋势、宏观周期、库存周期和反向因果，因此不是因果证明。

#### Token Usage → 中游云平台收入

- X：OpenRouter Top 50 模型 Token 季度增长。
- Y：云平台样本的公司收入增长。
- 当前 +1Q 完整季度配对只有 4 个。
- 当前 Verdict：Needs Data。
- 页面即使展示 -0.40/-1.00，也不能据此判断负向关系，因为样本过小且收入分母不够纯。

---

## 7. 页面三：Signal Monitor

Signal Monitor 回答“今天哪家公司出现值得研究的变化或错位”。它先在上游、中游、下游各自内部比较，再形成跨产业链研究排序。

### 7.1 顶部汇总

- 机会信号：`actionCategory = Opportunity`，即 Fundamental Dislocation。
- 风险信号：Expectation Risk 或 Deteriorating。
- 本次状态变化：NEW、Strengthening、Weakening 或 Exited 的公司数量。

### 7.2 筛选功能

研究动作筛选：全部、机会、动量、风险、观察。

产业链筛选：全产业链、上游基础设施、中游平台与模型、下游应用与变现。

搜索框支持公司名称、Ticker、一级环节和二级环节。

### 7.3 表格每一列

| 列 | 含义 | 来源/计算 |
|---|---|---|
| Rank | 当前研究排序 | 默认按同层 Gap 绝对值降序 |
| Company | Ticker 与公司名称 | Company Master |
| 产业链同组 | 一级环节与二级环节 | `research_universe.csv` 人工审核分类 |
| Signal | 当前研究情景 | 基本面分位与 20D excess 规则 |
| Signal Δ | 相比上一快照的变化 | `signal_monitor_history.json` |
| 20D Excess | 公司过去20日相对 QQQ 超额收益 | Massive 复权收盘价 |
| Rev YoY / Accel | 最新季度收入同比与同比增速变化 | SEC 季度财务数据 |
| EPS Rev 30D | 下一季度 EPS 预期相对30日前变化 | Alpha Vantage 当前供应商快照；缺失时显示待接入 |
| FCF Δ | 最新季度 FCF margin 相比上一季度变化 | SEC 季度财务数据 |
| Valuation %ile | 当前 P/S 在自身可用历史中的分位 | Massive 未复权价格 + SEC 每股销售代理 |
| 同层 Gap | 同一级环节的基本面分位减市场分位 | 0—100 分位差；同时显示全链 Gap 参考 |

### 7.4 基本面分数

当前基本面分数为同一一级环节内：

```text
Fundamental Percentile
= average(Revenue YoY percentile, FCF Margin percentile)
```

这里使用同层比较，避免把软件公司的利润结构与芯片、云平台机械放在同一分布里。

### 7.5 市场分数与 Gap

```text
Market Percentile = 20D Excess 在同一级环节中的分位

Fundamental–Price Gap
= (Fundamental Percentile - Market Percentile) × 100
```

- Gap 为正：基本面排序领先股价排序，可能存在 Fundamental Dislocation。
- Gap 为负：股价排序领先基本面排序，可能存在预期过热。
- 同层公司数量很少时，分位会离散并出现 ±100 等极端值；它是排序工具，不是概率或目标收益。

### 7.6 四类核心 Research Setup

| 条件 | 标签 | 研究含义 |
|---|---|---|
| 基本面分位 ≥ 55%，20D excess < 0 | Fundamental Dislocation | 基本面较强但股价跑输，优先查催化剂和市场担忧 |
| 基本面分位 ≥ 55%，20D excess ≥ 0 | Momentum | 基本面和价格同向较强 |
| 基本面分位 < 55%，20D excess ≥ 0 | Expectation Risk | 股价领先基本面，检查预期透支 |
| 基本面分位 < 55%，20D excess < 0 | Deteriorating | 基本面与价格同时较弱 |

若市场、基本面、盈利或估值核心输入覆盖率低于 80%，标记 Data Gap。

### 7.7 Signal Change

- Baseline：第一次建立快照，没有历史可比。
- NEW：上一快照不是可行动信号，本次进入 Fundamental Dislocation 或 Expectation Risk。
- Exited：上一快照为可行动信号，本次退出。
- Strengthening：Gap 绝对值较上一快照至少扩大 5 分。
- Weakening：Gap 绝对值较上一快照至少缩小 5 分。
- Unchanged：其他情况。

历史最多保留最近 120 个快照。第一次运行全部显示 Baseline 是正确行为，不应伪造历史变化。

### 7.8 估值口径

当前 P/S 是免费数据条件下的 filing-basis proxy：

```text
P/S proxy = 未复权股价 / 最近可用 Sales per diluted share
```

Valuation History Percentile 表示当前 P/S 在该公司可用历史中的位置。它不是 Forward P/S，也没有统一分析师未来收入预期，因此适合筛选，不适合直接写成精确估值结论。

---

## 8. 页面四：Factor Lab

Factor Lab 将“页面上看起来有意义的信号”转化为可证伪的历史检验。

### 8.1 两类实验

#### Fundamental Prediction

验证替代数据或资本开支是否领先未来收入、FCF 或 EPS。

#### Return Prediction

验证公司研究信号是否预测未来 20D、60D、120D 相对 QQQ 收益。

### 8.2 统计指标

| 指标 | 含义 |
|---|---|
| Rank IC | 因子排序与未来结果排序的 Spearman 相关 |
| IC Stability | 有效检验期中 Rank IC 为正的比例 |
| Hit Rate | 信号方向与未来结果方向一致的比例 |
| Sample Size | 完整可用观测数量 |
| Q5−Q1 Spread | 因子最高组平均收益减最低组平均收益 |
| Group Returns | 按因子分数从 Q1 到 Q5 的未来平均收益 |
| Lead–Lag | 同一输入对 +1Q、+2Q 等未来窗口的关系 |

### 8.3 Verdict

- Validated：方向、稳定性、样本和经济意义均达到预设标准。
- Promising：存在较有意义信号，但仍需更多数据或控制变量。
- Weak：当前关系弱或不稳定。
- Rejected：当前规则与未来结果方向相反或缺乏价值。
- Needs Data：样本不足，不能判断。

### 8.4 当前实验结果

#### F1 AI Adoption Factor

- 问题：开源开发活动是否领先下一次盈利意外？
- 输入：最近完整月 commits 相对前三个完整月均值的 log 变化。
- 样本：60。
- Rank IC：约 -0.02。
- Verdict：Weak。
- 结论：当前自动选择的公司开源仓库活动不能视为产品采用率。
- 下一步：积累 Cloudflare Radar 历史并引入产品级 GitHub/HF 映射。

#### F2 Capex Conversion Factor

- 问题：季度总 Capex 增长是否领先未来收入/FCF 转化？
- +1Q Revenue Rank IC：约 +0.118。
- +2Q Revenue Rank IC：约 +0.081。
- +1Q FCF Margin Rank IC：约 -0.053。
- +2Q FCF Margin Rank IC：约 -0.096。
- 样本：425 个公司季度。
- 正向 IC 期比例：56%。
- Verdict：Promising。
- 分环节结果：半导体 +1Q Revenue Rank IC 约 +0.125；Cloud 约 +0.035；Foundry 当前无可用横截面样本。
- 正确解释：Capex 增长对下一季度收入增长存在弱至中等正向排序关系，但未证明能够改善未来 FCF。

#### F3 Token Usage Factor

- 问题：OpenRouter Token 增长是否领先云平台收入？
- +1Q 样本：4。
- +1Q Rank IC：-0.40；+2Q：-1.00。
- Verdict：Needs Data。
- 结论：样本太小，数字不具有投资结论意义。

#### R1 Fundamental Dislocation Factor

- 问题：基本面排序强、20D 价格排序弱，是否预测未来超额收益？
- 方法：每 20 个交易日重建横截面；次日收盘进入；相对 QQQ。
- 20D：样本 460，Rank IC +0.019，正向期 43%，Q5−Q1 约 -1.15%。
- 60D：样本 420，Rank IC 约 -0.001，Q5−Q1 约 -3.68%。
- 120D：样本 360，Rank IC +0.022，Q5−Q1 约 -8.11%。
- Verdict：Weak。
- 结论：当前 Gap 规则尚未证明能够预测未来收益。
- 下一步：行业中性化、控制交易成本、扩展样本、引入 EPS Revision 和更纯的分部 KPI。

#### R2 EPS Revision Factor

- 问题：30D EPS 一致预期上调是否预测未来 20D/60D 收益？
- 当前样本：0 个严格 PIT 历史截面。
- Verdict：Needs Data。
- 原因：当前可以看到供应商的当期修正字段，但每日归档历史刚开始积累。

#### R3 Fundamental + Valuation Factor

- 当前规则：正盈利意外 + 正收入增长 + 正 FCF margin + P/S 不高于当日样本中位数。
- 样本：154。
- 20D Rank IC：约 -0.093。
- Q5−Q1：约 -0.20%。
- Verdict：Rejected。
- 结论：当前简单复合规则没有显示稳定的未来 20D 超额收益。
- 下一步：移除不严格的历史共识输入，改用正式 EPS Revision 并做行业中性化。

---

## 9. Company Drawer：单家公司详情

点击 Overview 队列、AI Value Chain 卡片或 Signal Monitor 行后打开。

### 9.1 Why Flagged

- Fundamental Score：同层 Revenue YoY 与 FCF Margin 分位的均值，0—100。
- Gap：同层 Fundamental Percentile 减 Market Percentile，乘 100。
- 收入增速变化：本季度 Revenue YoY 减上一季度 Revenue YoY。
- 20D Excess：公司相对 QQQ 的 20 日收益差。
- 自身历史估值分位：当前 filing-basis P/S 在自身可用历史中的分位。
- 结论：按 Research Setup 规则自动生成的研究解释。
- 今日催化：若今日事件与公司匹配，则显示事件标题。

### 9.2 四个行情/基本面指标

- Close：最新 Massive 复权收盘价。
- 20D vs QQQ：20D Excess。
- Core KPI：云平台显示 Company Capex YoY，其他当前主要显示 Company Revenue YoY。
- P/S Proxy：未复权价格和 SEC filing-basis 每股销售数据构造。

### 9.3 产业链角色与传导关系

- 主要环节：upstream/midstream/downstream。
- 细分环节：如 AI compute、cloud platform、enterprise AI applications。
- 次要暴露：公司除主环节外的重要 AI 业务。
- 上游依赖：芯片、代工、云或数据等主要依赖。
- 下游客户：主要客户类型或分发渠道。
- 财务可用日：最新进入页面计算的财务数据真正可用日期。

### 9.4 同层横截面分位

- 基本面质量。
- 相对估值吸引力。
- 20D 相对表现。
- 同层样本数量。

### 9.5 Last 120 Sessions

将公司和 QQQ 在共同起点归一化为 100：

```text
Indexed price = 当日收盘价 / 120日窗口首日收盘价 × 100
```

该图展示相对路径，不是累计超额收益的精确归因图。

### 9.6 Research Snapshot

- FCF Margin：最新季度自由现金流率。
- Latest EPS Surprise：最近一次实际 EPS 相对供应商预期的差异。
- GitHub Stars Snapshot：所选公司仓库 stars 汇总快照。
- HF Downloads Snapshot：所选组织 Top 50 模型累计下载快照。

---

## 10. 数据库逐表说明

数据库路径：`data/warehouse/ai_alpha_research.duckdb`。

### 10.1 主数据与配置

#### `company_master`

- 粒度：一家公司一行，目前 20 行。
- 关键字段：`ticker`, `company_name`, `cik`, `github_owner`, `huggingface_author`, `value_chain_bucket`, `product_focus`, `primary_stage`, `secondary_segment`, `secondary_exposure`, `upstream_dependencies`, `downstream_customers`。
- 来源：`config/research_universe.csv`。
- 作用：所有表的公司映射、产业链分类和产品映射底座。

#### `ai_product_domains`

- 粒度：一个 AI 产品/域名一行。
- 作用：把 ChatGPT、Claude 等产品域名映射到公司、非上市实体和上市关联公司。

#### `source_registry`

- 字段：来源 ID、名称、Tier、访问方式、成本、认证方式、基础 URL、历史覆盖、PIT 状态、可靠性、用途和限制。
- 作用：明确“数据能否拿到”与“数据能否用于回测”是两件不同的事。

#### `data_dictionary`

- 字段：`field_name`, `table_name`, `description`, `datatype`, `frequency`, `source_type`, `historical_available`, `period_end`, `available_date/as_of_date`, `update_rule`, `factor_hypothesis`, `MVP_priority`。
- 作用：字段级口径说明。

### 10.2 市场数据

#### `market_daily`

| 字段 | 含义 |
|---|---|
| `ticker` | 股票/ETF 代码 |
| `trade_date` | 交易日期 |
| `open`, `high`, `low`, `close` | 复权日线价格 |
| `volume` | 成交量 |
| `vwap` | 成交量加权平均价 |
| `transactions` | 成交笔数 |
| `adjusted` | 是否请求复权数据 |
| `available_at` | 该交易日数据可用于研究的时间 |
| `source_retrieved_at` | 系统抓取时间 |
| `source` | `massive` |

#### `market_unadjusted_daily`

- 字段：`ticker`, `trade_date`, `close_unadjusted`, `available_at`, `source_retrieved_at`, `source`。
- 作用：配合 SEC 稀释股数和每股销售/FCF 构造 filing-basis 估值，避免拆股导致价格与每股分母错配。

### 10.3 财务数据

#### `fundamental_observations`

字段包括 `ticker`, `metric_name`, `taxonomy`, `xbrl_tag`, `tag_priority`, `metric_value`, `unit`, `start_date`, `period_end`, `duration_days`, `fiscal_year`, `fiscal_period`, `form`, `accession_number`, `filed_date`, `available_date`, `frame`, `source_retrieved_at`, `source`。

这是最接近 SEC 原始事实的标准化长表，用于追踪每个数来自哪个 XBRL tag 和哪份申报。

#### `fundamental_annual`

字段包括年度、报告期、可用日期、财务币种、收入、毛利、营业利润、经营现金流、Capex、FCF、研发、稀释股数、每股销售、每股 FCF、同比增长、FCF margin 和 Capex/Revenue。

#### `fundamental_quarterly`

字段包括：

- 识别：`ticker`, `fiscal_year`, `fiscal_quarter`。
- 时间：`period_end`, `available_date`。
- 金额：`revenue`, `gross_profit`, `operating_income`, `operating_cash_flow`, `capex`, `free_cash_flow`, `rd_expense`。
- 比率：`fcf_margin`, `capex_to_revenue`。
- 增长：`revenue_yoy`, `capex_yoy`, `free_cash_flow_yoy`, `revenue_qoq`, `revenue_growth_acceleration`。
- 血缘：`metric_derivations`, `source_accessions`, `pit_selection_rule`。

若 SEC 只提供六个月或九个月累计现金流，单季度值通过累计差额还原；Q4 可用全年值减九个月累计值。还原方法必须保存在 `metric_derivations` 中。

### 10.4 Earnings 与预期

#### `earnings`

字段：`ticker`, `fiscal_period_end`, `reported_date`, `report_time`, `reported_eps`, `estimated_eps`, `surprise`, `surprise_pct`, `available_at`, `source_retrieved_at`, `pit_status`, `source`。

盘前财报可映射到当日；盘后或未知发布时间保守映射到下一交易日。

### 10.5 开发者与模型数据

#### `github_activity_events`

- 字段：`ticker`, `repo`, `event_type`, `event_id`, `event_at`, `source_retrieved_at`, `proxy_scope`。
- 粒度：一次 commit 或 release 事件。

#### `developer_monthly_activity`

- 字段：`ticker`, `repo`, `month_end`, `commit_count`, `release_count`, `history_complete_within_window`, `selection_rule`, `factor_hypothesis`。
- 作用：构造月度活动变化，避免把不完整当月与完整月份比较。

#### `developer_snapshot`

- GitHub：返回仓库数、stars、forks、open issues、近 90 天活跃仓库数、历史状态。
- Hugging Face：模型数、Top 50 downloads、Top 50 likes、历史状态。

#### `openrouter_model_snapshot`

- 字段：模型 ID、名称、创建时间、上下文长度、输入/输出/cache read 单 Token 价格、快照时间、PIT 状态。

#### `openrouter_usage_daily`

- 字段：`usage_date`, `model_permaslug`, `provider`, `total_tokens`, `available_at`, `source_retrieved_at`, `source`, `scope`。
- 粒度：一天 × 一个 Top 50 模型或 other 聚合行。

#### `product_domain_rank_daily`

- 字段：产品、域名、上市代码、Owner、观察日、精确 rank、rank bucket、类别、可用时间、来源、信号范围和 PIT 状态。

### 10.6 事件与手工另类数据

#### `events`

包含 27 个字段：事件 ID、发生时间、首次发现时间、可用时间、时间精度、类型、来源等级、来源名、URL、辅助 URL、标题、事实摘要、变化、预期差、受影响公司、受益方、受损方、传导路径、影响期限、定价状态、重要性、置信度、评分组件、下一催化剂、证伪条件、去重簇和验证状态。

#### `manual_alternative_observations`

每条数据保存 series ID、实体、Ticker、指标、观察期、可用时间、数值、单位、频率、来源名、URL、Tier、PIT 状态、原工作表、单元格、研究用途和备注。

### 10.7 Feature Store

字段：

- `ticker`
- `feature_date`
- `feature_name`
- `feature_value`
- `feature_version`
- `source_period_end`
- `source_max_available_at`
- `source`

当前来源标签包括 Massive、SEC EDGAR、GitHub dated history、GitHub/HF snapshot、Alpha Vantage unverified PIT，以及 Massive + SEC 构造的估值代理。

每个 Feature 必须能回答：公式是什么、版本是什么、使用了哪个报告期、最晚源数据什么时候可用、来自哪里。

### 10.8 Targets

字段：`ticker`, `target_date`, `benchmark_ticker`, `target_version`, `entry_rule`, `ret_1d`, `ret_5d`, `ret_20d`, `ret_60d`, `ret_120d`, `excess_return_20d`, `excess_return_60d`, `excess_return_120d`, `future_vol_20d`, `future_max_drawdown_20d`, `target_available_at`。

Targets 是未来结果 Y，不能与 Feature X 混在一起，也不能被页面当前状态反向污染。

### 10.9 审计与运行表

#### `raw_manifest`

记录每个原始 JSON 文件的路径、来源、实体、抓取时间、SHA-256、文件大小、payload 类型、记录数、请求信息和解析状态。

#### `latest_raw_by_source_entity`

视图；对每个来源和实体选择最新成功原始文件，方便审计最新抓取。

#### `ingestion_log`

记录处理报告、任务、来源、实体、状态、运行时间、原始文件和错误信息。

#### `quality_exceptions`

保存失败、主键重复、日期错配和已知研究限制，并区分 error/warning 和 open/known。

#### `factor_results`

保存实验类别、ID、因子名、Verdict、结论、下一步和完整 JSON。

#### `data_asset_registry`

保存每张仓库表属于哪一层、来自哪个本地文件、行数和加载时间。

#### `warehouse_metadata`

保存 Schema 版本、构建时间和项目名。

---

## 11. 数据质量检查

当前自动检查包括：

1. `market_daily` 的 ticker/date 重复。
2. `targets` 的 ticker/date/version 重复。
3. `feature_store` 的 ticker/date/name/version 重复。
4. `fundamental_quarterly` 的 ticker/period_end 重复。
5. 公司与 QQQ 交易日是否对齐。
6. `source_max_available_at` 是否晚于 feature decision date。
7. 季度财务 available date 是否违规。
8. 成熟 Target 是否缺少 QQQ excess。
9. 成熟 Target 是否缺少 target available time。
10. Revenue/Capex 是否出现不合理负值。
11. 20 家公司基本面覆盖是否完整。

当前结果：上述工程完整性检查为 PASS；重复主键 0；Feature 时间违规 0；季度时间违规 0；成熟 20D QQQ excess 缺失 0。

但工程 PASS 不证明：

- 因子有效；
- 供应商数据达到机构级；
- 所有代理变量具有正确经济含义；
- 小样本统计结果可以外推。

---

## 12. 日常更新流程

建议每天北京时间 08:00 前后运行：

```bash
cd /Users/cynthiaxii427/Projects/ai_alpha_research
python3 scripts/run_research_pipeline.py
```

注意：`run_research_pipeline.py` 是研究处理流程，不负责重新抓取全部外部 API。仅运行它不会使尚未抓取的来源自动变成今日数据。采集、研究重算和网页导出必须区分。

端到端更新应包括以下环节，其中前两步需要先运行相应采集流程：

1. 拉取可更新的市场、事件、开发者、模型和产品关注度数据。
2. 原始响应写入 `data/raw/`。
3. 标准化为 CSV。
4. 重建 Feature Store 和 Targets。
5. 运行质量检查。
6. 原子方式重建 DuckDB。
7. 运行假设检验并写入 Factor Results。
8. 更新 Signal Monitor 历史状态。
9. 导出 `dashboard.json`。
10. 网页刷新后读取最新数据。

若仅更新页面展示或从现有数据库生成需求链，可运行：

```bash
cd /Users/cynthiaxii427/Projects/ai_alpha_research
python3 scripts/export_web_data.py
npm --prefix web run build
```

导出会重新计算 `demandChain`，不会重新下载源数据。先在 DBeaver 中断开数据库连接，避免文件锁冲突；不要删除数据库来解决锁问题。页面证据截止时间、市场截至日和各指标观察日期可能不同。

每日 AI 晨报应优先覆盖：模型/产品发布与定价、云和 Capex、芯片/网络/存储、开发者采用、企业变现、监管和关键供应链事件。事件必须附原始链接、发布时间、影响对象、传导路径和证伪条件。

---

## 13. 如何人工核验一个页面数字

以 AVGO 的 20D Excess 为例：

1. 在网页公司详情确认 Market As Of 日期。
2. 在 `market_daily` 查询 AVGO 和 QQQ 最近 21 个共同交易日收盘价。
3. 分别计算 20D momentum。
4. 用 AVGO momentum 减 QQQ momentum。
5. 检查 `market_daily.source = massive`。
6. 在 `raw_manifest` 搜索 `source=massive, entity=AVGO/QQQ`，打开对应 raw JSON。
7. 对照 Massive 官方接口响应。

以 Revenue YoY 为例：

1. 在 `fundamental_quarterly` 找到公司最新 `period_end` 和 `available_date`。
2. 核对 `source_accessions` 和 `metric_derivations`。
3. 在 `fundamental_observations` 找到对应 accession、XBRL tag 和原始值。
4. 回到 SEC filing 核验。
5. 确认该值的 `available_date` 不晚于页面研究截止日。

---

## 14. 当前主要研究限制

1. 20 家公司样本较小，且历史行情主要从 2024-10 开始。
2. 日频重叠 20D/60D Targets 不是独立样本，不能把每行都当成独立观测计算显著性。
3. 产业链一级环节最小只有 4 家，同层分位较离散。
4. 基本面核心 KPI 仍大量使用公司总 Revenue/Capex，不够 AI-native。
5. EPS Revision 缺少长期、可验证的每日 PIT consensus 历史。
6. GitHub 自动选库只是公司开源代理。
7. Hugging Face downloads 是当前累计快照。
8. Cloudflare Radar 是 DNS/web attention 代理。
9. OpenRouter 只代表其平台内流量，Provider Token 口径不同。
10. Tracking Workbook 中部分数据缺少原始 URL、单位和 available_at。
11. 当前估值是 filing-basis proxy，不是正式 Forward P/E 或 Forward EV/Sales。
12. 当前信号尚未控制行业、规模、beta、质量、成长等传统风险因子。
13. 尚未纳入交易成本、换手率、借券成本和容量。
14. 当前页面保留 `Data & Methodology` 组件代码，但侧边栏实际只开放 Overview、AI Value Chain、Signal Monitor 和 Factor Lab；方法页需要在后续版本决定是恢复为第五页还是改为可下载文档。

---

## 15. 未来完善与修改目标

### P0：首先提升数据可靠性

1. 为每个页面数字增加可点击的 Data Lineage：来源 → 原始文件 → 标准化记录 → Feature 公式 → 页面字段。
2. 对 Massive 价格与第二免费来源做抽样交叉核验，检查复权、停牌和拆股。
3. 对 SEC 每家公司建立 XBRL tag 白名单，人工抽查最新 10-Q/10-K。
4. 将 Tracking Workbook 每条可用序列补齐 source URL、单位、发布时间和 available_at。
5. 每次更新生成 Data Quality Dashboard：缺失率、延迟、异常值、覆盖断点和供应商响应状态。
6. 数据库增加不可变 run ID 和代码版本，使任意历史页面可以重建。

### P0：把核心 KPI 升级为真正的 AI-native 数据

按二级环节替换公司总收入代理：

- AI Compute：Data Center/GPU Revenue、GM、供货周期。
- Memory/HBM：HBM Revenue、Memory ASP、库存天数、HBM 产能。
- Networking：AI Networking Revenue、订单、Backlog、800G/1.6T 出货。
- Foundry：HPC/AI Revenue、先进制程占比、CoWoS/先进封装产能、Capex。
- Cloud：Cloud Revenue Growth、AI/Cloud Capex、Capex/Revenue、积压订单。
- Model Labs：Token Usage、API Price、Latency、市场份额、产品 rank。
- Data/Developer Platform：Consumption Revenue、NRR、AI workload、developer adoption。
- Enterprise Apps：AI ARR、AI 客户数、席位、ARPU、AI attach rate。

### P0：建立可靠的 EPS Revision 历史

1. 每日归档 Alpha Vantage 当前 estimate 响应。
2. 如果免费来源不足，评估 Financial Modeling Prep、Finnhub 或公司指引文本替代。
3. 只有形成连续的 `as_of_date × forecast_period` 历史后，才正式测试 EPS Revision Factor。
4. 将 EPS Surprise 留在财报事件分析，不再当作日常预期变化替代。

### P1：Signal Monitor 升级

1. 同一级环节之外，再建立二级环节 peer group；样本太小时回退到一级环节。
2. Gap 加入 Revenue Acceleration、EPS Revision、FCF Delta 和估值分位的可配置权重。
3. 展示信号首次出现日期、持续天数和过去 5 个快照路径。
4. 增加催化剂日历和“为何今天变化”。
5. 增加风险中性 Gap：先去除行业、规模、beta 和过去收益影响。
6. 将 ±100 离散分位改为平滑 z-score/empirical Bayes 版本，并保留原始分位供审计。

### P1：AI Value Chain 升级

1. 将人工文本依赖升级为正式 `supply_chain_relationship` 表，包含关系类型、有效期、来源和置信度。
2. 增加产业链 Sankey/Network 图，但每条边必须有来源依据。
3. 加入环节景气时间序列，而不仅是当前快照。
4. 把 CSP Capex → 上游收入扩展到订单、交付、收入和 FCF 四阶段。
5. 从下游 AI 应用采用反向验证 Cloud consumption、Token 和 GPU demand。
6. 将 OpenAI/Anthropic 等非上市实体的影响映射到 MSFT、AMZN、GOOGL、ORCL 等上市公司，但不混入股票排名。

### P1：Factor Lab 升级

1. 使用非重叠月度/季度调仓样本作为主检验，重叠日频样本只做诊断。
2. 增加 Newey-West、block bootstrap 或 cluster-robust 统计误差。
3. 做行业、规模、beta、价值、成长、质量和动量中性化。
4. 加入交易成本、换手率、最大回撤和容量。
5. 做样本外检验：训练期、验证期、真正 holdout 期。
6. 对半导体、云、软件分别检验，避免混合不同经济模型。
7. 将 Signal Monitor 标签直接做事件研究：信号首次出现后 20D/60D/120D 收益。
8. 只有在简单因子具有稳定证据后才考虑机器学习。

### P1：每日 AI 晨报升级

1. 增加 RSS、SEC 8-K、公司 IR 和官方博客自动采集。
2. 事件去重并保留第一来源和首次发现时间。
3. 事件评分拆分为 Materiality、Confidence、Novelty 和 Market Sensitivity。
4. 每条事件连接到产业链环节、公司、可能受益/受损方和下一验证数据。
5. 保存事件历史，检验不同事件类型的后续收益和盈利修正。
6. 失败时显示真实采集状态，不用空话填充页面。

### P2：页面与产品体验

1. 恢复或重构 Data & Methodology 页面，允许查看来源、覆盖、延迟和已知限制。
2. 每个数字增加 tooltip：定义、公式、来源、截至日期和可靠性。
3. Company Drawer 增加最新财报、分部 KPI、估值历史和事件时间线。
4. 支持下载当前筛选结果、研究底稿和公司 memo。
5. 增加用户自定义 Universe、Benchmark、Horizon 和行业筛选。
6. 增加“一键复现该页面”的 run ID。

### P2：自动化与部署

1. 将每日更新放入 GitHub Actions、Cloudflare Cron 或本地定时任务。
2. 前端从静态 JSON 升级为只读查询 API。
3. 数据库从单机 DuckDB 平滑迁移到 PostgreSQL/对象存储，同时保留 DuckDB 本地研究能力。
4. API Keys 只保存在 Secrets，不写入仓库或网页。
5. 增加失败告警、重试、供应商限流和增量抓取。
6. 正式分享时使用可撤销访问控制；临时演示可继续使用短期 tunnel。

### 推荐实施顺序

```text
第一阶段：数据血缘与来源核验
→ 第二阶段：AI 分部 KPI 与 EPS Revision 历史
→ 第三阶段：Signal Monitor 历史变化
→ 第四阶段：产业链传导与因子稳健性
→ 第五阶段：自动更新、部署和访问控制
```

---

## 16. 一句话汇报口径

本项目搭建了一个面向 AI 产业链股票研究的 point-in-time 数据与网页平台：它将市场、SEC 财务、盈利、开发者活动、模型使用、产品关注度和重大事件统一到 DuckDB，通过上游—中游—下游框架识别景气传导和公司定价错位，并在 Factor Lab 中检验这些信号是否真正具有基本面或收益预测能力；当前工程链路已跑通，但投资结论仍处于探索验证阶段。

新增特色是「AI 需求兑现链」：将采用、消耗、算力、投资与商业兑现分别用可追溯数据观察，帮助研究员判断需求在哪一环获得支持、哪里还缺证据，而不是仅展示股票分类和静态财务数字。

---

## 17. 页面五：AI 需求兑现链

入口：侧栏 `05 AI 需求兑现链`；网页路由 `#demand-chain`。

### 17.1 研究逻辑与页面分工

`Adoption → Consumption → Compute → Investment → Monetization` 是观察框架，不是已经验证的单向因果模型。投资也可能先于需求，效率改善也可能使Token增长不对应同比例的算力增长。

- 需求兑现路径：用户采用 → 实际消耗 → 收入与现金流。
- 供给投入路径：算力供需 → 投资扩张 → 后续收入与现金流。

AI Value Chain回答“公司处于哪里”；本页回答“每个环节有什么实际证据”；Signal Monitor寻找公司级错位；Factor Lab检验预测关系。新页面的 Factor Lab 按钮目前只导航至已有实验，不表示五环节已完成新增传导回测。

### 17.2 Adoption：用户采用

来源表 `product_domain_rank_daily`，来源 Cloudflare Radar。当前导出包含9个产品最新可用快照。

| 页面内容 | 数据/计算 | 解读 |
|---|---|---|
| 产品名 | `product_name`，按 `product_id` 分组 | 产品层，不等同于上市公司 |
| 精确排名 | 有效数值 `rank`，显示 # | 排名数字越小表示排名越靠前 |
| 排名区间 | 无精确值时显示 `rank_bucket` | 例如500是区间标签，不宣称精确第500名 |
| 日期数量 | 去版本重复后的观察日期数 | 一个日期不能计算采用增长 |
| 观察日 | 最新 `observation_date` | 各产品日期可以不同 |
| 数据底稿 | `available_at`、来源表及域名来源链接 | DNS关注度不是活跃用户、留存或付费转化 |

同一产品和观察日期只保留证据截止前最新可用版本。页面不把ChatGPT、Claude等产品关注度直接归入某一家上市公司的收入。

### 17.3 Consumption：实际消耗

来源表 `openrouter_usage_daily`，来源 OpenRouter Rankings。观察范围仅限该平台，不代表全球模型总使用量。

| 指标 | 当前计算方式 |
|---|---|
| 模型日记录 | 按 `usage_date × model_permaslug` 去版本重复；只使用非负有效Token值 |
| 每日总量 | 当日模型Token相加，包括 `other` 长尾 |
| 最近7日总量 | 以最新有效观测日为终点的7个日历日合计，排除截止时间所在的未完成UTC日 |
| 7日变化 | 最近7日总量 / 此前7日总量 − 1；要求14个日期齐全且前期总量为正 |
| 日期覆盖 | 两个窗口实际存在的日期数 / 14；不将缺日填零 |
| other占比 | 最近7日长尾Token / 同窗口总量；若窗口有缺日，只反映已观测部分 |
| 趋势图 | 最近28个观测日的日总量；不是用户数或付费收入 |

最近7日缺日时总量为空，任一比较窗口缺日时变化率为空。日期齐全也不等于供应商每天模型覆盖必然完整，仍需核验源响应。免费模型比例、模型组合与Tokenizer差异会影响总量比较。

### 17.4 Compute：算力供需

来源表 `manual_alternative_observations`。当前选取工作簿中 `metric_name=gpu_rental_price` 且 `unit=USD_per_hour` 的 A100、H100、B200 三类序列。

- 当前报价：该序列最新可用观测值，单位为美元/GPU小时。
- 约30日变化：最新报价 / 基准报价 − 1。基准先定位30日前，允许向更早寻找最多7日；无合格正值基准则留空。
- 趋势图：最近60个观测点，按观测顺序排布；缺日不补值，横轴间距不代表严格日历距离。
- 陈旧程度：证据截止日减观察日，直接展示相差天数。
- 底稿：来源名称、URL（如有）、工作簿Sheet和单元格（如有）、`available_at`、`pit_status`。

报价受供给、需求、机型、地区和租约条款共同影响，不能当GPU利用率。工作簿历史按实际可用快照时间使用，不回填为历史当日已知；当前只作描述性观察。

### 17.5 Investment / Monetization：投入与兑现

来源 `fundamental_quarterly`，底层为 SEC Companyfacts。当前对象为 MSFT、AMZN、GOOGL、ORCL。两个页签共用同一张财务对照表，分别从投入和兑现角度阅读，尚未配置独立的AI分部收入或ROI模型。

| 页面字段 | 定义 |
|---|---|
| 公司 / 财季 | 每家公司最新可用 `period_end`；不同公司不强行对齐财年 |
| Capex YoY | 标准化表 `capex_yoy` |
| 收入 YoY | 标准化表 `revenue_yoy`，公司总口径 |
| 增速差 | Capex YoY − Revenue YoY，以百分点显示 |
| Capex / 收入 | 本季 `capex / revenue`，收入须为正 |
| FCF率 | 本季 `free_cash_flow / revenue`，收入须为正 |
| FCF率同比变化 | 本季FCF率 − 去年同一财季FCF率；缺少对应财季则留空 |

点击公司行打开 Company Drawer，查看现有行情、基本面和市场错位。底稿展开提供源表、可用日期和SEC accession（如有）。当前财务增长率沿用标准化表结果，本模块没有重新核验所有XBRL原始事实和重述版本。

### 17.6 本期研究线索与规则

规则按以下顺序执行，不是预测模型或交易评级：

1. **投入领先收入，现金流承压**：Capex增速减收入增速大于10个百分点，且FCF率同比下降超过2个百分点。
2. **收入增长且现金流率改善**：未触发第一项，收入同比为正且FCF率同比改善超过2个百分点。改善不意味着FCF已经转正。
3. **继续跟踪投入兑现**：未触发前两项，或必要值缺失；不应解读为数据已证明没有风险。

研究线索列表仅展示前两类，并保留公司和财季。点击打开公司详情。阈值为人工设置，后续需用历史样本验证敏感性、稳定性和行业差异。

### 17.7 相邻环节的证据状态

| 关系 | 当前可以做什么 | 还缺什么 |
|---|---|---|
| Adoption → Consumption | 分别观察产品关注度与平台Token | 同产品、同覆盖的活跃用户、留存、请求量历史 |
| Consumption → Compute | 对照Token与GPU报价趋势 | GPU小时、利用率、缓存、机型工作负载与推理效率 |
| Compute → Investment | 观察算力市场与资本开支 | 订单、交付时间、采购主体和供应商关系 |
| Investment → Monetization | 同公司同财季的增速差与现金流观察 | Cloud/AI分部收入利润、4Q/8Q滞后检验 |

### 17.8 存储、时间规则与复现

- 计算代码：`src/ai_alpha_research/demand_chain.py`。
- 页面组件：`web/src/DemandChain.jsx`。
- 数据出口：`scripts/export_web_data.py` 从统一DuckDB读取上述表，输出 `web/public/data/dashboard.json` 的 `demandChain` 字段。
- 版本：`demand_chain_v1`。新派生结果目前没有独立持久化为DuckDB表，不能在DBeaver中寻找同名实体表。
- 证据截止：导出时的UTC时间；按可用时间筛选，重复自然键选截止前最新版本。
- 财务可用日期若只有日期，当前按UTC零点解析；本页仅作当前观察，不适用于财报日内回测。
- Token记录按UTC日；工作簿和财务的观测日不等于数据抓取日。
- 回归测试：`PYTHONPATH=src python3 -m unittest discover -s tests -p test_demand_chain.py`，覆盖缺日、截止后版本排除、缺财年与同财季比较。
- 专项说明：`docs/DEMAND_CHAIN.md`。

### 17.9 下一步完善优先级

1. **先核验现有指标**：抽查原始API、SEC季度口径与工作簿报价来源；加强逐字段血缘和异常标记。
2. **再补齐同主体历史**：产品采用与消耗必须匹配产品、覆盖区域、时间频率，不能直接拼接不同平台总量。
3. **拆分供需与兑现**：加入GPU利用率、订单交付，以及Cloud/AI分部收入、利润和现金流；保留公司总口径作对照。
4. **落地派生历史**：按运行ID、代码版本和证据截止保存需求链快照、覆盖率与规则触发记录。
5. **进入Factor Lab检验**：检验相邻关系、4Q/8Q投入兑现及研究线索后的收益；控制时间泄漏、重叠样本和多重检验。
6. **验证后回流Signal Monitor**：只将有足够历史与稳定证据的指标加入公司排序，不先构造黑箱总分。

---

## 18. 交付快照与公开发布审计

交付网页可以冻结真实数据快照，不要求自动更新；但“数字真实”“研究口径可靠”和“拥有公开再分发许可”是三项不同要求。更换 React/Vite、Next.js、Vercel、Cloudflare 或 Sites 不会改变数据许可。

### 18.1 2026-09-05发布前检查结果

- 10,143条标准化行情逐行回溯到保留的Massive原始JSON，OHLCV与VWAP/成交笔数不一致数为0。
- 行情高低开收及非负成交量逻辑异常数为0。
- 季度收入、Capex和FCF同比按约一年前的实际经济期末重新计算，不一致数为0。
- 发现SEC发行人 `fy/fp` 标签存在23组重复/陈旧标签；已停止使用该标签作为同比连接键，改为330—400日窗口内最接近365日的经济期匹配。原标签仅保留作血缘提示。
- 官方事件保留来源URL并区分时间口径：RSS/Atom使用官方发布时间；OpenAI产品站点在页面未给明确发布时间时使用sitemap `lastmod`，不得改写为无法证实的发布日期。
- API密钥、本地用户路径和学校邮箱均未进入网页构建目录。
- 工程检查通过仍只表示一致性检查通过，不表示因子有效或达到机构级数据认证。

审计底稿：`data/research/public_release_audit.json`；可复现脚本：`scripts/audit_public_release.py`。

### 18.2 当前公开发布许可门槛

Massive Market Data Terms 明确限制未经书面同意向第三方复制、公开展示、分发市场数据，以及基于该数据的图表、分析和其他衍生作品。因此当前包含股价、QQQ超额收益、估值和收益因子结果的完整网页，不能仅凭免费API Key直接发布为公开链接。

Tracking Workbook 位于实习资料目录，其公开展示权不能从文件可读取推定。公开版本必须由资料权利方确认，或者移除工作簿衍生的GPU租价、CSP Capex、内存等内容。

### 18.3 两种合规交付方式

1. **完整研究版**：保留当前真实数据，只在已获得供应商和实习资料公开展示许可的受控环境中交付。
2. **公开安全版**：保留SEC公开事实、公司官方事件和经条款确认可公开的数据；移除Massive原始/衍生行情、QQQ超额收益、以行情形成的Targets及因子结果，并对工作簿数据按授权结果保留或删除。

公开安全版仍可展示真实数据，但研究功能范围会收缩。不得用另一免费API替换Massive后默认其允许公开转载；必须单独审核该来源许可。
