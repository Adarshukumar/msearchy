from __future__ import annotations

import os
import shutil
import sys
import textwrap
from collections.abc import Mapping

from .models import ProviderReport, SearchBundle, SearchCategory, SearchResponse, SearchResult

_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
}


class _Styler:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def wrap(self, text: str, *styles: str) -> str:
        if not self.enabled or not styles:
            return text
        prefix = "".join(_ANSI[s] for s in styles if s in _ANSI)
        return f"{prefix}{text}{_ANSI['reset']}"


def should_use_color(no_color: bool = False) -> bool:
    if no_color or os.environ.get("NO_COLOR") is not None:
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _terminal_width(max_width: int = 100) -> int:
    cols = shutil.get_terminal_size((88, 24)).columns
    return max(60, min(cols, max_width))


def _latency_bar(elapsed_ms: float, max_ms: float, width: int = 14) -> str:
    if max_ms <= 0:
        return "░" * width
    filled = max(1, round((elapsed_ms / max_ms) * width)) if elapsed_ms > 0 else 0
    filled = min(width, filled)
    return "█" * filled + "░" * (width - filled)


def _frame_header(title: str, subtitle: str, width: int, st: _Styler) -> list[str]:
    inner = width - 2
    top = f"╭{'─' * inner}╮"
    bottom = f"╰{'─' * inner}╯"
    title_pad = max(0, inner - 2 - len(title))
    sub_pad = max(0, inner - 2 - len(subtitle))
    line1 = f"│ {st.wrap(title, 'bold', 'cyan')}{' ' * title_pad} │"
    line2 = f"│ {st.wrap(subtitle, 'dim')}{' ' * sub_pad} │"
    return [st.wrap(top, "dim"), line1, line2, st.wrap(bottom, "dim")]


def _render_provider_table(reports: list[ProviderReport], st: _Styler) -> list[str]:
    if not reports:
        return [st.wrap("  No providers selected.", "yellow")]

    max_ms = max((r.elapsed_ms for r in reports), default=1.0)
    lines = [
        st.wrap(
            f"  {'PROVIDER':<13} {'STATUS':<7} {'HITS':>5}  {'LATENCY':>9}  TIMING",
            "dim",
        )
    ]
    for rep in reports:
        status = st.wrap("OK", "green", "bold") if rep.success else st.wrap("ERR", "red", "bold")
        bar_color = "green" if rep.success else "red"
        bar = st.wrap(_latency_bar(rep.elapsed_ms, max_ms), bar_color)
        # Pad visible width for ANSI status tag (2 or 3 chars).
        raw_len = 2 if rep.success else 3
        status_padded = f"{status}{' ' * (7 - raw_len)}"
        lines.append(
            f"  {rep.provider:<13} {status_padded} {rep.count:>5}  {rep.elapsed_ms:>6.1f} ms  {bar}"
        )
        if not rep.success and rep.error:
            lines.append(st.wrap(f"    -> {rep.error}", "red"))
    return lines


def _render_result_card(idx: int, item: SearchResult, width: int, st: _Styler) -> list[str]:
    matched = item.providers_matched or [item.provider]
    badge = f"[{item.provider}]"
    if len(matched) > 1:
        others = ", ".join(p for p in matched if p != item.provider)
        badge += f" (+{len(matched) - 1}: {others})"

    meta_parts: list[str] = []
    if item.domain:
        meta_parts.append(item.domain)
    if item.width and item.height:
        meta_parts.append(f"{item.width}x{item.height}")
    if item.duration:
        meta_parts.append(item.duration)
    if item.score > 0:
        meta_parts.append(f"rrf {item.score:.4f}")

    title = item.title or item.url
    header = f"  {st.wrap(f'{idx:>2}.', 'bold', 'cyan')} {st.wrap(title, 'bold')}"
    tag_line = f"      {st.wrap(badge, 'magenta')}  {st.wrap(' | '.join(meta_parts), 'dim')}"
    url_line = f"      {st.wrap(item.url, 'blue')}"
    lines = [header, tag_line, url_line]

    if item.snippet:
        wrapped = textwrap.wrap(item.snippet, width=max(40, width - 8))
        for seg in wrapped[:3]:
            lines.append(f"      {seg}")
    if item.thumbnail_url:
        lines.append(f"      {st.wrap(f'thumb: {item.thumbnail_url}', 'dim')}")
    return lines


def render_response(
    response: SearchResponse,
    *,
    fmt: str = "pretty",
    no_color: bool = False,
    width: int | None = None,
) -> str:
    """Render a single SearchResponse as pretty framed UI, compact list, JSON, or Markdown."""
    if fmt == "json":
        return response.to_json(indent=2)
    if fmt == "markdown":
        return response.to_markdown()

    st = _Styler(enabled=should_use_color(no_color))
    if fmt == "compact":
        lines = [
            f"[{response.category.value}] {response.query!r} | "
            f"{response.unique_results} unique ({response.total_results} total) | "
            f"{response.elapsed_ms:.1f} ms"
        ]
        for idx, item in enumerate(response.results, 1):
            lines.append(f"{idx:>2}. [{item.provider}] {item.title or item.url} -> {item.url}")
        for rep in response.providers:
            if not rep.success:
                lines.append(f"ERR [{rep.provider}] {rep.error or 'Unknown error'}")
        return "\n".join(lines)

    box_w = width or _terminal_width()
    cache_tag = " | cache hit" if response.cache_hit else ""
    dedup_tag = (
        f" | {response.duplicates_removed} dupes merged"
        if response.duplicates_removed > 0
        else ""
    )
    title = f"msearchy  {response.category.value.upper()}  \"{response.query}\""
    subtitle = (
        f"{response.unique_results} unique / {response.total_results} raw"
        f"{dedup_tag} | {response.elapsed_ms:.1f} ms{cache_tag}"
    )

    out: list[str] = []
    out.extend(_frame_header(title, subtitle, box_w, st))
    out.append("")
    out.extend(_render_provider_table(response.providers, st))
    out.append("")

    if not response.results:
        out.append(st.wrap("  No results returned.", "yellow"))
    else:
        for idx, item in enumerate(response.results, 1):
            out.extend(_render_result_card(idx, item, box_w, st))
            out.append("")

    return "\n".join(out).rstrip()


def render_bundle(
    bundle: Mapping[SearchCategory, SearchResponse],
    *,
    fmt: str = "pretty",
    no_color: bool = False,
    width: int | None = None,
) -> str:
    """Render a multi-category SearchBundle in the selected output format."""
    wrapped = bundle if isinstance(bundle, SearchBundle) else SearchBundle(bundle)
    if fmt == "json":
        return wrapped.to_json(indent=2)
    if fmt == "markdown":
        return wrapped.to_markdown()

    sections = [
        render_response(res, fmt=fmt, no_color=no_color, width=width)
        for res in wrapped.values()
    ]
    return "\n\n".join(sections)
