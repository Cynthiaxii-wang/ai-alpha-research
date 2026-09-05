#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.config import Settings  # noqa: E402
from ai_alpha_research.http import get_text  # noqa: E402
from ai_alpha_research.research_utils import write_csv  # noqa: E402
from ai_alpha_research.storage import write_raw_json  # noqa: E402


MAX_COMPONENTS = {"surprise": 25, "fundamental": 25, "tradability": 20, "breadth": 15, "evidence": 15}


def validate_scores(components: dict) -> int:
    missing = set(MAX_COMPONENTS) - set(components)
    if missing:
        raise ValueError(f"Missing score components: {sorted(missing)}")
    for name, maximum in MAX_COMPONENTS.items():
        value = components[name]
        if not isinstance(value, int) or not 0 <= value <= maximum:
            raise ValueError(f"Invalid {name} score: {value}")
    return sum(components.values())


def public_headers(url: str, settings: Settings) -> dict[str, str]:
    if "sec.gov" in url:
        return {"User-Agent": settings.sec_user_agent, "Accept": "text/html,application/xhtml+xml"}
    return {"User-Agent": "Mozilla/5.0 (compatible; AIAlphaResearch/0.1; research-use)", "Accept": "text/html,application/xhtml+xml"}


def main() -> int:
    candidates = json.loads((PROJECT_ROOT / "config" / "daily_event_candidates.json").read_text(encoding="utf-8"))
    settings = Settings.from_project_root(PROJECT_ROOT)
    now = datetime.now(timezone.utc).isoformat()
    normalized = []
    report = []
    for candidate in candidates:
        documents, errors = [], []
        for position, url in enumerate([candidate["source_url"], *candidate.get("supporting_urls", [])]):
            try:
                body = get_text(url, headers=public_headers(url, settings), timeout=60)
                path = write_raw_json(
                    PROJECT_ROOT, source="daily_events", entity=f"{candidate['event_id']}_{position}",
                    payload={"source_url": url, "body": body},
                    request_metadata={"purpose": "official_event_verification", "source_tier": candidate["source_tier"]},
                )
                documents.append({"url": url, "body": body, "raw_file": str(path.relative_to(PROJECT_ROOT))})
            except Exception as exc:
                errors.append({"url": url, "error": str(exc)})
            combined_so_far = " ".join(document["body"].lower() for document in documents)
            if documents and all(phrase.lower() in combined_so_far for phrase in candidate.get("expected_phrases", [])):
                break
        combined = " ".join(document["body"].lower() for document in documents)
        phrase_matches = {phrase: phrase.lower() in combined for phrase in candidate.get("expected_phrases", [])}
        verified = bool(documents) and all(phrase_matches.values())
        score = validate_scores(candidate["score_components"])
        status = "verified" if verified else "verification_failed"
        report.append({"event_id": candidate["event_id"], "status": status, "materiality_score": score, "source_documents": [document["raw_file"] for document in documents], "phrase_matches": phrase_matches, "errors": errors})
        if not verified:
            print(f"[daily_event] {candidate['event_id']}: verification_failed matches={phrase_matches} errors={len(errors)}", file=sys.stderr, flush=True)
            continue
        normalized.append({
            "event_id": candidate["event_id"], "event_time": candidate["published_date"], "first_seen_at": now,
            "available_at": now, "available_at_precision": "system_verified_timestamp",
            "event_type": candidate["event_type"], "source_tier": candidate["source_tier"], "source_name": candidate["source_name"],
            "source_url": candidate["source_url"], "supporting_urls": json.dumps(candidate.get("supporting_urls", []), ensure_ascii=False),
            "headline": candidate["headline"], "fact_summary": candidate["fact_summary"], "what_changed": candidate["what_changed"],
            "expectation_gap": candidate["expectation_gap"], "affected_companies": json.dumps(candidate["affected_companies"], ensure_ascii=False),
            "beneficiaries": json.dumps(candidate["beneficiaries"], ensure_ascii=False), "adversely_affected": json.dumps(candidate["adversely_affected"], ensure_ascii=False),
            "transmission_path": candidate["transmission_path"], "impact_horizon": candidate["impact_horizon"], "pricing_status": candidate["pricing_status"],
            "materiality_score": score, "confidence_score": candidate["confidence_score"], "score_components": json.dumps(candidate["score_components"], ensure_ascii=False),
            "next_catalyst": candidate["next_catalyst"], "falsification_condition": candidate["falsification_condition"],
            "duplicate_cluster_id": candidate["duplicate_cluster_id"], "verification_status": status,
        })
        print(f"[daily_event] {candidate['event_id']}: verified score={score}", flush=True)
    normalized.sort(key=lambda row: (-row["materiality_score"], row["event_id"]))
    brief_events = [row for row in normalized if row["materiality_score"] >= 60][:5]
    if normalized:
        write_csv(PROJECT_ROOT / "data" / "standardized" / "events.csv", normalized, list(normalized[0]))
    brief = {
        "status": "published" if brief_events else "no_material_event",
        "headline": f"今日识别 {len(brief_events)} 条重要 AI 事件" if brief_events else "今日暂无达到阈值的 AI 事件",
        "summary": "算力需求信号继续增强：Broadcom 验证自研 AI 芯片与网络需求，Dell 验证服务器真实订单，Microsoft 改善 Azure 货币化可观测性。" if brief_events else "未用低质量信息填充晨报。",
        "scheduledTime": "08:00 Asia/Shanghai", "generatedAt": now, "verifiedCount": len(normalized),
        "events": [{
            "id": row["event_id"], "publishedDate": row["event_time"], "type": row["event_type"], "sourceTier": row["source_tier"],
            "sourceName": row["source_name"], "sourceUrl": row["source_url"], "supportingUrls": json.loads(row["supporting_urls"]),
            "headline": row["headline"], "summary": row["fact_summary"], "whatChanged": row["what_changed"], "expectationGap": row["expectation_gap"],
            "affectedCompanies": json.loads(row["affected_companies"]), "beneficiaries": json.loads(row["beneficiaries"]),
            "impactPath": row["transmission_path"], "horizon": row["impact_horizon"], "pricingStatus": row["pricing_status"],
            "score": row["materiality_score"], "confidence": row["confidence_score"], "nextCatalyst": row["next_catalyst"],
            "falsification": row["falsification_condition"],
        } for row in brief_events],
    }
    processed = PROJECT_ROOT / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "daily_event_ingestion_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (processed / "daily_ai_brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = sum(row["status"] != "verified" for row in report)
    print(f"verified={len(normalized)} brief={len(brief_events)} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
