from __future__ import annotations

from urllib.parse import quote

import httpx

from ..base import BaseProvider, ProviderError
from ..html_utils import clean_int, clean_snippet, clean_str
from ..models import SearchCategory, SearchResult
from ..url_utils import is_http_url

_WIKI_HEADERS: dict[str, str] = {
    "User-Agent": "msearchy/2.0.0 (https://github.com/Adarshukumar/msearchy)",
    "Api-User-Agent": "msearchy/2.0.0 (https://github.com/Adarshukumar/msearchy)",
    "Accept": "application/json",
}


class WikipediaProvider(BaseProvider):
    """Wikipedia text and Wikimedia Commons image search provider."""

    name = "wikipedia"
    supports_text = True
    supports_images = True
    supports_videos = False

    def __init__(self, lang: str = "en") -> None:
        self.lang = lang.strip().lower() or "en"

    async def search_text(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []
        resp = await self._request(
            client,
            "GET",
            f"https://{self.lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": min(limit, 50),
                "format": "json",
            },
            headers=_WIKI_HEADERS,
        )
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError("Wikipedia API returned invalid JSON") from exc

        if not isinstance(data, dict):
            return []

        items = (data.get("query") or {}).get("search") or []
        results: list[SearchResult] = []
        for item in items:
            if len(results) >= limit:
                break
            if not isinstance(item, dict):
                continue
            title = clean_str(item.get("title"))
            if not title:
                continue
            slug = quote(title.replace(" ", "_"), safe="_-.~():,'")
            snippet = clean_snippet(clean_str(item.get("snippet")))
            results.append(
                SearchResult(
                    category=SearchCategory.TEXT,
                    provider=self.name,
                    title=title,
                    url=f"https://{self.lang}.wikipedia.org/wiki/{slug}",
                    snippet=snippet,
                )
            )
        return results

    async def search_images(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []
        resp = await self._request(
            client,
            "GET",
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"filetype:bitmap {query}",
                "gsrnamespace": "6",
                "gsrlimit": min(limit, 50),
                "prop": "imageinfo",
                "iiprop": "url|size",
                "iiurlwidth": "400",
                "format": "json",
            },
            headers=_WIKI_HEADERS,
        )
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError("Wikimedia Commons API returned invalid JSON") from exc

        if not isinstance(data, dict):
            return []

        pages = (data.get("query") or {}).get("pages") or {}
        if not isinstance(pages, dict):
            return []

        results: list[SearchResult] = []
        for page in pages.values():
            if len(results) >= limit:
                break
            if not isinstance(page, dict):
                continue
            info_list = page.get("imageinfo") or []
            if not info_list or not isinstance(info_list[0], dict):
                continue
            info = info_list[0]
            img_url = clean_str(info.get("url"))
            if not is_http_url(img_url):
                continue
            raw_title = clean_str(page.get("title"))
            results.append(
                SearchResult(
                    category=SearchCategory.IMAGES,
                    provider=self.name,
                    title=raw_title.removeprefix("File:"),
                    url=img_url,
                    thumbnail_url=clean_str(info.get("thumburl")),
                    source_url=clean_str(info.get("descriptionurl")),
                    width=clean_int(info.get("width")),
                    height=clean_int(info.get("height")),
                )
            )
        return results
