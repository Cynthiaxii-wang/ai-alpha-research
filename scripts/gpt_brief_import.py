#!/usr/bin/env python3
"""Import a user-pasted ChatGPT morning brief without using a paid API.

The importer accepts a versioned JSON block embedded anywhere in the copied
brief. It validates source provenance, freshness and materiality, stores the
original paste in the private raw layer, rebuilds research outputs, and invokes
the existing allowlisted Git publisher only after the quality gate passes.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_alpha_research.storage import write_raw_json  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = "ai-alpha-gpt-brief-v2"
START_MARKER = "AI_ALPHA_IMPORT_V2_START"
END_MARKER = "AI_ALPHA_IMPORT_V2_END"
PROCESSED_BRIEF = ROOT / "data" / "processed" / "daily_ai_brief.json"
IMPORT_REPORT = ROOT / "data" / "processed" / "gpt_brief_import_report.json"
UPDATE_REPORT = ROOT / "data" / "processed" / "daily_update_report.json"

SCORE_LIMITS = {
    "surprise": 25,
    "fundamental": 25,
    "tradability": 20,
    "breadth": 15,
    "evidence": 15,
}

# Tier A is a primary issuer/regulator/developer source. Tier B is reputable
# reporting suitable as an attributed lead, but not treated as issuer-confirmed.
PRIMARY_DOMAINS = {
    "sec.gov", "openai.com", "anthropic.com", "microsoft.com", "google.com",
    "blog.google", "amazon.com", "aboutamazon.com", "aws.amazon.com",
    "meta.com", "nvidia.com", "amd.com", "broadcom.com", "dell.com",
    "oracle.com", "cloudflare.com", "github.com", "huggingface.co",
    "tcs.com", "foxconn.com.tw", "fortum.com", "googlecloudpresscorner.com",
    "investor.apple.com", "investor.tsmc.com", "investors.micron.com",
    "investors.arista.com", "investors.palantir.com", "investors.adobe.com",
    "investors.snowflake.com", "investors.mongodb.com", "investors.datadoghq.com",
}
SECONDARY_DOMAINS = {
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "cnbc.com",
    "channelnewsasia.com",
}
FORBIDDEN_TEXT = (
    "/Users/", "\\Users\\", ".env", "api_key", "apikey", "authorization: bearer",
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
)


class ImportRejected(ValueError):
    pass


def _write_report(payload: dict) -> None:
    IMPORT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    IMPORT_REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_payload(text: str) -> dict:
    """Extract the versioned machine-readable block from a copied response."""
    stripped = text.strip()
    candidates: list[str] = []
    marker = re.search(
        rf"{START_MARKER}\s*(?:```(?:json)?\s*)?(.*?)(?:\s*```)?\s*{END_MARKER}",
        stripped,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if marker:
        candidates.append(marker.group(1).strip())
    candidates.extend(match.strip() for match in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL | re.IGNORECASE))
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("schemaVersion") == SCHEMA_VERSION:
            return payload
    raise ImportRejected(
        f"没有找到 {SCHEMA_VERSION} 数据块。请让 GPT 按项目提示词在日报末尾附加 {START_MARKER} / {END_MARKER} JSON。"
    )


def _parse_timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ImportRejected(f"缺少 {field}")
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ImportRejected(f"{field} 必须是包含时区的真实发布时间，不能只有日期")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ImportRejected(f"{field} 不是 ISO 日期/时间：{value}") from exc
    if parsed.tzinfo is None:
        raise ImportRejected(f"{field} 必须包含时区：{value}")
    return parsed.astimezone(TZ)


def _parse_date(value: str, field: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        raise ImportRejected(f"{field} 必须是 YYYY-MM-DD")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ImportRejected(f"{field} 不是有效日期：{value}") from exc


def _domain_tier(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ImportRejected(f"来源必须是完整 HTTPS 直链：{url}")
    host = parsed.hostname.lower().removeprefix("www.")
    if host in {"chatgpt.com", "chat.openai.com"} or (host == "google.com" and parsed.path.startswith(("/search", "/url"))):
        raise ImportRejected(f"不能使用聊天页或搜索结果页作为来源：{url}")
    for domain in PRIMARY_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return "A", host
    for domain in SECONDARY_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return "B", host
    raise ImportRejected(f"来源域名尚未列入白名单，需要人工审核后再加入：{host}")


def _required_text(event: dict, key: str) -> str:
    value = event.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ImportRejected(f"事件缺少 {key}")
    return re.sub(r"\s+", " ", value).strip()


def _string_list(event: dict, key: str) -> list[str]:
    value = event.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ImportRejected(f"{key} 必须是字符串数组")
    return sorted({item.strip().upper() for item in value if item.strip()})


def validate_and_normalize(payload: dict, imported_at: datetime | None = None) -> dict:
    imported_at = (imported_at or datetime.now(TZ)).astimezone(TZ)
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise ImportRejected(f"schemaVersion 必须是 {SCHEMA_VERSION}")
    brief_date = _parse_date(payload.get("brief_date", ""), "brief_date")
    as_of = _parse_timestamp(payload.get("asOf", ""), "asOf")
    if brief_date != as_of.date():
        raise ImportRejected("brief_date 必须等于 asOf 在 Asia/Shanghai 的日期")
    if abs(as_of - imported_at) > timedelta(days=4):
        raise ImportRejected("日报 asOf 与本次导入时间相差超过 4 天")
    rows = payload.get("events")
    if not isinstance(rows, list) or not rows:
        raise ImportRejected("events 必须是非空数组；没有事件时无需手工导入")
    max_age = timedelta(hours=96 if as_of.weekday() == 0 else 48)
    normalized = []
    urls_seen: set[str] = set()
    for index, event in enumerate(rows, start=1):
        if not isinstance(event, dict):
            raise ImportRejected(f"第 {index} 条事件不是对象")
        source_url = _required_text(event, "sourceUrl")
        source_tier, source_host = _domain_tier(source_url)
        event_date = _parse_date(event.get("event_date", ""), "event_date")
        published = _parse_timestamp(event.get("source_published_at", ""), "source_published_at")
        if event_date > brief_date:
            raise ImportRejected(f"第 {index} 条 event_date 晚于 brief_date")
        if published == as_of:
            raise ImportRejected(f"第 {index} 条 source_published_at 与晨报生成时刻完全相同，疑似错误替代")
        if published > as_of + timedelta(minutes=15):
            raise ImportRejected(f"第 {index} 条事件发布时间晚于日报 asOf")
        if as_of - published > max_age:
            raise ImportRejected(f"第 {index} 条事件超出当前日报时间窗：{published.isoformat()}")
        components = event.get("scoreComponents")
        if not isinstance(components, dict) or set(components) != set(SCORE_LIMITS):
            raise ImportRejected(f"第 {index} 条事件 scoreComponents 必须包含 {sorted(SCORE_LIMITS)}")
        for name, maximum in SCORE_LIMITS.items():
            if not isinstance(components[name], int) or not 0 <= components[name] <= maximum:
                raise ImportRejected(f"第 {index} 条事件 {name} 必须是 0–{maximum} 的整数")
        score = sum(components.values())
        if score < 60:
            raise ImportRejected(f"第 {index} 条事件总分 {score} 低于 60，不进入公开晨报")
        canonical_url = source_url.split("#", 1)[0]
        if canonical_url in urls_seen:
            raise ImportRejected(f"重复来源链接：{canonical_url}")
        urls_seen.add(canonical_url)
        supporting = event.get("supportingUrls", [])
        if not isinstance(supporting, list):
            raise ImportRejected("supportingUrls 必须是数组")
        checked_supporting = []
        for url in supporting:
            if not isinstance(url, str):
                raise ImportRejected("supportingUrls 只能包含字符串")
            _domain_tier(url)
            checked_supporting.append(url)
        source_name = _required_text(event, "sourceName")
        event_id = re.sub(r"[^a-z0-9-]+", "-", str(event.get("id") or "").lower()).strip("-")
        if not event_id:
            event_id = f"gpt-import-{event_date.isoformat()}-{index}"
        normalized.append({
            "id": event_id,
            "event_date": event_date.isoformat(),
            "source_published_at": published.astimezone(timezone.utc).isoformat(),
            "timeBasis": "event_date is the occurrence date; source_published_at is the source publication timestamp",
            "type": event.get("type") or "reported_ai_event",
            "sourceTier": source_tier,
            "sourceType": "official" if source_tier == "A" else "media",
            "sourceName": source_name,
            "sourceHost": source_host,
            "sourceUrl": canonical_url,
            "supportingUrls": checked_supporting,
            "headline": _required_text(event, "headline"),
            "summary": _required_text(event, "summary"),
            "whatChanged": _required_text(event, "whatChanged"),
            "expectationGap": _required_text(event, "expectationGap"),
            "affectedCompanies": _string_list(event, "affectedCompanies"),
            "beneficiaries": _string_list(event, "beneficiaries"),
            "adverselyAffected": _string_list(event, "adverselyAffected"),
            "impactPath": _required_text(event, "impactPath"),
            "horizon": _required_text(event, "horizon"),
            "pricingStatus": _required_text(event, "pricingStatus"),
            "score": score,
            "scoreComponents": components,
            "confidence": _required_text(event, "confidence"),
            "nextCatalyst": _required_text(event, "nextCatalyst"),
            "falsification": _required_text(event, "falsification"),
            "verificationStatus": "primary_source_link_supplied" if source_tier == "A" else "attributed_secondary_report",
            "importMethod": "manual_chatgpt_copy",
        })
    normalized.sort(key=lambda row: (row["score"], row["source_published_at"]), reverse=True)
    return {"brief_date": brief_date.isoformat(), "asOf": as_of.isoformat(), "events": normalized[:5]}


def reject_sensitive_text(text: str) -> None:
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in FORBIDDEN_TEXT):
        raise ImportRejected("粘贴内容包含本地路径、环境变量或认证字段，已阻止导入")
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        raise ImportRejected("粘贴内容疑似包含密钥，已阻止导入")


def _event_rows(events: list[dict], imported_at: datetime, brief_date: str) -> list[dict]:
    return [{
        "event_id": event["id"], "brief_date": brief_date,
        "event_date": event["event_date"], "source_published_at": event["source_published_at"],
        "first_seen_at": imported_at.astimezone(timezone.utc).isoformat(),
        "available_at": imported_at.astimezone(timezone.utc).isoformat(),
        "available_at_precision": "manual_import_timestamp", "event_type": event["type"],
        "source_tier": event["sourceTier"], "source_type": event["sourceType"], "source_name": event["sourceName"],
        "source_url": event["sourceUrl"],
        "supporting_urls": json.dumps(event["supportingUrls"], ensure_ascii=False),
        "headline": event["headline"], "fact_summary": event["summary"],
        "what_changed": event["whatChanged"], "expectation_gap": event.get("expectationGap", ""),
        "affected_companies": json.dumps(event["affectedCompanies"], ensure_ascii=False),
        "beneficiaries": json.dumps(event["beneficiaries"], ensure_ascii=False),
        "adversely_affected": json.dumps(event.get("adverselyAffected", []), ensure_ascii=False),
        "transmission_path": event["impactPath"], "impact_horizon": event["horizon"],
        "pricing_status": event["pricingStatus"], "materiality_score": event["score"],
        "confidence_score": event["confidence"],
        "score_components": json.dumps(event.get("scoreComponents", {}), ensure_ascii=False),
        "next_catalyst": event["nextCatalyst"], "falsification_condition": event["falsification"],
        "verification_status": event["verificationStatus"], "import_method": event.get("importMethod", "official_feed"),
    } for event in events]


def persist_import(text: str, normalized: dict, imported_at: datetime | None = None) -> Path:
    imported_at = (imported_at or datetime.now(TZ)).astimezone(TZ)
    raw_path = write_raw_json(
        ROOT,
        source="gpt_manual_import",
        entity=f"daily_brief_{normalized['brief_date']}",
        payload={"pasted_text": text, "normalized": normalized},
        request_metadata={"method": "user_copy_paste", "schema_version": SCHEMA_VERSION},
    )
    existing = {}
    if PROCESSED_BRIEF.exists():
        try:
            existing = json.loads(PROCESSED_BRIEF.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    as_of = _parse_timestamp(normalized["asOf"], "asOf")
    max_age = timedelta(hours=96 if as_of.weekday() == 0 else 48)

    def is_current(event: dict) -> bool:
        try:
            _parse_date(event.get("event_date", ""), "event_date")
            published = _parse_timestamp(event.get("source_published_at", ""), "source_published_at")
        except ImportRejected:
            return False
        return published <= as_of + timedelta(minutes=15) and as_of - published <= max_age

    combined = {
        event.get("id") or event["sourceUrl"]: event
        for event in existing.get("events", [])
        if isinstance(event, dict) and event.get("sourceUrl") and is_current(event)
    }
    combined.update({event.get("id") or event["sourceUrl"]: event for event in normalized["events"]})
    events = sorted(combined.values(), key=lambda row: (row.get("score", 0), row.get("source_published_at", "")), reverse=True)[:5]
    payload = {
        "status": "published", "brief_date": normalized["brief_date"], "asOf": normalized["asOf"], "eventCount": len(events),
        "verifiedCount": sum(event.get("sourceTier") == "A" for event in events),
        "headline": f"今日识别 {len(events)} 条重要 AI 事件",
        "summary": "事件来自人工搬运的结构化 GPT 晨报与官方订阅源；正文为研究摘要，来源等级与时间依据逐条保留。",
        "scheduledTime": "08:00 Asia/Shanghai", "generatedAt": imported_at.isoformat(),
        "events": events, "importMethod": "manual_chatgpt_copy",
        "method": "结构化复制、时间窗校验、来源域名白名单、重要性阈值与 URL 去重",
    }
    PROCESSED_BRIEF.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_BRIEF.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = _event_rows(events, imported_at, normalized["brief_date"])
    event_csv = ROOT / "data" / "standardized" / "events.csv"
    event_csv.parent.mkdir(parents=True, exist_ok=True)
    with event_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return raw_path


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True)


def rebuild_and_publish(run_date: date) -> dict:
    started = datetime.now(TZ)
    pipeline = _run([sys.executable, str(ROOT / "scripts" / "run_research_pipeline.py")])
    task_rows = [
        {"task": "gpt_brief_import", "status": "ok", "last_run_at": started.isoformat()},
        {"task": "research_pipeline", "status": "ok" if pipeline.returncode == 0 else "failed", "last_run_at": datetime.now(TZ).isoformat()},
    ]
    failed = [] if pipeline.returncode == 0 else ["research_pipeline"]
    UPDATE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    UPDATE_REPORT.write_text(json.dumps({"runDate": run_date.isoformat(), "tasks": task_rows, "failed": failed}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if pipeline.returncode != 0:
        return {"status": "blocked", "reason": "research_pipeline_failed", "details": (pipeline.stderr or pipeline.stdout)[-2000:]}
    publish = _run([sys.executable, str(ROOT / "scripts" / "publish_public_dashboard.py"), "--date", run_date.isoformat()])
    publication_path = ROOT / "data" / "processed" / "public_publication_report.json"
    try:
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        publication = {"status": "failed", "reason": "publication_report_missing"}
    if publish.returncode != 0 and publication.get("status") not in {"push_failed", "blocked"}:
        publication = {**publication, "status": "failed", "reason": (publish.stderr or publish.stdout)[-2000:]}
    return publication


def import_text(text: str, *, publish: bool = True, imported_at: datetime | None = None) -> dict:
    imported_at = (imported_at or datetime.now(TZ)).astimezone(TZ)
    try:
        reject_sensitive_text(text)
        normalized = validate_and_normalize(extract_payload(text), imported_at)
        raw_path = persist_import(text, normalized, imported_at)
        _write_report({
            "status": "validated", "runDate": imported_at.date().isoformat(),
            "importedAt": imported_at.isoformat(), "asOf": normalized["asOf"],
            "importedEvents": len(normalized["events"]),
            "rawFile": str(raw_path.relative_to(ROOT)),
            "publication": {"status": "not_attempted"},
        })
        publication = rebuild_and_publish(imported_at.date()) if publish else {"status": "skipped", "reason": "publish_disabled"}
        result = {
            "status": "ok" if publication.get("status") in {"pushed", "skipped"} else "saved_not_published",
            "runDate": imported_at.date().isoformat(), "importedAt": imported_at.isoformat(),
            "importedEvents": len(normalized["events"]), "asOf": normalized["asOf"],
            "rawFile": str(raw_path.relative_to(ROOT)), "publication": publication,
        }
        _write_report(result)
        return result
    except ImportRejected as exc:
        result = {"status": "rejected", "reason": str(exc), "publication": {"status": "not_attempted"}}
        _write_report(result)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a copied structured GPT AI brief.")
    parser.add_argument("input", nargs="?", type=Path, help="Text/Markdown file containing the copied brief; stdin when omitted")
    parser.add_argument("--no-publish", action="store_true", help="Validate and persist without rebuilding/pushing")
    args = parser.parse_args()
    text = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
    result = import_text(text, publish=not args.no_publish)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
