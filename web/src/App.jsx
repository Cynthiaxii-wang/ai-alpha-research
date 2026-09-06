'use client'

import { useEffect, useMemo, useState } from 'react'
import DemandChain from './DemandChain'

const NAV = [
  ['overview', 'Overview', '01'],
  ['value-chain', 'AI Value Chain', '02'],
  ['signals', 'Signal Monitor', '03'],
  ['factors', 'Factor Lab', '04'],
  ['demand-chain', 'AI 需求兑现链', '05'],
]

const BUCKET_NAMES = {
  compute: 'Compute', semiconductor_networking: 'Semis & Networking', foundry: 'Foundry',
  memory: 'Memory', networking: 'Networking', cloud_platform: 'Cloud Platform',
  cloud_model_platform: 'Cloud & Models', model_application: 'Models & Applications',
  enterprise_application: 'Enterprise Applications', data_platform: 'Data Platform',
  developer_infrastructure: 'Developer Infrastructure',
}

const STAGE_NAMES = {upstream:'上游基础设施', midstream:'中游平台与模型', downstream:'下游应用与变现'}
const SEGMENT_NAMES = {
  ai_compute:'AI 计算芯片', custom_silicon_networking:'定制芯片与网络', foundry:'晶圆代工', memory:'存储与 HBM',
  data_center_networking:'数据中心网络', cloud_platform:'云计算平台', cloud_model_platform:'云与模型平台',
  foundation_models:'基础模型', model_labs:'非上市模型实验室', data_platform:'数据平台',
  developer_infrastructure:'开发与推理基础设施', enterprise_ai_applications:'企业 AI 应用',
  creative_productivity_apps:'创意与生产力应用',
}

