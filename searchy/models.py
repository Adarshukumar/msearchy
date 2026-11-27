from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class SearchCategory(str, Enum):
    TEXT = "text"
    IMAGES = "images"
    VIDEOS = "videos"


class SearchResult(BaseModel):
    """Unified result schema returned by every Searchy provider."""

    category: SearchCategory
    provider: str
    title: str
    url: str
    snippet: str = ""
    thumbnail_url: str = ""
    source_url: str = ""
    duration: str = ""
    width: int | None = None
    height: int | None = None


class ProviderReport(BaseModel):
    provider: str
    success: bool
    count: int = 0
    elapsed_ms: float = 0.0
    error: str | None = None


class SearchResponse(BaseModel):
    query: str
    category: SearchCategory
    total_results: int = 0
    unique_results: int = 0
    elapsed_ms: float = 0.0
    provider_counts: dict[str, int] = Field(default_factory=dict)
    providers: list[ProviderReport] = Field(default_factory=list)
    results: list[SearchResult] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
