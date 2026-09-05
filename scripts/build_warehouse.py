#!/usr/bin/env python3
"""Build an atomic local DuckDB warehouse with provenance and quality metadata."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_alpha_research.warehouse import warehouse_path  # noqa: E402


def safe_name(value: str) -> str:
    name = "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")
    if not name or name[0].isdigit():
        name = "t_" + name
    return name


def record_count(payload) -> int | None:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("data", "results", "estimates", "quarterlyEarnings"):
            if isinstance(payload.get(key), list):
                return len(payload[key])
    return None


def raw_manifest_rows(root: Path) -> list[tuple]:
    rows = []
    for path in sorted((root / "data" / "raw").glob("**/*.json")):
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            payload = envelope.get("payload")
            rows.append((
                str(path.relative_to(root)), envelope.get("source"), envelope.get("entity"),
                envelope.get("retrieved_at"), envelope.get("content_sha256"), path.stat().st_size,
                type(payload).__name__, record_count(payload),
                json.dumps(envelope.get("request_metadata") or {}, ensure_ascii=False, separators=(",", ":")),
                "ok", None,
            ))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append((str(path.relative_to(root)), None, None, None, None, path.stat().st_size, None, None, "{}", "invalid", type(exc).__name__))
    return rows


def ingestion_rows(root: Path) -> list[tuple]:
    rows = []
    for path in sorted((root / "data" / "processed").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        records = payload if isinstance(payload, list) else payload.get("tasks") if isinstance(payload, dict) and isinstance(payload.get("tasks"), list) else [payload]
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                record = {"value": record}
            rows.append((
                str(path.relative_to(root)), index, record.get("task"), record.get("source"),
                record.get("entity"), record.get("status"), record.get("last_run_at") or record.get("generated_at"),
                record.get("raw_file"), record.get("error"), json.dumps(record, ensure_ascii=False, separators=(",", ":")),
            ))
    return rows


def quality_rows(root: Path) -> list[tuple]:
    path = root / "data" / "research" / "research_quality_report.json"
    if not path.exists():
        return []
    report = json.loads(path.read_text(encoding="utf-8"))
    generated = report.get("generated_at")
    rows = [(generated, "failure", item, "error", None, "open") for item in report.get("failures") or []]
    for key, value in (report.get("duplicate_checks") or {}).items():
        if value:
            rows.append((generated, "duplicate", key, "error", str(value), "open"))
    for ticker, value in (report.get("company_benchmark_date_mismatches") or {}).items():
        if value:
            rows.append((generated, "date_alignment", ticker, "error", str(value), "open"))
    for item in report.get("known_research_limitations") or []:
        rows.append((generated, "research_limitation", item, "warning", None, "known"))
    return rows


def factor_rows(root: Path) -> list[tuple]:
    path = root / "research" / "results" / "hypothesis_results.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    generated = payload.get("generated_at")
    rows = []
    lab = payload.get("factor_lab") or {}
    for category, cards in lab.items():
        for card in cards or []:
            rows.append((generated, category, card.get("experiment_id"), card.get("name"), card.get("verdict"), card.get("conclusion"), card.get("next_action"), json.dumps(card, ensure_ascii=False, separators=(",", ":"))))
    return rows


def create_table_from_csv(connection, table_name: str, path: Path) -> int:
    connection.execute(
        f"CREATE OR REPLACE TABLE \"{table_name}\" AS SELECT * FROM read_csv_auto(?, header=true, sample_size=-1, nullstr='')",
        [str(path)],
    )
    return connection.execute(f'SELECT count(*) FROM "{table_name}"').fetchone()[0]


def main() -> int:
    target = warehouse_path(PROJECT_ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".ai_alpha_", suffix=".duckdb", dir=target.parent)
    os.close(descriptor)
    os.unlink(temporary_name)
    loaded_at = datetime.now(timezone.utc).isoformat()
    assets = []
    connection = duckdb.connect(temporary_name)
    try:
        csv_assets = []
        for path in sorted((PROJECT_ROOT / "data" / "standardized").glob("*.csv")):
            csv_assets.append((path.stem, "standardized", path))
        for path in sorted((PROJECT_ROOT / "data" / "research").glob("*.csv")):
            csv_assets.append((path.stem, "research", path))
        csv_assets.extend([
            ("company_master", "config", PROJECT_ROOT / "config" / "research_universe.csv"),
            ("source_registry", "catalog", PROJECT_ROOT / "config" / "source_registry_v1.csv"),
            ("data_dictionary", "catalog", PROJECT_ROOT / "data_dictionary_v1.csv"),
            ("ai_product_domains", "config", PROJECT_ROOT / "config" / "ai_product_domains.csv"),
        ])
        for name, layer, path in csv_assets:
            if path.exists():
                count = create_table_from_csv(connection, safe_name(name), path)
                assets.append((safe_name(name), layer, str(path.relative_to(PROJECT_ROOT)), count, loaded_at))

        connection.execute("CREATE TABLE raw_manifest(raw_file VARCHAR, source VARCHAR, entity VARCHAR, retrieved_at TIMESTAMPTZ, content_sha256 VARCHAR, file_size_bytes BIGINT, payload_type VARCHAR, record_count BIGINT, request_metadata_json JSON, parse_status VARCHAR, parse_error VARCHAR)")
        connection.executemany("INSERT INTO raw_manifest VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", raw_manifest_rows(PROJECT_ROOT))
        connection.execute("CREATE VIEW latest_raw_by_source_entity AS SELECT * EXCLUDE(row_number) FROM (SELECT *, row_number() OVER(PARTITION BY source, entity ORDER BY retrieved_at DESC) row_number FROM raw_manifest WHERE parse_status='ok') WHERE row_number=1")

        connection.execute("CREATE TABLE ingestion_log(report_file VARCHAR, record_index INTEGER, task VARCHAR, source VARCHAR, entity VARCHAR, status VARCHAR, run_at TIMESTAMPTZ, raw_file VARCHAR, error VARCHAR, details_json JSON)")
        rows = ingestion_rows(PROJECT_ROOT)
        if rows:
            connection.executemany("INSERT INTO ingestion_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

        connection.execute("CREATE TABLE quality_exceptions(generated_at TIMESTAMPTZ, category VARCHAR, item VARCHAR, severity VARCHAR, value VARCHAR, status VARCHAR)")
        rows = quality_rows(PROJECT_ROOT)
        if rows:
            connection.executemany("INSERT INTO quality_exceptions VALUES (?, ?, ?, ?, ?, ?)", rows)

        connection.execute("CREATE TABLE factor_results(generated_at TIMESTAMPTZ, category VARCHAR, experiment_id VARCHAR, factor_name VARCHAR, verdict VARCHAR, conclusion VARCHAR, next_action VARCHAR, result_json JSON)")
        rows = factor_rows(PROJECT_ROOT)
        if rows:
            connection.executemany("INSERT INTO factor_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)

        assets.extend([
            ("raw_manifest", "provenance", "data/raw/**/*.json", connection.execute("SELECT count(*) FROM raw_manifest").fetchone()[0], loaded_at),
            ("ingestion_log", "operations", "data/processed/*.json", connection.execute("SELECT count(*) FROM ingestion_log").fetchone()[0], loaded_at),
            ("quality_exceptions", "quality", "data/research/research_quality_report.json", connection.execute("SELECT count(*) FROM quality_exceptions").fetchone()[0], loaded_at),
            ("factor_results", "research", "research/results/hypothesis_results.json", connection.execute("SELECT count(*) FROM factor_results").fetchone()[0], loaded_at),
        ])
        connection.execute("CREATE TABLE data_asset_registry(table_name VARCHAR, layer VARCHAR, source_path VARCHAR, row_count BIGINT, loaded_at TIMESTAMPTZ)")
        connection.executemany("INSERT INTO data_asset_registry VALUES (?, ?, ?, ?, ?)", assets)
        connection.execute("CREATE TABLE warehouse_metadata(key VARCHAR PRIMARY KEY, value VARCHAR)")
        connection.executemany("INSERT INTO warehouse_metadata VALUES (?, ?)", [("schema_version", "1"), ("built_at", loaded_at), ("project", "ai_alpha_research")])
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    os.replace(temporary_name, target)
    print(f"warehouse={target.relative_to(PROJECT_ROOT)} tables={len(assets)} raw_files={next(row[3] for row in assets if row[0] == 'raw_manifest')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