const pct = (value, digits = 1) => value == null ? '—' : `${(value * 100).toFixed(digits)}%`
const ppt = (value, digits = 1) => value == null ? '—' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)}ppt`
const num = (value, digits = 1) => value == null ? '—' : Number(value).toFixed(digits)
const compact = (value) => value == null ? '—' : Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
const tone = (value) => value == null ? '' : value > 0 ? 'positive' : value < 0 ? 'negative' : ''
const dateTimeCN = value => value ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value)) : '—'
const epsSurprise = value => value == null ? '—' : Math.abs(value) > 100 ? `${value > 0 ? '>+100' : '<-100'}%*` : `${num(value)}%`
const median = values => { const clean = values.filter(value => value != null).sort((a,b) => a-b); if (!clean.length) return null; const m = Math.floor(clean.length / 2); return clean.length % 2 ? clean[m] : (clean[m-1] + clean[m]) / 2 }
const trendLabel = value => value === 'Accelerating' ? '加速 ↑' : value === 'Decelerating' ? '放缓 ↓' : '稳定 →'
const eventSource = event => {
  const type = event.sourceType || (event.sourceTier === 'B' ? 'media' : 'official')
  return {type, label: type === 'media' ? 'Media Source' : 'Official Source', linkLabel: type === 'media' ? '查看媒体原文 ↗' : '查看官方原文 ↗'}
}

function LineChart({ rows }) {
  if (!rows?.length) return <div className="empty-chart">No price history</div>
  const width = 760, height = 260, pad = 18
  const values = rows.flatMap(row => [row.stock, row.benchmark]).filter(value => value != null)
  const min = Math.min(...values), max = Math.max(...values)
  const x = index => pad + index * (width - pad * 2) / Math.max(rows.length - 1, 1)
  const y = value => height - pad - (value - min) * (height - pad * 2) / Math.max(max - min, 1)
  const path = key => rows.map((row, index) => `${index ? 'L' : 'M'}${x(index)},${y(row[key])}`).join(' ')
  return <div className="chart-wrap">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Normalized price performance">
      {[0, .25, .5, .75, 1].map(mark => <line key={mark} x1={pad} x2={width-pad} y1={pad + mark*(height-pad*2)} y2={pad + mark*(height-pad*2)} className="grid-line" />)}
      <path d={path('benchmark')} className="line benchmark" />
      <path d={path('stock')} className="line stock" />
    </svg>
    <div className="chart-legend"><span><i className="dot stock-dot"/>Selected company</span><span><i className="dot benchmark-dot"/>QQQ</span><span>Indexed to 100</span></div>
  </div>
}

function Metric({ label, value, hint, className = '' }) {
  return <div className={`metric ${className}`}><span>{label}</span><strong>{value}</strong>{hint && <small>{hint}</small>}</div>
}

function SignalPill({ label }) {
  const className = label?.toLowerCase().replaceAll(' ', '-') || 'n-a'
  return <span className={`signal-pill ${className}`}>{label || 'N/A'}</span>
}

function SignalChangePill({ label }) {
  const className = label?.toLowerCase() || 'baseline'
  const copy = {NEW:'NEW', Strengthening:'↑ 增强', Weakening:'↓ 减弱', Exited:'已退出', Unchanged:'→ 稳定', Baseline:'基准建立'}
  return <span className={`signal-change ${className}`}>{copy[label] || label}</span>
}

function PercentileBar({ label, value, reverse = false }) {
  return <div className="percentile-row"><div><span>{label}</span><b>{value == null ? '—' : `${Math.round(value * 100)}th`}</b></div><div className="percentile-track"><i className={reverse ? 'reverse' : ''} style={{width: `${Math.max(2, (value || 0) * 100)}%`}}/></div></div>
}

function Overview({ data, openCompany }) {
  const q = data.quality
  const h1 = data.hypotheses.H1_developer_adoption_to_earnings
  const h2 = data.hypotheses.H2_capex_conversion
  const h3 = data.hypotheses.H3_fundamental_surprise_valuation
  const events = data.dailyBrief.events || []
  const topEvent = events[0]
  const excessReturns = data.companies.map(company => company.excess20d).filter(value => value != null).sort((a,b) => a-b)
  const medianExcess = excessReturns.length ? (excessReturns[Math.floor((excessReturns.length - 1) / 2)] + excessReturns[Math.ceil((excessReturns.length - 1) / 2)]) / 2 : null
  const outperformers = excessReturns.filter(value => value > 0).length
  const qqq20d = data.companies.find(company => company.benchmarkMomentum20d != null)?.benchmarkMomentum20d
  const firstQueue = data.researchQueue[0]
  return <>
    <section className={`hero-grid ${topEvent ? '' : 'no-brief'}`}>
      <div className="hero-copy">
        <span className="eyebrow">DAILY MARKET SNAPSHOT</span>
        <div className="snapshot-title"><h2>市场与研究概览</h2><span>{data.marketAsOfDate}</span></div>
        <div className="snapshot-grid">
          <Metric label="纳斯达克100基准（QQQ）" value={pct(qqq20d)} hint="过去 20 个交易日" className={tone(qqq20d)}/>
          <Metric label="跑赢基准的公司" value={`${outperformers} / ${excessReturns.length}`} hint="AI 样本公司"/>
          <Metric label="中位超额收益" value={pct(medianExcess)} className={tone(medianExcess)}/>
          <Metric label="今日事件" value={events.length} hint="已核验重要事件"/>
        </div>
        {firstQueue && <button className="snapshot-focus" onClick={() => openCompany(firstQueue.ticker)}><span>首要研究对象</span><b>{firstQueue.ticker}</b><p>{firstQueue.setup}</p><strong className={tone(firstQueue.excess20d)}>{pct(firstQueue.excess20d)} vs QQQ</strong><i>↗</i></button>}
      </div>
      {topEvent && <article className="brief-card">
        <div className="card-kicker"><span>今日核心事件</span><span className="status-tag"><b className={`source-type source-${eventSource(topEvent).type}`}>{eventSource(topEvent).label}</b>{topEvent.sourceName} · {topEvent.event_date}</span></div>
        <h3>{topEvent.headline}</h3>
        <p className="brief-summary">{topEvent.summary}</p>
        <div className="brief-insight"><span>投资含义</span><p>{topEvent.whatChanged}</p></div>
        <div className="brief-footer">
          <div><span>关联公司</span><div className="brief-tickers">{topEvent.affectedCompanies.map(ticker => <b key={ticker}>{ticker}</b>)}</div></div>
          <a href={topEvent.sourceUrl} target="_blank" rel="noreferrer" title={topEvent.sourceUrl}>{eventSource(topEvent).linkLabel}</a>
        </div>
      </article>}
    </section>

    <section className="metrics-grid">
      <Metric label="Research universe" value={data.companies.length} hint="AI value-chain companies" />
      <Metric label="Feature table rows" value={compact(q.row_counts.feature_store)} hint="Standardized research rows" />
      <Metric label="20D forward labels" value={compact(q.mature_targets['20d'])} hint="Benchmark-relative targets" />
      <Metric label="Feature timing violations" value={q.feature_available_date_violations} hint="Engineering timing check" className="accent-metric" />
    </section>

    {data.alternativePulse?.length > 0 && <section className="alt-section">
      <div className="panel-head alt-heading"><div><span className="eyebrow">AI-NATIVE ALTERNATIVE DATA</span><h2>另类数据脉冲</h2></div><span className="subtle">来自 AI 跟踪工作簿 · 仅用截止日前可得快照</span></div>
      <div className="alt-grid">{data.alternativePulse.map(item => <article className="alt-card" key={item.id}>
        <div className="alt-top"><span>{item.eyebrow}</span><b className={`quality-${item.qualityTone}`}>{item.quality}</b></div>
        <h3>{item.title}</h3>
        <div className="alt-value"><strong>{item.value}</strong>{item.change != null && <span className={tone(item.change)}>{item.changeLabel} {pct(item.change)}</span>}</div>
        <p>{item.note}</p><footer>AS OF {item.asOf}</footer>
      </article>)}</div>
      <p className="alt-disclaimer">历史回测采用已核验 available_at 的观测；其余序列用于当期市场监测。</p>
    </section>}

    {events.length > 1 && <section className="event-section">
      <div className="panel-head event-heading"><div><span className="eyebrow">TRACEABLE EVENT INTELLIGENCE</span><h2>今日 AI 产业重要事件</h2></div><span className="subtle">Official Source / Media Source · 按重要性排序</span></div>
      <div className="event-grid">{events.map((event, index) => <article className="event-card" key={event.id}>
        <div className="event-top"><span className="event-rank">0{index + 1}</span><span className={`event-tier source-${eventSource(event).type}`}>{eventSource(event).label}</span></div>
        <h3>{event.headline}</h3><p className="event-summary">{event.summary}</p>
        <div className="event-impact"><span>传导逻辑</span><p>{event.whatChanged}</p></div>
        <div className="ticker-tags">{event.affectedCompanies.slice(0, 6).map(ticker => <span key={ticker}>{ticker}</span>)}</div>
        <div className="event-footer"><span>事件 {event.event_date} · 来源发布 {dateTimeCN(event.source_published_at)}</span><a href={event.sourceUrl} target="_blank" rel="noreferrer" title={event.sourceUrl}>{event.sourceName} ↗</a></div>
      </article>)}</div>
    </section>}

    <section className="two-column">
      <div className="panel queue-panel">
        <div className="panel-head"><div><span className="eyebrow">ACTIONABLE RESEARCH QUEUE</span><h2>今天先看什么</h2></div><span className="subtle">按横截面信号排序</span></div>
        <div className="queue-list">{data.researchQueue.map((item, index) => <button className="queue-row" key={item.ticker} onClick={() => openCompany(item.ticker)}>
          <span className="queue-index">0{index + 1}</span><div className="queue-company"><b>{item.ticker}</b><small>{item.name}</small></div>
          <div className="queue-thesis"><SignalPill label={item.setup}/><p>{item.reason}</p></div>
          <strong className={tone(item.excess20d)}>{pct(item.excess20d)}<small>vs QQQ</small></strong><span className="open-arrow">↗</span>
        </button>)}</div>
      </div>
      <div className="panel dark-panel">
        <div className="panel-head"><div><span className="eyebrow">RESEARCH STATUS</span><h2>What the evidence says</h2></div></div>
        <div className="finding"><span>H1</span><div><b>Developer activity → Earnings</b><p>{h1.sample_size} observations · selected-repository activity</p></div><strong>IC {num(h1.rank_ic_activity_change_vs_next_earnings_surprise, 2)}</strong></div>
        <div className="finding"><span>H2</span><div><b>Capex growth → Conversion</b><p>{h2.sample_size} observations · quarterly revenue conversion</p></div><strong>IC {num(h2.lead_lag?.['+1Q_revenue']?.rank_ic, 2)}</strong></div>
        <div className="finding"><span>H3</span><div><b>Fundamentals + Surprise + Valuation</b><p>20D and 60D benchmark-relative returns</p></div><strong>IC {num(h3.rank_ic_20d, 2)}</strong></div>
      </div>
    </section>
  </>
}

function ValueChain({ data, openCompany }) {
  const companies = data.companies
  const privateEntities = data.privateEntities || []
  const stageMap = Object.fromEntries((data.stageSummaries || []).map(item => [item.stage, item]))
  const segmentMap = Object.fromEntries((data.segmentSummaries || []).map(item => [`${item.stage}:${item.segment}`, item]))
  const setupOrder = {'Fundamental dislocation':0, 'Expectation risk':1, 'Deteriorating':2, 'Momentum':3, 'Data gap':4}
  const stageOrder = ['upstream','midstream','downstream']
  const segmentOrder = {
    upstream:['foundry','memory','ai_compute','custom_silicon_networking','data_center_networking'],
    midstream:['cloud_platform','cloud_model_platform','model_labs','foundation_models','data_platform','developer_infrastructure'],
    downstream:['enterprise_ai_applications','creative_productivity_apps'],
  }
  return <section>
    <div className="page-title tech-title"><span className="eyebrow">SUPPLY × PLATFORM × MONETIZATION</span><h1>AI Value Chain</h1><p>沿上游基础设施、中游平台与模型、下游应用追踪景气传导，并在同环节识别基本面与定价错位。</p></div>
    <div className="chain-direction"><span>资本与供给传导</span><b>上游 → 中游 → 下游</b><i/><span>需求验证反向传导</span><b>下游 → 中游 → 上游</b></div>
    <div className="stage-overview">{stageOrder.map((stage,index) => { const summary=stageMap[stage] || {}; return <article className={`stage-summary stage-${stage}`} key={stage}>
      <div className="stage-number">0{index+1}</div><div><span>{STAGE_NAMES[stage]}</span><p>{summary.description}</p></div><b className={`trend-${summary.trend?.toLowerCase()}`}>{trendLabel(summary.trend)}</b>
      <dl><div><dt>公司</dt><dd>{summary.companyCount || 0}</dd></div><div><dt>基本面中位分</dt><dd>{summary.medianFundamentalScore == null ? '—' : Math.round(summary.medianFundamentalScore)}</dd></div><div><dt>20D 超额</dt><dd className={tone(summary.medianExcess20d)}>{pct(summary.medianExcess20d)}</dd></div><div><dt>错位机会</dt><dd>{summary.opportunityCount || 0}</dd></div></dl>
    </article>})}</div>
    <div className="value-chain-stack">{stageOrder.map(stage => <section className={`value-stage value-stage-${stage}`} key={stage}>
      <div className="value-stage-head"><div><span className="eyebrow">{stage.toUpperCase()}</span><h2>{STAGE_NAMES[stage]}</h2></div><p>{stageMap[stage]?.description}</p></div>
      <div className="segment-grid">{segmentOrder[stage].map(segment => {
        const rows=companies.filter(company => company.primaryStage===stage && company.secondarySegment===segment)
        const privateRows=privateEntities.filter(entity => entity.primaryStage===stage && entity.secondarySegment===segment)
        if (!rows.length && !privateRows.length) return null
        const summary=segmentMap[`${stage}:${segment}`]
        return <article className="segment-card" key={segment}>
          <div className="segment-head"><div><span>{SEGMENT_NAMES[segment] || segment}</span><small>{rows.length} 上市 · {privateRows.length} 非上市</small></div>{summary && <b className={`trend-${summary.trend?.toLowerCase()}`}>{trendLabel(summary.trend)}</b>}</div>
          {summary && <div className="segment-stats"><span>{summary.coreKpiLabel}<b>{pct(summary.medianCoreKpi)}</b></span><span>20D vs QQQ<b className={tone(summary.medianExcess20d)}>{pct(summary.medianExcess20d)}</b></span></div>}
          {[...rows].sort((a,b) => setupOrder[a.researchSetup] - setupOrder[b.researchSetup] || Math.abs(b.fundamentalPriceGap || 0) - Math.abs(a.fundamentalPriceGap || 0)).map(company => <button className={`company-card setup-${company.researchSetup.toLowerCase().replaceAll(' ','-')}`} key={company.ticker} onClick={() => openCompany(company.ticker)}>
            <div className="company-monogram">{company.ticker.slice(0,2)}</div><div className="company-card-body"><div className="company-name"><b>{company.ticker}</b><span>{company.name}</span></div><div className="company-fundamental"><span>{company.coreKpiLabel}</span><b className={tone(company.coreKpiValue)}>{pct(company.coreKpiValue)}</b><small>{company.valuationLabel}</small></div><SignalPill label={company.researchSetup}/></div><div className="company-return"><strong className={tone(company.excess20d)}>{pct(company.excess20d)}</strong><small>20D EXCESS</small></div>
          </button>)}
          {privateRows.map(entity => <div className="private-node" key={entity.id}><div className="company-monogram">{entity.name.slice(0,2).toUpperCase()}</div><div><div><b>{entity.name}</b><span>PRIVATE</span></div><p>{entity.focus}</p><small>关联上市公司：{entity.linkedPublicCompanies.join(' / ')}</small></div><strong>{entity.productSignal ? `#${entity.productSignal}` : entity.productSignalBucket || '—'}<small>{entity.productSignalLabel}</small></strong></div>)}
        </article>
      })}</div>
    </section>)}</div>
    <section className="transmission-section"><div className="panel-head"><div><span className="eyebrow">LEAD–LAG EVIDENCE</span><h2>产业链传导检验</h2></div><span className="subtle">季度 Rank correlation · 同期 / +1Q / +2Q</span></div><div className="transmission-grid">{(data.transmissionTests || []).map(test => <article key={test.id}><div><span>{test.path}</span><b className={`verdict verdict-${test.verdict.toLowerCase().replaceAll(' ','-')}`}>{test.verdict}</b></div><p>{test.conclusion}</p><div>{test.leadLag.map(item => <span key={item.label}><small>{item.label}</small><b className={tone(item.value)}>{num(item.value,2)}</b></span>)}</div><footer>样本 {test.sampleSize ?? '—'}</footer></article>)}</div></section>
  </section>
}

