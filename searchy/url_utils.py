from __future__ import annotations

import base64
import binascii
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

# Query parameters stripped during URL canonicalization so tracking links
# from different search engines collapse onto the same canonical URL.
_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "si",
        "spm",
        "ref_src",
        "ref_url",
        "yclid",
    }
)

_BING_HOSTS: frozenset[str] = frozenset({"www.bing.com", "bing.com"})
_GOOGLE_HOSTS: frozenset[str] = frozenset(
    {"www.google.com", "google.com", "www.google.co.in", "www.google.co.uk"}
)
_DDG_HOSTS: frozenset[str] = frozenset(
    {"duckduckgo.com", "www.duckduckgo.com", "lite.duckduckgo.com", "html.duckduckgo.com"}
)


def unwrap_bing_url(href: str) -> str:
    """Decode Bing ck/a base64url tracking links into their direct target URL."""
    cleaned = href.strip()
    if not cleaned:
        return cleaned
    parsed = urlparse(cleaned)
    if parsed.netloc.lower() in _BING_HOSTS and parsed.path == "/ck/a":
        qs = parse_qs(parsed.query)
        u_values = qs.get("u")
        if u_values and u_values[0].startswith("a1"):
            encoded = u_values[0][2:]
            encoded += "=" * (-len(encoded) % 4)
            try:
                decoded = base64.urlsafe_b64decode(encoded).decode("utf-8", errors="replace").strip()
            except (ValueError, binascii.Error):
                return cleaned
            if decoded.startswith(("http://", "https://")):
                return decoded
    return cleaned


def unwrap_google_url(href: str) -> str:
    """Extract target URL from relative (/url?q=...) or full Google redirect links."""
    cleaned = href.strip()
    if not cleaned:
        return cleaned
    parsed = urlparse(cleaned)
    is_relative_redirect = cleaned.startswith("/url?")
    is_full_redirect = parsed.netloc.lower() in _GOOGLE_HOSTS and parsed.path == "/url"
    if is_relative_redirect or is_full_redirect:
        qs = parse_qs(parsed.query)
        q_vals = qs.get("q") or qs.get("url")
        if q_vals and q_vals[0].strip():
            return q_vals[0].strip()
    return cleaned


def unwrap_duckduckgo_url(href: str) -> str:
    """Extract target URL from DuckDuckGo /l/?uddg=... redirect links."""
    cleaned = href.strip()
    if not cleaned:
        return cleaned
    normalized = f"https:{cleaned}" if cleaned.startswith("//") else cleaned
    parsed = urlparse(normalized)
    is_relative = cleaned.startswith("/l/?")
    is_ddg = parsed.netloc.lower() in _DDG_HOSTS and parsed.path.rstrip("/") == "/l"
    if is_relative or is_ddg:
        qs = parse_qs(parsed.query)
        uddg = qs.get("uddg")
        if uddg and uddg[0].strip():
            return uddg[0].strip()
    return normalized if cleaned.startswith("//") else cleaned


def unwrap_url(href: str) -> str:
    """Run all supported redirect unwrappers on a URL."""
    result = unwrap_bing_url(href)
    result = unwrap_duckduckgo_url(result)
    result = unwrap_google_url(result)
    return result


def is_http_url(href: str) -> bool:
    """Return True if href is an http or https URL with a non-empty host."""
    if not href:
        return False
    parsed = urlparse(href.strip())
    return parsed.scheme.lower() in ("http", "https") and bool(parsed.netloc)


def extract_domain(url: str) -> str:
    """Return the normalized lowercase hostname without a leading www. prefix."""
    if not url:
        return ""
    host = urlparse(url.strip()).netloc.lower()
    if ":" in host:
        host = host.split(":", 1)[0]
    return host.removeprefix("www.")


def canonicalize_url(url: str) -> str:
    """Normalize a URL for cross-provider deduplication.

    Normalizes scheme/host casing, strips a leading ``www.``, removes common
    analytics parameters (``utm_*``, ``fbclid``, ``gclid``, etc.), drops URL
    fragments, and trims trailing slashes on non-root paths.
    """
    cleaned = url.strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if not parsed.netloc:
        return cleaned.rstrip("/")

    scheme = parsed.scheme.lower()
    if scheme == "http":
        scheme = "https"

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host.endswith(":80") or host.endswith(":443"):
        host = host.rsplit(":", 1)[0]

    path = parsed.path.rstrip("/")
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ]
    query_pairs.sort()
    query = urlencode(query_pairs)

    return urlunparse((scheme, host, path, "", query, ""))
