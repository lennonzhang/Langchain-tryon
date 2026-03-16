from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from json import JSONDecodeError
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TAVILY_BASE_URL = "https://api.tavily.com"
_DEFAULT_TAVILY_TIMEOUT_SECONDS = 15.0
_DEFAULT_TAVILY_SEARCH_DEPTH = "basic"
_DEFAULT_TAVILY_EXTRACT_DEPTH = "advanced"
_DEFAULT_TAVILY_MAX_EXTRACT_RESULTS = 3
_MAX_EXTRACT_RESULTS_LIMIT = 20


def _string_env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _float_env(name: str, default: float, min_value: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= min_value else min_value


def _int_env(name: str, default: int, min_value: int, max_value: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    value = value if value >= min_value else min_value
    if max_value is not None:
        value = min(value, max_value)
    return value


@dataclass(frozen=True)
class TavilySettings:
    api_key: str
    base_url: str
    timeout_seconds: float
    search_depth: str
    extract_depth: str
    max_extract_results: int


def resolve_search_backend() -> str:
    value = os.getenv("SEARCH_BACKEND", "tavily").strip().lower()
    return "legacy" if value == "legacy" else "tavily"


def resolve_tavily_settings() -> TavilySettings:
    timeout_seconds = _float_env(
        "TAVILY_TIMEOUT_SECONDS",
        _float_env(
            "WEB_SEARCH_TOTAL_BUDGET_SECONDS",
            _float_env("WEB_LOADER_TIMEOUT_SECONDS", _DEFAULT_TAVILY_TIMEOUT_SECONDS, 0.1),
            0.1,
        ),
        0.1,
    )
    max_extract_results = _int_env(
        "TAVILY_MAX_EXTRACT_RESULTS",
        _int_env("WEB_LOADER_MAX_PAGES", _DEFAULT_TAVILY_MAX_EXTRACT_RESULTS, 0, _MAX_EXTRACT_RESULTS_LIMIT),
        0,
        _MAX_EXTRACT_RESULTS_LIMIT,
    )
    return TavilySettings(
        api_key=os.getenv("TAVILY_API_KEY", "").strip(),
        base_url=_string_env("TAVILY_BASE_URL", _DEFAULT_TAVILY_BASE_URL).rstrip("/"),
        timeout_seconds=timeout_seconds,
        search_depth=_string_env("TAVILY_SEARCH_DEPTH", _DEFAULT_TAVILY_SEARCH_DEPTH),
        extract_depth=_string_env("TAVILY_EXTRACT_DEPTH", _DEFAULT_TAVILY_EXTRACT_DEPTH),
        max_extract_results=max_extract_results,
    )


def source_domain_for_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    return parsed.netloc.lower()


class TavilyClient:
    def __init__(self, settings: TavilySettings | None = None):
        self._settings = settings or resolve_tavily_settings()
        if not self._settings.api_key:
            raise RuntimeError("Missing TAVILY_API_KEY for SEARCH_BACKEND=tavily.")

    def _post(self, endpoint: str, payload: dict, *, timeout_seconds: float | None = None) -> dict:
        timeout = timeout_seconds if timeout_seconds is not None else self._settings.timeout_seconds
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{self._settings.base_url}{endpoint}",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._settings.api_key}",
                    },
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TimeoutError("Tavily request timed out") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise RuntimeError(f"Tavily {endpoint} failed: status={exc.response.status_code} body={detail}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Tavily {endpoint} failed: {exc}") from exc

        try:
            data = response.json()
        except (ValueError, JSONDecodeError) as exc:
            raise RuntimeError(f"Tavily {endpoint} returned invalid JSON.") from exc
        if isinstance(data, dict):
            request_id = data.get("request_id")
            if request_id:
                logger.debug("Tavily %s request_id=%s", endpoint, request_id)
            return data
        raise RuntimeError(f"Tavily {endpoint} returned a non-object JSON payload.")

    def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        timeout_seconds: float | None = None,
        search_depth: str | None = None,
    ) -> list[dict]:
        payload = {
            "query": query,
            "max_results": max(1, int(max_results)),
            "search_depth": search_depth or self._settings.search_depth,
            "include_raw_content": False,
            "include_answer": False,
        }
        data = self._post("/search", payload, timeout_seconds=timeout_seconds)
        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            raise RuntimeError("Tavily search response did not include a valid results list.")
        return [self._normalize_search_result(item) for item in raw_results if isinstance(item, dict)]

    def extract(
        self,
        urls: list[str],
        *,
        timeout_seconds: float | None = None,
        extract_depth: str | None = None,
    ) -> dict[str, str]:
        normalized_urls = [url.strip() for url in urls if isinstance(url, str) and url.strip()]
        if not normalized_urls:
            return {}

        payload = {
            "urls": normalized_urls,
            "extract_depth": extract_depth or self._settings.extract_depth,
            "include_images": False,
        }
        data = self._post("/extract", payload, timeout_seconds=timeout_seconds)
        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            raise RuntimeError("Tavily extract response did not include a valid results list.")

        extracted: dict[str, str] = {}
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            content = self._extract_text(item)
            if content:
                extracted[url] = content
        return extracted

    @staticmethod
    def _normalize_search_result(item: dict) -> dict:
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or url or "Untitled result").strip()
        snippet = str(item.get("content") or item.get("snippet") or "").strip()
        normalized = {
            "title": title,
            "url": url,
            "snippet": snippet,
            "source_domain": source_domain_for_url(url),
        }
        score = item.get("score")
        if isinstance(score, (int, float)):
            normalized["score"] = float(score)
        published_date = item.get("published_date")
        if isinstance(published_date, str) and published_date.strip():
            normalized["published_date"] = published_date.strip()
        return normalized

    @staticmethod
    def _extract_text(item: dict) -> str:
        for key in ("raw_content", "content", "text", "markdown"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""
