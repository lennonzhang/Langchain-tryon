from __future__ import annotations

from backend.search_provider import SearchProvider


class SearchService:
    def __init__(self, search_fn):
        self._search_fn = search_fn

    @property
    def raw_search(self):
        return self._search_fn

    def provider(self, emit_fn, cancel_token=None) -> SearchProvider:
        return SearchProvider(self._search_fn, emit_fn, cancel_token=cancel_token)

    def search_with_events(self, query: str, emit_fn, cancel_token=None) -> tuple[str, list]:
        provider = self.provider(emit_fn, cancel_token=cancel_token)
        return provider.search_with_events(query)