function Signals({ companies, openCompany }) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All')
  const [stage, setStage] = useState('All')
  const categories = ['All', 'Opportunity', 'Momentum', 'Risk', 'Watch']
  const categoryNames = {All:'全部', Opportunity:'机会', Momentum:'动量', Risk:'风险', Watch:'观察'}
  const filtered = companies.filter(c => `${c.ticker} ${c.name} ${c.bucket} ${c.primaryStage} ${c.secondarySegment}`.toLowerCase().includes(query.toLowerCase()) && (category === 'All' || c.actionCategory === category) && (stage === 'All' || c.primaryStage === stage)).sort((a,b) => Math.abs(b.fundamentalPriceGap ?? -1) - Math.abs(a.fundamentalPriceGap ?? -1))
  const opportunityCount = companies.filter(c => c.actionCategory === 'Opportunity').length
  const riskCount = companies.filter(c => c.actionCategory === 'Risk').length
  const changedCount = companies.filter(c => ['NEW','Strengthening','Weakening','Exited'].includes(c.signalChange)).length
  return <section>
    <div className="page-title row-title tech-title"><div><span className="eyebrow">CHANGE & DISLOCATION</span><h1>Signal Monitor</h1><p>寻找基本面变化、市场定价与估值之间的背离，回答今天哪家公司最值得研究。</p></div><input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索公司、代码或产业链" /></div>
    <div className="signal-summary"><Metric label="机会信号" value={opportunityCount} hint="基本面领先价格"/><Metric label="风险信号" value={riskCount} hint="价格领先基本面"/><Metric label="本次状态变化" value={changedCount} hint="NEW / 增强 / 减弱 / 退出"/></div>
    <div className="signal-filters"><div className="filter-strip">{categories.map(item => <button key={item} className={category === item ? 'active' : ''} onClick={() => setCategory(item)}>{categoryNames[item]}</button>)}</div><div className="filter-strip stage-filter">{['All','upstream','midstream','downstream'].map(item => <button key={item} className={stage === item ? 'active' : ''} onClick={() => setStage(item)}>{item === 'All' ? '全产业链' : STAGE_NAMES[item]}</button>)}</div></div>
    <div className="table-panel signal-table">
      <table><thead><tr><th>Rank</th><th>Company</th><th>产业链同组</th><th>Signal</th><th>Signal Δ</th><th>20D Excess</th><th>Rev YoY / Accel</th><th>EPS Rev 30D</th><th>FCF Δ</th><th>Valuation %ile</th><th>同层 Gap</th></tr></thead>
      <tbody>{filtered.map((company, index) => <tr key={company.ticker} onClick={() => openCompany(company.ticker)}>
        <td className="rank-cell">{String(index + 1).padStart(2,'0')}</td>
        <td><b>{company.ticker}</b><small>{company.name}</small></td>
        <td><b>{STAGE_NAMES[company.primaryStage]}</b><small>{SEGMENT_NAMES[company.secondarySegment] || company.secondarySegment}</small></td>
        <td><SignalPill label={company.researchSetup}/><small className="action-label">{categoryNames[company.actionCategory]}</small></td>
        <td><SignalChangePill label={company.signalChange}/></td>
        <td className={tone(company.excess20d)}><b>{pct(company.excess20d)}</b><small>vs QQQ</small></td>
        <td><b className={tone(company.revenueYoY)}>{pct(company.revenueYoY)}</b><small className={tone(company.revenueAcceleration)}>{ppt(company.revenueAcceleration)}</small></td>
        <td>{company.epsRevision30d == null ? <span className="data-pending">待接入</span> : <b className={tone(company.epsRevision30d)}>{pct(company.epsRevision30d, 2)}</b>}</td>
        <td><b className={tone(company.fcfMarginDelta)}>{ppt(company.fcfMarginDelta)}</b><small>margin</small></td>
        <td><b>{company.valuationHistoryPercentile == null ? '—' : `${Math.round(company.valuationHistoryPercentile*100)}%`}</b><small>自身历史</small></td>
        <td><b className={`gap-score ${tone(company.fundamentalPriceGap)}`}>{company.fundamentalPriceGap == null ? '—' : `${company.fundamentalPriceGap > 0 ? '+' : ''}${company.fundamentalPriceGap}`}</b><small>全链 {company.crossChainGap == null ? '—' : `${company.crossChainGap > 0 ? '+' : ''}${company.crossChainGap}`}</small></td>
      </tr>)}</tbody></table>
    </div>
    <p className="footnote">同层 Gap 先在上游、中游或下游内部计算基本面和市场分位，再做差；全链 Gap 仅作为跨产业链参考。正值代表基本面领先价格，负值代表价格领先基本面。估值分位越高代表当前 P/S 越接近该公司可用历史区间高位。</p>
  </section>
}

