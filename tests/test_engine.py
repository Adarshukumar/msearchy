from __future__ import annotations

import asyncio

import httpx
import pytest

from searchy import BaseProvider, SearchCategory, SearchResult, Searchy


class StaticProvider(BaseProvider):
    def __init__(
        self,
        name: str,
        results: list[SearchResult],
        *,
        delay: float = 0.0,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.supports_text = True
        self.supports_images = True
        self.supports_videos = True
        self._results = results
        self._delay = delay
        self._error = error
        self.calls = 0

    async def search_text(self, client: httpx.AsyncClient, query: str, limit: int = 10) -> list[SearchResult]:
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error
        return self._results[:limit]

    async def search_images(self, client: httpx.AsyncClient, query: str, limit: int = 10) -> list[SearchResult]:
        return []

    async def search_videos(self, client: httpx.AsyncClient, query: str, limit: int = 10) -> list[SearchResult]:
        return []


async def test_rrf_deduplication_merges_metadata_and_ranks_consensus_first() -> None:
    p1 = StaticProvider(
        "alpha",
        [
            SearchResult(category=SearchCategory.TEXT, provider="alpha", title="Unique A", url="https://a.example.com/1", snippet="Short"),
            SearchResult(category=SearchCategory.TEXT, provider="alpha", title="Shared Doc", url="https://Docs.Example.com/guide/?utm_source=a", snippet="Short"),
        ],
    )
    p2 = StaticProvider(
        "beta",
        [
            SearchResult(category=SearchCategory.TEXT, provider="beta", title="Unique B", url="https://b.example.com/2", snippet="Beta"),
            SearchResult(category=SearchCategory.TEXT, provider="beta", title="Shared Doc", url="http://www.docs.example.com/guide#top", snippet="Much longer detailed snippet from beta"),
        ],
    )
    async with Searchy(providers=[p1, p2]) as engine:
        res = await engine.asearch("guide", category="TEXT")

    assert res.total_results == 4
    assert res.unique_results == 3
    assert res.duplicates_removed == 1
    # Shared Doc appeared in both providers so RRF ranks it #1.
    assert res.results[0].title == "Shared Doc"
    assert res.results[0].providers_matched == ["alpha", "beta"]
    assert res.results[0].snippet == "Much longer detailed snippet from beta"


async def test_empty_providers_list_selects_zero_providers() -> None:
    p1 = StaticProvider("alpha", [SearchResult(category=SearchCategory.TEXT, provider="alpha", title="A", url="https://a.com")])
    engine = Searchy(providers=[p1])
    res = await engine.asearch("hello", providers=[])
    assert res.providers == []
    assert res.results == []
    assert p1.calls == 0


async def test_validation_and_empty_query() -> None:
    engine = Searchy(providers=[])
    with pytest.raises(ValueError):
        await engine.asearch("hello", limit_per_provider=0)
    with pytest.raises(ValueError):
        await engine.asearch("hello", limit_per_provider=-1)
    with pytest.raises(ValueError):
        Searchy(timeout=0)

    empty = await engine.asearch("   ")
    assert empty.query == ""
    assert empty.results == []


async def test_error_isolation_preserves_exception_type_when_message_empty() -> None:
    failing = StaticProvider("slow", [], error=httpx.ReadTimeout(""))
    working = StaticProvider(
        "good",
        [SearchResult(category=SearchCategory.TEXT, provider="good", title="OK", url="https://ok.example.com")],
    )
    res = await Searchy(providers=[failing, working]).asearch("query")
    assert res.unique_results == 1
    assert res.failed_providers == ["slow"]
    assert res.succeeded_providers == ["good"]
    slow_rep = next(r for r in res.providers if r.provider == "slow")
    assert slow_rep.error == "ReadTimeout"


async def test_ttl_cache_and_single_flight_coalescing() -> None:
    p = StaticProvider(
        "cached",
        [SearchResult(category=SearchCategory.TEXT, provider="cached", title="Item", url="https://item.example.com")],
        delay=0.04,
    )
    async with Searchy(providers=[p], cache_ttl=60.0) as engine:
        # Concurrent identical calls coalesce onto one flight.
        r1, r2 = await asyncio.gather(engine.asearch("python"), engine.asearch("python"))
        assert p.calls == 1
        assert r1.unique_results == 1
        assert r2.unique_results == 1

        # Subsequent call returns cached response immediately.
        r3 = await engine.asearch("python")
        assert p.calls == 1
        assert r3.cache_hit is True


async def test_astream_yields_faster_provider_first() -> None:
    slow = StaticProvider("slow", [], delay=0.08)
    fast = StaticProvider(
        "fast",
        [SearchResult(category=SearchCategory.TEXT, provider="fast", title="Fast", url="https://fast.example.com")],
        delay=0.01,
    )
    order: list[str] = []
    async with Searchy(providers=[slow, fast]) as engine:
        async for report, _ in engine.astream("speed"):
            order.append(report.provider)
    assert order == ["fast", "slow"]


async def test_sync_search_works_even_inside_running_event_loop() -> None:
    p = StaticProvider(
        "syncsafe",
        [SearchResult(category=SearchCategory.TEXT, provider="syncsafe", title="OK", url="https://sync.example.com")],
    )
    res = Searchy(providers=[p]).search("inside loop")
    assert res.unique_results == 1
    assert res.results[0].domain == "sync.example.com"
