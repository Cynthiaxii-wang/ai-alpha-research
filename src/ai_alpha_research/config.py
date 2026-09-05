from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REQUIRED_KEYS = (
    "GITHUB_TOKEN",
    "HUGGINGFACE_TOKEN",
    "ALPHAVANTAGE_API_KEY",
    "MASSIVE_API_KEY",
    "OPENROUTER_API_KEY",
    "CLOUDFLARE_API_TOKEN",
    "SEC_USER_AGENT",
)


class ConfigurationError(RuntimeError):
    """Raised when a required local configuration value is absent."""


def load_dotenv(path: Path) -> None:
    """Load a minimal KEY=VALUE file without logging secret values."""
    if not path.exists():
        raise ConfigurationError(f"Missing local configuration file: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    project_root: Path
    github_token: str
    huggingface_token: str
    alpha_vantage_api_key: str
    massive_api_key: str
    openrouter_api_key: str
    cloudflare_api_token: str
    sec_user_agent: str

    @classmethod
    def from_project_root(cls, project_root: Path) -> "Settings":
        project_root = project_root.resolve()
        load_dotenv(project_root / ".env")
        missing = [key for key in REQUIRED_KEYS if not os.environ.get(key, "").strip()]
        if missing:
            raise ConfigurationError("Missing required environment variables: " + ", ".join(missing))
        return cls(
            project_root=project_root,
            github_token=os.environ["GITHUB_TOKEN"],
            huggingface_token=os.environ["HUGGINGFACE_TOKEN"],
            alpha_vantage_api_key=os.environ["ALPHAVANTAGE_API_KEY"],
            massive_api_key=os.environ["MASSIVE_API_KEY"],
            openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
            cloudflare_api_token=os.environ["CLOUDFLARE_API_TOKEN"],
            sec_user_agent=os.environ["SEC_USER_AGENT"],
        )

    def configured_key_names(self) -> list[str]:
        return list(REQUIRED_KEYS)
