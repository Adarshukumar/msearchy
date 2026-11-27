from __future__ import annotations

import json
import threading

import httpx

from searchy import ProviderReport, SearchCategory, SearchResponse, SearchResult
from searchy.cli import build_parser
from searchy.render import render_bundle, render_response
from searchy.web import create_server


def _sample_response() -> SearchResponse:
    return SearchResponse(
        query="python asyncio",
        category=SearchCategory.TEXT,
        total_results=2,
        unique_results=1,
        elapsed_ms=42.5,
        provider_counts={"duckduckgo": 1, "bing": 1, "brave": 0},
        providers=[
            ProviderReport(provider="duckduckgo", success=True, count=1, elapsed_ms=25.0),
            ProviderReport(provider="bing", success=True, count=1, elapsed_ms=40.0),
            ProviderReport(provider="brave", success=False, count=0, elapsed_ms=15.0, error="HTTPStatusError: 429"),
        ],
        results=[
            SearchResult(
                category=SearchCategory.TEXT,
                provider="duckduckgo",
                title="Python Asyncio Docs",
                url="https://docs.python.org/3/library/asyncio.html",
                snippet="Asynchronous I/O in Python.",
                score=0.032787,
                providers_matched=["duckduckgo", "bing"],
            )
        ],
    )


def test_render_formats_pretty_compact_json_markdown() -> None:
    res = _sample_response()

    pretty = render_response(res, fmt="pretty", no_color=True, width=84)
    assert "msearchy  TEXT" in pretty
    assert "HTTPStatusError: 429" in pretty
    assert "+1: bing" in pretty

    compact = render_response(res, fmt="compact", no_color=True)
    assert "ERR [brave]" in compact
    assert "Python Asyncio Docs" in compact

    as_json = json.loads(render_response(res, fmt="json"))
    assert as_json["unique_results"] == 1
    assert as_json["results"][0]["domain"] == "docs.python.org"

    md = render_response(res, fmt="markdown")
    assert "## Text results for `python asyncio`" in md
    assert "`brave`" in md

    bundle_out = render_bundle({SearchCategory.TEXT: res}, fmt="pretty", no_color=True)
    assert "Python Asyncio Docs" in bundle_out


def test_cli_parser_options() -> None:
    parser = build_parser()
    args = parser.parse_args(["rust", "-c", "all", "-l", "8", "-p", "bing", "wikipedia", "--format", "markdown"])
    assert args.query == "rust"
    assert args.category == "all"
    assert args.limit == 8
    assert args.providers == ["bing", "wikipedia"]
    assert args.format == "markdown"


def test_web_explorer_endpoints() -> None:
    server = create_server(host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        r_html = httpx.get(f"{base}/")
        assert r_html.status_code == 200
        assert "msearchy" in r_html.text

        r_health = httpx.get(f"{base}/api/health")
        assert r_health.json()["status"] == "ok"

        r_prov = httpx.get(f"{base}/api/providers")
        names = [p["name"] for p in r_prov.json()["providers"]]
        assert names == ["duckduckgo", "bing", "wikipedia", "brave"]

        r_search = httpx.get(f"{base}/api/search", params={"q": "python asyncio", "category": "all", "mode": "demo"})
        assert r_search.status_code == 200
        payload = r_search.json()
        assert payload["data"]["text"]["unique_results"] >= 4
        assert payload["data"]["images"]["unique_results"] >= 3
        assert payload["data"]["videos"]["unique_results"] >= 2

        r_unwrap = httpx.get(
            f"{base}/api/unwrap",
            params={"url": "https://www.google.com/url?q=https://python.org/?utm_source=x"},
        )
        unwrapped = r_unwrap.json()
        assert unwrapped["unwrapped"] == "https://python.org/?utm_source=x"
        assert unwrapped["canonical"] == "https://python.org"
        assert unwrapped["domain"] == "python.org"
    finally:
        server.shutdown()
        server.server_close()
