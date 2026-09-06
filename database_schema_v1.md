# Database Schema v1

## 1. 设计结论

底层采用“规范化原始观察表 + 按需物化 Feature Store + 独立 Targets”的三层架构，而不是单张超宽日频表。

```text
                         ┌──────────────────┐
                         │  company_master  │
                         └────────┬─────────┘
                                  │ 1:N
                  ┌───────────────┼────────────────┐
                  ▼               ▼                ▼
          security_master   product_master   supply_chain_relationship
                  │               │                │
          ┌───────┼───────┐       ├──────────┐     │
          ▼       ▼       ▼       ▼          ▼     ▼
       market  valuation targets product   ai_metric   events
       daily   observation       observation observation + company map
          │       │                  │          │
          └───────┴──────────┬───────┴──────────┘
                             ▼
                       feature_store
                             │
                             ▼
                    factor test / backtest

company_master ── fundamental_observation
company_master ── estimate_observation
research_run   ── feature_store / targets
```

## 2. 主键与关系

`company_master` 同时维护 `primary_stage`、`secondary_segment`、`secondary_exposure`、`upstream_dependencies` 和 `downstream_customers`。一级环节用于上游/中游/下游同层比较；二级环节用于配置差异化 KPI；依赖和客户字段用于产业链领先—滞后检验。

| 表 | 主键/自然唯一键 | 主要外键 | 粒度 |
|---|---|---|---|
| `company_master` | `company_id` | — | 一家公司 |
| `security_master` | `security_id` | `company_id` | 一只证券/一个有效上市身份 |
| `market_daily` | `(security_id, trade_date, revision_seq)` | `security_id` | 证券×交易日×版本 |
| `fundamental_observation` | `(company_id, metric_name, fiscal_period_end, fiscal_period_type, available_at)` | `company_id` | 公司×指标×报告期×发布版本 |
| `estimate_observation` | `(company_id, estimate_metric, forecast_period_end, as_of_date)` | `company_id` | 公司×预测指标×预测期×快照日 |
| `product_master` | `product_id` | `company_id` | 产品/开发者生态实体 |
| `product_observation` | `(product_id, metric_name, observation_end, geo_code, available_at)` | `product_id` | 产品×指标×观察期×地域×发布版本 |
| `ai_entity_master` | `ai_entity_id` | `company_id`, `product_id` | 模型/API/代码库/组织 |
| `ai_metric_observation` | `(ai_entity_id, metric_name, observation_end, available_at)` | `ai_entity_id` | AI 实体×指标×观察期×发布版本 |
| `valuation_observation` | `(security_id, metric_name, trade_date, denominator_period, available_at)` | `security_id` | 证券×估值指标×交易日×版本 |
| `supply_chain_relationship` | `relationship_id` | 两端 `company_id` | 有效期内的公司关系 |
| `event_observation` | `event_id` | — | 一项去重事件 |
| `event_company_map` | `(event_id, company_id, impact_role)` | 事件、公司 | 事件与公司的多对多映射 |
| `feature_store` | `(security_id, feature_date, feature_name, feature_version)` | `security_id`, `lineage_run_id` | 证券×决策日×特征版本 |
| `targets` | `(security_id, target_date, target_version)` | `security_id`, `lineage_run_id`, `benchmark_id` | 证券×信号日×标签版本 |
| `research_run` | `run_id` | — | 一次可复现计算任务 |

## 3. 时间语义

系统明确区分六类时间；事件层的三个时钟不得相互替代：

| 时间 | 含义 | 示例 |
|---|---|---|
| `period_end` / `observation_end` | 经济事实或测量窗口结束 | 2025Q4 财务期末、某周产品访问量周末 |
| `brief_date` | 晨报所属的上海日期 | 2026-09-06 早间简报 |
| `event_date` | 被描述事件实际发生的日期 | 模型于 2026-09-03 正式发布 |
| `source_published_at` | 原始来源自己的发布时间，保留时区 | Reuters 于 2026-09-05T22:10:00Z 发布报道 |
| `available_at` / `as_of_date` | 市场参与者能够获得该数据的最早时间 | 供应商次周一发布上周流量 |
| `feature_date` | 研究者准备形成仓位的决策交易日 | 周一收盘形成信号 |

Point-in-time 查询必须满足：

```sql
source.available_at <= decision_cutoff_at
```

晨报生成时间、页面更新时间、抓取时间和 sitemap `lastmod` 只能用于运行审计，禁止写入 `event_date` 或 `source_published_at`。事件同时保存 `source_type`（`official` / `media`）和不可变的原始 `source_url`。

对同一个自然键，只选择截止时点前 `available_at` 最大的版本。不得根据 `period_end` 直接向日频面板 forward fill。

### 缺少精确发布时间时的保守规则

- 只有发布日期：按来源当地时间当日收盘后可得，进入下一交易日信号。
- 只有月份：按月末后第一个交易日可得，且标记低时间精度。
- 供应商发生历史回填：新增版本并保留原始 `available_at` 与本次 `ingested_at`；回测默认只能看到当时真实发布版本。
- 财务重述：原披露值不删除，重述值以新的 `available_at` 追加。

