from __future__ import annotations

import re
import httpx

from ..base import BaseProvider, DEFAULT_HEADERS
from ..models import SearchCategory, SearchResult

_HTML_TAG_RE = re.compile(r"<[^>]+>")


class WikipediaProvider(BaseProvider):
    name = "wikipedia"
    supports_text = True
    supports_images = True
    supports_videos = False

    async def search_text(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        resp = await client.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": min(limit, 20),
                "format": "json",
            },
            headers={**DEFAULT_HEADERS, "Api-User-Agent": "Searchy/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("query", {}).get("search", [])[:limit]:
            title = item.get("title", "")
            if not title:
                continue
            slug = title.replace(" ", "_")
            snippet = _HTML_TAG_RE.sub("", item.get("snippet", ""))
            results.append(
                SearchResult(
                    category=SearchCategory.TEXT,
                    provider=self.name,
                    title=title,
                    url=f"https://en.wikipedia.org/wiki/{slug}",
                    snippet=snippet,
                )
            )
        return results

    async def search_images(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        resp = await client.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"filetype:bitmap {query}",
                "gsrnamespace": "6",
                "gsrlimit": min(limit, 20),
                "prop": "imageinfo",
                "iiprop": "url|size",
                "iiurlwidth": "400",
                "format": "json",
            },
            headers={**DEFAULT_HEADERS, "Api-User-Agent": "Searchy/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        results: list[SearchResult] = []
        pages = data.get("query", {}).get("pages", {})
        for page in list(pages.values())[:limit]:
            info_list = page.get("imageinfo") or []
            if not info_list:
                continue
            info = info_list[0]
            img_url = info.get("url")
            if not img_url:
                continue
            results.append(
                SearchResult(
                    category=SearchCategory.IMAGES,
                    provider=self.name,
                    title=page.get("title", "").removeprefix("File:"),
                    url=img_url,
                    thumbnail_url=info.get("thumburl", ""),
                    source_url=info.get("descriptionurl", ""),
                    width=info.get("width"),
                    height=info.get("height"),
                )
            )
        return results
