from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import duckdb


def warehouse_path(project_root: Path) -> Path:
    return project_root / "data" / "warehouse" / "ai_alpha_research.duckdb"


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def read_table(project_root: Path, table_name: str) -> list[dict[str, str]]:
    """Read a warehouse table in the string-valued shape used by research scripts."""
    path = warehouse_path(project_root)
    if not path.exists():
        raise FileNotFoundError(path)
    if not table_name.replace("_", "").isalnum():
        raise ValueError(f"Unsafe table name: {table_name}")
    connection = duckdb.connect(str(path), read_only=True)
    try:
        cursor = connection.execute(f'SELECT * FROM "{table_name}"')
        columns = [item[0] for item in cursor.description]
        return [{column: _text(value) for column, value in zip(columns, row)} for row in cursor.fetchall()]
    finally:
        connection.close()
