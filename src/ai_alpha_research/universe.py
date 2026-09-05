from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Company:
    ticker: str
    company_name: str
    cik: str
    github_owner: str
    huggingface_author: str
    value_chain_bucket: str
    product_focus: str


def load_universe(path: Path) -> list[Company]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle)
        return [
            Company(
                ticker=row["ticker"],
                company_name=row["company_name"],
                cik=row["cik"],
                github_owner=row["github_owner"],
                huggingface_author=row["huggingface_author"],
                value_chain_bucket=row["value_chain_bucket"],
                product_focus=row["product_focus"],
            )
            for row in rows
            if row.get("include_in_research", row.get("include_in_pilot", "true")).strip().lower() == "true"
        ]


def load_pilot_universe(path: Path) -> list[Company]:
    """Backward-compatible alias for the original five-company configuration."""
    return load_universe(path)
