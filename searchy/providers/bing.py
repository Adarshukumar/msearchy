from __future__ import annotations

import json

import httpx

from ..base import DEFAULT_HEADERS, BaseProvider
from ..html_utils import clean_int, clean_str, compile_xpath, extract_text, parse_html
from ..models import SearchCategory, SearchResult
from ..url_utils import is_http_url, unwrap_bing_url

_XP_ALGO = compile_xpath('//ol[@id="b_results"]/li[contains(@class, "b_algo")]')
_XP_H2_A = compile_xpath(".//h2/a")
_XP_CAPTION_P = compile_xpath('.//div[contains(@class, "b_caption")]//p')
_XP_ANY_P = compile_xpath(".//p")
_XP_IUSC = compile_xpath('//a[contains(@class, "iusc")]')
_XP_VIDEO_CARD = compile_xpath('//div[contains(@class, "dg_u")]')
_XP_VRHM = compile_xpath('.//div[contains(@class, "vrhdata")]/@vrhm')


class BingProvider(BaseProvider):
    """Bing web, image, and video provider with ck/a tracking URL decoding."""

    name = "bing"
    supports_text = True
    supports_images = True
    supports_videos = True

    async def search_text(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []
        resp = await self._request(
            client,
            "GET",
            "https://www.bing.com/search",
            params={"q": query, "setlang": "en"},
            headers=DEFAULT_HEADERS,
        )
        dom = parse_html(resp.text)

        results: list[SearchResult] = []
        for item in _XP_ALGO(dom):
            if len(results) >= limit:
                break
            links = _XP_H2_A(item)
            if not links:
                continue
            href = unwrap_bing_url(clean_str(links[0].attrib.get("href")))
            title = extract_text(links[0])
            if not title or not is_http_url(href):
                continue

            snippet = ""
            for el in _XP_CAPTION_P(item) or _XP_ANY_P(item):
                candidate = extract_text(el)
                if candidate:
                    snippet = candidate
                    break

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
        if limit <= 0:
            return []
        resp = await self._request(
            client,
            "GET",
            "https://www.bing.com/images/search",
            params={"q": query, "form": "HDRSC2"},
            headers=DEFAULT_HEADERS,
        )
        dom = parse_html(resp.text)

        results: list[SearchResult] = []
        for el in _XP_IUSC(dom):
            if len(results) >= limit:
                break
            m_attr = el.attrib.get("m")
            if not m_attr:
                continue
            try:
                meta = json.loads(m_attr)
            except json.JSONDecodeError:
                continue
            if not isinstance(meta, dict):
                continue
            img_url = clean_str(meta.get("murl"))
            if not is_http_url(img_url):
                continue
            results.append(
                SearchResult(
                    category=SearchCategory.IMAGES,
                    provider=self.name,
                    title=clean_str(meta.get("t")),
                    url=img_url,
                    thumbnail_url=clean_str(meta.get("turl")),
                    source_url=clean_str(meta.get("purl")),
                    width=clean_int(meta.get("mw") or meta.get("w")),
                    height=clean_int(meta.get("mh") or meta.get("h")),
                )
            )
        return results

    async def search_videos(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []
        resp = await self._request(
            client,
            "GET",
            "https://www.bing.com/videos/search",
            params={"q": query},
            headers=DEFAULT_HEADERS,
        )
        dom = parse_html(resp.text)

        results: list[SearchResult] = []
        for card in _XP_VIDEO_CARD(dom):
            if len(results) >= limit:
                break
            vrh = _XP_VRHM(card)
            if not vrh:
                continue
            try:
                meta = json.loads(vrh[0])
            except json.JSONDecodeError:
                continue
            if not isinstance(meta, dict):
                continue
            url = clean_str(meta.get("murl")) or clean_str(meta.get("pgurl"))
            if not is_http_url(url):
                continue
            results.append(
                SearchResult(
                    category=SearchCategory.VIDEOS,
                    provider=self.name,
                    title=clean_str(meta.get("vt")),
                    url=url,
                    thumbnail_url=clean_str(meta.get("turl")),
                    duration=clean_str(meta.get("du")),
                )
            )
        return results
