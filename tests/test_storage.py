import json
import tempfile
import unittest
from pathlib import Path

from ai_alpha_research.storage import write_raw_json


class StorageTests(unittest.TestCase):
    def test_raw_storage_redacts_sensitive_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = write_raw_json(
                Path(directory),
                source="test",
                entity="NVDA",
                payload={"ok": True},
                request_metadata={"apikey": "secret", "purpose": "test"},
            )
            envelope = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(envelope["request_metadata"]["apikey"], "***")
            self.assertEqual(envelope["request_metadata"]["purpose"], "test")
            self.assertEqual(len(envelope["content_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
