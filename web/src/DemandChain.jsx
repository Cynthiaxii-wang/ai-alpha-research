import { useState } from 'react'

const pct = v => v == null ? '—' : `${(v * 100).toFixed(1)}%`
const pp = v => v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}ppt`
const count = v => v == null ? '—' : Intl.NumberFormat('en', {notation:'compact', maximumFractionDigits:2}).format(v)
const steps = [['Adoption','用户采用'],['Consumption','实际消耗'],['Compute','算力供需'],['Investment','投资扩张'],['Monetization','商业兑现']]
function Trend({rows=[]}) {
  if (rows.length < 2) return <p>单次快照，尚无趋势</p>
  const values=rows.map(r=>r.value), min=Math.min(...values), span=Math.max(...values)-min || 1
  return <div className="dc-trend"><svg viewBox="0 0 280 60" role="img" aria-label="按观测值绘制的趋势，纵轴为本序列范围"><polyline points={rows.map((r,i)=>`${4+i*272/(rows.length-1)},${54-(r.value-min)/span*48}`).join(' ')} fill="none" stroke="currentColor" strokeWidth="2"/></svg><small>{rows[0].date} — {rows.at(-1).date} · {count(min)}—{count(Math.max(...values))}</small></div>
}
function Evidence({row}) {
  const url=/^https:\/\//.test(row.url || '') ? row.url : null
  return <details className="dc-evidence"><summary>数据底稿与口径</summary><p>{row.scope}</p><p>来源：{row.source || '工作簿'} · 表：{row.table}</p><p>可用时间：{row.availableAt || '—'}</p>{row.sheet && <p>工作表：{row.sheet} · 单元格：{row.cell}</p>}{row.pitStatus && <p>历史状态：{row.pitStatus}</p>}{row.accessions && <p>SEC 申报：{row.accessions}</p>}{url && <a href={url} target="_blank" rel="noreferrer">查看来源 ↗</a>}</details>
}
export default function DemandChain({data, openCompany, openFactors}) {
  const [active,setActive]=useState('Adoption')
  if (!data) return <section className="panel">需求链数据尚未生成，请运行数据导出。</section>
  const c=data.consumption
  const captions=[`${data.adoption.length} 个产品快照`,`${pct(c.change)} · 7日变化`,`${data.compute.length} 类GPU租价`,`${data.companies.length} 家CSP`,`${data.watch.length} 项待研究变化`]
  return <section className="dc-page">
    <div className="page-title"><span className="eyebrow">AI DEMAND → COMMERCIAL RETURNS</span><h1>AI 需求兑现链</h1><p>从产品使用到资本回报，定位需求增长在哪个环节得到验证。</p><small>证据截止 {data.cutoff.slice(0,10)} · 各指标观察日期分别标注</small></div>
    <div className="dc-path">{steps.map(([id,name],i)=><button key={id} className={active===id?'active':''} onClick={()=>setActive(id)}><small>0{i+1} / {id}</small><b>{name}</b><span>{captions[i]}</span></button>)}</div>
    <div className="dc-body">
      <div className="dc-section-title"><h2>{steps.find(s=>s[0]===active)[1]}</h2><span>{active==='Monetization' ? '收入与FCF采用公司总口径' : '点击下方底稿查看来源与测量范围'}</span></div>
      {active==='Adoption' && <div className="dc-grid">{data.adoption.map(r=><article key={r.id}><span className="eyebrow">{r.name}</span><strong>{r.value!=null?`#${r.value}`:r.bucket || '—'}</strong><p>{r.value!=null?'全球域名排名':'排名区间，不是精确名次'} · {r.samples} 个日期</p><small>观察日 {r.date}</small><Evidence row={r}/></article>)}</div>}
      {active==='Consumption' && <div className="dc-consumption"><article><span className="eyebrow">OpenRouter · 最近7个完整UTC日</span><strong>{count(c.value)} Tokens</strong><p>较此前7日 {pct(c.change)} · 日期覆盖 {c.coverage}/14</p><p>长尾 other 占比 {pct(c.otherShare)}</p><small>截至 {c.date || '—'}；缺失日期不填零</small><Evidence row={c}/></article><article><h3>近28个观测日</h3><Trend rows={c.series}/><p>采用同平台数据观察变化；免费模型、模型结构及Tokenizer变化会影响总量。</p></article></div>}
      {active==='Compute' && <div className="dc-grid">{data.compute.map(r=><article key={r.id}><span className="eyebrow">{r.name} 租赁报价</span><strong>${r.value?.toFixed(2)}<small> / GPU小时</small></strong><p>约30日变化 {pct(r.change)} · 基准日 {r.baseDate || '—'}</p><Trend rows={r.series}/><small>观察日 {r.date} · 距证据截止 {r.ageDays} 天</small><Evidence row={r}/></article>)}</div>}
      {['Investment','Monetization'].includes(active) && <div className="dc-finance"><table><thead><tr><th>公司 / 财季</th><th>Capex YoY</th><th>收入 YoY</th><th>增速差</th><th>Capex/收入</th><th>FCF率</th><th>FCF率同比变化</th></tr></thead><tbody>{data.companies.map(r=><tr key={r.ticker} onClick={()=>openCompany(r.ticker)}><td><b>{r.ticker} ↗</b><small>{r.date}</small></td><td>{pct(r.capexGrowth)}</td><td>{pct(r.revenueGrowth)}</td><td>{pp(r.investmentRevenueGap)}</td><td>{pct(r.capexIntensity)}</td><td>{pct(r.fcfMargin)}</td><td>{pp(r.fcfMarginYoYDelta)}</td></tr>)}</tbody></table><p>增速差 = Capex YoY − Revenue YoY；FCF率同比变化采用去年同财季，避免将季节性误读为恶化。</p><div className="dc-grid">{data.companies.map(r=><article key={r.ticker}><b>{r.ticker} · {r.flag}</b><Evidence row={r}/></article>)}</div></div>}
    </div>
    <section className="dc-watch"><div className="dc-section-title"><h2>本期研究线索</h2><button onClick={openFactors}>进入 Factor Lab 验证 ↗</button></div>{data.watch.length?data.watch.map(w=><button key={w.ticker} onClick={()=>openCompany(w.ticker)}><b>{w.title} ↗</b><span>{w.detail} · {w.date}</span></button>):<p>当前同财季比较未触发预设观察条件。</p>}<small>观察条件：Capex增速领先收入超过10ppt且FCF率同比下降超过2ppt；或收入增长且FCF率同比改善超过2ppt。只生成研究线索。</small></section>
    <section className="dc-links"><h2>相邻环节：证据接到哪里了</h2><div className="dc-grid">{data.links.map(l=><article key={l.from}><span className="eyebrow">{l.from} → {l.to}</span><h3>{l.status}</h3><p>{l.evidence}</p><small>下一项验证：{l.next}</small></article>)}</div></section>
  </section>
}
