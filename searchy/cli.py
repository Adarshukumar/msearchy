from __future__ import annotations

import argparse
import json

from .engine import Searchy
from .models import SearchCategory


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="searchy",
        description="Searchy: parallel multi-provider search for text, images, and videos.",
    )
    parser.add_argument("query", help="Search query")
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
        type=int,
        default=5,
        help="Max results per provider",
    )
    parser.add_argument(
        "-p",
        "--providers",
        nargs="*",
        default=None,
        help="Filter providers (duckduckgo, bing, wikipedia, brave)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    client = Searchy()

    if args.category == "all":
        bundle = client.search_all(
            query=args.query,
            limit_per_provider=args.limit,
            providers=args.providers,
        )
        if args.json:
            print(json.dumps({k.value: v.to_dict() for k, v in bundle.items()}, indent=2))
            return
        for cat, res in bundle.items():
            print(
                f"\n=== {cat.value.upper()} | Total: {res.total_results} | "
                f"Unique: {res.unique_results} | {res.elapsed_ms} ms ==="
            )
            print(f"Counts: {res.provider_counts}")
            for idx, item in enumerate(res.results[:5], 1):
                print(f"  {idx}. [{item.provider}] {item.title} -> {item.url}")
        return

    res = client.search(
        query=args.query,
        category=args.category,
        limit_per_provider=args.limit,
        providers=args.providers,
    )

    if args.json:
        print(json.dumps(res.to_dict(), indent=2))
        return

    print(
        f"\n[Searchy] Query: {res.query!r} | Category: {res.category.value} | "
        f"Total: {res.total_results} | Unique: {res.unique_results} | "
        f"Time: {res.elapsed_ms} ms"
    )
    print(f"Provider counts: {res.provider_counts}\n")
    for idx, item in enumerate(res.results, 1):
        print(f"{idx}. [{item.provider}] {item.title}\n   URL: {item.url}")


if __name__ == "__main__":
    main()
