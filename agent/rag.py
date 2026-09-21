"""RAG helpers — ChromaDB + Ollama embeddings."""

import logging
from pathlib import Path

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_core.documents import Document

from agent.config import settings

log = logging.getLogger(__name__)

_vectorstore: Chroma | None = None


def get_vectorstore() -> Chroma:
    global _vectorstore
    if _vectorstore is None:
        embeddings = OllamaEmbeddings(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embed_model,
        )
        _vectorstore = Chroma(
            collection_name="agent_memory",
            embedding_function=embeddings,
            persist_directory=settings.chroma_persist_dir,
        )
        log.info("ChromaDB initialised at %s", settings.chroma_persist_dir)
    return _vectorstore


def add_documents(texts: list[str], metadatas: list[dict] | None = None) -> None:
    store = get_vectorstore()
    docs = [
        Document(page_content=t, metadata=m or {})
        for t, m in zip(texts, metadatas or [{}] * len(texts))
    ]
    store.add_documents(docs)
    log.info("Added %d documents to vector store", len(docs))


def reset_vectorstore() -> None:
    global _vectorstore

    store = _vectorstore or get_vectorstore()

    try:
        store.delete_collection()
        log.info("Deleted existing ChromaDB collection")
    except Exception as exc:
        log.warning("Could not delete existing collection: %s", exc)

    _vectorstore = None

def similarity_search(query: str, k: int = 4) -> list[Document]:
    return get_vectorstore().similarity_search(query, k=k)
