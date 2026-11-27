from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .html_utils import extract_text, parse_html
from .models import ProviderCapabilities, SearchCategory, SearchResult
from .url_utils import unwrap_bing_url, unwrap_duckduckgo_url, unwrap_google_url, unwrap_url

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 502, 503, 504})


class ProviderError(RuntimeError):
    """Raised by providers for non-HTTP errors such as bot challenges."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BaseProvider:
    """Base interface implemented by all Searchy search providers."""

    name: str = "base"
    supports_text: bool = False
    supports_images: bool = False
    supports_videos: bool = False

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            text=self.supports_text,
            images=self.supports_images,
            videos=self.supports_videos,
        )

    def supports(self, category: SearchCategory) -> bool:
        return self.capabilities.supports(category)

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        retries: int = 1,
        backoff: float = 0.25,
        **kwargs: Any,
    ) -> httpx.Response:
        """Issue an HTTP request with bounded retry on transient network/5xx/429 errors."""
        last_exc: Exception | None = None
        attempts = max(1, retries + 1)
        for attempt in range(attempts):
            try:
                resp = await client.request(method, url, **kwargs)
                if resp.status_code in _RETRYABLE_STATUSES and attempt + 1 < attempts:
                    await asyncio.sleep(backoff * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(backoff * (attempt + 1))
                    continue
                raise
        if last_exc is not None:
            raise last_exc
        raise ProviderError("Request failed without response")

    async def search_text(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        return []

    async def search_images(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        return []

    async def search_videos(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        return []


__all__ = [
    "BaseProvider",
    "DEFAULT_HEADERS",
    "ProviderError",
    "extract_text",
    "parse_html",
    "unwrap_bing_url",
    "unwrap_duckduckgo_url",
    "unwrap_google_url",
    "unwrap_url",
]
