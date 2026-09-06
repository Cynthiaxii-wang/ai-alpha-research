#!/usr/bin/env python3
"""Frequency-aware updater for the AI alpha research platform."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "processed" / "daily_update_state.json"
LOCK_PATH = ROOT / "data" / "processed" / "daily_update.lock"
TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class Task:
    name: str
    frequency: str
    command: tuple[str, ...]
    weekdays_only: bool = False


def tasks_for(run_date: date) -> list[Task]:
    end = run_date.isoformat()
    py = sys.executable
    scripts = ROOT / "scripts"
    tasks = [
        Task("ai_events", "daily", (py, str(scripts / "discover_daily_events.py"), "--hours", "72" if run_date.weekday() == 0 else "36")),
        Task("market_prices", "daily", (py, str(scripts / "ingest_research_universe.py"), "--start", "2024-10-01", "--end", end, "--sources", "massive"), True),
        Task("benchmark_prices", "daily", (py, str(scripts / "ingest_benchmarks.py"), "--start", "2024-10-01", "--end", end), True),
        Task("filings", "daily", (py, str(scripts / "ingest_research_universe.py"), "--start", "2024-10-01", "--end", end, "--sources", "sec"), True),
        Task("earnings_estimates", "daily", (py, str(scripts / "ingest_earnings_estimates.py")), True),
        Task("alternative_usage", "daily", (py, str(scripts / "ingest_alternative_usage.py"))),
        Task("developer_and_model_data", "weekly", (py, str(scripts / "ingest_research_universe.py"), "--start", "2024-10-01", "--end", end, "--sources", "github", "huggingface", "openrouter")),
        # Weekly jobs run on Sunday. Do not mark this task weekdays_only,
        # otherwise it can never become due.
        Task("unadjusted_prices", "weekly", (py, str(scripts / "ingest_unadjusted_prices.py"), "--start", "2024-10-01", "--end", end)),
        Task("research_pipeline", "daily", (py, str(scripts / "run_research_pipeline.py"))),
    ]
    return tasks


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"tasks": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"tasks": {}}


def is_due(task: Task, run_date: date, state: dict, force: bool) -> bool:
    if force:
        return not task.weekdays_only or run_date.weekday() < 5
    if task.weekdays_only and run_date.weekday() >= 5:
        return False
    last = state.get("tasks", {}).get(task.name, {}).get("last_success_date")
    if last == run_date.isoformat():
        return False
    if task.frequency == "weekly" and run_date.weekday() != 6:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Update event, market and research data at appropriate frequencies.")
    parser.add_argument("--date", type=date.fromisoformat, default=datetime.now(TZ).date())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", nargs="+", help="Run only named tasks.")
    args = parser.parse_args()
    state = load_state()
    selected = [task for task in tasks_for(args.date) if is_due(task, args.date, state, args.force)]
    if args.only:
        requested = set(args.only)
        selected = [task for task in selected if task.name in requested]
    print(f"run_date={args.date} mode={'dry-run' if args.dry_run else 'live'}")
    for task in selected:
        print(f"{'PLAN' if args.dry_run else 'RUN '} {task.name} [{task.frequency}]")
    if args.dry_run:
        return 0
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
    except FileExistsError:
        print("another update is already running", file=sys.stderr)
        return 2
    failed = []
    run_rows = []
    try:
        for task in selected:
            started = time.monotonic()
            result = subprocess.run(task.command, cwd=ROOT, text=True)
            row = {"status": "ok" if result.returncode == 0 else "failed", "last_run_at": datetime.now(TZ).isoformat(), "duration_seconds": round(time.monotonic() - started, 2)}
            if result.returncode == 0:
                row["last_success_date"] = args.date.isoformat()
            else:
                failed.append(task.name)
            state.setdefault("tasks", {})[task.name] = {**state.get("tasks", {}).get(task.name, {}), **row}
            run_rows.append({"task": task.name, **row})
            STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = ROOT / "data" / "processed" / "daily_update_report.json"
        report.write_text(json.dumps({"runDate": args.date.isoformat(), "tasks": run_rows, "failed": failed}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        LOCK_PATH.unlink(missing_ok=True)
    print(f"completed={len(run_rows) - len(failed)} failed={len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