function FactorLab({ hypotheses }) {
  const [tab, setTab] = useState('return_prediction')
  const lab = hypotheses.factor_lab || {fundamental_prediction:[], return_prediction:[]}
  const cards = lab[tab] || []
  const metricText = (key, value) => value == null ? '—' : key === 'sample_size' ? Math.round(value) : key === 'rank_ic' ? num(value, 3) : pct(value)
  const metricNames = {rank_ic:'Rank IC', ic_stability:'IC Stability', hit_rate:'Hit Rate', sample_size:'Sample Size', top_bottom_spread:'Top–Bottom'}
  return <section>
    <div className="page-title tech-title"><span className="eyebrow">EVIDENCE, NOT JUST METRICS</span><h1>Factor Lab</h1><p>验证另类数据能否领先基本面，以及公司级错位能否预测未来超额收益。</p></div>
    <div className="factor-tabs"><button className={tab === 'fundamental_prediction' ? 'active' : ''} onClick={() => setTab('fundamental_prediction')}><b>Fundamental Prediction</b><span>替代数据 → Revenue / FCF / EPS</span></button><button className={tab === 'return_prediction' ? 'active' : ''} onClick={() => setTab('return_prediction')}><b>Return Prediction</b><span>研究信号 → Forward Excess Return</span></button></div>
    <div className="factor-lab-grid">{cards.map((card, cardIndex) => {
      const primary = card.horizons?.['20'] || card.metrics || {}
      const groups = primary.group_returns || card.group_returns || []
      const maxGroup = Math.max(...groups.filter(value => value != null).map(value => Math.abs(value)), .01)
      return <article className={`factor-experiment ${cardIndex === 0 ? 'featured' : ''}`} key={card.experiment_id}>
        <div className="factor-exp-head"><div><span className="experiment-id">{card.experiment_id}</span><span className="factor-kind">{card.category}</span></div><span className={`verdict verdict-${card.verdict.toLowerCase().replaceAll(' ','-')}`}>{card.verdict}</span></div>
        <h2>{card.name}</h2><p className="human-conclusion">{card.conclusion}</p>
        <div className="factor-stat-grid">{Object.entries(metricNames).map(([key,label]) => <div key={key}><span>{label}</span><b className={key !== 'sample_size' ? tone(primary[key]) : ''}>{metricText(key, primary[key])}</b></div>)}</div>
        {card.horizons && <div className="horizon-strip">{['20','60','120'].map(horizon => { const item=card.horizons[horizon]; return <div key={horizon}><span>{horizon}D FORWARD</span><b className={tone(item?.top_quintile_return)}>{pct(item?.top_quintile_return)}</b><small>Top group · IC {num(item?.rank_ic,3)}</small></div>})}</div>}
        {groups.length > 0 && <div className="factor-chart"><div className="factor-subhead"><b>Factor Score 分组收益</b><span>Q5 − Q1 {pct(primary.top_bottom_spread)}</span></div><div className="quintile-chart">{groups.map((value,index) => <div key={index}><span className="bar-space"><i className={tone(value)} style={{height:`${Math.max(5, Math.abs(value || 0)/maxGroup*64)}px`}}/></span><b>Q{index+1}</b><small className={tone(value)}>{pct(value)}</small></div>)}</div></div>}
        {card.ic_time_series?.length > 0 && <div className="factor-chart"><div className="factor-subhead"><b>季度 IC 稳定性</b><span>按20D检验</span></div><div className="ic-series">{card.ic_time_series.map(item => <div key={item.period}><span>{item.period}</span><i><b className={tone(item.value)} style={{width:`${Math.min(100,Math.abs(item.value||0)*180)}%`}}/></i><strong className={tone(item.value)}>{num(item.value,2)}</strong></div>)}</div></div>}
        {card.lead_lag?.length > 0 && <div className="lead-lag"><div className="factor-subhead"><b>Lead–Lag Test</b><span>领先窗口比较</span></div>{card.lead_lag.map(item => <div key={item.label}><span>{item.label}</span><b className={tone(item.value)}>{num(item.value,3)}</b></div>)}</div>}
        {card.monitoring_metrics?.length > 0 && <div className="monitoring-evidence"><div className="factor-subhead"><b>当前数据覆盖</b><span>只展示已取得的数据</span></div><div>{card.monitoring_metrics.map(item => <span key={item.label}><small>{item.label}</small><b>{item.value}</b></span>)}</div></div>}
        {!groups.length && !card.ic_time_series?.length && !card.lead_lag?.length && !card.monitoring_metrics?.length && <div className="evidence-empty"><b>{card.verdict === 'Needs Data' ? '等待历史数据' : '当前仅有汇总检验'}</b><span>{card.next_action}</span></div>}
        {(groups.length > 0 || card.ic_time_series?.length > 0 || card.lead_lag?.length > 0 || card.monitoring_metrics?.length > 0) && <div className="next-action"><span>NEXT ACTION</span><p>{card.next_action}</p></div>}
        <details><summary>研究口径</summary><p>{card.method}</p></details>
      </article>
    })}</div>
  </section>
}

