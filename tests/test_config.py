import os
import tempfile
import unittest
from pathlib import Path

from ai_alpha_research.config import load_dotenv


class ConfigTests(unittest.TestCase):
    def test_load_dotenv_parses_values_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("TEST_AI_ALPHA_KEY=value-with-symbols_123\n", encoding="utf-8")
            os.environ.pop("TEST_AI_ALPHA_KEY", None)
            load_dotenv(env_file)
            self.assertEqual(os.environ["TEST_AI_ALPHA_KEY"], "value-with-symbols_123")


if __name__ == "__main__":
    unittest.main()
