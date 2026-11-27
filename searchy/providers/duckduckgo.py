from __future__ import annotations

import re
from typing import Any

import httpx

from ..base import DEFAULT_HEADERS, BaseProvider, ProviderError
from ..cache import SingleFlight, TTLCache
from ..html_utils import (
    clean_int,
    clean_snippet,
    clean_str,
    compile_xpath,
    extract_text,
    parse_html,
)
from ..models import SearchCategory, SearchResult
from ..url_utils import is_http_url, unwrap_duckduckgo_url

_VQD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'vqd\s*=\s*["\']?([0-9]+-[0-9A-Za-z_-]+)["\']?'),
    re.compile(r'"vqd"\s*:\s*"([0-9]+-[0-9A-Za-z_-]+)"'),
    re.compile(r"vqd%3D([0-9]+-[0-9A-Za-z_-]+)"),
)

_XP_ROWS = compile_xpath("//tr")
_XP_RESULT_LINK = compile_xpath('.//a[contains(@class, "result-link")]')
_XP_RESULT_SNIPPET = compile_xpath('.//td[contains(@class, "result-snippet")]')
_XP_ALL_LINKS = compile_xpath('//a[contains(@class, "result-link")]')


class DuckDuckGoProvider(BaseProvider):
    """DuckDuckGo provider supporting text (Lite), images (i.js), and videos (v.js)."""

    name = "duckduckgo"
    supports_text = True
    supports_images = True
    supports_videos = True

    def __init__(self, vqd_ttl: float = 300.0) -> None:
        self._vqd_cache: TTLCache[str] = TTLCache(maxsize=128, ttl=vqd_ttl)
        self._vqd_flight: SingleFlight[str] = SingleFlight()

    @staticmethod
    def _extract_vqd(text: str) -> str | None:
        for pattern in _VQD_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1)
        return None

    async def _get_vqd(self, client: httpx.AsyncClient, query: str) -> str:
        cache_key = query.strip().lower()
        cached = self._vqd_cache.get(cache_key)
        if cached:
            return cached

        async def _fetch() -> str:
            resp = await self._request(
                client,
                "GET",
                "https://duckduckgo.com/",
                params={"q": query},
                headers=DEFAULT_HEADERS,
            )
            if resp.status_code == 202:
                raise ProviderError(
                    "DuckDuckGo returned HTTP 202 bot challenge while fetching vqd token",
                    status_code=202,
                )
            vqd = self._extract_vqd(resp.text)
            if not vqd:
                raise ProviderError(
                    "DuckDuckGo did not return a vqd token (possible rate limit or markup change)",
                    status_code=resp.status_code,
                )
            self._vqd_cache.set(cache_key, vqd)
            return vqd

        return await self._vqd_flight.do(cache_key, _fetch)

    @staticmethod
    def _is_ad_row(row: Any, raw_href: str) -> bool:
        row_class = clean_str(row.attrib.get("class")).lower()
        if "result--ad" in row_class or "ad" in row_class.split():
            return True
        lowered = raw_href.lower()
        return "duckduckgo.com/y.js" in lowered or "ad_domain=" in lowered

    async def search_text(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []
        resp = await self._request(
            client,
            "POST",
            "https://lite.duckduckgo.com/lite/",
            data={"q": query},
            headers={**DEFAULT_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code == 202:
            raise ProviderError("DuckDuckGo Lite returned HTTP 202 challenge", status_code=202)

        dom = parse_html(resp.text)
        results: list[SearchResult] = []
        rows = _XP_ROWS(dom)

        if rows:
            pending_idx: int | None = None
            skip_next_snippet = False

            for row in rows:
                links = _XP_RESULT_LINK(row)
                if links:
                    link = links[0]
                    raw_href = clean_str(link.attrib.get("href"))
                    if self._is_ad_row(row, raw_href):
                        pending_idx = None
                        skip_next_snippet = True
                        continue

                    skip_next_snippet = False
                    href = unwrap_duckduckgo_url(raw_href)
                    title = extract_text(link)
                    if not title or not is_http_url(href):
                        pending_idx = None
                        continue

                    if len(results) < limit:
                        results.append(
                            SearchResult(
                                category=SearchCategory.TEXT,
                                provider=self.name,
                                title=title,
                                url=href,
                                snippet="",
                            )
                        )
                        pending_idx = len(results) - 1
                    else:
                        pending_idx = None
                    continue

                snippets = _XP_RESULT_SNIPPET(row)
                if snippets and pending_idx is not None and not skip_next_snippet:
                    if not results[pending_idx].snippet:
                        results[pending_idx].snippet = extract_text(snippets[0])
                    pending_idx = None
            return results[:limit]

        # Fallback for non-table HTML fragments.
        for link in _XP_ALL_LINKS(dom):
            if len(results) >= limit:
                break
            raw_href = clean_str(link.attrib.get("href"))
            href = unwrap_duckduckgo_url(raw_href)
            title = extract_text(link)
            if not title or not is_http_url(href):
                continue
            results.append(
                SearchResult(
                    category=SearchCategory.TEXT,
                    provider=self.name,
                    title=title,
                    url=href,
                )
            )
        return results

    async def search_images(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []
        vqd = await self._get_vqd(client, query)
        resp = await self._request(
            client,
            "GET",
            "https://duckduckgo.com/i.js",
            params={"l": "us-en", "o": "json", "q": query, "vqd": vqd, "f": ",,,", "p": "1"},
            headers={**DEFAULT_HEADERS, "Referer": "https://duckduckgo.com/"},
        )
        if resp.status_code == 202:
            raise ProviderError("DuckDuckGo image endpoint returned HTTP 202", status_code=202)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError("DuckDuckGo image endpoint returned invalid JSON") from exc

        if not isinstance(data, dict):
            return []

        results: list[SearchResult] = []
        raw_items = data.get("results") or []
        for item in raw_items:
            if len(results) >= limit:
                break
            if not isinstance(item, dict):
                continue
            img_url = clean_str(item.get("image"))
            if not is_http_url(img_url):
                continue
            results.append(
                SearchResult(
                    category=SearchCategory.IMAGES,
                    provider=self.name,
                    title=clean_str(item.get("title")),
                    url=img_url,
                    thumbnail_url=clean_str(item.get("thumbnail")),
                    source_url=clean_str(item.get("url")),
                    width=clean_int(item.get("width")),
                    height=clean_int(item.get("height")),
                )
            )
        return results

    async def search_videos(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []
        vqd = await self._get_vqd(client, query)
        resp = await self._request(
            client,
            "GET",
            "https://duckduckgo.com/v.js",
            params={"l": "us-en", "o": "json", "q": query, "vqd": vqd, "f": ",,,", "p": "1"},
            headers={**DEFAULT_HEADERS, "Referer": "https://duckduckgo.com/"},
        )
        if resp.status_code == 202:
            raise ProviderError("DuckDuckGo video endpoint returned HTTP 202", status_code=202)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError("DuckDuckGo video endpoint returned invalid JSON") from exc

        if not isinstance(data, dict):
            return []

        results: list[SearchResult] = []
        raw_items = data.get("results") or []
        for item in raw_items:
            if len(results) >= limit:
                break
            if not isinstance(item, dict):
                continue
            url = clean_str(item.get("content")) or clean_str(item.get("url"))
            if not is_http_url(url):
                continue
            images = item.get("images")
            thumb = ""
            if isinstance(images, dict):
                thumb = clean_str(images.get("medium")) or clean_str(images.get("small"))
            results.append(
                SearchResult(
                    category=SearchCategory.VIDEOS,
                    provider=self.name,
                    title=clean_str(item.get("title")),
                    url=url,
                    thumbnail_url=thumb,
                    duration=clean_str(item.get("duration")),
                    snippet=clean_snippet(clean_str(item.get("description"))),
                )
            )
        return results
