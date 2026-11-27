from __future__ import annotations

import argparse
import html
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import __version__
from .engine import Searchy
from .models import (
    ProviderReport,
    SearchCategory,
    SearchResponse,
    SearchResult,
)
from .url_utils import canonicalize_url, extract_domain, unwrap_url


def _build_demo_response(
    query: str,
    category: SearchCategory,
    limit: int,
    selected_providers: list[str] | None,
    deduplicate: bool,
) -> SearchResponse:
    """Deterministic demo payload so the explorer UI works cleanly offline/in sandboxes."""
    q = query.strip() or "python asyncio"
    slug = "-".join(q.lower().split())[:40] or "search"
    allowed = {p.lower() for p in selected_providers} if selected_providers is not None else None

    def _keep(name: str) -> bool:
        return allowed is None or name in allowed

    if category == SearchCategory.TEXT:
        raw_pool: list[tuple[str, float, list[SearchResult]]] = [
            (
                "duckduckgo",
                118.4,
                [
                    SearchResult(
                        category=SearchCategory.TEXT,
                        provider="duckduckgo",
                        title=f"{q.title()} — Official Reference & Architecture Guide",
                        url=f"https://docs.python.org/3/library/{slug}.html",
                        snippet=f"Comprehensive documentation covering {q}, event loops, tasks, connection pooling, and structured concurrency.",
                    ),
                    SearchResult(
                        category=SearchCategory.TEXT,
                        provider="duckduckgo",
                        title=f"High-Performance {q.title()} Patterns in Production",
                        url=f"https://realpython.com/{slug}-guide/",
                        snippet=f"Practical walkthrough of {q} with benchmarks, backpressure strategies, and clean error isolation.",
                    ),
                    SearchResult(
                        category=SearchCategory.TEXT,
                        provider="duckduckgo",
                        title=f"GitHub: Awesome {q.title()} Curated Resources",
                        url=f"https://github.com/topics/{slug}",
                        snippet=f"Curated libraries, benchmarks, and production tools for {q} maintained by the open-source community.",
                    ),
                ],
            ),
            (
                "bing",
                142.9,
                [
                    SearchResult(
                        category=SearchCategory.TEXT,
                        provider="bing",
                        title=f"{q.title()} — Official Reference & Architecture Guide",
                        url=f"https://docs.python.org/3/library/{slug}.html",
                        snippet=f"Complete API reference and tutorials for {q}, including timeout boundaries, cancellation, and pooling best practices.",
                    ),
                    SearchResult(
                        category=SearchCategory.TEXT,
                        provider="bing",
                        title=f"Understanding {q.title()} Under the Hood",
                        url=f"https://engineering.example.com/posts/{slug}",
                        snippet=f"Deep dive into scheduling internals, latency profiles, and diagnostic tooling for {q}.",
                    ),
                    SearchResult(
                        category=SearchCategory.TEXT,
                        provider="bing",
                        title=f"Benchmarks Comparing {q.title()} Implementations",
                        url=f"https://benchmarks.dev/{slug}",
                        snippet=f"Reproducible latency percentiles (p50, p95, p99) and memory footprints across {q} setups.",
                    ),
                ],
            ),
            (
                "wikipedia",
                64.2,
                [
                    SearchResult(
                        category=SearchCategory.TEXT,
                        provider="wikipedia",
                        title=f"{q.title()} — Wikipedia",
                        url=f"https://en.wikipedia.org/wiki/{q.replace(' ', '_')}",
                        snippet=f"Encyclopedic overview of {q}, its history, core concepts, design trade-offs, and notable implementations.",
                    ),
                    SearchResult(
                        category=SearchCategory.TEXT,
                        provider="wikipedia",
                        title="Metasearch engine — Wikipedia",
                        url="https://en.wikipedia.org/wiki/Metasearch_engine",
                        snippet="A metasearch engine queries multiple search engines concurrently and merges results using ranking algorithms such as RRF.",
                    ),
                ],
            ),
            (
                "brave",
                171.6,
                [
                    SearchResult(
                        category=SearchCategory.TEXT,
                        provider="brave",
                        title=f"High-Performance {q.title()} Patterns in Production",
                        url=f"https://realpython.com/{slug}-guide/",
                        snippet=f"Practical walkthrough of {q} with benchmarks, backpressure strategies, and clean error isolation.",
                    ),
                    SearchResult(
                        category=SearchCategory.TEXT,
                        provider="brave",
                        title=f"{q.title()} Cheat Sheet & Common Pitfalls",
                        url=f"https://cheatsheets.dev/{slug}",
                        snippet=f"Concise checklist covering edge cases, HTTP/2 multiplexing, TTL caching, and safe sync/async bridges for {q}.",
                    ),
                ],
            ),
        ]
    elif category == SearchCategory.IMAGES:
        raw_pool = [
            (
                "duckduckgo",
                131.5,
                [
                    SearchResult(
                        category=SearchCategory.IMAGES,
                        provider="duckduckgo",
                        title=f"{q.title()} Architecture Diagram",
                        url="https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200",
                        thumbnail_url="https://images.unsplash.com/photo-1518770660439-4636190af475?w=480",
                        source_url="https://unsplash.com/photos/circuit-board",
                        width=1200,
                        height=800,
                    ),
                    SearchResult(
                        category=SearchCategory.IMAGES,
                        provider="duckduckgo",
                        title=f"{q.title()} Code Visualization",
                        url="https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=1200",
                        thumbnail_url="https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=480",
                        source_url="https://unsplash.com/photos/code-screen",
                        width=1200,
                        height=800,
                    ),
                ],
            ),
            (
                "bing",
                155.1,
                [
                    SearchResult(
                        category=SearchCategory.IMAGES,
                        provider="bing",
                        title=f"{q.title()} Architecture Diagram",
                        url="https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200",
                        thumbnail_url="https://images.unsplash.com/photo-1518770660439-4636190af475?w=480",
                        source_url="https://unsplash.com/photos/circuit-board",
                        width=1200,
                        height=800,
                    ),
                    SearchResult(
                        category=SearchCategory.IMAGES,
                        provider="bing",
                        title=f"{q.title()} Telemetry Dashboard",
                        url="https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200",
                        thumbnail_url="https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=480",
                        source_url="https://unsplash.com/photos/analytics-dashboard",
                        width=1200,
                        height=800,
                    ),
                ],
            ),
            (
                "wikipedia",
                72.8,
                [
                    SearchResult(
                        category=SearchCategory.IMAGES,
                        provider="wikipedia",
                        title=f"Commons Diagram — {q.title()}",
                        url="https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=1200",
                        thumbnail_url="https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=480",
                        source_url="https://commons.wikimedia.org/",
                        width=1200,
                        height=800,
                    ),
                ],
            ),
        ]
    else:
        raw_pool = [
            (
                "duckduckgo",
                148.0,
                [
                    SearchResult(
                        category=SearchCategory.VIDEOS,
                        provider="duckduckgo",
                        title=f"{q.title()} in 15 Minutes — Full Deep Dive",
                        url=f"https://www.youtube.com/watch?v=demo_{slug[:8]}1",
                        thumbnail_url="https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=480",
                        duration="15:42",
                        snippet=f"Step-by-step live coding walkthrough explaining {q} internals and performance tuning.",
                    ),
                    SearchResult(
                        category=SearchCategory.VIDEOS,
                        provider="duckduckgo",
                        title=f"Scaling {q.title()} Beyond 10k req/s",
                        url=f"https://www.youtube.com/watch?v=demo_{slug[:8]}2",
                        thumbnail_url="https://images.unsplash.com/photo-1504639725590-34d0984388bd?w=480",
                        duration="28:19",
                        snippet=f"Conference talk detailing connection pooling, single-flight coalescing, and RRF ranking for {q}.",
                    ),
                ],
            ),
            (
                "bing",
                163.4,
                [
                    SearchResult(
                        category=SearchCategory.VIDEOS,
                        provider="bing",
                        title=f"{q.title()} in 15 Minutes — Full Deep Dive",
                        url=f"https://www.youtube.com/watch?v=demo_{slug[:8]}1",
                        thumbnail_url="https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=480",
                        duration="15:42",
                        snippet=f"Step-by-step live coding walkthrough explaining {q} internals and performance tuning.",
                    ),
                    SearchResult(
                        category=SearchCategory.VIDEOS,
                        provider="bing",
                        title=f"Debugging Async Concurrency & {q.title()}",
                        url=f"https://www.youtube.com/watch?v=demo_{slug[:8]}3",
                        thumbnail_url="https://images.unsplash.com/photo-1515879218367-8466d910aaa4?w=480",
                        duration="19:05",
                        snippet="Practical debugging workshop covering timeouts, cancellation, and provider isolation.",
                    ),
                ],
            ),
        ]

    reports: list[ProviderReport] = []
    provider_counts: dict[str, int] = {}
    outcomes: list[tuple[ProviderReport, list[SearchResult]]] = []
    raw_total = 0

    for name, ms, items in raw_pool:
        if not _keep(name):
            continue
        sliced = items[:limit]
        rep = ProviderReport(
            provider=name,
            success=True,
            count=len(sliced),
            elapsed_ms=ms,
            status_code=200,
        )
        reports.append(rep)
        provider_counts[name] = len(sliced)
        outcomes.append((rep, sliced))
        raw_total += len(sliced)

    from .engine import _deduplicate_and_rank

    results = _deduplicate_and_rank(outcomes, deduplicate=deduplicate, rank=True)
    elapsed = max((r.elapsed_ms for r in reports), default=0.0)
    return SearchResponse(
        query=q,
        category=category,
        total_results=raw_total,
        unique_results=len(results),
        elapsed_ms=elapsed,
        cache_hit=False,
        provider_counts=provider_counts,
        providers=reports,
        results=results,
    )


