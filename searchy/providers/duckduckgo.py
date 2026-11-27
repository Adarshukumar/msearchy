from __future__ import annotations

import re
import httpx

from ..base import BaseProvider, DEFAULT_HEADERS, extract_text, parse_html
from ..models import SearchCategory, SearchResult


class DuckDuckGoProvider(BaseProvider):
    name = "duckduckgo"
    supports_text = True
    supports_images = True
    supports_videos = True

    async def _get_vqd(self, client: httpx.AsyncClient, query: str) -> str | None:
        resp = await client.get(
            "https://duckduckgo.com/",
            params={"q": query},
            headers=DEFAULT_HEADERS,
        )
        resp.raise_for_status()
        m = re.search(r'vqd=[\'"]?([0-9-]+)[\'"]?', resp.text)
        return m.group(1) if m else None

    async def search_text(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        resp = await client.post(
            "https://lite.duckduckgo.com/lite/",
            data={"q": query},
            headers={**DEFAULT_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        dom = parse_html(resp.text)

        results: list[SearchResult] = []
        links = dom.xpath('//a[contains(@class, "result-link")]')
        snippets = dom.xpath('//td[contains(@class, "result-snippet")]')

        for idx, link in enumerate(links):
            if len(results) >= limit:
                break
            href = link.attrib.get("href", "").strip()
            title = extract_text(link)
            if not href or not title or href.startswith("/"):
                continue
            snippet = extract_text(snippets[idx]) if idx < len(snippets) else ""
            results.append(
                SearchResult(
                    category=SearchCategory.TEXT,
                    provider=self.name,
                    title=title,
                    url=href,
                    snippet=snippet,
                )
            )
        return results

    async def search_images(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        vqd = await self._get_vqd(client, query)
        if not vqd:
            return []
        resp = await client.get(
            "https://duckduckgo.com/i.js",
            params={"l": "us-en", "o": "json", "q": query, "vqd": vqd, "f": ",,,", "p": "1"},
            headers={**DEFAULT_HEADERS, "Referer": "https://duckduckgo.com/"},
        )
        resp.raise_for_status()
        data = resp.json()
        results: list[SearchResult] = []
        for item in data.get("results", [])[:limit]:
            img_url = item.get("image")
            if not img_url:
                continue
            results.append(
                SearchResult(
                    category=SearchCategory.IMAGES,
                    provider=self.name,
                    title=item.get("title", ""),
                    url=img_url,
                    thumbnail_url=item.get("thumbnail", ""),
                    source_url=item.get("url", ""),
                    width=item.get("width"),
                    height=item.get("height"),
                )
            )
        return results

    async def search_videos(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        vqd = await self._get_vqd(client, query)
        if not vqd:
            return []
        resp = await client.get(
            "https://duckduckgo.com/v.js",
            params={"l": "us-en", "o": "json", "q": query, "vqd": vqd, "f": ",,,", "p": "1"},
            headers={**DEFAULT_HEADERS, "Referer": "https://duckduckgo.com/"},
        )
        resp.raise_for_status()
        data = resp.json()
        results: list[SearchResult] = []
        for item in data.get("results", [])[:limit]:
            url = item.get("content") or item.get("url")
            if not url:
                continue
            images = item.get("images") or {}
            thumb = images.get("medium") or images.get("small") or ""
            results.append(
                SearchResult(
                    category=SearchCategory.VIDEOS,
                    provider=self.name,
                    title=item.get("title", ""),
                    url=url,
                    thumbnail_url=thumb,
                    duration=str(item.get("duration", "")),
                    snippet=item.get("description", ""),
                )
            )
        return results
