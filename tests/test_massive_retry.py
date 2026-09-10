from datetime import date
from types import SimpleNamespace

from ai_alpha_research import clients


def test_massive_retries_transient_308(monkeypatch):
    calls = []

    def fake_get_json(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            raise clients.SafeHTTPError("HTTP 308 from https://api.massive.com/v2/aggs/ticker/TSM")
        return {"status": "DELAYED", "results": []}

    monkeypatch.setattr(clients, "get_json", fake_get_json)
    monkeypatch.setattr(clients.time, "sleep", lambda seconds: None)
    client = clients.MassiveClient(SimpleNamespace(massive_api_key="test"))
    client._last_request_at = -100.0

    result = client.daily_bars("TSM", date(2026, 9, 1), date(2026, 9, 10))

    assert result["status"] == "DELAYED"
    assert len(calls) == 2


def test_massive_does_not_retry_permanent_http_error(monkeypatch):
    calls = []

    def fake_get_json(*args, **kwargs):
        calls.append((args, kwargs))
        raise clients.SafeHTTPError("HTTP 401 from https://api.massive.com/v2/aggs/ticker/TSM")

    monkeypatch.setattr(clients, "get_json", fake_get_json)
    monkeypatch.setattr(clients.time, "sleep", lambda seconds: None)
    client = clients.MassiveClient(SimpleNamespace(massive_api_key="test"))
    client._last_request_at = -100.0

    try:
        client.daily_bars("TSM", date(2026, 9, 1), date(2026, 9, 10))
    except clients.SafeHTTPError:
        pass
    else:
        raise AssertionError("permanent authentication errors must not be retried")

    assert len(calls) == 1
