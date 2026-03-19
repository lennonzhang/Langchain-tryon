"""Web search via Tavily-first with a temporary legacy fallback."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import re
import time
import warnings
from urllib.parse import urlparse

import httpx
import requests

from backend.infrastructure.search.tavily_client import TavilyClient, resolve_search_backend, resolve_tavily_settings

logger = logging.getLogger(__name__)

_DEFAULT_WEB_LOADER_TIMEOUT_SECONDS = 10.0
_DEFAULT_WEB_SEARCH_TOTAL_BUDGET_SECONDS = 15.0
_DEFAULT_WEB_LOADER_CONNECT_TIMEOUT = 5.0
_DEFAULT_WEB_LOADER_MAX_PAGES = 3
_DEFAULT_WEB_LOADER_CONCURRENCY = 3
_DEFAULT_MAX_FORMAT_RESULTS = 5
_MAX_SNIPPET_CHARS = 240
_MAX_CONTENT_CHARS = 600

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


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


_MAX_CONTEXT_CHARS = _int_env("SEARCH_CONTEXT_MAX_CHARS", 3200, 500)


def _normalize_text(value: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip()
    if max_chars <= 0:
        return text
    return text[:max_chars]


def _resolved_search_timeout() -> float:
    return resolve_tavily_settings().timeout_seconds


def _resolved_extract_limit(max_pages: int | None = None) -> int:
    if max_pages is not None:
        return max(0, min(int(max_pages), 20))
    return resolve_tavily_settings().max_extract_results


def _resolved_extract_timeout(page_timeout_s: float | None = None) -> float:
    if page_timeout_s is not None and page_timeout_s > 0:
        return page_timeout_s
    return resolve_tavily_settings().extract_timeout_seconds


def _resolved_total_budget(total_budget_s: float | None = None) -> float | None:
    if total_budget_s is not None and total_budget_s > 0:
        return total_budget_s
    raw = os.getenv("WEB_SEARCH_TOTAL_BUDGET_SECONDS", "").strip()
    if not raw:
        return None
    return _float_env(
        "WEB_SEARCH_TOTAL_BUDGET_SECONDS",
        _DEFAULT_WEB_SEARCH_TOTAL_BUDGET_SECONDS,
        0.1,
    )


def _resolved_load_timeout(timeout_s: float | None = None) -> float:
    if timeout_s is not None and timeout_s > 0:
        return timeout_s
    if resolve_search_backend() == "legacy":
        return _float_env(
            "WEB_LOADER_TIMEOUT_SECONDS",
            _DEFAULT_WEB_LOADER_TIMEOUT_SECONDS,
            0.1,
        )
    return resolve_tavily_settings().extract_timeout_seconds


def _source_domain(url: str) -> str:
    return urlparse((url or "").strip()).netloc.lower()


def _extract_with_bs4(html: str, max_chars: int) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return _normalize_text(html, max_chars=max_chars)

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return _normalize_text(text, max_chars=max_chars)


def _extract_text(html: str, max_chars: int) -> str:
    """Extract main content from HTML, preferring trafilatura over bs4."""
    try:
        import trafilatura
        text = trafilatura.extract(html)
        if text:
            return _normalize_text(text, max_chars=max_chars)
    except Exception:  # noqa: BLE001
        pass
    return _extract_with_bs4(html, max_chars=max_chars)


def _fetch_with_requests(url: str, max_chars: int, timeout: float = 10.0) -> str:
    """Fallback loader using requests + trafilatura/bs4."""
    headers = {"User-Agent": _BROWSER_UA}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return _extract_text(resp.text, max_chars=max_chars)
    except requests.exceptions.SSLError:
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
            resp.raise_for_status()
            return _extract_text(resp.text, max_chars=max_chars)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Requests fallback failed for %s: %s", url, exc)
            return ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("Requests fallback failed for %s: %s", url, exc)
        return ""


# ---------------------------------------------------------------------------
# Async page loading with httpx
# ---------------------------------------------------------------------------

async def _fetch_page_async(
    client: httpx.AsyncClient,
    url: str,
    max_chars: int,
    sem: asyncio.Semaphore,
) -> str:
    """Fetch a single page using httpx, extract text with trafilatura/bs4."""
    async with sem:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return _extract_text(resp.text, max_chars=max_chars)
        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP %s for %s", exc.response.status_code, url)
            return ""
        except Exception as exc:  # noqa: BLE001
            # Try with SSL verification disabled
            try:
                resp = await client.get(url, extensions={"verify": False})
                resp.raise_for_status()
                return _extract_text(resp.text, max_chars=max_chars)
            except Exception as inner_exc:  # noqa: BLE001
                logger.warning("httpx failed for %s: %s (ssl retry: %s)", url, exc, inner_exc)
                return ""


async def _load_pages_async(
    urls: list[str],
    read_timeout: float,
    connect_timeout: float,
    budget_s: float,
    max_chars: int,
    concurrency: int,
) -> dict[str, str]:
    """Concurrently load multiple pages with httpx async."""
    sem = asyncio.Semaphore(concurrency)
    timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=5.0, pool=5.0)
    results: dict[str, str] = {}

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": _BROWSER_UA},
    ) as client:
        tasks = {
            url: asyncio.create_task(
                asyncio.wait_for(
                    _fetch_page_async(client, url, max_chars, sem),
                    timeout=read_timeout,
                )
            )
            for url in urls
        }

        done, pending = await asyncio.wait(
            tasks.values(), timeout=budget_s
        )

        for task in pending:
            task.cancel()

        for url, task in tasks.items():
            if task in done and not task.cancelled():
                try:
                    content = task.result()
                    if content:
                        results[url] = content
                except Exception:  # noqa: BLE001
                    pass

    return results


def _load_pages_sync(
    urls: list[str],
    read_timeout: float,
    connect_timeout: float,
    budget_s: float,
    max_chars: int,
    concurrency: int,
) -> dict[str, str]:
    """Synchronous wrapper around async page loader."""
    coro = _load_pages_async(urls, read_timeout, connect_timeout, budget_s, max_chars, concurrency)
    try:
        asyncio.get_running_loop()
        # Already in async context (e.g. FastAPI), run in a thread
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=budget_s + 5)
    except RuntimeError:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Public API (signatures unchanged)
# ---------------------------------------------------------------------------

def _legacy_load_webpage_content(url: str, max_chars: int = 1800, timeout_s: float = 10.0) -> str:
    """Load and trim webpage text content. Drop-in replacement for the old WebBaseLoader path."""
    try:
        result = _load_pages_sync(
            urls=[url],
            read_timeout=timeout_s,
            connect_timeout=_DEFAULT_WEB_LOADER_CONNECT_TIMEOUT,
            budget_s=timeout_s + 2,
            max_chars=max_chars,
            concurrency=1,
        )
        content = result.get(url, "")
        if content:
            return content
    except Exception as exc:  # noqa: BLE001
        logger.warning("httpx loader failed for %s: %s", url, exc)

    return _fetch_with_requests(url, max_chars=max_chars, timeout=timeout_s)


def _legacy_web_search(
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
                urls = [url for _, url in candidates]
                idx_map = {url: idx for idx, url in candidates}

                loaded = _load_pages_sync(
                    urls=urls,
                    read_timeout=effective_timeout,
                    connect_timeout=_float_env(
                        "WEB_LOADER_CONNECT_TIMEOUT",
                        _DEFAULT_WEB_LOADER_CONNECT_TIMEOUT,
                        0.1,
                    ),
                    budget_s=effective_budget,
                    max_chars=1800,
                    concurrency=effective_concurrency,
                )

                for url, content in loaded.items():
                    idx = idx_map[url]
                    results[idx]["content"] = content

        return results
    except Exception as exc:
        logger.error("DuckDuckGo search error: %s", exc)
        return []


def load_webpage_content(url: str, max_chars: int = 1800, timeout_s: float | None = None) -> str:
    resolved_timeout = _resolved_load_timeout(timeout_s)
    if resolve_search_backend() == "legacy":
        return _legacy_load_webpage_content(url, max_chars=max_chars, timeout_s=resolved_timeout)

    client = TavilyClient()
    try:
        extracted = client.extract(
            [url],
            timeout_seconds=resolved_timeout + 5.0,
            api_timeout_seconds=resolved_timeout,
        )
        return _normalize_text(extracted.get(url, ""), max_chars=max_chars)
    finally:
        client.close()


def web_search(
    query: str,
    num_results: int = 5,
    include_page_content: bool = True,
    page_timeout_s: float | None = None,
    total_budget_s: float | None = None,
    max_pages: int | None = None,
    concurrency: int | None = None,
) -> list[dict]:
    if resolve_search_backend() == "legacy":
        return _legacy_web_search(
            query,
            num_results=num_results,
            include_page_content=include_page_content,
            page_timeout_s=page_timeout_s,
            total_budget_s=total_budget_s,
            max_pages=max_pages,
            concurrency=concurrency,
        )

    _ = concurrency  # Deprecated compatibility knob; Tavily paths do not use local fetch concurrency.
    search_timeout_s = _resolved_search_timeout()
    extract_timeout_s = _resolved_extract_timeout(page_timeout_s=page_timeout_s)
    total_budget = _resolved_total_budget(total_budget_s=total_budget_s)
    extract_limit = _resolved_extract_limit(max_pages=max_pages)
    effective_search_timeout = (
        min(search_timeout_s, total_budget)
        if total_budget is not None
        else search_timeout_s
    )

    client = TavilyClient()
    try:
        search_started = time.monotonic()
        results = client.search(query, max_results=num_results, timeout_seconds=effective_search_timeout)
        search_elapsed = time.monotonic() - search_started
        normalized_results = [
            {
                "title": _normalize_text(item.get("title", ""), 200),
                "url": str(item.get("url") or "").strip(),
                "snippet": _normalize_text(item.get("snippet", ""), 1200),
                "source_domain": item.get("source_domain") or _source_domain(item.get("url", "")),
                **({"score": item["score"]} if "score" in item else {}),
                **({"published_date": item["published_date"]} if "published_date" in item else {}),
            }
            for item in results
        ]

        if not include_page_content or extract_limit <= 0:
            return normalized_results

        ordered_urls: list[str] = []
        for item in normalized_results:
            url = item.get("url", "")
            if not url or url in ordered_urls:
                continue
            ordered_urls.append(url)
            if len(ordered_urls) >= extract_limit:
                break

        if not ordered_urls:
            return normalized_results

        remaining_budget = (
            max(total_budget - search_elapsed, 0.0)
            if total_budget is not None
            else None
        )
        if remaining_budget is not None and remaining_budget <= 0:
            return normalized_results

        effective_extract_timeout = extract_timeout_s
        if remaining_budget is not None:
            effective_extract_timeout = max(min(extract_timeout_s, remaining_budget), 0.1)
        effective_extract_client_timeout = effective_extract_timeout + 5.0

        try:
            extracted = client.extract(
                ordered_urls,
                timeout_seconds=effective_extract_client_timeout,
                api_timeout_seconds=effective_extract_timeout,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Tavily extract failed, returning search-only results: urls=%d depth=%s client_timeout=%.1f api_timeout=%.1f error=%s",
                len(ordered_urls),
                resolve_tavily_settings().extract_depth,
                effective_extract_client_timeout,
                effective_extract_timeout,
                exc,
            )
            return normalized_results

        for item in normalized_results:
            url = item.get("url", "")
            content = extracted.get(url, "")
            if content:
                item["content"] = _normalize_text(content, max_chars=1800)
        return normalized_results
    finally:
        client.close()


def format_search_context(query: str, results: list[dict]) -> str:
    """Format search results into a compact citation-friendly system context."""
    if not results:
        return ""

    lines = [f'The user enabled web search. Here are search results for "{query}":', ""]
    context = "\n".join(lines)

    for i, result in enumerate(results[:_DEFAULT_MAX_FORMAT_RESULTS], 1):
        title = _normalize_text(str(result.get("title") or f"Result {i}"), 160)
        url = str(result.get("url") or "").strip()
        source_domain = _normalize_text(str(result.get("source_domain") or _source_domain(url) or "unknown"), 80)
        snippet = _normalize_text(str(result.get("snippet") or ""), _MAX_SNIPPET_CHARS)
        content = _normalize_text(str(result.get("content") or ""), _MAX_CONTENT_CHARS)

        entry_lines = [f"[{i}] {title}"]
        if source_domain:
            entry_lines.append(f"    Source: {source_domain}")
        if url:
            entry_lines.append(f"    URL: {url}")
        if snippet:
            entry_lines.append(f"    Summary: {snippet}")
        if content:
            entry_lines.append(f"    Evidence: {content}")

        candidate = context + "\n".join(entry_lines) + "\n\n"
        if len(candidate) > _MAX_CONTEXT_CHARS:
            break
        context = candidate

    suffix = (
        "Use the search results above to answer the question when relevant. "
        "When you cite a specific result, cite it with [N]. "
        "If the results are not relevant, you may ignore them."
    )
    if len(context) + len(suffix) > _MAX_CONTEXT_CHARS:
        context = context[: _MAX_CONTEXT_CHARS - len(suffix) - 1].rstrip() + "\n"
    return context + suffix
