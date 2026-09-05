#!/usr/bin/env python3
"""Print a credential-safe summary of the local research warehouse."""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.warehouse import warehouse_path  # noqa: E402


def main() -> int:
    path = warehouse_path(PROJECT_ROOT)
    if not path.exists():
        print("Warehouse not found. Run: python3 scripts/build_warehouse.py", file=sys.stderr)
        return 1
    connection = duckdb.connect(str(path), read_only=True)
    try:
        print(f"warehouse={path.relative_to(PROJECT_ROOT)} size_mb={path.stat().st_size / 1024 / 1024:.1f}")
        for table_name, layer, row_count in connection.execute(
            "SELECT table_name, layer, row_count FROM data_asset_registry ORDER BY layer, table_name"
        ).fetchall():
            print(f"{layer:12} {table_name:34} {row_count:>8}")
        errors = connection.execute("SELECT count(*) FROM quality_exceptions WHERE severity='error' AND status='open'").fetchone()[0]
        warnings = connection.execute("SELECT count(*) FROM quality_exceptions WHERE severity='warning'").fetchone()[0]
        print(f"quality_open_errors={errors} known_warnings={warnings}")
    finally:
        connection.close()
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
