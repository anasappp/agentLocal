"""Tool: web_search — DuckDuckGo search."""

from duckduckgo_search import DDGS
import asyncio
import logging

log = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> dict:
    """Return top DuckDuckGo results for query."""
    max_results = max(1, min(max_results, 10))

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _sync_search, query, max_results)
    return {"query": query, "results": results}


def _sync_search(query: str, max_results: int) -> list[dict]:
    with DDGS() as ddgs:
        return [
            {"title": r["title"], "url": r["href"], "snippet": r["body"]}
            for r in ddgs.text(query, max_results=max_results)
        ]