function Methodology({ quality, data }) {
  const stages = [
    ['01','原始数据','保存 API 原始返回，记录来源与抓取时间'],
    ['02','标准化数据','统一公司代码、日期、频率与字段口径'],
    ['03','特征与目标','计算当时可用的信号 X 与未来收益 Y'],
    ['04','历史检验','检验 IC、分组收益、超额收益与转化效率'],
    ['05','研究输出','生成公司筛选、因子结果与后续研究任务'],
  ]
  return <section>
    <div className="page-title tech-title"><span className="eyebrow">DATA & METHODOLOGY</span><h1>数据与研究方法</h1><p>这一页说明数据从哪里来、如何加工，以及最终如何形成研究结果。</p></div>
    <div className="pipeline">{stages.map((stage,index) => <div className="stage" key={stage[0]}><span>{stage[0]}</span><b>{stage[1]}</b><p>{stage[2]}</p>{index < stages.length-1 && <i/>}</div>)}</div>
    <div className="source-section simple-source"><div className="panel-head"><div><span className="eyebrow">DATA SOURCES</span><h2>数据来源与用途</h2></div><span className="subtle">当前数据口径</span></div><div className="source-table">
      <div className="source-row source-head"><span>数据类型</span><span>来源</span><span>主要用途</span><span>当前用法</span></div>
      {data.sourceRegistry.map(source => <div className="source-row" key={source.dataset}><b>{source.dataset}</b><span>{source.provider}</span><span>{source.use}</span><strong className={`quality-${source.tone}`}>{source.status}</strong></div>)}
    </div></div>
    <div className="method-grid">
      <div className="panel"><span className="eyebrow">DATA CHECKS</span><h2>数据检查结果</h2>
        <div className="audit-row"><span>整体检查</span><b className="positive">{quality.status.toUpperCase()}</b></div>
        <div className="audit-row"><span>重复主键</span><b>{Object.values(quality.duplicate_checks).reduce((a,b)=>a+b,0)}</b></div>
        <div className="audit-row"><span>时间可用性违规</span><b>{quality.feature_available_date_violations}</b></div>
        <div className="audit-row"><span>缺失 QQQ 超额收益</span><b>{quality.mature_20d_missing_qqq_excess}</b></div>
        <div className="audit-row"><span>行情数据截至</span><b>{data.marketAsOfDate}</b></div>
        <div className="audit-row"><span>财务数据截至</span><b>{data.fundamentalAsOfDate || '—'}</b></div>
      </div>
      <div className="panel"><span className="eyebrow">CURRENT SCOPE</span><h2>当前研究范围</h2>
        <div className="scope-grid"><Metric label="公司数量" value={data.companies.length} hint="AI 核心产业链"/><Metric label="基准" value={data.platform.benchmark}/><Metric label="未来收益" value="1D / 5D / 20D / 60D"/><Metric label="研究模块" value="3" hint="开发者、Capex、复合因子"/></div>
      </div>
    </div>
  </section>
}

