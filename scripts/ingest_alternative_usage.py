#!/usr/bin/env python3
"""Collect historical model usage and current AI product-domain attention proxies."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.clients import CloudflareRadarClient, OpenRouterClient  # noqa: E402
from ai_alpha_research.config import Settings  # noqa: E402
from ai_alpha_research.storage import write_raw_json  # noqa: E402


def save(source: str, entity: str, payload: object, purpose: str) -> str:
    path = write_raw_json(
        PROJECT_ROOT,
        source=source,
        entity=entity,
        payload=payload,
        request_metadata={"purpose": purpose},
    )
    print(f"[{source}] {entity}: {path.relative_to(PROJECT_ROOT)}", flush=True)
    return str(path.relative_to(PROJECT_ROOT))


def collect_openrouter_usage(client: OpenRouterClient, start: date, end: date) -> dict:
    """Backfill in bounded windows and deduplicate inclusive boundary rows."""
    observations = {}
    cursor = start
    as_of = None
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=119), end)
        payload = client.rankings_daily(start_date=cursor, end_date=chunk_end)
        for row in payload.get("data") or []:
            observations[(row.get("date"), row.get("model_permaslug"))] = row
        as_of = max(as_of or "", str((payload.get("meta") or {}).get("as_of") or ""))
        cursor = chunk_end + timedelta(days=1)
    rows = sorted(observations.values(), key=lambda row: (row.get("date") or "", -(int(row.get("total_tokens") or 0))))
    return {"data": rows, "meta": {"start_date": start.isoformat(), "end_date": end.isoformat(), "as_of": as_of, "collection": "120_day_chunks"}}


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect OpenRouter usage and Cloudflare Radar product signals.")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2025, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    args = parser.parse_args()
    settings = Settings.from_project_root(PROJECT_ROOT)
    report = []

    try:
        payload = collect_openrouter_usage(OpenRouterClient(settings), args.start, args.end)
        report.append({"source": "openrouter_usage", "entity": "rankings_daily", "status": "ok", "raw_file": save("openrouter_usage", "rankings_daily", payload, "model_usage_factor")})
    except Exception as exc:
        report.append({"source": "openrouter_usage", "entity": "rankings_daily", "status": "failed", "error": str(exc)})
        print(f"[openrouter_usage] rankings_daily: FAILED - {exc}", file=sys.stderr)

    radar = CloudflareRadarClient(settings)
    with (PROJECT_ROOT / "config" / "ai_product_domains.csv").open(encoding="utf-8", newline="") as handle:
        domains = list(csv.DictReader(handle))
    for item in domains:
        try:
            payload = radar.domain_rank(item["domain"])
            report.append({"source": "cloudflare_radar", "entity": item["product_id"], "domain": item["domain"], "status": "ok", "raw_file": save("cloudflare_radar", item["product_id"], payload, "product_adoption_proxy")})
        except Exception as exc:
            report.append({"source": "cloudflare_radar", "entity": item["product_id"], "domain": item["domain"], "status": "failed", "error": str(exc)})
            print(f"[cloudflare_radar] {item['domain']}: FAILED - {exc}", file=sys.stderr)

    target = PROJECT_ROOT / "data" / "processed" / "alternative_usage_ingestion_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = sum(row["status"] != "ok" for row in report)
    print(f"completed={len(report) - failures} failed={failures} report={target.relative_to(PROJECT_ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
