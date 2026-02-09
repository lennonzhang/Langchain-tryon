"""Web search via DuckDuckGo for context injection."""

import logging
import re
import warnings

import requests

logger = logging.getLogger(__name__)


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


def _fetch_with_requests(url: str, max_chars: int, timeout: int = 8) -> str:
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


def load_webpage_content(url: str, max_chars: int = 1800) -> str:
    """Load and trim webpage text content using LangChain WebBaseLoader."""
    try:
        from langchain_community.document_loaders import WebBaseLoader
    except ImportError:
        logger.warning("langchain-community not installed; skip webpage loading.")
        return ""

    try:
        try:
            loader = WebBaseLoader(url, requests_kwargs={"timeout": 8})
        except TypeError:
            loader = WebBaseLoader(web_paths=(url,), requests_kwargs={"timeout": 8})
        docs = loader.load()
    except Exception as exc:  # noqa: BLE001
        logger.warning("WebBaseLoader failed for %s: %s", url, exc)
        return _fetch_with_requests(url, max_chars=max_chars)

    parts = []
    for doc in docs or []:
        page = getattr(doc, "page_content", "")
        if isinstance(page, str) and page.strip():
            parts.append(page)

    merged = _normalize_text("\n".join(parts), max_chars=max_chars)
    if merged:
        return merged
    return _fetch_with_requests(url, max_chars=max_chars)


def web_search(query: str, num_results: int = 5, include_page_content: bool = True) -> list[dict]:
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
            for item in results:
                url = item.get("url", "")
                if not url:
                    continue
                content = load_webpage_content(url, max_chars=1800)
                if content:
                    item["content"] = content
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
