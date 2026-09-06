import importlib.util
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gpt_brief_import", ROOT / "scripts" / "gpt_brief_import.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
TZ = ZoneInfo("Asia/Shanghai")


def event(**overrides):
    row = {
        "id": "byte-dance-financing",
        "event_date": "2026-09-05",
        "source_published_at": "2026-09-06T07:00:00+08:00",
        "type": "ai_financing",
        "sourceName": "Reuters",
        "sourceUrl": "https://www.reuters.com/technology/example-story-2026-09-06/",
        "supportingUrls": [],
        "headline": "字节跳动取得新的融资安排",
        "summary": "Reuters 报道了融资规模及期限。",
        "whatChanged": "AI 投资的可用融资规模上升。",
        "expectationGap": "融资侧信号强于此前预期。",
        "affectedCompanies": ["NVDA"],
        "beneficiaries": ["NVDA"],
        "adverselyAffected": [],
        "impactPath": "融资 → AI 投资 → 算力需求",
        "horizon": "2Q–8Q",
        "pricingStatus": "待验证",
        "scoreComponents": {"surprise": 18, "fundamental": 18, "tradability": 14, "breadth": 8, "evidence": 10},
        "confidence": "中",
        "nextCatalyst": "资本开支披露",
        "falsification": "融资未用于 AI 或资本开支不增长",
    }
    row.update(overrides)
    return row


def payload(**overrides):
    value = {"schemaVersion": MODULE.SCHEMA_VERSION, "brief_date": "2026-09-06", "asOf": "2026-09-06T08:00:00+08:00", "events": [event()]}
    value.update(overrides)
    return value


def test_extracts_marked_json_and_derives_reuters_as_tier_b():
    copied = f"日报正文\n{MODULE.START_MARKER}\n```json\n{json.dumps(payload(), ensure_ascii=False)}\n```\n{MODULE.END_MARKER}"
    parsed = MODULE.extract_payload(copied)
    result = MODULE.validate_and_normalize(parsed, datetime(2026, 9, 6, 8, 10, tzinfo=TZ))
    assert result["events"][0]["sourceTier"] == "B"
    assert result["events"][0]["sourceType"] == "media"
    assert result["events"][0]["event_date"] == "2026-09-05"
    assert result["events"][0]["source_published_at"] == "2026-09-05T23:00:00+00:00"
    assert result["events"][0]["score"] == 68
    assert result["events"][0]["verificationStatus"] == "attributed_secondary_report"


def test_rejects_missing_machine_block():
    try:
        MODULE.extract_payload("只有普通日报文字")
    except MODULE.ImportRejected as exc:
        assert MODULE.SCHEMA_VERSION in str(exc)
    else:
        raise AssertionError("plain prose must not be silently interpreted")


def test_rejects_stale_event_and_unknown_source():
    old = payload(events=[event(source_published_at="2026-09-01T07:00:00+08:00")])
    unknown = payload(events=[event(sourceUrl="https://example.com/story")])
    for value in (old, unknown):
        try:
            MODULE.validate_and_normalize(value, datetime(2026, 9, 6, 8, 10, tzinfo=TZ))
        except MODULE.ImportRejected:
            pass
        else:
            raise AssertionError("unreliable event must be rejected")


def test_rejects_date_only_or_brief_time_as_source_publication_time():
    values = [
        payload(events=[event(source_published_at="2026-09-06")]),
        payload(events=[event(source_published_at="2026-09-06T08:00:00+08:00")]),
    ]
    for value in values:
        try:
            MODULE.validate_and_normalize(value, datetime(2026, 9, 6, 8, 10, tzinfo=TZ))
        except MODULE.ImportRejected:
            pass
        else:
            raise AssertionError("brief time must never substitute for source publication time")


def test_rejects_secrets_before_raw_or_public_write():
    try:
        MODULE.reject_sensitive_text("OPENAI_API_KEY=not-a-real-key")
    except MODULE.ImportRejected:
        pass
    else:
        raise AssertionError("secret-like text must be rejected")


def test_end_to_end_private_persist_without_publication():
    copied = f"{MODULE.START_MARKER}\n{json.dumps(payload(), ensure_ascii=False)}\n{MODULE.END_MARKER}"
    original = {name: getattr(MODULE, name) for name in ("ROOT", "PROCESSED_BRIEF", "IMPORT_REPORT", "UPDATE_REPORT", "write_raw_json")}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        def fake_raw(project_root, *, source, entity, payload, request_metadata):
            path = project_root / "data" / "raw" / source / "test.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return path

        try:
            MODULE.ROOT = root
            MODULE.PROCESSED_BRIEF = root / "data/processed/daily_ai_brief.json"
            MODULE.IMPORT_REPORT = root / "data/processed/gpt_brief_import_report.json"
            MODULE.UPDATE_REPORT = root / "data/processed/daily_update_report.json"
            MODULE.write_raw_json = fake_raw
            result = MODULE.import_text(copied, publish=False, imported_at=datetime(2026, 9, 6, 8, 10, tzinfo=TZ))
            assert result["status"] == "ok"
            assert result["runDate"] == "2026-09-06"
            assert result["publication"]["status"] == "skipped"
            assert MODULE.PROCESSED_BRIEF.exists()
            assert (root / "data/standardized/events.csv").exists()
            assert (root / result["rawFile"]).exists()
        finally:
            for name, value in original.items():
                setattr(MODULE, name, value)
