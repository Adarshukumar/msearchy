from __future__ import annotations

import httpx

from ..base import BaseProvider, DEFAULT_HEADERS, extract_text, parse_html
from ..models import SearchCategory, SearchResult


class BraveProvider(BaseProvider):
    name = "brave"
    supports_text = True
    supports_images = False
    supports_videos = False

    async def search_text(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        resp = await client.get(
            "https://search.brave.com/search",
            params={"q": query, "source": "web"},
            headers=DEFAULT_HEADERS,
        )
        resp.raise_for_status()
        dom = parse_html(resp.text)

        results: list[SearchResult] = []
        for card in dom.xpath('//div[@data-type="web"]'):
            if len(results) >= limit:
                break
            links = card.xpath('.//a[contains(@class, "heading-serpresult")]')
            if not links:
                links = card.xpath(".//a[@href]")
            if not links:
                continue
            href = links[0].attrib.get("href", "").strip()
            title = extract_text(links[0])
            if not href or not title or not href.startswith("http"):
                continue

            snippet_els = card.xpath('.//div[contains(@class, "snippet-description")]')
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
