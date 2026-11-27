from __future__ import annotations

import base64

from searchy.html_utils import clean_int, clean_snippet, clean_str, extract_text, parse_html
from searchy.url_utils import (
    canonicalize_url,
    extract_domain,
    is_http_url,
    unwrap_bing_url,
    unwrap_duckduckgo_url,
    unwrap_google_url,
    unwrap_url,
)


def test_unwrap_bing_url_valid_and_variants() -> None:
    target = "https://docs.python.org/3/library/asyncio.html"
    encoded = "a1" + base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    assert unwrap_bing_url(f"https://www.bing.com/ck/a?u={encoded}&ntb=1") == target
    assert unwrap_bing_url(f"http://bing.com/ck/a?u={encoded}") == target
    assert unwrap_bing_url("https://example.com/direct") == "https://example.com/direct"
    # Invalid base64 falls back safely without raising.
    bad = "https://www.bing.com/ck/a?u=a1!!!"
    assert unwrap_bing_url(bad) == bad


def test_unwrap_google_url_relative_and_full() -> None:
    assert unwrap_google_url("/url?q=https://example.com/a&sa=U") == "https://example.com/a"
    assert (
        unwrap_google_url("https://www.google.com/url?q=https://example.com/b&sa=U")
        == "https://example.com/b"
    )
    assert unwrap_google_url("https://google.com/url?url=https://example.com/c") == (
        "https://example.com/c"
    )
    assert unwrap_google_url("https://example.com/plain") == "https://example.com/plain"


def test_unwrap_duckduckgo_url_protocol_relative_and_full() -> None:
    raw = "//duckduckgo.com/l/?uddg=https%3A%2F%2Frealpython.com%2Fasync%2F&rut=abc"
    assert unwrap_duckduckgo_url(raw) == "https://realpython.com/async/"
    assert (
        unwrap_duckduckgo_url("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fpython.org")
        == "https://python.org"
    )
    assert unwrap_url(raw) == "https://realpython.com/async/"


def test_canonicalize_url_and_domain() -> None:
    u1 = "https://WWW.Example.COM/Docs/Intro/?utm_source=bing&b=2&a=1#section"
    u2 = "http://example.com/Docs/Intro?a=1&b=2&fbclid=xyz"
    assert canonicalize_url(u1) == canonicalize_url(u2)
    assert extract_domain("https://www.docs.python.org:443/3/") == "docs.python.org"
    assert is_http_url("https://python.org")
    assert not is_http_url("javascript:alert(1)")
    assert not is_http_url("/relative/path")


def test_parse_html_handles_empty_and_xml_declaration() -> None:
    empty_dom = parse_html("")
    assert empty_dom.xpath("//a") == []

    ws_dom = parse_html("   \n\t  ")
    assert ws_dom.xpath("//a") == []

    xml_dom = parse_html('<?xml version="1.0" encoding="UTF-8"?><html><body><p>Hello</p></body></html>')
    assert extract_text(xml_dom.xpath("//p")[0]) == "Hello"


def test_clean_helpers_null_safety() -> None:
    assert clean_str(None) == ""
    assert clean_str("  hi ") == "hi"
    assert clean_str(42) == "42"
    assert clean_int("800") == 800
    assert clean_int("") is None
    assert clean_int(None) is None
    assert clean_int(True) is None
    assert clean_snippet("<span>C#</span> &amp; &quot;Async&quot;   guide") == 'C# & "Async" guide'