function CompanyDrawer({ company, series, close }) {
  if (!company) return null
  return <div className="drawer-backdrop" onClick={close}><aside className="drawer" onClick={e => e.stopPropagation()}>
    <button className="drawer-close" onClick={close}>×</button>
    <div className="company-hero"><div className="company-monogram large">{company.ticker.slice(0,2)}</div><div><span className="eyebrow">{STAGE_NAMES[company.primaryStage]} / {SEGMENT_NAMES[company.secondarySegment] || company.secondarySegment}</span><h1>{company.ticker}</h1><p>{company.name} · {company.focus}</p></div><SignalPill label={company.researchSetup}/></div>
    <div className="setup-card why-card"><span className="eyebrow">WHY FLAGGED?</span><h2>{company.researchSetup}</h2><div className="why-metrics"><span>基本面得分<b>{company.fundamentalScore == null ? '—' : `${company.fundamentalScore}/100`}</b></span><span>定价错位 Gap<b className={tone(company.fundamentalPriceGap)}>{company.fundamentalPriceGap == null ? '—' : `${company.fundamentalPriceGap > 0 ? '+' : ''}${company.fundamentalPriceGap}`}</b></span><span>收入增速变化<b className={tone(company.revenueAcceleration)}>{ppt(company.revenueAcceleration)}</b></span><span>20D excess<b className={tone(company.excess20d)}>{pct(company.excess20d)}</b></span><span>自身历史估值分位<b>{company.valuationHistoryPercentile == null ? '—' : `${Math.round(company.valuationHistoryPercentile*100)}%`}</b></span></div><p className="why-conclusion"><b>结论</b>{company.flagConclusion}</p>{company.latestCatalyst && <div><b>今日催化</b><span>{company.latestCatalyst}</span></div>}</div>
    <div className="drawer-metrics"><Metric label="Close" value={`$${num(company.close, 2)}`}/><Metric label="20D vs QQQ" value={pct(company.excess20d)} className={tone(company.excess20d)}/><Metric label={company.coreKpiLabel} value={pct(company.coreKpiValue)} className={tone(company.coreKpiValue)}/><Metric label="P/S proxy" value={num(company.priceToSales)}/></div>
    <div className="drawer-section chain-position"><div className="panel-head"><div><span className="eyebrow">VALUE-CHAIN POSITION</span><h2>产业链角色与传导关系</h2></div><span className="subtle">主环节 + 次要暴露</span></div><div className="chain-position-grid"><span>主要环节<b>{STAGE_NAMES[company.primaryStage]}</b></span><span>细分环节<b>{SEGMENT_NAMES[company.secondarySegment] || company.secondarySegment}</b></span><span>次要暴露<b>{company.secondaryExposure || '—'}</b></span><span>上游依赖<b>{company.upstreamDependencies || '—'}</b></span><span>下游客户<b>{company.downstreamCustomers || '—'}</b></span><span>财务可用日<b>{company.fundamentalAvailableDate || '—'}</b></span></div></div>
    <div className="drawer-section percentile-panel"><div className="panel-head"><div><span className="eyebrow">WITHIN-STAGE POSITION</span><h2>同层横截面分位</h2></div><span className="subtle">同层样本 {company.peerGroupSize || '—'} 家</span></div><PercentileBar label="基本面质量" value={company.fundamentalPercentile}/><PercentileBar label="相对估值吸引力" value={company.valuationPercentile}/><PercentileBar label="20D 相对表现" value={company.marketPercentile}/></div>
    <div className="drawer-section"><div className="panel-head"><div><span className="eyebrow">RELATIVE PERFORMANCE</span><h2>Last 120 sessions</h2></div></div><LineChart rows={series}/></div>
    <div className="drawer-section signal-detail"><h2>Research snapshot</h2><div><span>FCF margin<b className={tone(company.fcfMargin)}>{pct(company.fcfMargin)}</b></span><span>Latest EPS surprise<b className={tone(company.earningsSurprisePct)}>{company.earningsSurprisePct == null ? '—' : `${num(company.earningsSurprisePct)}%`}</b></span><span>GitHub stars snapshot<b>{compact(company.githubStars)}</b></span><span>HF downloads snapshot<b>{compact(company.hfDownloads)}</b></span></div></div>
    <p className="drawer-note">研究情景由横截面规则生成，用于排序人工研究，不构成交易建议。GitHub 与 Hugging Face 数据为当前快照，未回填历史日期。</p>
  </aside></div>
}

