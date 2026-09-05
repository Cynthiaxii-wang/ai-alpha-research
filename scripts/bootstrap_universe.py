#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.clients import SECClient  # noqa: E402
from ai_alpha_research.config import Settings  # noqa: E402
from ai_alpha_research.research_utils import write_csv  # noqa: E402


def main() -> int:
    settings = Settings.from_project_root(PROJECT_ROOT)
    with (PROJECT_ROOT / "config" / "universe_candidates.csv").open(encoding="utf-8", newline="") as handle:
        candidates = list(csv.DictReader(handle))
    payload = SECClient(settings).company_tickers()
    ticker_map = {
        item["ticker"].upper(): str(item["cik_str"]).zfill(10)
        for item in payload.values()
    }
    missing = [row["ticker"] for row in candidates if row["ticker"] not in ticker_map]
    if missing:
        raise RuntimeError(f"SEC ticker mapping missing: {', '.join(missing)}")
    rows = []
    for row in candidates:
        rows.append({
            "ticker": row["ticker"],
            "company_name": row["company_name"],
            "cik": ticker_map[row["ticker"]],
            "github_owner": row["github_owner"],
            "huggingface_author": row["huggingface_author"],
            "value_chain_bucket": row["value_chain_bucket"],
            "product_focus": row["product_focus"],
            "include_in_research": row["include_in_research"],
            "identifier_source": "sec_company_tickers",
        })
    output = PROJECT_ROOT / "config" / "research_universe.csv"
    write_csv(output, rows, list(rows[0]))
    print(f"universe={len(rows)} missing=0 output={output.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
