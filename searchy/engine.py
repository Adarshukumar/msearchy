from __future__ import annotations

import asyncio
import time
from typing import Sequence

import httpx

from .base import BaseProvider
from .models import ProviderReport, SearchCategory, SearchResponse, SearchResult
from .providers import (
    BingProvider,
    BraveProvider,
    DuckDuckGoProvider,
    WikipediaProvider,
)


class Searchy:
    """Async-first metasearch client that queries all providers in parallel."""

    def __init__(
        self,
        providers: Sequence[BaseProvider] | None = None,
        timeout: float = 8.0,
    ) -> None:
        self.providers: list[BaseProvider] = (
            list(providers)
            if providers is not None
            else [
                DuckDuckGoProvider(),
                BingProvider(),
                WikipediaProvider(),
                BraveProvider(),
            ]
        )
        self.timeout = timeout

    def _eligible_providers(
        self, category: SearchCategory, provider_names: Sequence[str] | None
    ) -> list[BaseProvider]:
        allowed = {p.lower() for p in provider_names} if provider_names else None
        selected: list[BaseProvider] = []
        for p in self.providers:
            if allowed is not None and p.name.lower() not in allowed:
                continue
            if category == SearchCategory.TEXT and p.supports_text:
                selected.append(p)
            elif category == SearchCategory.IMAGES and p.supports_images:
                selected.append(p)
            elif category == SearchCategory.VIDEOS and p.supports_videos:
                selected.append(p)
        return selected

    async def _run_provider(
        self,
        client: httpx.AsyncClient,
        provider: BaseProvider,
        query: str,
        category: SearchCategory,
        limit: int,
    ) -> tuple[ProviderReport, list[SearchResult]]:
        t0 = time.perf_counter()
        try:
            if category == SearchCategory.TEXT:
                items = await provider.search_text(client, query, limit=limit)
            elif category == SearchCategory.IMAGES:
                items = await provider.search_images(client, query, limit=limit)
            else:
                items = await provider.search_videos(client, query, limit=limit)
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            return (
                ProviderReport(
                    provider=provider.name,
                    success=True,
                    count=len(items),
                    elapsed_ms=elapsed,
                ),
                items,
            )
        except Exception as exc:
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            return (
                ProviderReport(
                    provider=provider.name,
                    success=False,
                    count=0,
                    elapsed_ms=elapsed,
                    error=str(exc),
                ),
                [],
            )

    async def asearch(
        self,
        query: str,
        category: SearchCategory | str = SearchCategory.TEXT,
        limit_per_provider: int = 10,
        providers: Sequence[str] | None = None,
        deduplicate: bool = True,
        _client: httpx.AsyncClient | None = None,
    ) -> SearchResponse:
        cat = SearchCategory(category)
        active = self._eligible_providers(cat, providers)
        t0 = time.perf_counter()

        async def _execute(client: httpx.AsyncClient):
            tasks = [
                self._run_provider(client, p, query, cat, limit_per_provider)
                for p in active
            ]
            return await asyncio.gather(*tasks)

        if _client is not None:
            outcomes = await _execute(_client)
        else:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True
            ) as client:
                outcomes = await _execute(client)

        reports: list[ProviderReport] = []
        raw_results: list[SearchResult] = []
        provider_counts: dict[str, int] = {}

        for report, items in outcomes:
            reports.append(report)
            provider_counts[report.provider] = report.count
            raw_results.extend(items)

        if deduplicate:
            seen: set[str] = set()
            final_results: list[SearchResult] = []
            for item in raw_results:
                key = item.url.rstrip("/")
                if key not in seen:
                    seen.add(key)
                    final_results.append(item)
        else:
            final_results = raw_results

        total_elapsed = round((time.perf_counter() - t0) * 1000, 2)
        return SearchResponse(
            query=query,
            category=cat,
            total_results=len(raw_results),
            unique_results=len(final_results),
            elapsed_ms=total_elapsed,
            provider_counts=provider_counts,
            providers=reports,
            results=final_results,
        )

    async def asearch_all(
        self,
        query: str,
        limit_per_provider: int = 5,
        providers: Sequence[str] | None = None,
        deduplicate: bool = True,
    ) -> dict[SearchCategory, SearchResponse]:
        """Run text, image, and video searches in parallel in a single call."""
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            text_task = self.asearch(
                query, SearchCategory.TEXT, limit_per_provider, providers, deduplicate, _client=client
            )
            img_task = self.asearch(
                query, SearchCategory.IMAGES, limit_per_provider, providers, deduplicate, _client=client
            )
            vid_task = self.asearch(
                query, SearchCategory.VIDEOS, limit_per_provider, providers, deduplicate, _client=client
            )
            text_res, img_res, vid_res = await asyncio.gather(text_task, img_task, vid_task)

        return {
            SearchCategory.TEXT: text_res,
            SearchCategory.IMAGES: img_res,
            SearchCategory.VIDEOS: vid_res,
        }

    def search(
        self,
        query: str,
        category: SearchCategory | str = SearchCategory.TEXT,
        limit_per_provider: int = 10,
        providers: Sequence[str] | None = None,
        deduplicate: bool = True,
    ) -> SearchResponse:
        return asyncio.run(
            self.asearch(
                query=query,
                category=category,
                limit_per_provider=limit_per_provider,
                providers=providers,
                deduplicate=deduplicate,
            )
        )

    def search_all(
        self,
        query: str,
        limit_per_provider: int = 5,
        providers: Sequence[str] | None = None,
        deduplicate: bool = True,
    ) -> dict[SearchCategory, SearchResponse]:
        return asyncio.run(
            self.asearch_all(
                query=query,
                limit_per_provider=limit_per_provider,
                providers=providers,
                deduplicate=deduplicate,
            )
        )
