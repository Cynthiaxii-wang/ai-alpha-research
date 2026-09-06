from datetime import date
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("daily_update", ROOT / "scripts" / "daily_update.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_weekday_plan_excludes_weekly_tasks():
    run_date = date(2026, 9, 4)  # Friday
    names = {task.name for task in MODULE.tasks_for(run_date) if MODULE.is_due(task, run_date, {"tasks": {}}, False)}
    assert "ai_events" in names
    assert "market_prices" in names
    assert "developer_and_model_data" not in names


def test_sunday_plan_keeps_events_and_weekly_but_skips_market():
    run_date = date(2026, 9, 6)
    names = {task.name for task in MODULE.tasks_for(run_date) if MODULE.is_due(task, run_date, {"tasks": {}}, False)}
    assert "ai_events" in names
    assert "developer_and_model_data" in names
    assert "unadjusted_prices" in names
    assert "market_prices" not in names


def test_successful_task_is_not_repeated_same_day():
    run_date = date(2026, 9, 4)
    state = {"tasks": {"ai_events": {"last_success_date": "2026-09-04"}}}
    task = next(task for task in MODULE.tasks_for(run_date) if task.name == "ai_events")
    assert not MODULE.is_due(task, run_date, state, False)


def test_event_failure_does_not_block_other_dashboard_publication():
    blocking, non_blocking = MODULE.partition_publication_failures(["ai_events"])
    assert blocking == []
    assert non_blocking == ["ai_events"]
    blocking, non_blocking = MODULE.partition_publication_failures(["ai_events", "market_prices"])
    assert blocking == ["market_prices"]
