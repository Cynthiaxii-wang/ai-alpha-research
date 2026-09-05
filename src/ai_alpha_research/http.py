from __future__ import annotations

import json
import gzip
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SafeHTTPError(RuntimeError):
    """HTTP error that never includes query strings or credentials."""


def get_text(
    base_url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: int = 45,
    retries: int = 2,
) -> str:
    """Fetch public text while keeping error messages credential-safe."""
    request = Request(base_url, headers=dict(headers or {}), method="GET")
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip" or body[:2] == b"\x1f\x8b":
                    body = gzip.decompress(body)
                charset = response.headers.get_content_charset() or "utf-8"
                return body.decode(charset, errors="replace")
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries:
                raise SafeHTTPError(f"HTTP {exc.code} from {base_url}") from None
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == retries:
                raise SafeHTTPError(f"Network failure from {base_url}: {type(exc).__name__}") from None
        time.sleep(2**attempt)
    raise SafeHTTPError(f"Request failed for {base_url}: {type(last_error).__name__}")


def get_json(
    base_url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: int = 30,
    retries: int = 2,
) -> Any:
    query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = base_url + ("?" + query if query else "")
    request = Request(url, headers=dict(headers or {}), method="GET")
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip" or body[:2] == b"\x1f\x8b":
                    body = gzip.decompress(body)
                return json.loads(body.decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries:
                raise SafeHTTPError(f"HTTP {exc.code} from {base_url}") from None
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == retries:
                raise SafeHTTPError(f"Network failure from {base_url}: {type(exc).__name__}") from None
        time.sleep(2**attempt)
    raise SafeHTTPError(f"Request failed for {base_url}: {type(last_error).__name__}")


def post_json(
    base_url: str,
    payload: Mapping[str, Any],
    *,
    headers: Mapping[str, str] | None = None,
    timeout: int = 60,
    retries: int = 1,
) -> Any:
    """POST JSON without ever placing credentials or request content in errors."""
    request_headers = {"Content-Type": "application/json", **dict(headers or {})}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = Request(base_url, data=body, headers=request_headers, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries:
                raise SafeHTTPError(f"HTTP {exc.code} from {base_url}") from None
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == retries:
                raise SafeHTTPError(f"Network failure from {base_url}: {type(exc).__name__}") from None
        time.sleep(2**attempt)
    raise SafeHTTPError(f"Request failed for {base_url}: {type(last_error).__name__}")
