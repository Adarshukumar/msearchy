from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Bounded in-memory LRU cache with per-entry TTL expiration."""

    def __init__(self, maxsize: int = 256, ttl: float = 60.0) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        if ttl < 0:
            raise ValueError("ttl cannot be negative")
        self.maxsize = maxsize
        self.ttl = ttl
        self._store: OrderedDict[str, tuple[float, T]] = OrderedDict()

    def get(self, key: str) -> T | None:
        if self.ttl <= 0:
            return None
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: T, ttl: float | None = None) -> None:
        effective_ttl = self.ttl if ttl is None else ttl
        if effective_ttl <= 0:
            return
        expires_at = time.monotonic() + effective_ttl
        self._store[key] = (expires_at, value)
        self._store.move_to_end(key)
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._store.items() if now >= exp]
        for k in expired:
            self._store.pop(k, None)
        return len(self._store)


class SingleFlight(Generic[T]):
    """Coalesce duplicate concurrent async calls for the same key into one flight."""

    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future[T]] = {}

    async def do(self, key: str, fn: Callable[[], Awaitable[T]]) -> T:
        existing = self._inflight.get(key)
        if existing is not None:
            return await asyncio.shield(existing)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()
        self._inflight[key] = future
        try:
            result = await fn()
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
            raise
        else:
            if not future.done():
                future.set_result(result)
            return result
        finally:
            self._inflight.pop(key, None)