def _render_html() -> str:
    version = html.escape(__version__)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>msearchy: Metasearch Explorer</title>
  <style>
    :root {{
      --bg: #0b0f17;
      --surface: #121826;
      --surface-2: #182032;
      --border: #24304a;
      --border-strong: #32446a;
      --text: #e6edf7;
      --muted: #8ea0bd;
      --accent: #38bdf8;
      --accent-soft: rgba(56, 189, 248, 0.14);
      --green: #34d399;
      --green-soft: rgba(52, 211, 153, 0.14);
      --amber: #fbbf24;
      --red: #f87171;
      --red-soft: rgba(248, 113, 113, 0.14);
      --purple: #a78bfa;
      --purple-soft: rgba(167, 139, 250, 0.14);
      --radius: 14px;
      --radius-sm: 9px;
      --font: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
      --mono: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Consolas, monospace;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      padding: 0;
      background:
        radial-gradient(900px 420px at 15% -10%, rgba(56, 189, 248, 0.14), transparent 60%),
        radial-gradient(700px 380px at 85% -10%, rgba(167, 139, 250, 0.12), transparent 60%),
        var(--bg);
      color: var(--text);
      font-family: var(--font);
      min-height: 100vh;
      line-height: 1.5;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    .shell {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 26px 20px 64px;
    }}

    /* Header */
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 22px;
      flex-wrap: wrap;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .logo {{
      width: 40px;
      height: 40px;
      border-radius: 11px;
      background: linear-gradient(135deg, #38bdf8, #818cf8);
      display: grid;
      place-items: center;
      font-weight: 800;
      font-size: 18px;
      color: #08101c;
      box-shadow: 0 8px 24px rgba(56, 189, 248, 0.25);
    }}
    .brand-title {{
      font-size: 20px;
      font-weight: 750;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .ver-pill {{
      font-family: var(--mono);
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.3);
    }}
    .brand-sub {{
      font-size: 13px;
      color: var(--muted);
    }}
    .top-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .mode-switch {{
      display: inline-flex;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 3px;
    }}
    .mode-btn {{
      border: 0;
      background: transparent;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      padding: 6px 12px;
      border-radius: 999px;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .mode-btn.active {{
      background: var(--accent);
      color: #07101c;
    }}
    .ghost-btn {{
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
      font-size: 12px;
      font-weight: 600;
      padding: 8px 12px;
      border-radius: 999px;
      cursor: pointer;
    }}
    .ghost-btn:hover {{
      border-color: var(--border-strong);
      background: var(--surface-2);
    }}

    /* Search Command Panel */
    .search-panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 18px;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
      margin-bottom: 20px;
    }}
    .search-row {{
      display: flex;
      gap: 10px;
      margin-bottom: 14px;
    }}
    .search-input {{
      flex: 1;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 11px;
      padding: 13px 16px;
      color: var(--text);
      font-size: 15px;
      outline: none;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }}
    .search-input:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.18);
    }}
    .search-submit {{
      background: linear-gradient(135deg, #38bdf8, #60a5fa);
      color: #06101d;
      border: 0;
      border-radius: 11px;
      padding: 0 22px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      white-space: nowrap;
      transition: transform 0.1s ease, opacity 0.15s ease;
    }}
    .search-submit:hover {{ opacity: 0.94; }}
    .search-submit:active {{ transform: scale(0.98); }}
    .search-submit:disabled {{ opacity: 0.55; cursor: wait; }}

    .controls-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
    }}
    .tab-group, .chip-group, .meta-controls {{
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .tab-btn {{
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 6px 13px;
      border-radius: 8px;
      font-size: 12.5px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .tab-btn.active {{
      background: var(--accent-soft);
      border-color: rgba(56, 189, 248, 0.55);
      color: var(--accent);
    }}
    .prov-chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 5px 11px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      user-select: none;
    }}
    .prov-chip .dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--border-strong);
    }}
    .prov-chip.active {{
      color: var(--text);
      border-color: var(--border-strong);
      background: var(--surface-2);
    }}
    .prov-chip.active .dot {{
      background: var(--green);
      box-shadow: 0 0 8px rgba(52, 211, 153, 0.7);
    }}
    .mini-select {{
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 8px;
      padding: 5px 9px;
      font-size: 12px;
    }}
    .toggle-label {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 12px;
      color: var(--muted);
      cursor: pointer;
    }}

    /* Telemetry Strip */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    @media (max-width: 780px) {{
      .stats-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    .stat-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 13px 15px;
    }}
    .stat-label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    .stat-val {{
      font-size: 21px;
      font-weight: 750;
      font-family: var(--mono);
      letter-spacing: -0.02em;
    }}
    .stat-sub {{
      font-size: 11.5px;
      color: var(--muted);
      margin-top: 2px;
    }}

    /* Main 2-column Layout */
    .workspace {{
      display: grid;
      grid-template-columns: 290px minmax(0, 1fr);
      gap: 18px;
      align-items: start;
    }}
    @media (max-width: 900px) {{
      .workspace {{ grid-template-columns: 1fr; }}
    }}

    .panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 16px;
    }}
    .panel-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--border);
    }}
    .panel-title {{
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }}

    /* Provider Telemetry Rows */
    .prov-row {{
      padding: 10px 0;
      border-bottom: 1px solid rgba(36, 48, 74, 0.55);
    }}
    .prov-row:last-child {{ border-bottom: 0; padding-bottom: 2px; }}
    .prov-row-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 13px;
      margin-bottom: 6px;
    }}
    .prov-name {{
      font-weight: 650;
      display: flex;
      align-items: center;
      gap: 7px;
    }}
    .badge {{
      font-family: var(--mono);
      font-size: 10.5px;
      padding: 2px 7px;
      border-radius: 6px;
      font-weight: 700;
    }}
    .badge-ok {{ background: var(--green-soft); color: var(--green); }}
    .badge-err {{ background: var(--red-soft); color: var(--red); }}
    .badge-rrf {{ background: var(--purple-soft); color: var(--purple); }}
    .badge-prov {{ background: var(--accent-soft); color: var(--accent); }}
    .bar-track {{
      height: 6px;
      background: var(--bg);
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, #38bdf8, #34d399);
    }}
    .bar-fill.err {{
      background: var(--red);
    }}
    .prov-err {{
      margin-top: 6px;
      font-size: 11.5px;
      font-family: var(--mono);
      color: var(--red);
      word-break: break-word;
    }}

    /* View Tabs */
    .view-switch {{
      display: inline-flex;
      gap: 4px;
      background: var(--bg);
      padding: 3px;
      border-radius: 8px;
      border: 1px solid var(--border);
    }}
    .view-btn {{
      border: 0;
      background: transparent;
      color: var(--muted);
      font-size: 11.5px;
      font-weight: 650;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
    }}
    .view-btn.active {{
      background: var(--surface-2);
      color: var(--text);
    }}

    /* Result Cards */
    .section-heading {{
      font-size: 12px;
      font-weight: 750;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--accent);
      margin: 18px 0 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .section-heading:first-child {{ margin-top: 0; }}

    .result-list {{
      display: flex;
      flex-direction: column;
      gap: 11px;
    }}
    .result-card {{
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 11px;
      padding: 14px 15px;
      transition: border-color 0.15s ease, transform 0.12s ease;
    }}
    .result-card:hover {{
      border-color: var(--border-strong);
      transform: translateY(-1px);
    }}
    .card-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 5px;
      flex-wrap: wrap;
    }}
    .card-domain {{
      font-family: var(--mono);
      font-size: 11.5px;
      color: var(--muted);
    }}
    .card-badges {{
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .card-title {{
      display: block;
      font-size: 15.5px;
      font-weight: 650;
      color: var(--text);
      margin-bottom: 5px;
    }}
    .card-title:hover {{ color: var(--accent); }}
    .card-snippet {{
      font-size: 13.5px;
      color: var(--muted);
      margin: 0 0 8px;
    }}
    .card-url {{
      font-family: var(--mono);
      font-size: 11.5px;
      color: #6ea8d6;
      word-break: break-all;
    }}

    /* Image & Video Grids */
    .media-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: 12px;
    }}
    .media-card {{
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 11px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      transition: border-color 0.15s ease, transform 0.12s ease;
    }}
    .media-card:hover {{
      border-color: var(--border-strong);
      transform: translateY(-1px);
    }}
    .media-thumb-wrap {{
      position: relative;
      aspect-ratio: 16 / 10;
      background: #0f1625;
      overflow: hidden;
    }}
    .media-thumb {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .duration-pill {{
      position: absolute;
      right: 8px;
      bottom: 8px;
      background: rgba(8, 12, 22, 0.86);
      color: var(--text);
      font-family: var(--mono);
      font-size: 11px;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 6px;
      border: 1px solid rgba(255, 255, 255, 0.14);
    }}
    .media-body {{
      padding: 11px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      flex: 1;
    }}
    .media-title {{
      font-size: 13px;
      font-weight: 650;
      color: var(--text);
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .media-meta {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      font-family: var(--mono);
      color: var(--muted);
      margin-top: auto;
    }}

    /* Code View (JSON / Markdown) */
    .code-box {{
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px;
      font-family: var(--mono);
      font-size: 12px;
      color: #cbd5e1;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 640px;
      margin: 0;
    }}
    .empty-state {{
      text-align: center;
      padding: 36px 20px;
      color: var(--muted);
      font-size: 14px;
    }}

    /* URL Unwrapper Drawer */
    .modal-backdrop {{
      position: fixed;
      inset: 0;
      background: rgba(5, 8, 15, 0.72);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
      z-index: 40;
    }}
    .modal-backdrop.open {{ display: flex; }}
    .modal {{
      width: 100%;
      max-width: 640px;
      background: var(--surface);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
      padding: 20px;
      box-shadow: 0 24px 64px rgba(0, 0, 0, 0.5);
    }}
    .unwrap-out {{
      margin-top: 12px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 12px;
      font-family: var(--mono);
      font-size: 12px;
      display: grid;
      gap: 6px;
      word-break: break-all;
    }}
    .notice {{
      font-size: 12px;
      color: var(--amber);
      background: rgba(251, 191, 36, 0.1);
      border: 1px solid rgba(251, 191, 36, 0.25);
      border-radius: 9px;
      padding: 8px 12px;
      margin-bottom: 14px;
      display: none;
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="logo">S</div>
        <div>
          <div class="brand-title">
            msearchy <span class="ver-pill">v{version}</span>
          </div>
          <div class="brand-sub">Parallel Async Metasearch · RRF Fusion · Redirect Unwrapper</div>
        </div>
      </div>
      <div class="top-actions">
        <div class="mode-switch" title="Demo mode renders deterministic sample results when outbound search engines are restricted">
          <button type="button" class="mode-btn active" data-mode="demo">Demo Mode</button>
          <button type="button" class="mode-btn" data-mode="live">Live Engines</button>
        </div>
        <button type="button" class="ghost-btn" id="openUnwrapBtn">URL Unwrapper</button>
      </div>
    </header>

    <section class="search-panel">
      <form id="searchForm" class="search-row">
        <input
          id="queryInput"
          class="search-input"
          type="text"
          value="python asyncio"
          placeholder="Search across DuckDuckGo, Bing, Wikipedia, Brave..."
          autocomplete="off"
        />
        <button id="searchBtn" class="search-submit" type="submit">Search</button>
      </form>

      <div class="controls-row">
        <div class="tab-group" id="categoryTabs">
          <button type="button" class="tab-btn" data-cat="text">Text</button>
          <button type="button" class="tab-btn" data-cat="images">Images</button>
          <button type="button" class="tab-btn" data-cat="videos">Videos</button>
          <button type="button" class="tab-btn active" data-cat="all">All Categories</button>
        </div>

        <div class="chip-group" id="providerChips">
          <span class="prov-chip active" data-provider="duckduckgo"><span class="dot"></span>duckduckgo</span>
          <span class="prov-chip active" data-provider="bing"><span class="dot"></span>bing</span>
          <span class="prov-chip active" data-provider="wikipedia"><span class="dot"></span>wikipedia</span>
          <span class="prov-chip active" data-provider="brave"><span class="dot"></span>brave</span>
        </div>

        <div class="meta-controls">
          <select id="limitSelect" class="mini-select" aria-label="Results per provider">
            <option value="3">3 / engine</option>
            <option value="5" selected>5 / engine</option>
            <option value="10">10 / engine</option>
          </select>
          <label class="toggle-label">
            <input type="checkbox" id="dedupToggle" checked />
            Dedup + RRF
          </label>
        </div>
      </div>
    </section>

    <div id="modeNotice" class="notice"></div>

    <section class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Unique Results</div>
        <div class="stat-val" id="statUnique">0</div>
        <div class="stat-sub" id="statRaw">0 raw before merge</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Wall Latency</div>
        <div class="stat-val" id="statLatency">0 ms</div>
        <div class="stat-sub" id="statCache">Parallel async gather</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Providers Healthy</div>
        <div class="stat-val" id="statHealth">0 / 0</div>
        <div class="stat-sub" id="statMode">Mode: demo</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Duplicates Merged</div>
        <div class="stat-val" id="statDupes">0</div>
        <div class="stat-sub">Canonical URL + RRF boost</div>
      </div>
    </section>

    <main class="workspace">
      <aside class="panel">
        <div class="panel-head">
          <span class="panel-title">Provider Telemetry</span>
          <span class="ver-pill" id="telemetryTag">ready</span>
        </div>
        <div id="telemetryBody">
          <div class="empty-state">Run a search to inspect provider timings.</div>
        </div>
      </aside>

      <section class="panel">
        <div class="panel-head">
          <span class="panel-title" id="resultsHeading">Results</span>
          <div class="view-switch" id="viewSwitch">
            <button type="button" class="view-btn active" data-view="cards">Cards</button>
            <button type="button" class="view-btn" data-view="json">JSON</button>
            <button type="button" class="view-btn" data-view="markdown">Markdown</button>
          </div>
        </div>
        <div id="resultsBody">
          <div class="empty-state">Loading initial search...</div>
        </div>
      </section>
    </main>
  </div>

  <div class="modal-backdrop" id="unwrapModal">
    <div class="modal">
      <div class="panel-head">
        <span class="panel-title">Redirect Unwrapper &amp; URL Canonicalizer</span>
        <button type="button" class="ghost-btn" id="closeUnwrapBtn">Close</button>
      </div>
      <form id="unwrapForm" class="search-row" style="margin-bottom: 10px;">
        <input
          id="unwrapInput"
          class="search-input"
          type="text"
          value="https://www.google.com/url?q=https://docs.python.org/3/library/asyncio.html?utm_source=bing#tasks"
          placeholder="Paste a Bing ck/a, DuckDuckGo /l/?uddg=, or Google /url?q= link"
        />
        <button type="submit" class="search-submit">Unwrap</button>
      </form>
      <div id="unwrapOutput" class="unwrap-out">
        <div><strong>Unwrapped:</strong> <span id="uTarget">-</span></div>
        <div><strong>Canonical:</strong> <span id="uCanon">-</span></div>
        <div><strong>Domain:</strong> <span id="uDomain">-</span></div>
      </div>
    </div>
  </div>

  <script>
    const state = {{
      category: "all",
      mode: "demo",
      view: "cards",
      providers: new Set(["duckduckgo", "bing", "wikipedia", "brave"]),
      lastPayload: null,
    }};

    const $ = (id) => document.getElementById(id);

    function esc(str) {{
      return String(str ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    document.querySelectorAll(".mode-btn").forEach((btn) => {{
      btn.addEventListener("click", () => {{
        document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.mode = btn.dataset.mode;
        runSearch();
      }});
    }});

    document.querySelectorAll("#categoryTabs .tab-btn").forEach((btn) => {{
      btn.addEventListener("click", () => {{
        document.querySelectorAll("#categoryTabs .tab-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.category = btn.dataset.cat;
        runSearch();
      }});
    }});

    document.querySelectorAll("#providerChips .prov-chip").forEach((chip) => {{
      chip.addEventListener("click", () => {{
        const p = chip.dataset.provider;
        if (state.providers.has(p)) {{
          state.providers.delete(p);
          chip.classList.remove("active");
        }} else {{
          state.providers.add(p);
          chip.classList.add("active");
        }}
        runSearch();
      }});
    }});

    document.querySelectorAll("#viewSwitch .view-btn").forEach((btn) => {{
      btn.addEventListener("click", () => {{
        document.querySelectorAll("#viewSwitch .view-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.view = btn.dataset.view;
        renderResults();
      }});
    }});

    $("limitSelect").addEventListener("change", runSearch);
    $("dedupToggle").addEventListener("change", runSearch);
    $("searchForm").addEventListener("submit", (e) => {{
      e.preventDefault();
      runSearch();
    }});

    $("openUnwrapBtn").addEventListener("click", () => {{
      $("unwrapModal").classList.add("open");
      runUnwrap();
    }});
    $("closeUnwrapBtn").addEventListener("click", () => $("unwrapModal").classList.remove("open"));
    $("unwrapModal").addEventListener("click", (e) => {{
      if (e.target === $("unwrapModal")) $("unwrapModal").classList.remove("open");
    }});
    $("unwrapForm").addEventListener("submit", (e) => {{
      e.preventDefault();
      runUnwrap();
    }});

    async function runUnwrap() {{
      const url = $("unwrapInput").value.trim();
      if (!url) return;
      const resp = await fetch(`/api/unwrap?url=${{encodeURIComponent(url)}}`);
      const data = await resp.json();
      $("uTarget").textContent = data.unwrapped || "-";
      $("uCanon").textContent = data.canonical || "-";
      $("uDomain").textContent = data.domain || "-";
    }}

    async function runSearch() {{
      const q = $("queryInput").value.trim();
      if (!q) return;
      $("searchBtn").disabled = true;
      $("telemetryTag").textContent = "querying...";
      const params = new URLSearchParams({{
        q,
        category: state.category,
        limit: $("limitSelect").value,
        dedup: $("dedupToggle").checked ? "1" : "0",
        mode: state.mode,
        providers: Array.from(state.providers).join(","),
      }});

      try {{
        const resp = await fetch(`/api/search?${{params.toString()}}`);
        const payload = await resp.json();
        state.lastPayload = payload;
        renderStats(payload);
        renderTelemetry(payload);
        renderResults();
      }} catch (err) {{
        $("resultsBody").innerHTML = `<div class="empty-state">Request failed: ${{esc(err.message)}}</div>`;
      }} finally {{
        $("searchBtn").disabled = false;
      }}
    }}

    function collectResponses(payload) {{
      if (!payload || !payload.data) return [];
      if (payload.category === "all") {{
        return ["text", "images", "videos"]
          .map((cat) => payload.data[cat])
          .filter(Boolean);
      }}
      return [payload.data];
    }}

    function renderStats(payload) {{
      const responses = collectResponses(payload);
      let unique = 0, raw = 0, ok = 0, totalProv = 0, maxMs = 0, cacheHits = 0;
      for (const r of responses) {{
        unique += r.unique_results || 0;
        raw += r.total_results || 0;
        maxMs = Math.max(maxMs, r.elapsed_ms || 0);
        if (r.cache_hit) cacheHits += 1;
        for (const p of r.providers || []) {{
          totalProv += 1;
          if (p.success) ok += 1;
        }}
      }}
      $("statUnique").textContent = unique;
      $("statRaw").textContent = `${{raw}} raw before merge`;
      $("statLatency").textContent = `${{maxMs.toFixed(1)}} ms`;
      $("statCache").textContent = cacheHits > 0 ? "Served from TTL cache" : "Parallel async gather";
      $("statHealth").textContent = `${{ok}} / ${{totalProv}}`;
      $("statMode").textContent = `Mode: ${{payload.mode}}`;
      $("statDupes").textContent = Math.max(0, raw - unique);
      $("telemetryTag").textContent = `${{maxMs.toFixed(0)}} ms`;

      const notice = $("modeNotice");
      if (payload.mode === "live" && totalProv > 0 && ok === 0) {{
        notice.style.display = "block";
        notice.textContent = "Live engines could not be reached from this network environment. Switch to Demo Mode to inspect full RRF fusion, cards, and media layouts.";
      }} else if (payload.mode === "demo") {{
        notice.style.display = "block";
        notice.textContent = "Demo Mode active: deterministic sample responses demonstrating RRF consensus ranking, canonical URL deduplication, and provider telemetry.";
      }} else {{
        notice.style.display = "none";
      }}
    }}

    function renderTelemetry(payload) {{
      const responses = collectResponses(payload);
      const rows = [];
      for (const r of responses) {{
        const maxMs = Math.max(1, ...(r.providers || []).map((p) => p.elapsed_ms || 0));
        if (responses.length > 1) {{
          rows.push(`<div class="section-heading" style="margin-top:12px;"><span>${{esc(r.category)}}</span><span>${{r.unique_results}} hits</span></div>`);
        }}
        for (const p of r.providers || []) {{
          const pct = Math.min(100, Math.max(4, Math.round(((p.elapsed_ms || 0) / maxMs) * 100)));
          rows.push(`
            <div class="prov-row">
              <div class="prov-row-top">
                <span class="prov-name">
                  <span>${{esc(p.provider)}}</span>
                  <span class="badge ${{p.success ? "badge-ok" : "badge-err"}}">${{p.success ? "OK" : "ERR"}}</span>
                </span>
                <span style="font-family:var(--mono);font-size:12px;color:var(--muted);">
                  ${{p.count}} · ${{(p.elapsed_ms || 0).toFixed(1)}} ms
                </span>
              </div>
              <div class="bar-track">
                <div class="bar-fill ${{p.success ? "" : "err"}}" style="width:${{pct}}%;"></div>
              </div>
              ${{!p.success && p.error ? `<div class="prov-err">${{esc(p.error)}}</div>` : ""}}
            </div>
          `);
        }}
      }}
      $("telemetryBody").innerHTML = rows.length ? rows.join("") : '<div class="empty-state">No providers selected.</div>';
    }}

    function renderTextCard(item) {{
      const matched = item.providers_matched && item.providers_matched.length ? item.providers_matched : [item.provider];
      const badges = matched.map((p) => `<span class="badge badge-prov">${{esc(p)}}</span>`).join("");
      const rrf = item.score ? `<span class="badge badge-rrf">RRF ${{Number(item.score).toFixed(4)}}</span>` : "";
      return `
        <article class="result-card">
          <div class="card-top">
            <span class="card-domain">${{esc(item.domain || "")}}</span>
            <div class="card-badges">${{badges}}${{rrf}}</div>
          </div>
          <a class="card-title" href="${{esc(item.url)}}" target="_blank" rel="noopener noreferrer">${{esc(item.title || item.url)}}</a>
          ${{item.snippet ? `<p class="card-snippet">${{esc(item.snippet)}}</p>` : ""}}
          <div class="card-url">${{esc(item.url)}}</div>
        </article>
      `;
    }}

    function renderMediaCard(item) {{
      const img = item.thumbnail_url || item.url;
      const dims = item.width && item.height ? `${{item.width}}×${{item.height}}` : (item.domain || "");
      const matched = item.providers_matched && item.providers_matched.length ? item.providers_matched.join("+") : item.provider;
      return `
        <article class="media-card">
          <a class="media-thumb-wrap" href="${{esc(item.url)}}" target="_blank" rel="noopener noreferrer">
            <img class="media-thumb" src="${{esc(img)}}" alt="${{esc(item.title || "")}}" loading="lazy" />
            ${{item.duration ? `<span class="duration-pill">${{esc(item.duration)}}</span>` : ""}}
          </a>
          <div class="media-body">
            <a class="media-title" href="${{esc(item.url)}}" target="_blank" rel="noopener noreferrer">${{esc(item.title || item.url)}}</a>
            ${{item.snippet ? `<div style="font-size:12px;color:var(--muted);">${{esc(item.snippet)}}</div>` : ""}}
            <div class="media-meta">
              <span>${{esc(matched)}}</span>
              <span>${{esc(dims)}}</span>
            </div>
          </div>
        </article>
      `;
    }}

    function renderResults() {{
      const payload = state.lastPayload;
      if (!payload) return;
      $("resultsHeading").textContent = `Results for "${{payload.query}}"`;

      if (state.view === "json") {{
        $("resultsBody").innerHTML = `<pre class="code-box">${{esc(JSON.stringify(payload.data, null, 2))}}</pre>`;
        return;
      }}
      if (state.view === "markdown") {{
        $("resultsBody").innerHTML = `<pre class="code-box">${{esc(payload.markdown || "")}}</pre>`;
        return;
      }}

      const responses = collectResponses(payload);
      const chunks = [];
      for (const r of responses) {{
        chunks.push(`<div class="section-heading"><span>${{esc(r.category)}} results</span><span>${{r.unique_results}} unique</span></div>`);
        const items = r.results || [];
        if (!items.length) {{
          chunks.push('<div class="empty-state" style="padding:18px;">No results in this category.</div>');
          continue;
        }}
        if (r.category === "text") {{
          chunks.push(`<div class="result-list">${{items.map(renderTextCard).join("")}}</div>`);
        }} else {{
          chunks.push(`<div class="media-grid">${{items.map(renderMediaCard).join("")}}</div>`);
        }}
      }}
      $("resultsBody").innerHTML = chunks.join("");
    }}

    runSearch();
  </script>
</body>
</html>
"""


class _SearchyHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], timeout: float = 8.0) -> None:
        self.engine = Searchy(timeout=timeout, cache_ttl=60.0)
        self.html_page = _render_html().encode("utf-8")
        super().__init__(server_address, _SearchyHandler)


class _SearchyHandler(BaseHTTPRequestHandler):
    server: _SearchyHTTPServer

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send_html(self.server.html_page)
            return

        if path == "/api/health":
            self._send_json({"status": "ok", "version": __version__})
            return

        if path == "/api/providers":
            self._send_json({"providers": self.server.engine.list_providers()})
            return

        if path == "/api/unwrap":
            raw_url = (qs.get("url") or [""])[0]
            target = unwrap_url(raw_url)
            self._send_json(
                {
                    "input": raw_url,
                    "unwrapped": target,
                    "canonical": canonicalize_url(target),
                    "domain": extract_domain(target),
                }
            )
            return

        if path == "/api/search":
            query = (qs.get("q") or [""])[0].strip()
            category = (qs.get("category") or ["text"])[0].strip().lower()
            mode = (qs.get("mode") or ["live"])[0].strip().lower()
            dedup = (qs.get("dedup") or ["1"])[0].strip().lower() not in ("0", "false", "no")
            try:
                limit = max(1, min(25, int((qs.get("limit") or ["5"])[0])))
            except ValueError:
                limit = 5

            providers: list[str] | None = None
            if "providers" in qs:
                raw_providers = [p.strip() for p in qs["providers"][0].split(",") if p.strip()]
                providers = raw_providers

            if not query:
                self._send_json({"error": "Missing query parameter 'q'"}, HTTPStatus.BAD_REQUEST)
                return

            if category not in ("text", "images", "videos", "all"):
                self._send_json({"error": f"Invalid category: {category}"}, HTTPStatus.BAD_REQUEST)
                return

            if mode == "demo":
                if category == "all":
                    bundle = {
                        cat: _build_demo_response(query, cat, limit, providers, dedup)
                        for cat in (SearchCategory.TEXT, SearchCategory.IMAGES, SearchCategory.VIDEOS)
                    }
                    self._send_json(
                        {
                            "query": query,
                            "category": "all",
                            "mode": "demo",
                            "data": {k.value: v.to_dict() for k, v in bundle.items()},
                            "markdown": "\n\n".join(v.to_markdown() for v in bundle.values()),
                        }
                    )
                    return

                cat_enum = SearchCategory.coerce(category)
                res = _build_demo_response(query, cat_enum, limit, providers, dedup)
                self._send_json(
                    {
                        "query": query,
                        "category": category,
                        "mode": "demo",
                        "data": res.to_dict(),
                        "markdown": res.to_markdown(),
                    }
                )
                return

            if category == "all":
                live_bundle = self.server.engine.search_all(
                    query=query,
                    limit_per_provider=limit,
                    providers=providers,
                    deduplicate=dedup,
                )
                self._send_json(
                    {
                        "query": query,
                        "category": "all",
                        "mode": "live",
                        "data": live_bundle.to_dict(),
                        "markdown": live_bundle.to_markdown(),
                    }
                )
                return

            live_res = self.server.engine.search(
                query=query,
                category=category,
                limit_per_provider=limit,
                providers=providers,
                deduplicate=dedup,
            )
            self._send_json(
                {
                    "query": query,
                    "category": category,
                    "mode": "live",
                    "data": live_res.to_dict(),
                    "markdown": live_res.to_markdown(),
                }
            )
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)


def create_server(
    host: str = "0.0.0.0", port: int = 8080, timeout: float = 8.0
) -> _SearchyHTTPServer:
    return _SearchyHTTPServer((host, port), timeout=timeout)


def serve(host: str = "0.0.0.0", port: int = 8080, timeout: float = 8.0) -> None:
    server = create_server(host=host, port=port, timeout=timeout)
    print(f"msearchy web explorer listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="searchy-web",
        description="Launch the built-in msearchy Metasearch Explorer web UI.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument("--timeout", type=float, default=8.0, help="Provider timeout in seconds")
    args = parser.parse_args(argv)

    serve(host=args.host, port=args.port, timeout=args.timeout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
