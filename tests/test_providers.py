from __future__ import annotations

import base64
import json

import httpx
import pytest

from searchy.base import ProviderError
from searchy.providers import (
    BingProvider,
    BraveProvider,
    DuckDuckGoProvider,
    WikipediaProvider,
)


async def test_duckduckgo_text_unwraps_redirects_skips_ads_and_aligns_snippets() -> None:
    html = """
    <html><body><table>
      <tr class="result--ad">
        <td><a class="result-link" href="https://duckduckgo.com/y.js?ad_domain=ads.example">Sponsored</a></td>
      </tr>
      <tr><td class="result-snippet">Sponsored description</td></tr>
      <tr>
        <td><a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fno-snip&amp;rut=1">No Snippet Item</a></td>
      </tr>
      <tr>
        <td><a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Freal&amp;rut=2">Real Item</a></td>
      </tr>
      <tr><td class="result-snippet">Snippet for Real Item</td></tr>
    </table></body></html>
    """
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=html))
    async with httpx.AsyncClient(transport=transport) as client:
        items = await DuckDuckGoProvider().search_text(client, "test", limit=5)

    assert len(items) == 2
    assert items[0].url == "https://example.com/no-snip"
    assert items[0].snippet == ""
    assert items[1].url == "https://example.com/real"
    assert items[1].snippet == "Snippet for Real Item"


async def test_duckduckgo_caches_vqd_and_handles_nulls() -> None:
    vqd_hits = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal vqd_hits
        if req.url.host == "duckduckgo.com" and req.url.path == "/":
            vqd_hits += 1
            return httpx.Response(200, text='<html><script>vqd="4-555666777";</script></html>')
        if "/i.js" in str(req.url):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": None,
                            "image": "https://img.example.com/1.png",
                            "thumbnail": None,
                            "url": None,
                            "width": "",
                            "height": "600",
                        }
                    ]
                },
            )
        if "/v.js" in str(req.url):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": None,
                            "content": "https://vid.example.com/1",
                            "images": None,
                            "duration": None,
                            "description": None,
                        }
                    ]
                },
            )
        return httpx.Response(404)

    provider = DuckDuckGoProvider()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        imgs = await provider.search_images(client, "mountain", limit=5)
        vids = await provider.search_videos(client, "mountain", limit=5)

    assert vqd_hits == 1  # Shared vqd across images + videos!
    assert len(imgs) == 1
    assert imgs[0].title == ""
    assert imgs[0].width is None
    assert imgs[0].height == 600
    assert len(vids) == 1
    assert vids[0].duration == ""
    assert vids[0].snippet == ""


async def test_duckduckgo_detects_http_202_challenge() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(202, text="<html>challenge</html>"))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ProviderError) as exc_info:
            await DuckDuckGoProvider().search_images(client, "test")
    assert exc_info.value.status_code == 202


async def test_bing_unwraps_ck_and_handles_null_duration() -> None:
    encoded = "a1" + base64.urlsafe_b64encode(b"https://python.org/").decode().rstrip("=")
    text_html = f"""
    <ol id="b_results">
      <li class="b_algo">
        <h2><a href="https://www.bing.com/ck/a?u={encoded}">Python</a></h2>
        <div class="b_caption"><p>Official Python site.</p></div>
      </li>
      <li class="b_algo">
        <h2><a href="/search?q=internal">Internal Relative Link</a></h2>
        <p>Must be skipped.</p>
      </li>
    </ol>
    """
    vid_meta = json.dumps({"vt": None, "murl": "https://v.example.com/a", "turl": None, "du": None})
    vid_html = f"<div class='dg_u'><div class='vrhdata' vrhm='{vid_meta}'></div></div>"

    def handler(req: httpx.Request) -> httpx.Response:
        if "/videos/search" in str(req.url):
            return httpx.Response(200, text=vid_html)
        return httpx.Response(200, text=text_html)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        text_items = await BingProvider().search_text(client, "python")
        vid_items = await BingProvider().search_videos(client, "python")

    assert len(text_items) == 1
    assert text_items[0].url == "https://python.org/"
    assert text_items[0].snippet == "Official Python site."
    assert len(vid_items) == 1
    assert vid_items[0].duration == ""
    assert vid_items[0].title == ""


async def test_wikipedia_encodes_special_titles_and_unescapes_entities() -> None:
    payload = {
        "query": {
            "search": [
                {
                    "title": "C# (programming language)?",
                    "snippet": "<span class='searchmatch'>C#</span> &amp; &quot;.NET&quot;",
                }
            ]
        }
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        items = await WikipediaProvider().search_text(client, "C#")

    assert len(items) == 1
    assert items[0].url == "https://en.wikipedia.org/wiki/C%23_(programming_language)%3F"
    assert items[0].snippet == 'C# & ".NET"'


async def test_brave_extracts_clean_title_without_breadcrumb() -> None:
    html = """
    <div data-type="web">
      <a class="heading-serpresult" href="https://python.org">
        <span class="site">python.org</span>
        <div class="title">Welcome to Python.org</div>
      </a>
      <div class="snippet-description">The official home of Python.</div>
    </div>
    """
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=html))
    async with httpx.AsyncClient(transport=transport) as client:
        items = await BraveProvider().search_text(client, "python")

    assert len(items) == 1
    assert items[0].title == "Welcome to Python.org"
    assert items[0].snippet == "The official home of Python."
