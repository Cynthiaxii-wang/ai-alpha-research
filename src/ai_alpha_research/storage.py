from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SENSITIVE_KEYS = {"apikey", "api_key", "token", "authorization", "key"}


def _sanitize(mapping: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        key: "***" if key.lower() in SENSITIVE_KEYS else value
        for key, value in (mapping or {}).items()
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def write_raw_json(
    project_root: Path,
    *,
    source: str,
    entity: str,
    payload: Any,
    request_metadata: Mapping[str, Any] | None = None,
) -> Path:
    retrieved_at = utc_now()
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    envelope = {
        "source": source,
        "entity": entity,
        "retrieved_at": retrieved_at.isoformat(),
        "content_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "request_metadata": _sanitize(request_metadata),
        "payload": payload,
    }
    target_dir = project_root / "data" / "raw" / source / retrieved_at.date().isoformat()
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_entity = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in entity)
    target = target_dir / f"{safe_entity}_{retrieved_at.strftime('%H%M%S%f')}.json"
    fd, temporary_name = tempfile.mkstemp(prefix=".tmp_", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(envelope, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return target

