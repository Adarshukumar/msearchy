from __future__ import annotations

import httpx

from ..base import DEFAULT_HEADERS, BaseProvider
from ..html_utils import clean_str, compile_xpath, extract_text, parse_html
from ..models import SearchCategory, SearchResult
from ..url_utils import is_http_url

_XP_CARDS = compile_xpath('//div[@data-type="web"]')
_XP_HEADING_LINK = compile_xpath('.//a[contains(@class, "heading-serpresult")]')
_XP_ANY_LINK = compile_xpath(".//a[@href]")
_XP_TITLE_NODE = compile_xpath(
    './/div[contains(@class, "title")] | .//span[contains(@class, "title")]'
)
_XP_SNIPPET = compile_xpath(
    './/div[contains(@class, "snippet-description")] | .//p[contains(@class, "snippet-description")] | .//div[contains(@class, "content")]'
)


class BraveProvider(BaseProvider):
    """Brave web search provider."""

    name = "brave"
    supports_text = True
    supports_images = False
    supports_videos = False

    async def search_text(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []
        resp = await self._request(
            client,
            "GET",
            "https://search.brave.com/search",
            params={"q": query, "source": "web"},
            headers=DEFAULT_HEADERS,
        )
        dom = parse_html(resp.text)

        results: list[SearchResult] = []
        for card in _XP_CARDS(dom):
            if len(results) >= limit:
                break
            links = _XP_HEADING_LINK(card) or _XP_ANY_LINK(card)
            if not links:
                continue
            link = links[0]
            href = clean_str(link.attrib.get("href"))
            if not is_http_url(href):
                continue

            title_nodes = _XP_TITLE_NODE(link)
            title = extract_text(title_nodes[0]) if title_nodes else extract_text(link)
            if not title:
                continue

            snippet = ""
            for el in _XP_SNIPPET(card):
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
