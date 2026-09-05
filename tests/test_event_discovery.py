import importlib.util
import sys
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


def test_openai_sitemap_parser_reads_canonical_url_and_lastmod():
    xml = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://openai.com/index/gpt-6-astra/</loc><lastmod>2026-09-04T05:27:06.192Z</lastmod></url></urlset>"""
    rows = MODULE.parse_sitemap(xml)
    assert rows[0]["url"].endswith("/gpt-6-astra/")
    assert rows[0]["published"].date().isoformat() == "2026-09-04"
