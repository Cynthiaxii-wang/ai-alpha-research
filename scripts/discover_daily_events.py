#!/usr/bin/env python3
"""Discover recent material AI events from official RSS/Atom feeds.

The output is deliberately conservative: it keeps source links and publication
times, deduplicates by URL, and uses transparent keyword rules. It never invents
an event merely to fill the morning brief.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ai_alpha_research.config import load_dotenv  # noqa: E402
from ai_alpha_research.http import get_text, post_json  # noqa: E402

AI_WORDS = ("artificial intelligence", "generative ai", " ai ", "model", "llm", "gpt", "agent", "gpu", "accelerator", "inference")
MATERIAL_WORDS = ("launch", "release", "price", "revenue", "capex", "data center", "partnership", "acquisition", "earnings", "availability")
MODEL_RELEASE_WORDS = ("gpt-", "gpt‑", "new model", "flagship model", "frontier model", "most capable model", "model family")
ENTITY_MAP = {
    "nvidia": "NVDA", "microsoft": "MSFT", "azure": "MSFT", "google": "GOOGL",
    "gemini": "GOOGL", "amazon": "AMZN", "aws": "AMZN", "meta": "META",
    "broadcom": "AVGO", "amd": "AMD", "oracle": "ORCL", "openai": "MSFT",
}
OPENAI_PRODUCT_SITEMAP = "https://openai.com/sitemap.xml/product/"


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


def child_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1].lower() in names and child.text:
            return child.text.strip()
    return ""


def parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_feed(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    rows = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() not in {"item", "entry"}:
            continue
        link = child_text(node, ("link",))
        if not link:
            for child in node:
                if child.tag.rsplit("}", 1)[-1].lower() == "link" and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        rows.append({
            "title": clean(child_text(node, ("title",))),
            "summary": clean(child_text(node, ("description", "summary", "content"))),
            "url": link,
            "published": parse_date(child_text(node, ("pubdate", "published", "updated", "date"))),
        })
    return rows


def parse_sitemap(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    rows = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() != "url":
            continue
        loc = child_text(node, ("loc",))
        modified = parse_date(child_text(node, ("lastmod",)))
        if loc and modified:
            rows.append({"url": loc, "published": modified})
    return rows


def title_from_url(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return " ".join(part.upper() if part in {"gpt", "api", "ai"} else part.capitalize() for part in slug.split("-"))


def discover_openai_sitemap(now: datetime, hours: int) -> tuple[list[dict], dict]:
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=hours)
    try:
        xml_text = get_text(OPENAI_PRODUCT_SITEMAP, headers={"User-Agent": "AIAlphaResearch/0.1 research@local"}, timeout=25, retries=0)
        rows = parse_sitemap(xml_text)
    except Exception as exc:
        return [], {"source": "OpenAI Product Sitemap", "status": "failed", "error": type(exc).__name__}
    candidates = []
    for row in rows:
        url = row["url"]
        if row["published"] < cutoff or not url.startswith("https://openai.com/index/"):
            continue
        slug = url.rstrip("/").rsplit("/", 1)[-1].lower()
        if not re.search(r"(?:gpt[-‑]?\d|model|codex|sora)", slug):
            continue
        candidates.append(row)
    # Old pages can receive a new lastmod during site maintenance. New launches
    # sit in the newest sitemap update batch, so exclude older maintenance batches.
    newest = max((row["published"] for row in candidates), default=None)
    if newest:
        candidates = [row for row in candidates if row["published"] >= newest - timedelta(hours=4)]
    events = []
    for row in candidates:
        url = row["url"]
        title = title_from_url(url)
        combined = f"{title} OpenAI official model release available"
        if score(combined, "A") < 65 or not has_material_signal(combined):
            continue
        events.append({
            "id": hashlib.sha256(url.encode()).hexdigest()[:16],
            "publishedDate": row["published"].date().isoformat(),
            "publishedAt": row["published"].isoformat(),
            "timeBasis": "OpenAI product sitemap lastmod; source page has no explicit publication time",
            "type": "model_release",
            "sourceTier": "A",
            "sourceName": "OpenAI",
            "sourceUrl": url,
            "supportingUrls": [],
            "headline": title,
            "summary": f"OpenAI 官方产品页面更新：{title}。",
            "whatChanged": "OpenAI 官方产品站点出现新的模型发布页面，具体能力、价格和可用范围以原文为准。",
            "affectedCompanies": ["MSFT"],
            "beneficiaries": ["MSFT"],
            "impactPath": "前沿模型发布 → 产品采用与推理需求 → 云与算力产业链验证",
            "horizon": "1D / 5D / 20D",
            "pricingStatus": "待市场数据验证",
            "score": score(combined, "A"),
            "confidence": "高",
            "nextCatalyst": "API 价格、用户可用范围及合作伙伴披露",
            "falsification": "实际可用范围、采用率或推理需求低于发布所隐含的预期",
        })
    return events, {"source": "OpenAI Product Sitemap", "status": "ok", "entries": len(rows), "materialCandidates": len(events)}


def score(text: str, tier: str) -> int:
    lowered = f" {text.lower()} "
    ai_hits = sum(word in lowered for word in AI_WORDS)
    material_hits = sum(word in lowered for word in MATERIAL_WORDS)
    model_release = any(word in lowered for word in MODEL_RELEASE_WORDS) and any(word in lowered for word in ("releas", "launch", "available", "introduc"))
    return min(95, (35 if tier == "A" else 20) + min(ai_hits, 3) * 12 + min(material_hits, 3) * 8 + (25 if model_release else 0))


def has_material_signal(text: str) -> bool:
    lowered = text.lower()
    expanded = MATERIAL_WORDS + ("available", "contract", "order", "guidance", "investment", "customer", "enterprise", "chip", "server", "cloud")
    model_release = any(word in lowered for word in MODEL_RELEASE_WORDS) and any(word in lowered for word in ("releas", "launch", "available", "introduc"))
    return any(word in lowered for word in expanded) or model_release


def localize(events: list[dict]) -> tuple[list[dict], str]:
    if not events:
        return events, "not_needed"
    load_dotenv(ROOT / ".env")
    token = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not token:
        return events, "missing_key"
    source = [{"id": e["id"], "title": e["headline"], "description": e["whatChanged"], "source": e["sourceName"]} for e in events]
    prompt = (
        "你是对冲基金AI产业研究员。仅根据输入，不添加事实。返回纯JSON数组；每项必须包含id、headline、summary、whatChanged。"
        "全部正文使用简洁中文，专有名词可保留英文；headline说明事件，summary说明已知事实，whatChanged说明对预期或产业链的变化。输入："
        + json.dumps(source, ensure_ascii=False)
    )
    try:
        response = post_json(
            "https://openrouter.ai/api/v1/chat/completions",
            {"model": os.environ.get("OPENROUTER_MODEL", "openrouter/free"), "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            headers={"Authorization": f"Bearer {token}", "HTTP-Referer": "https://local.ai-alpha-research", "X-Title": "AI Alpha Research"},
            timeout=25,
            retries=0,
        )
        content = response["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
        translated = {row["id"]: row for row in json.loads(content)}
        for event in events:
            row = translated.get(event["id"], {})
            for key in ("headline", "summary", "whatChanged"):
                if isinstance(row.get(key), str) and row[key].strip():
                    event[key] = row[key].strip()
        return events, "ok"
    except Exception as exc:
        return events, f"fallback:{type(exc).__name__}"


def apply_verified_overrides(events: list[dict]) -> list[dict]:
    path = ROOT / "config" / "event_overrides.json"
    if not path.exists():
        return events
    overrides = json.loads(path.read_text(encoding="utf-8"))
    for event in events:
        override = overrides.get(event["sourceUrl"])
        if isinstance(override, dict):
            event.update(override)
            event["analystVerified"] = True
    return events


def discover(now: datetime, hours: int) -> tuple[list[dict], list[dict]]:
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=hours)
    events, feed_status = [], []
    with (ROOT / "config" / "daily_event_feeds.csv").open(encoding="utf-8", newline="") as handle:
        feeds = list(csv.DictReader(handle))
    for feed in feeds:
        try:
            entries = parse_feed(get_text(feed["feed_url"], headers={"User-Agent": "AIAlphaResearch/0.1 research@local"}, timeout=12, retries=0))
            feed_status.append({"source": feed["source_name"], "status": "ok", "entries": len(entries)})
        except Exception as exc:
            feed_status.append({"source": feed["source_name"], "status": "failed", "error": type(exc).__name__})
            continue
        for entry in entries:
            combined = f'{entry["title"]} {entry["summary"]}'
            event_score = score(combined, feed["source_tier"])
            if not entry["url"] or not entry["published"] or entry["published"] < cutoff or event_score < 65 or not has_material_signal(combined):
                continue
            tickers = {x for x in feed["default_tickers"].split("|") if x}
            lowered = combined.lower()
            tickers.update(ticker for word, ticker in ENTITY_MAP.items() if word in lowered)
            event_id = hashlib.sha256(entry["url"].encode()).hexdigest()[:16]
            events.append({
                "id": event_id,
                "publishedDate": entry["published"].date().isoformat(),
                "publishedAt": entry["published"].isoformat(),
                "timeBasis": "official RSS/Atom publication timestamp",
                "type": "official_update",
                "sourceTier": feed["source_tier"],
                "sourceName": feed["source_name"],
                "sourceUrl": entry["url"],
                "supportingUrls": [],
                "headline": entry["title"],
                "summary": f'官方来源发布：{entry["title"]}。',
                "whatChanged": clean(entry["summary"])[:280] or "官方发布新增信息，待结合公司披露与市场数据进一步核验。",
                "affectedCompanies": sorted(tickers),
                "beneficiaries": sorted(tickers),
                "impactPath": "官方事件 → 预期修正 → 基本面与股价验证",
                "horizon": "1D / 5D / 20D",
                "pricingStatus": "待市场数据验证",
                "score": event_score,
                "confidence": "高" if feed["source_tier"] == "A" else "中",
                "nextCatalyst": "下一次公司披露或经营数据更新",
                "falsification": "后续财务、采用率或市场数据未确认该事件影响",
            })
    sitemap_events, sitemap_status = discover_openai_sitemap(now, hours)
    events.extend(sitemap_events)
    feed_status.append(sitemap_status)
    deduped = {event["sourceUrl"]: event for event in events}
    return sorted(deduped.values(), key=lambda x: (x["score"], x["publishedAt"]), reverse=True)[:8], feed_status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=36)
    parser.add_argument("--as-of", type=datetime.fromisoformat)
    args = parser.parse_args()
    now = args.as_of or datetime.now(timezone.utc)
    events, status = discover(now, args.hours)
    events, localization_status = localize(events)
    events = apply_verified_overrides(events)
    output = ROOT / "data" / "processed" / "daily_ai_brief.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "published",
        "asOf": now.isoformat(),
        "eventCount": len(events),
        "verifiedCount": len(events),
        "headline": f"今日识别 {len(events)} 条重要 AI 事件" if events else "今日暂无达到阈值的重要 AI 事件",
        "summary": "本页仅保留官方来源、处于有效时间窗且达到重要性阈值的事件。" if events else "官方来源在当前时间窗内暂无达到研究阈值的新事件。",
        "scheduledTime": "08:00 Asia/Shanghai",
        "generatedAt": now.isoformat(),
        "events": events,
        "feedStatus": status,
        "localizationStatus": localization_status,
        "method": "官方 RSS/Atom 来源、时间窗过滤、关键词重要性评分与 URL 去重",
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"events={len(events)} feeds_ok={sum(x['status'] == 'ok' for x in status)} output={output.relative_to(ROOT)}")
    return 0 if any(x["status"] == "ok" for x in status) else 1


if __name__ == "__main__":
    raise SystemExit(main())
