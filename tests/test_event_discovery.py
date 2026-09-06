import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("discover_daily_events", ROOT / "scripts" / "discover_daily_events.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_parse_rss_and_materiality_score():
    xml = """<rss><channel><item><title>New AI model launch</title><link>https://example.com/a</link><description>GPU inference price and availability</description><pubDate>Fri, 04 Sep 2026 00:00:00 GMT</pubDate></item></channel></rss>"""
    rows = MODULE.parse_feed(xml)
    assert rows[0]["url"] == "https://example.com/a"
    assert MODULE.score(rows[0]["title"] + " " + rows[0]["summary"], "A") >= 55
    assert MODULE.has_material_signal(rows[0]["summary"])


def test_gpt_flagship_release_is_never_filtered_as_low_materiality():
    text = "Today we are releasing GPT-6 Astra, our most capable model."
    assert MODULE.score(text, "A") >= 65
    assert MODULE.has_material_signal(text)


def test_old_official_event_is_not_redated_by_site_maintenance(monkeypatch):
    xml = """<rss><channel><item><title>Today we are releasing GPT-6 Astra</title><link>https://openai.com/index/gpt-6-astra/</link><description>New flagship AI model available through the API</description><pubDate>Thu, 03 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>"""
    monkeypatch.setattr(MODULE, "get_text", lambda *args, **kwargs: xml)
    events, _ = MODULE.discover(datetime(2026, 9, 6, 5, tzinfo=timezone.utc), 36)
    assert events == []


def test_official_event_keeps_source_timestamp_and_separate_event_date(monkeypatch):
    xml = """<rss><channel><item><title>New AI model launch</title><link>https://openai.com/index/new-model/</link><description>New flagship model available through the API</description><pubDate>Sun, 06 Sep 2026 00:30:00 GMT</pubDate></item></channel></rss>"""
    monkeypatch.setattr(MODULE, "get_text", lambda *args, **kwargs: xml)
    events, _ = MODULE.discover(datetime(2026, 9, 6, 5, tzinfo=timezone.utc), 36)
    assert events[0]["event_date"] == "2026-09-06"
    assert events[0]["source_published_at"] == "2026-09-06T00:30:00+00:00"
    assert events[0]["sourceType"] == "official"
    assert "publishedDate" not in events[0]
    assert "publishedAt" not in events[0]
