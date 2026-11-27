from .base import BaseProvider, ProviderError
from .cache import SingleFlight, TTLCache
from .engine import Searchy
from .html_utils import clean_snippet, extract_text, parse_html
from .models import (
    ProviderCapabilities,
    ProviderReport,
    SearchBundle,
    SearchCategory,
    SearchResponse,
    SearchResult,
)
from .render import render_bundle, render_response
from .url_utils import (
    canonicalize_url,
    extract_domain,
    unwrap_bing_url,
    unwrap_duckduckgo_url,
    unwrap_google_url,
    unwrap_url,
)

__version__ = "2.0.0"

__all__ = [
    "BaseProvider",
    "ProviderCapabilities",
    "ProviderError",
    "ProviderReport",
    "SearchBundle",
    "SearchCategory",
    "SearchResponse",
    "SearchResult",
    "Searchy",
    "SingleFlight",
    "TTLCache",
    "__version__",
    "canonicalize_url",
    "clean_snippet",
    "extract_domain",
    "extract_text",
    "parse_html",
    "render_bundle",
    "render_response",
    "unwrap_bing_url",
    "unwrap_duckduckgo_url",
    "unwrap_google_url",
    "unwrap_url",
]
