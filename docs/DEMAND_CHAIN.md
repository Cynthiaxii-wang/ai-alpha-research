# AI demand chain v1

新入口：AI 需求兑现链。五个可切换环节：用户采用、实际消耗、算力供需、投资扩张、商业兑现。

这是一组可追溯的观测证据，不代表已经验证五个环节之间的因果关系。当前不计算跨平台用户转化率、Token 到 GPU 小时的换算或投资回报率。

## 数据和计算

- Adoption：product_domain_rank_daily，Cloudflare Radar 域名排名或排名区间。DNS 关注度不是活跃用户数。逐产品展示最新可用观测及历史日期数量。
- Consumption：openrouter_usage_daily，同日期模型去重，含 other 长尾。最近七个完整 UTC 日 Token 总量，与前七日比较；任一比较窗口缺日则不计算变化。覆盖范围仅为 OpenRouter。
- Compute：manual_alternative_observations 中 USD_per_hour 口径的 GPU 租赁报价。30日前基准允许向前寻找最多七日；展示原始工作簿页、单元格、来源及快照可用时间。不能将租价等同于利用率。
- Investment / Monetization：fundamental_quarterly 中 MSFT、AMZN、GOOGL、ORCL 最新可用财季。展示公司总收入及 Capex 同比、两者增速差、Capex/收入、FCF率及去年同财季的FCF率差，不混合财季汇总。公司总收入不是 AI 收入。

研究观察规则：Capex 同比领先收入超过10个百分点且FCF率同比下降超过2个百分点，或收入同比为正且FCF率同比改善超过2个百分点。阈值是明确的人为观察规则，尚未验证预测能力；不是买卖评级。

## 可追溯性

正式网页导出从统一 DuckDB 读取既有表，计算模块位于 src/ai_alpha_research/demand_chain.py，输出 dashboard.json 的 demandChain 字段。保留观测日期、可用日期、来源表和适用的工作簿定位或 SEC accession。该派生模块目前不单独持久化为数据库表。

以明确的证据截止时间筛选可用记录，同自然键保留截止时间前最新版本。财务 available_date 若只有日期，按 UTC 零点解析，因此本页面仅作当前观察，不应用于财报当日的日内回测。租赁历史的工作簿可用时间不回填为历史观测日期。

## 后续研究

1. 积累同产品的采用、留存和请求量历史，明确平台覆盖范围。
2. 补 GPU 利用率、GPU小时、模型工作负载，区分价格与需求。
3. 补订单、交付和采购主体映射，连接需求与投资。
4. 补 Cloud / AI 分部收入与利润，检验4Q/8Q投入兑现。
5. 新观察规则进入 Factor Lab 做时间外检验，再考虑优化 Signal Monitor；当前按钮仅导航到既有实验页，不宣称已完成新链条的统计验证。

## 验证与运行

PYTHONPATH=src python3 -m unittest discover -s tests -p test_demand_chain.py

python3 scripts/export_web_data.py

npm --prefix web run build

导出要求 DBeaver 断开数据库连接，避免多进程锁冲突；不要删除数据库或绕过锁覆盖文件。
