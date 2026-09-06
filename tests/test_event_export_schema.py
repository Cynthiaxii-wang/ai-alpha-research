import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("event_export_schema", ROOT / "scripts" / "export_web_data.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_legacy_event_clocks_migrate_without_redating_from_generation_time():
    result = MODULE.normalize_event_brief({
        "asOf": "2026-09-06T08:00:00+08:00",
        "generatedAt": "2026-09-06T12:00:00+08:00",
        "events": [{
            "id": "old-event", "publishedDate": "2026-09-03",
            "publishedAt": "2026-09-03T12:00:00+00:00", "sourceTier": "A",
        }],
    })
    assert result["brief_date"] == "2026-09-06"
    assert result["events"][0]["event_date"] == "2026-09-03"
    assert result["events"][0]["source_published_at"] == "2026-09-03T12:00:00+00:00"
    assert result["events"][0]["sourceType"] == "official"
    assert "publishedDate" not in result["events"][0]
    assert "publishedAt" not in result["events"][0]


def test_missing_event_date_is_not_filled_from_dashboard_or_brief_time():
    result = MODULE.normalize_event_brief({
        "asOf": "2026-09-06T08:00:00+08:00",
        "generatedAt": "2026-09-06T12:00:00+08:00",
        "events": [{"id": "ambiguous", "source_published_at": "2026-09-06T01:00:00Z", "sourceTier": "B"}],
    })
    assert result["events"] == []
