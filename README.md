# msearchy

msearchy is an async Python metasearch library built by Adarsh. It queries multiple search engines in parallel and returns a single normalized schema for text, image, and video results.

## Features

- **Parallel execution:** Queries DuckDuckGo, Bing, Wikipedia, and Brave at the same time using `asyncio.gather` and `httpx.AsyncClient`.
- **One response format:** Every provider returns `SearchResult` objects inside a `SearchResponse` with `total_results`, `unique_results`, `provider_counts`, and per-provider timing.
- **Three categories:** Supports `text`, `images`, and `videos`, plus `search_all()` to fetch all three in one call.
- **Clean URLs:** Decodes Bing `ck/a` base64url tracking links and Google `/url?q=` redirects.
- **Error isolation:** If one provider times out or fails, the rest still return results and the failure is recorded in `providers`.

## Installation

```bash
pip install msearchy
```

## Python Usage

```python
from searchy import Searchy, SearchCategory

client = Searchy()

# Single category
res = client.search("python asyncio", category=SearchCategory.TEXT, limit_per_provider=5)
print(res.total_results, res.unique_results, res.provider_counts)

# All categories in parallel
bundle = client.search_all("mountain", limit_per_provider=3)
for category, response in bundle.items():
    print(category.value, response.unique_results)
```

For async code, use `await client.asearch(...)` and `await client.asearch_all(...)`.

## CLI

```bash
python -m searchy.cli "python tutorial" --category all --limit 3
```
