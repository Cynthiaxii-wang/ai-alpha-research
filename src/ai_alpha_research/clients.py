from __future__ import annotations

from datetime import date
from typing import Any

from .config import Settings
from .http import get_json


class GitHubClient:
    def __init__(self, settings: Settings):
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {settings.github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-alpha-research",
        }

    def public_repositories(self, owner: str, limit: int = 30) -> Any:
        return get_json(
            f"https://api.github.com/users/{owner}/repos",
            params={"type": "public", "sort": "updated", "direction": "desc", "per_page": limit},
            headers=self.headers,
        )

    def commits(self, full_name: str, *, since: str, until: str, page: int = 1, per_page: int = 100) -> Any:
        return get_json(
            f"https://api.github.com/repos/{full_name}/commits",
            params={"since": since, "until": until, "page": page, "per_page": per_page},
            headers=self.headers,
            timeout=60,
        )

    def releases(self, full_name: str, *, per_page: int = 100) -> Any:
        return get_json(
            f"https://api.github.com/repos/{full_name}/releases",
            params={"per_page": per_page},
            headers=self.headers,
            timeout=60,
        )


class HuggingFaceClient:
    def __init__(self, settings: Settings):
        self.headers = {"Authorization": f"Bearer {settings.huggingface_token}"}

    def models(self, author: str, limit: int = 30) -> Any:
        return get_json(
            "https://huggingface.co/api/models",
            params={"author": author, "sort": "downloads", "direction": -1, "limit": limit, "full": "true"},
            headers=self.headers,
        )


class MassiveClient:
    def __init__(self, settings: Settings):
        self.api_key = settings.massive_api_key

    def daily_bars(self, ticker: str, start: date, end: date, *, adjusted: bool = True) -> Any:
        return get_json(
            f"https://api.massive.com/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}",
            params={"adjusted": str(adjusted).lower(), "sort": "asc", "limit": 50000, "apiKey": self.api_key},
            timeout=90,
        )


class AlphaVantageClient:
    def __init__(self, settings: Settings):
        self.api_key = settings.alpha_vantage_api_key

    def earnings(self, ticker: str) -> Any:
        return get_json(
            "https://www.alphavantage.co/query",
            params={"function": "EARNINGS", "symbol": ticker, "apikey": self.api_key},
        )


class SECClient:
    def __init__(self, settings: Settings):
        self.headers = {
            "User-Agent": settings.sec_user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov",
        }

    @staticmethod
    def _cik(cik: str) -> str:
        return str(cik).zfill(10)

    def submissions(self, cik: str) -> Any:
        return get_json(
            f"https://data.sec.gov/submissions/CIK{self._cik(cik)}.json",
            headers=self.headers,
        )

    def company_facts(self, cik: str) -> Any:
        return get_json(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{self._cik(cik)}.json",
            headers=self.headers,
        )

    def company_tickers(self) -> Any:
        headers = {key: value for key, value in self.headers.items() if key != "Host"}
        return get_json("https://www.sec.gov/files/company_tickers.json", headers=headers)


class OpenRouterClient:
    def __init__(self, settings: Settings):
        self.headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}

    def models(self) -> Any:
        return get_json("https://openrouter.ai/api/v1/models", headers=self.headers)

    def rankings_daily(self, *, start_date: date, end_date: date) -> Any:
        return get_json(
            "https://openrouter.ai/api/v1/datasets/rankings-daily",
            params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "period": "day"},
            headers=self.headers,
            timeout=90,
        )


class CloudflareRadarClient:
    def __init__(self, settings: Settings):
        self.headers = {"Authorization": f"Bearer {settings.cloudflare_api_token}"}

    def domain_rank(self, domain: str) -> Any:
        return get_json(
            f"https://api.cloudflare.com/client/v4/radar/ranking/domain/{domain}",
            params={"rankingType": "POPULAR", "includeTopLocations": "false"},
            headers=self.headers,
        )
