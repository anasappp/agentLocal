"""Tool: kb_search — query the local AI ecosystem knowledge base."""

import asyncio
import logging

log = logging.getLogger(__name__)


async def query_knowledge_base(query: str = "", question: str = "", k: int = 4) -> dict:
    """Search ChromaDB for chunks relevant to query. Returns content + source + url."""
    query = query or question
    if not query:
        return {"error": "missing required argument: query"}
    k = max(1, min(k, 10))
    try:
        from agent.rag import similarity_search
        docs = await asyncio.get_event_loop().run_in_executor(
            None, similarity_search, query, k
        )
    except Exception as exc:
        log.warning("KB search failed: %s", exc)
        return {"query": query, "results": [], "error": str(exc)}

    return {
        "query": query,
        "results": [
            {
                "content": doc.page_content,
                "source": doc.metadata.get("source", "unknown"),
                "url": doc.metadata.get("url", ""),
            }
            for doc in docs
        ],
    }
