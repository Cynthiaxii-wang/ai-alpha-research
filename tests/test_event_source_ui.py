from pathlib import Path


def test_event_cards_use_explicit_dates_source_types_and_original_url():
    source = (Path(__file__).resolve().parents[1] / "web/src/App.jsx").read_text(encoding="utf-8")
    assert "Official Source" in source
    assert "Media Source" in source
    assert "event.event_date" in source
    assert "event.source_published_at" in source
    assert "href={event.sourceUrl}" in source
