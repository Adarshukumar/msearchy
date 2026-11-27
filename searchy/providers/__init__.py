from __future__ import annotations

from ..base import BaseProvider
from .bing import BingProvider
from .brave import BraveProvider
from .duckduckgo import DuckDuckGoProvider
from .wikipedia import WikipediaProvider


def get_default_providers() -> list[BaseProvider]:
    """Return a fresh list of all built-in search providers."""
    return [
        DuckDuckGoProvider(),
        BingProvider(),
        WikipediaProvider(),
        BraveProvider(),
    ]


__all__ = [
    "BingProvider",
    "BraveProvider",
    "DuckDuckGoProvider",
    "WikipediaProvider",
    "get_default_providers",
]
