from __future__ import annotations

import argparse
import asyncio
import sys

from . import __version__
from .engine import Searchy
from .models import SearchCategory
from .render import render_bundle, render_response, should_use_color


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("limit must be at least 1")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="searchy",
        description="Parallel metasearch CLI for text, images, and videos.",
    )
    parser.add_argument("query", nargs="?", default=None, help="Search query")
    parser.add_argument(
        "-c",
        "--category",
        choices=[c.value for c in SearchCategory] + ["all"],
        default="text",
        help="Search category (text, images, videos, or all)",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=_positive_int,
        default=5,
        help="Max results per provider (default: 5)",
    )
    parser.add_argument(
        "-p",
        "--providers",
        nargs="+",
        default=None,
        help="Filter providers (duckduckgo, bing, wikipedia, brave)",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=_positive_float,
        default=8.0,
        help="Per-provider timeout in seconds (default: 8.0)",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Disable cross-provider URL deduplication",
    )
    parser.add_argument(
        "--no-rank",
        action="store_true",
        help="Keep provider order instead of Reciprocal Rank Fusion sorting",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["pretty", "compact", "json", "markdown"],
        default="pretty",
        help="Output format (default: pretty)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Shorthand for --format json",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Print each provider's results as soon as it finishes",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color sequences",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Launch the built-in Searchy web explorer UI",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host for --serve (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Bind port for --serve (default: 8080)",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"msearchy {__version__}",
    )
    return parser


async def _run_stream(
    client: Searchy,
    query: str,
    category: str,
    limit: int,
    providers: list[str] | None,
    no_color: bool,
) -> None:
    use_color = should_use_color(no_color)
    async with client:
        async for report, items in client.astream(
            query=query,
            category=category,
            limit_per_provider=limit,
            providers=providers,
        ):
            status = "OK" if report.success else "ERR"
            header = f"[{status}] {report.provider} ({report.count} hits, {report.elapsed_ms:.1f} ms)"
            if use_color:
                code = "\033[32m" if report.success else "\033[31m"
                print(f"{code}{header}\033[0m", flush=True)
            else:
                print(header, flush=True)
            if not report.success and report.error:
                print(f"  error: {report.error}", flush=True)
            for idx, item in enumerate(items, 1):
                print(f"  {idx}. {item.title or item.url} -> {item.url}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.serve:
        from .web import serve

        serve(host=args.host, port=args.port, timeout=args.timeout)
        return 0

    if not args.query or not args.query.strip():
        parser.error("a non-empty query is required unless --serve is passed")

    fmt = "json" if args.json else args.format
    client = Searchy(timeout=args.timeout)

    if args.stream and args.category != "all" and fmt != "json":
        asyncio.run(
            _run_stream(
                client=client,
                query=args.query,
                category=args.category,
                limit=args.limit,
                providers=args.providers,
                no_color=args.no_color,
            )
        )
        return 0

    if args.category == "all":
        bundle = client.search_all(
            query=args.query,
            limit_per_provider=args.limit,
            providers=args.providers,
            deduplicate=not args.no_dedup,
            rank=not args.no_rank,
        )
        print(render_bundle(bundle, fmt=fmt, no_color=args.no_color))
        return 0

    response = client.search(
        query=args.query,
        category=args.category,
        limit_per_provider=args.limit,
        providers=args.providers,
        deduplicate=not args.no_dedup,
        rank=not args.no_rank,
    )
    print(render_response(response, fmt=fmt, no_color=args.no_color))
    return 0


if __name__ == "__main__":
    sys.exit(main())
