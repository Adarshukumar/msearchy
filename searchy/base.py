from __future__ import annotations

import base64
from abc import ABC
from urllib.parse import parse_qs, urlparse

import httpx
from lxml import html as lxml_html

from .models import SearchResult

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def unwrap_bing_url(href: str) -> str:
    """Decode Bing ck/a tracking URLs into direct target URLs."""
    if href.startswith("https://www.bing.com/ck/a?"):
        qs = parse_qs(urlparse(href).query)
        u_values = qs.get("u")
        if u_values and u_values[0].startswith("a1"):
            encoded = u_values[0][2:]
            encoded += "=" * (-len(encoded) % 4)
            try:
                return base64.urlsafe_b64decode(encoded).decode("utf-8", errors="replace")
            except Exception:
                return href
    return href


def unwrap_google_url(href: str) -> str:
    """Extract target URL from Google /url?q=... redirect links."""
    if href.startswith("/url?"):
        qs = parse_qs(urlparse(href).query)
        q_vals = qs.get("q") or qs.get("url")
        if q_vals:
            return q_vals[0]
    return href


def extract_text(el) -> str:
    if el is None:
        return ""
    if isinstance(el, str):
        return " ".join(el.split())
    return " ".join("".join(el.itertext()).split())


def parse_html(content: str):
    return lxml_html.fromstring(content)


class BaseProvider(ABC):
    name: str = "base"
    supports_text: bool = False
    supports_images: bool = False
    supports_videos: bool = False

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
