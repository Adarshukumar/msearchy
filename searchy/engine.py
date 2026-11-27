from __future__ import annotations

import asyncio
import concurrent.futures
import importlib.util
import time
from collections.abc import AsyncIterator, Coroutine, Sequence
from typing import Any, TypeVar

import httpx

from .base import BaseProvider, ProviderError
from .cache import SingleFlight, TTLCache
from .models import (
    ProviderReport,
    SearchBundle,
    SearchCategory,
    SearchResponse,
    SearchResult,
)
from .providers import get_default_providers
from .url_utils import canonicalize_url

_T = TypeVar("_T")
_HAS_HTTP2 = importlib.util.find_spec("h2") is not None


def _format_error(exc: BaseException) -> tuple[str, int | None]:
    status_code: int | None = None
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
    elif isinstance(exc, ProviderError):
        status_code = exc.status_code

    detail = str(exc).strip()
    name = type(exc).__name__
    if detail:
        return f"{name}: {detail}", status_code
    return name, status_code


def _run_sync(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run a coroutine synchronously, even if an event loop is already active."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _merge_metadata(primary: SearchResult, secondary: SearchResult) -> SearchResult:
    """Keep the richest non-empty fields across duplicate provider hits."""
    updates: dict[str, Any] = {}
    if len(secondary.snippet) > len(primary.snippet):
        updates["snippet"] = secondary.snippet
    if not primary.title and secondary.title:
        updates["title"] = secondary.title
    if not primary.thumbnail_url and secondary.thumbnail_url:
        updates["thumbnail_url"] = secondary.thumbnail_url
    if not primary.source_url and secondary.source_url:
        updates["source_url"] = secondary.source_url
    if not primary.duration and secondary.duration:
        updates["duration"] = secondary.duration
    if primary.width is None and secondary.width is not None:
        updates["width"] = secondary.width
    if primary.height is None and secondary.height is not None:
        updates["height"] = secondary.height
    return primary.model_copy(update=updates) if updates else primary


def _deduplicate_and_rank(
    outcomes: list[tuple[ProviderReport, list[SearchResult]]],
    *,
    deduplicate: bool,
    rank: bool,
    rrf_k: int = 60,
) -> list[SearchResult]:
    """Deduplicate by canonical URL and rank via Reciprocal Rank Fusion (RRF)."""
    if not deduplicate:
        flat: list[SearchResult] = []
        for _, items in outcomes:
            for idx, item in enumerate(items, 1):
                score = round(1.0 / (rrf_k + idx), 6)
                flat.append(
                    item.model_copy(
                        update={
                            "score": score,
                            "providers_matched": item.providers_matched or [item.provider],
                        }
                    )
                )
        return flat

    merged: dict[str, SearchResult] = {}
    scores: dict[str, float] = {}
    matched_providers: dict[str, list[str]] = {}
    order: list[str] = []

    for _, items in outcomes:
        seen_in_provider: set[str] = set()
        for idx, item in enumerate(items, 1):
            key = canonicalize_url(item.url)
            if key in seen_in_provider:
                continue
            seen_in_provider.add(key)

            rrf_delta = 1.0 / (rrf_k + idx)
            if key not in merged:
                merged[key] = item
                scores[key] = rrf_delta
                matched_providers[key] = [item.provider]
                order.append(key)
            else:
                merged[key] = _merge_metadata(merged[key], item)
                scores[key] += rrf_delta
                if item.provider not in matched_providers[key]:
                    matched_providers[key].append(item.provider)

    final_items = [
        merged[key].model_copy(
            update={
                "score": round(scores[key], 6),
                "providers_matched": matched_providers[key],
            }
        )
        for key in order
    ]

    if rank:
        final_items.sort(key=lambda item: item.score, reverse=True)
    return final_items


class Searchy:
    """Async metasearch engine with connection pooling, TTL caching, and RRF ranking."""

    def __init__(
        self,
        providers: Sequence[BaseProvider] | None = None,
        timeout: float = 8.0,
        *,
        cache_ttl: float = 0.0,
        cache_maxsize: int = 256,
        max_connections: int = 32,
        max_keepalive_connections: int = 16,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than 0")
        self.providers: list[BaseProvider] = (
            list(providers) if providers is not None else get_default_providers()
        )
        self.timeout = timeout
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self._cache: TTLCache[SearchResponse] = TTLCache(
            maxsize=cache_maxsize, ttl=cache_ttl
        )
        self._flight: SingleFlight[SearchResponse] = SingleFlight()
        self._shared_client: httpx.AsyncClient | None = None

    def register_provider(self, provider: BaseProvider) -> None:
        """Add or replace a provider by name."""
        lower = provider.name.lower()
        self.providers = [p for p in self.providers if p.name.lower() != lower]
        self.providers.append(provider)

    def list_providers(self) -> list[dict[str, Any]]:
        """Return metadata and capabilities for all registered providers."""
        return [
            {
                "name": p.name,
                "text": p.supports_text,
                "images": p.supports_images,
                "videos": p.supports_videos,
            }
            for p in self.providers
        ]

    def clear_cache(self) -> None:
        """Remove all cached responses."""
        self._cache.clear()

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            http2=_HAS_HTTP2,
            limits=httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=self.max_keepalive_connections,
                keepalive_expiry=30.0,
            ),
        )

    async def __aenter__(self) -> Searchy:
        if self._shared_client is None or self._shared_client.is_closed:
            self._shared_client = self._build_client()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the shared connection pool if open."""
        if self._shared_client is not None and not self._shared_client.is_closed:
            await self._shared_client.aclose()
        self._shared_client = None

    def _eligible_providers(
        self, category: SearchCategory, provider_names: Sequence[str] | None
    ) -> list[BaseProvider]:
        allowed = (
            {p.strip().lower() for p in provider_names if p.strip()}
            if provider_names is not None
            else None
        )
        return [
            p
            for p in self.providers
            if (allowed is None or p.name.lower() in allowed) and p.supports(category)
        ]

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
                coro = provider.search_text(client, query, limit=limit)
            elif category == SearchCategory.IMAGES:
                coro = provider.search_images(client, query, limit=limit)
            else:
                coro = provider.search_videos(client, query, limit=limit)

            items = await asyncio.wait_for(coro, timeout=self.timeout)
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            return (
                ProviderReport(
                    provider=provider.name,
                    success=True,
                    count=len(items),
                    elapsed_ms=elapsed,
                    status_code=200,
                ),
                items,
            )
        except asyncio.TimeoutError:
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            return (
                ProviderReport(
                    provider=provider.name,
                    success=False,
                    count=0,
                    elapsed_ms=elapsed,
                    error=f"TimeoutError: exceeded {self.timeout}s",
                ),
                [],
            )
        except Exception as exc:  # noqa: BLE001 - intentional provider error isolation
            elapsed = round((time.perf_counter() - t0) * 1000, 2)
            message, status_code = _format_error(exc)
            return (
                ProviderReport(
                    provider=provider.name,
                    success=False,
                    count=0,
                    elapsed_ms=elapsed,
                    status_code=status_code,
                    error=message,
                ),
                [],
            )

    def _cache_key(
        self,
        query: str,
        category: SearchCategory,
        limit_per_provider: int,
        providers: Sequence[str] | None,
        deduplicate: bool,
        rank: bool,
    ) -> str:
        prov_sig = (
            "*"
            if providers is None
            else ",".join(sorted(p.strip().lower() for p in providers))
        )
        return (
            f"{category.value}|{query.strip().lower()}|{limit_per_provider}|"
            f"{prov_sig}|{int(deduplicate)}|{int(rank)}"
        )

    async def asearch(
        self,
        query: str,
        category: SearchCategory | str = SearchCategory.TEXT,
        limit_per_provider: int = 10,
        providers: Sequence[str] | None = None,
        deduplicate: bool = True,
        *,
        rank: bool = True,
        use_cache: bool = True,
        _client: httpx.AsyncClient | None = None,
    ) -> SearchResponse:
        if limit_per_provider < 1:
            raise ValueError("limit_per_provider must be at least 1")

        cat = SearchCategory.coerce(category)
        cleaned_query = query.strip()
        if not cleaned_query:
            return SearchResponse(query="", category=cat)

        key = self._cache_key(
            cleaned_query, cat, limit_per_provider, providers, deduplicate, rank
        )
        if use_cache and self._cache.ttl > 0:
            cached = self._cache.get(key)
            if cached is not None:
                return cached.model_copy(update={"cache_hit": True, "elapsed_ms": 0.0})

        async def _execute_search() -> SearchResponse:
            active = self._eligible_providers(cat, providers)
            t0 = time.perf_counter()

            async def _gather(client: httpx.AsyncClient) -> list[tuple[ProviderReport, list[SearchResult]]]:
                if not active:
                    return []
                tasks = [
                    self._run_provider(client, p, cleaned_query, cat, limit_per_provider)
                    for p in active
                ]
                return list(await asyncio.gather(*tasks))

            http_client = _client or self._shared_client
            if http_client is not None and not http_client.is_closed:
                outcomes = await _gather(http_client)
            else:
                async with self._build_client() as temp_client:
                    outcomes = await _gather(temp_client)

            reports: list[ProviderReport] = []
            provider_counts: dict[str, int] = {}
            raw_count = 0
            for report, items in outcomes:
                reports.append(report)
                provider_counts[report.provider] = (
                    provider_counts.get(report.provider, 0) + report.count
                )
                raw_count += len(items)

            final_results = _deduplicate_and_rank(
                outcomes, deduplicate=deduplicate, rank=rank
            )
            total_elapsed = round((time.perf_counter() - t0) * 1000, 2)
            response = SearchResponse(
                query=cleaned_query,
                category=cat,
                total_results=raw_count,
                unique_results=len(final_results),
                elapsed_ms=total_elapsed,
                cache_hit=False,
                provider_counts=provider_counts,
                providers=reports,
                results=final_results,
            )
            if use_cache and self._cache.ttl > 0:
                self._cache.set(key, response)
            return response

        if use_cache and self._cache.ttl > 0:
            return await self._flight.do(key, _execute_search)
        return await _execute_search()

    async def astream(
        self,
        query: str,
        category: SearchCategory | str = SearchCategory.TEXT,
        limit_per_provider: int = 10,
        providers: Sequence[str] | None = None,
        _client: httpx.AsyncClient | None = None,
    ) -> AsyncIterator[tuple[ProviderReport, list[SearchResult]]]:
        """Yield each provider's report and results as soon as it finishes."""
        if limit_per_provider < 1:
            raise ValueError("limit_per_provider must be at least 1")
        cat = SearchCategory.coerce(category)
        cleaned_query = query.strip()
        if not cleaned_query:
            return

        active = self._eligible_providers(cat, providers)
        if not active:
            return

        http_client = _client or self._shared_client
        owns_client = http_client is None or http_client.is_closed
        client = self._build_client() if owns_client else http_client
        assert client is not None
        try:
            tasks = [
                asyncio.create_task(
                    self._run_provider(client, p, cleaned_query, cat, limit_per_provider)
                )
                for p in active
            ]
            for completed in asyncio.as_completed(tasks):
                yield await completed
        finally:
            if owns_client:
                await client.aclose()

    async def asearch_all(
        self,
        query: str,
        limit_per_provider: int = 5,
        providers: Sequence[str] | None = None,
        deduplicate: bool = True,
        *,
        rank: bool = True,
        use_cache: bool = True,
        _client: httpx.AsyncClient | None = None,
    ) -> SearchBundle:
        """Run text, image, and video searches in parallel using a shared connection pool."""
        http_client = _client or self._shared_client
        owns_client = http_client is None or http_client.is_closed
        client = self._build_client() if owns_client else http_client
        assert client is not None
        try:
            text_res, img_res, vid_res = await asyncio.gather(
                self.asearch(
                    query,
                    SearchCategory.TEXT,
                    limit_per_provider,
                    providers,
                    deduplicate,
                    rank=rank,
                    use_cache=use_cache,
                    _client=client,
                ),
                self.asearch(
                    query,
                    SearchCategory.IMAGES,
                    limit_per_provider,
                    providers,
                    deduplicate,
                    rank=rank,
                    use_cache=use_cache,
                    _client=client,
                ),
                self.asearch(
                    query,
                    SearchCategory.VIDEOS,
                    limit_per_provider,
                    providers,
                    deduplicate,
                    rank=rank,
                    use_cache=use_cache,
                    _client=client,
                ),
            )
        finally:
            if owns_client:
                await client.aclose()

        return SearchBundle(
            {
                SearchCategory.TEXT: text_res,
                SearchCategory.IMAGES: img_res,
                SearchCategory.VIDEOS: vid_res,
            }
        )

    def search(
        self,
        query: str,
        category: SearchCategory | str = SearchCategory.TEXT,
        limit_per_provider: int = 10,
        providers: Sequence[str] | None = None,
        deduplicate: bool = True,
        *,
        rank: bool = True,
        use_cache: bool = True,
    ) -> SearchResponse:
        return _run_sync(
            self.asearch(
                query=query,
                category=category,
                limit_per_provider=limit_per_provider,
                providers=providers,
                deduplicate=deduplicate,
                rank=rank,
                use_cache=use_cache,
            )
        )

    def search_all(
        self,
        query: str,
        limit_per_provider: int = 5,
        providers: Sequence[str] | None = None,
        deduplicate: bool = True,
        *,
        rank: bool = True,
        use_cache: bool = True,
    ) -> SearchBundle:
        return _run_sync(
            self.asearch_all(
                query=query,
                limit_per_provider=limit_per_provider,
                providers=providers,
                deduplicate=deduplicate,
                rank=rank,
                use_cache=use_cache,
            )
        )