## 4. Feature Store 规则

`feature_store` 使用长表，避免 MVP 阶段频繁修改宽表结构。研究任务需要矩阵时，再按 `feature_name` pivot。

每项特征必须带有：

- `feature_version`：公式、窗口、标准化和缺失值规则的版本；
- `source_max_available_at`：参与计算的最晚源数据时间；
- `lineage_run_id`：生成任务及代码版本；
- `feature_date`：该特征真正可用于决策的交易日。

验收约束：

```text
source_max_available_at <= research_run.data_cutoff_at
source_max_available_at <= feature decision cutoff
```

Raw variables 先进入原始观察表。诸如 AI 货币化指数、Capex 转化率、Developer Adoption Composite 只作为 versioned candidate features，不能反写原始层。

## 5. Targets 规则

### 收益起点

v1 默认采用“信号可得后的下一个可交易收盘价”为起点，避免使用形成信号时已经无法成交的价格。具体起止规则记录在 `target_version` 中，例如：

```text
close_to_close_next_session_v1
```

### 标签集合

- 原始总收益：`ret_1d`, `ret_5d`, `ret_20d`, `ret_60d`；
- 基准超额收益：`excess_return_20d`, `excess_return_60d`；
- 行业中性残差收益：`industry_neutral_return_20d`, `industry_neutral_return_60d`；
- 风险标签：`future_vol_20d`, `future_max_drawdown_20d`。

标签仅在完整未来窗口存在后写入；样本末端未成熟标签保持 `NULL`，不能用零填充。

## 6. 三个 MVP 假设对应的数据路径

### H1：产品/开发者采用领先盈利预测修正

```text
product_observation + ai_metric_observation
    → PIT growth / acceleration / breadth features
    → estimate_observation revision over 20D/60D
    → targets excess_return_20d / 60d
```

控制变量：市值、行业、过去收益、估值、供应商覆盖率变化。

### H2：AI Capex 转化效率

```text
fundamental_observation(capex, revenue, fcf)
    + AI-specific disclosure / ai_metric_observation
    → lagged capex growth and forward revenue/FCF conversion candidates
    → cross-sectional rank and future 60D return
```

必须区分总 Capex 与明确披露的 AI Capex；无法可靠拆分时保留估计标记与置信度，不把估算值伪装成披露值。

### H3：基本面改善 + EPS 上调 + 估值不过热

```text
fundamental_observation
    + estimate_observation
    + valuation_observation
    + market_daily controls
    → candidate composite / conditional sorts
    → industry_neutral_return_20d / 60d
```

先检验 raw features 的 IC、Rank IC、分组收益、long-short return、turnover、drawdown 和不同市场状态稳定性，再决定组合形式。

## 7. MVP 数据接入顺序

| 顺序 | 数据层 | 最小接入内容 |
|---|---|---|
| 1 | Master + Market + Targets | 证券映射、调整价格、20D/60D 收益和中性化标签 |
| 2 | Estimates | Revenue/EPS/Capex/FCF 的历史快照与修正 |
| 3 | Product + AI Metrics | 访问量、MAU/下载量、GitHub/Hugging Face、API 价格和模型采用指标 |
| 4 | Fundamental | Revenue、FCF、Capex、Margins、AI 收入披露 |
| 5 | Valuation | Forward PE、EV/Sales、FCF Yield及历史分位候选特征 |
| 6 | Feature Store | 三个假设需要的最少特征，附 lineage |
| 7 | Supply Chain + Events | 仅先做实体映射和接口，不在三天内追求全覆盖 |

## 8. 质量检查

每次构建至少执行：

1. 主键重复检查；
2. `available_at` 缺失率与晚于采集时间异常检查；
3. 原始数据版本是否被覆盖检查；
4. 单位、币种和拆股调整一致性检查；
5. 产品供应商覆盖率断点检查；
6. Feature lineage 完整性检查；
7. `source_max_available_at` 穿越检查；
8. Target horizon 完整性及交易日历检查；
9. 横截面 winsorization/neutralization 仅在当日样本内拟合检查；
10. 幸存者偏差检查：退市、改名和历史成分必须保留。

## 9. 非目标

v1 不预设最终因子权重，不把供应商回填历史视为实时可得历史，不承诺从 15–25 家公司的小样本直接训练复杂机器学习模型，也不将网页展示结构耦合到底层存储结构。
# Runtime implementation

The v1 logical schema is materialized locally in `data/warehouse/ai_alpha_research.duckdb`. `scripts/build_warehouse.py` loads the current standardized and research tables and adds `raw_manifest`, `data_asset_registry`, `ingestion_log`, `quality_exceptions`, and `factor_results` for provenance and auditability. PostgreSQL DDL below remains the production-target schema; DuckDB is the three-day MVP research runtime.
