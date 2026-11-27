from __future__ import annotations

import json
import httpx

from ..base import BaseProvider, DEFAULT_HEADERS, extract_text, parse_html, unwrap_bing_url
from ..models import SearchCategory, SearchResult


class BingProvider(BaseProvider):
    name = "bing"
    supports_text = True
    supports_images = True
    supports_videos = True

    async def search_text(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        resp = await client.get(
            "https://www.bing.com/search",
            params={"q": query, "setlang": "en"},
            headers=DEFAULT_HEADERS,
        )
        resp.raise_for_status()
        dom = parse_html(resp.text)

        results: list[SearchResult] = []
        for item in dom.xpath('//ol[@id="b_results"]/li[contains(@class, "b_algo")]'):
            if len(results) >= limit:
                break
            links = item.xpath(".//h2/a")
            if not links:
                continue
            href = unwrap_bing_url(links[0].attrib.get("href", "").strip())
            title = extract_text(links[0])
            if not href or not title:
                continue
            snippet_els = item.xpath(".//p")
            snippet = extract_text(snippet_els[0]) if snippet_els else ""
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
        resp = await client.get(
            "https://www.bing.com/images/search",
            params={"q": query, "form": "HDRSC2"},
            headers=DEFAULT_HEADERS,
        )
        resp.raise_for_status()
        dom = parse_html(resp.text)

        results: list[SearchResult] = []
        for el in dom.xpath('//a[contains(@class, "iusc")]'):
            if len(results) >= limit:
                break
            m_attr = el.attrib.get("m")
            if not m_attr:
                continue
            try:
                meta = json.loads(m_attr)
            except json.JSONDecodeError:
                continue
            img_url = meta.get("murl")
            if not img_url:
                continue
            results.append(
                SearchResult(
                    category=SearchCategory.IMAGES,
                    provider=self.name,
                    title=meta.get("t", ""),
                    url=img_url,
                    thumbnail_url=meta.get("turl", ""),
                    source_url=meta.get("purl", ""),
                )
            )
        return results

    async def search_videos(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        resp = await client.get(
            "https://www.bing.com/videos/search",
            params={"q": query},
            headers=DEFAULT_HEADERS,
        )
        resp.raise_for_status()
        dom = parse_html(resp.text)

        results: list[SearchResult] = []
        for card in dom.xpath('//div[contains(@class, "dg_u")]'):
            if len(results) >= limit:
                break
            vrh = card.xpath('.//div[contains(@class, "vrhdata")]/@vrhm')
            if not vrh:
                continue
            try:
                meta = json.loads(vrh[0])
            except json.JSONDecodeError:
                continue
            url = meta.get("murl") or meta.get("pgurl")
            if not url:
                continue
            results.append(
                SearchResult(
                    category=SearchCategory.VIDEOS,
                    provider=self.name,
                    title=meta.get("vt", ""),
                    url=url,
                    thumbnail_url=meta.get("turl", ""),
                    duration=str(meta.get("du", "")),
                )
            )
        return results
