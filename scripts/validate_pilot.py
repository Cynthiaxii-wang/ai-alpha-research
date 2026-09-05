#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.universe import load_pilot_universe  # noqa: E402


def latest(source: str, ticker: str) -> Path | None:
    files = sorted((PROJECT_ROOT / "data" / "raw" / source).glob(f"*/{ticker}_*.json"))
    return files[-1] if files else None


def load_verified(path: Path) -> tuple[dict, bool]:
    envelope = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(envelope["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return envelope, digest == envelope.get("content_sha256")


def market_summary(payload: dict) -> dict:
    rows = payload.get("results") or []
    dates = [datetime.fromtimestamp(row["t"] / 1000, tz=timezone.utc).date().isoformat() for row in rows]
    return {
        "records": len(rows),
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
        "api_status": payload.get("status"),
    }


def summarize(source: str, payload) -> dict:
    if source == "massive":
        return market_summary(payload)
    if source == "alpha_vantage":
        return {"quarterly_earnings": len(payload.get("quarterlyEarnings") or [])}
    if source == "sec_submissions":
        recent = ((payload.get("filings") or {}).get("recent") or {}).get("accessionNumber") or []
        return {"company_name": payload.get("name"), "recent_filings": len(recent)}
    if source == "sec_companyfacts":
        return {"company_name": payload.get("entityName"), "fact_namespaces": len(payload.get("facts") or {})}
    if source == "github":
        return {"repositories": len(payload) if isinstance(payload, list) else 0}
    if source == "huggingface":
        return {"models": len(payload) if isinstance(payload, list) else 0}
    return {}


def main() -> int:
    universe = load_pilot_universe(PROJECT_ROOT / "config" / "pilot_universe.csv")
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "companies": {}, "failures": []}
    required = ["massive", "alpha_vantage", "sec_submissions", "sec_companyfacts", "github"]
    for company in universe:
        company_report = {}
        sources = required + (["huggingface"] if company.huggingface_author else [])
        for source in sources:
            path = latest(source, company.ticker)
            if path is None:
                report["failures"].append(f"{company.ticker}:{source}:missing")
                company_report[source] = {"status": "missing"}
                continue
            envelope, hash_ok = load_verified(path)
            summary = summarize(source, envelope["payload"])
            status = "ok" if hash_ok else "hash_mismatch"
            if not hash_ok:
                report["failures"].append(f"{company.ticker}:{source}:hash_mismatch")
            company_report[source] = {
                "status": status,
                "hash_verified": hash_ok,
                "retrieved_at": envelope.get("retrieved_at"),
                "raw_file": str(path.relative_to(PROJECT_ROOT)),
                **summary,
            }
        report["companies"][company.ticker] = company_report
    openrouter_files = sorted((PROJECT_ROOT / "data" / "raw" / "openrouter").glob("*/models_*.json"))
    if openrouter_files:
        envelope, hash_ok = load_verified(openrouter_files[-1])
        report["openrouter"] = {
            "status": "ok" if hash_ok else "hash_mismatch",
            "models": len(envelope["payload"].get("data") or []),
            "hash_verified": hash_ok,
        }
    else:
        report["failures"].append("openrouter:missing")
    output = PROJECT_ROOT / "data" / "processed" / "pilot_quality_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
