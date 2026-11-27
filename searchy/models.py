from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field

from .url_utils import extract_domain


class SearchCategory(str, Enum):
    TEXT = "text"
    IMAGES = "images"
    VIDEOS = "videos"

    @classmethod
    def coerce(cls, value: SearchCategory | str) -> SearchCategory:
        """Accept case-insensitive strings or SearchCategory members."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(value.strip().lower())
        raise ValueError(f"Unsupported category: {value!r}")


class ProviderCapabilities(BaseModel):
    """Declares which categories a provider supports."""

    text: bool = False
    images: bool = False
    videos: bool = False

    def supports(self, category: SearchCategory) -> bool:
        if category == SearchCategory.TEXT:
            return self.text
        if category == SearchCategory.IMAGES:
            return self.images
        return self.videos


class SearchResult(BaseModel):
    """Normalized search result returned by every provider."""

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
    score: float = 0.0
    providers_matched: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def domain(self) -> str:
        return extract_domain(self.url)


class ProviderReport(BaseModel):
    """Execution telemetry for one provider in a search request."""

    provider: str
    success: bool
    count: int = 0
    elapsed_ms: float = 0.0
    status_code: int | None = None
    error: str | None = None


class SearchResponse(BaseModel):
    """Aggregated response across all queried providers for one category."""

    query: str
    category: SearchCategory
    total_results: int = 0
    unique_results: int = 0
    elapsed_ms: float = 0.0
    cache_hit: bool = False
    provider_counts: dict[str, int] = Field(default_factory=dict)
    providers: list[ProviderReport] = Field(default_factory=list)
    results: list[SearchResult] = Field(default_factory=list)

    @property
    def succeeded_providers(self) -> list[str]:
        return [p.provider for p in self.providers if p.success]

    @property
    def failed_providers(self) -> list[str]:
        return [p.provider for p in self.providers if not p.success]

    @property
    def duplicates_removed(self) -> int:
        return max(0, self.total_results - self.unique_results)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [
            f"## {self.category.value.capitalize()} results for `{self.query}`",
            "",
            f"Found {self.unique_results} unique results ({self.total_results} total) in {self.elapsed_ms:.2f} ms.",
            "",
        ]
        for idx, item in enumerate(self.results, 1):
            badge = ", ".join(item.providers_matched) if item.providers_matched else item.provider
            title = item.title or item.url
            lines.append(f"{idx}. [{title}]({item.url}) (`{badge}`)")
            if item.snippet:
                lines.append(f"   {item.snippet}")
        if self.failed_providers:
            lines.append("")
            lines.append("Errors:")
            for rep in self.providers:
                if not rep.success:
                    lines.append(f"- `{rep.provider}`: {rep.error or 'Unknown error'}")
        return "\n".join(lines)


class SearchBundle(dict[SearchCategory, SearchResponse]):
    """Dictionary of category responses with convenience accessors."""

    @property
    def text(self) -> SearchResponse:
        return self[SearchCategory.TEXT]

    @property
    def images(self) -> SearchResponse:
        return self[SearchCategory.IMAGES]

    @property
    def videos(self) -> SearchResponse:
        return self[SearchCategory.VIDEOS]

    @property
    def total_results(self) -> int:
        return sum(r.total_results for r in self.values())

    @property
    def unique_results(self) -> int:
        return sum(r.unique_results for r in self.values())

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {k.value: v.to_dict() for k, v in self.items()}

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        return "\n\n".join(res.to_markdown() for res in self.values())