export default function App() {
  const [data, setData] = useState(null)
  const [page, updatePage] = useState('overview')
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const [selected, setSelected] = useState(null)
  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    fetch('/data/dashboard.json', { signal: controller.signal, cache: 'no-store' })
      .then(response => {
        if (!response.ok) throw new Error(`数据加载失败（${response.status}）`)
        return response.json()
      })
      .then(setData)
      .catch(error => { if (error.name !== 'AbortError') setError('研究数据暂时无法加载，请重试。') })
    return () => controller.abort()
  }, [attempt])
  useEffect(() => {
    const syncPage = () => {
      const hash = window.location.hash.slice(1)
      updatePage(NAV.some(item => item[0] === hash) ? hash : 'overview')
    }
    syncPage()
    window.addEventListener('hashchange', syncPage)
    return () => window.removeEventListener('hashchange', syncPage)
  }, [])
  const setPage = nextPage => {
    updatePage(nextPage)
    window.location.hash = nextPage
  }
  const company = useMemo(() => data?.companies.find(item => item.ticker === selected), [data, selected])
  if (error) return <div className="loading" role="alert"><span>AIα</span><p>{error}</p><button onClick={() => setAttempt(value => value + 1)}>重新加载</button></div>
  if (!data) return <div className="loading"><span>AIα</span><p>Loading research platform</p></div>
  return <div className="app-shell">
    <aside className="sidebar">
      <button className="brand" onClick={() => setPage('overview')}><span>AIα</span><div><b>AI Alpha</b><small>RESEARCH PLATFORM</small></div></button>
      <nav>{NAV.map(([id,label,index]) => <button key={id} onClick={() => setPage(id)} className={page === id ? 'active' : ''}><span>{index}</span>{label}</button>)}</nav>
      <div className="sidebar-foot"><span className="live-dot"/><div><b>Research engine online</b><small>Framework v0.1</small></div></div>
    </aside>
    <main>
      <header><div><span>AI EQUITY INTELLIGENCE</span><b>/</b><strong>{NAV.find(item => item[0] === page)?.[1] || 'Overview'}</strong></div><div className="header-right"><span>MARKET AS OF {data.marketAsOfDate}</span></div></header>
      <div className="content">
        {page === 'overview' && <Overview data={data} openCompany={setSelected}/>} 
        {page === 'value-chain' && <ValueChain data={data} openCompany={setSelected}/>} 
        {page === 'signals' && <Signals companies={data.companies} openCompany={setSelected}/>} 
        {page === 'factors' && <FactorLab hypotheses={data.hypotheses}/>} 
        {page === 'demand-chain' && <DemandChain data={data.demandChain} openCompany={setSelected} openFactors={()=>setPage('factors')}/>}
      </div>
    </main>
    <CompanyDrawer company={company} series={data.priceSeries[selected]} close={() => setSelected(null)}/>
  </div>
}
