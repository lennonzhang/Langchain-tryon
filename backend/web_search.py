"""Web search via DuckDuckGo for context injection."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
import logging
import os
import re
import time
import warnings

import requests

logger = logging.getLogger(__name__)

_DEFAULT_WEB_LOADER_TIMEOUT_SECONDS = 2.0
_DEFAULT_WEB_SEARCH_TOTAL_BUDGET_SECONDS = 4.0
_DEFAULT_WEB_LOADER_MAX_PAGES = 3
_DEFAULT_WEB_LOADER_CONCURRENCY = 3


def _float_env(name: str, default: float, min_value: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= min_value else min_value


def _int_env(name: str, default: int, min_value: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= min_value else min_value


def _normalize_text(value: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip()
    if max_chars <= 0:
        return text
    return text[:max_chars]


def _extract_with_bs4(html: str, max_chars: int) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return _normalize_text(html, max_chars=max_chars)

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return _normalize_text(text, max_chars=max_chars)


def _fetch_with_requests(url: str, max_chars: int, timeout: float = 8.0) -> str:
    headers = {"User-Agent": "langchain-tryon/1.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return _extract_with_bs4(resp.text, max_chars=max_chars)
    except requests.exceptions.SSLError:
        # Some sites have broken cert chains / hostname mismatch.
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
            resp.raise_for_status()
            return _extract_with_bs4(resp.text, max_chars=max_chars)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Requests fallback failed for %s: %s", url, exc)
            return ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("Requests fallback failed for %s: %s", url, exc)
        return ""


def load_webpage_content(url: str, max_chars: int = 1800, timeout_s: float = 8.0) -> str:
    """Load and trim webpage text content using LangChain WebBaseLoader."""
    try:
        from langchain_community.document_loaders import WebBaseLoader
    except ImportError:
        logger.warning("langchain-community not installed; skip webpage loading.")
        return ""

    try:
        try:
            loader = WebBaseLoader(url, requests_kwargs={"timeout": timeout_s})
        except TypeError:
            loader = WebBaseLoader(web_paths=(url,), requests_kwargs={"timeout": timeout_s})
        docs = loader.load()
    except Exception as exc:  # noqa: BLE001
        logger.warning("WebBaseLoader failed for %s: %s", url, exc)
        return _fetch_with_requests(url, max_chars=max_chars, timeout=timeout_s)

    parts = []
    for doc in docs or []:
        page = getattr(doc, "page_content", "")
        if isinstance(page, str) and page.strip():
            parts.append(page)

    merged = _normalize_text("\n".join(parts), max_chars=max_chars)
    if merged:
        return merged
    return _fetch_with_requests(url, max_chars=max_chars, timeout=timeout_s)


def web_search(
    query: str,
    num_results: int = 5,
    include_page_content: bool = True,
    page_timeout_s: float | None = None,
    total_budget_s: float | None = None,
    max_pages: int | None = None,
    concurrency: int | None = None,
) -> list[dict]:
    """Return a list of ``{title, url, snippet}`` dicts, or ``[]`` on failure."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        logger.error("duckduckgo-search not installed. pip install duckduckgo-search")
        return []

    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=num_results))
        results = [
            {
                "title": h.get("title", ""),
                "url": h.get("href", ""),
                "snippet": h.get("body", ""),
            }
            for h in hits
        ]
        if include_page_content:
            effective_timeout = (
                page_timeout_s
                if page_timeout_s is not None
                else _float_env(
                    "WEB_LOADER_TIMEOUT_SECONDS",
                    _DEFAULT_WEB_LOADER_TIMEOUT_SECONDS,
                    0.1,
                )
            )
            effective_budget = (
                total_budget_s
                if total_budget_s is not None
                else _float_env(
                    "WEB_SEARCH_TOTAL_BUDGET_SECONDS",
                    _DEFAULT_WEB_SEARCH_TOTAL_BUDGET_SECONDS,
                    0.1,
                )
            )
            effective_max_pages = (
                max_pages
                if max_pages is not None
                else _int_env("WEB_LOADER_MAX_PAGES", _DEFAULT_WEB_LOADER_MAX_PAGES, 0)
            )
            effective_concurrency = (
                concurrency
                if concurrency is not None
                else _int_env("WEB_LOADER_CONCURRENCY", _DEFAULT_WEB_LOADER_CONCURRENCY, 1)
            )

            candidates: list[tuple[int, str]] = []
            for idx, item in enumerate(results[:effective_max_pages]):
                url = item.get("url", "")
                if url:
                    candidates.append((idx, url))

            if candidates:
                workers = min(effective_concurrency, len(candidates))
                executor = ThreadPoolExecutor(max_workers=workers)
                started_at = time.monotonic()
                future_to_index = {
                    executor.submit(
                        load_webpage_content,
                        url,
                        max_chars=1800,
                        timeout_s=effective_timeout,
                    ): idx
                    for idx, url in candidates
                }
                try:
                    for future in as_completed(future_to_index, timeout=effective_budget):
                        idx = future_to_index[future]
                        try:
                            content = future.result()
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("Parallel page loading failed: %s", exc)
                            continue
                        if content:
                            results[idx]["content"] = content
                except FuturesTimeoutError:
                    elapsed = max(0.0, time.monotonic() - started_at)
                    logger.info(
                        "Web page loading budget exceeded for query '%s' (%.2fs/%.2fs).",
                        query,
                        elapsed,
                        effective_budget,
                    )
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)
        return results
    except Exception as exc:
        logger.error("DuckDuckGo search error: %s", exc)
        return []


def format_search_context(query: str, results: list[dict]) -> str:
    """Format search results into a system message for LLM context injection."""
    if not results:
        return ""

    lines = [f'The user enabled web search. Here are search results for "{query}":\n']
    for i, r in enumerate(results, 1):
        entry = f"[{i}] {r.get('title', '')}"
        url = r.get("url", "")
        if url:
            entry += f"\n    URL: {url}"
        snippet = r.get("snippet", "")
        if snippet:
            entry += f"\n    {snippet}"
        content = r.get("content", "")
        if content:
            entry += f"\n    Page content: {content}"
        lines.append(entry)

    lines.append(
        "\nUse the above search results to inform your answer. "
        "Cite sources with [N] notation when referencing specific results. "
        "If the search results are not relevant, you may ignore them."
    )
    return "\n".join(lines)
