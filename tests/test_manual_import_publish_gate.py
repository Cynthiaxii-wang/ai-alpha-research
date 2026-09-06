import importlib.util
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("publish_public_dashboard_test", ROOT / "scripts" / "publish_public_dashboard.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_manual_import_requires_current_validated_audit():
    names = ("UPDATE_REPORT", "QUALITY_REPORT", "DAILY_BRIEF", "GPT_IMPORT_REPORT")
    original = {name: getattr(MODULE, name) for name in names}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        try:
            for name in names:
                setattr(MODULE, name, root / f"{name.lower()}.json")
            write(MODULE.UPDATE_REPORT, {"runDate": "2026-09-06", "tasks": [{"task": "gpt_brief_import", "status": "ok"}, {"task": "research_pipeline", "status": "ok"}], "failed": []})
            write(MODULE.QUALITY_REPORT, {"status": "pass", "generated_at": "2026-09-06T01:00:00+00:00"})
            write(MODULE.DAILY_BRIEF, {"importMethod": "manual_chatgpt_copy", "events": [{"verificationStatus": "attributed_secondary_report"}]})
            write(MODULE.GPT_IMPORT_REPORT, {"status": "validated", "runDate": "2026-09-06", "importedEvents": 1})
            MODULE.verify_release_gates(date(2026, 9, 6))
            write(MODULE.GPT_IMPORT_REPORT, {"status": "rejected", "runDate": "2026-09-06", "importedEvents": 1})
            try:
                MODULE.verify_release_gates(date(2026, 9, 6))
            except MODULE.PublishBlocked as exc:
                assert "not_validated" in str(exc)
            else:
                raise AssertionError("rejected manual import must block publishing")
        finally:
            for name, value in original.items():
                setattr(MODULE, name, value)


def test_missing_brief_or_failed_event_refresh_does_not_block_other_data():
    names = ("UPDATE_REPORT", "QUALITY_REPORT", "DAILY_BRIEF", "GPT_IMPORT_REPORT")
    original = {name: getattr(MODULE, name) for name in names}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        try:
            for name in names:
                setattr(MODULE, name, root / f"{name.lower()}.json")
            write(MODULE.UPDATE_REPORT, {
                "runDate": "2026-09-06",
                "tasks": [{"task": "ai_events", "status": "failed"}, {"task": "research_pipeline", "status": "ok"}],
                "failed": ["ai_events"], "blockingFailed": [], "nonBlockingFailed": ["ai_events"],
            })
            write(MODULE.QUALITY_REPORT, {"status": "pass", "generated_at": "2026-09-06T01:00:00+00:00"})
            assert not MODULE.DAILY_BRIEF.exists()
            MODULE.verify_release_gates(date(2026, 9, 6))
        finally:
            for name, value in original.items():
                setattr(MODULE, name, value)
