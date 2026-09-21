#!/usr/bin/env python3
"""Ingest local-AI ecosystem docs into ChromaDB.

Fetches README + docs/**/*.md from a curated list of public GitHub repos
about local LLM tooling, chunks them, and stores vectors in ChromaDB.

Prerequisites
-------------
  Ollama must be running (used for nomic-embed-text embeddings).

Usage
-----
  python scripts/ingest.py              # ingest everything
  python scripts/ingest.py --reset      # wipe collection first, then ingest
  python scripts/ingest.py --dry-run    # list files without ingesting
"""

import argparse
import logging
import sys
import time

import os
from dotenv import load_dotenv

from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agent.rag import add_documents, reset_vectorstore

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Target repos  (owner, repo)
# ---------------------------------------------------------------------------

REPOS = [
    # LLM runtimes
    ("ollama",          "ollama"),
    ("ggerganov",       "llama.cpp"),
    ("mudler",          "LocalAI"),
    # Chat UIs / front-ends
    ("open-webui",      "open-webui"),
    ("janhq",           "jan"),
    ("oobabooga",       "text-generation-webui"),
    # RAG / knowledge base
    ("Mintplex-Labs",   "anything-llm"),
    ("zylon-ai",        "private-gpt"),
    # OpenAI-compatible proxies / routers
    ("BerriAI",         "litellm"),
    # Embeddings / vector search
    ("nomic-ai",        "gpt4all"),
    # Code assistants
    ("continuedev",     "continue"),
    ("TabbyML",         "tabby"),
    # This project itself
    ("Adrien-1997",     "mcp-ollama-agent"),
]

# Markdown files to include (matched against lowercase path)
INCLUDE_DIRS = {"", "docs", "documentation", "doc", "wiki"}
MAX_FILE_BYTES = 150_000

# Paths / filenames to skip
EXCLUDE_FRAGMENTS = {
    ".github", "node_modules", "test/", "tests/",
    "changelog", "contributing", "license", "code_of_conduct",
    # non-English README variants
    "readme.ja", "readme.zh", "readme.ko", "readme-ja", "readme-zh", "readme-ko",
    # low-value project boilerplate
    "cla.md", "terms_", "pull_request_template", "maintainers.md",
    "agents.md", "claude.md", "gemini.md",  # AI-assistant instruction files
}

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
)

# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------

GITHUB_API = "https://api.github.com"
RAW_BASE   = "https://raw.githubusercontent.com"
HEADERS    = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

github_token = os.getenv("GITHUB_TOKEN", "").strip()

if github_token:
    HEADERS["Authorization"] = f"Bearer {github_token}"

def _get_with_retry(
    client: httpx.Client,
    url: str,
    headers: dict | None = None,
    attempts: int = 5,
) -> httpx.Response:
    """GET with retry for transient network errors."""

    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            response = client.get(url, headers=headers)

            # Retry server-side / temporary errors
            if response.status_code == 429 or response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"temporary HTTP {response.status_code}",
                    request=response.request,
                    response=response,
                )

            return response

        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_error = exc

            if attempt == attempts:
                raise

            wait_seconds = min(2 ** (attempt - 1), 8)

            log.warning(
                "  request failed (%s), retry %d/%d in %ds",
                exc,
                attempt,
                attempts,
                wait_seconds,
            )

            time.sleep(wait_seconds)

    raise last_error

def _get_tree(client: httpx.Client, owner: str, repo: str) -> tuple[str, list[dict]]:
    """Return (default_branch, [file_entries]) for a repo."""
    #meta = client.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=HEADERS)
    meta = _get_with_retry(
        client,
        f"{GITHUB_API}/repos/{owner}/{repo}",
        headers=HEADERS,
    )
    if meta.status_code == 404:
        log.warning("  repo not found: %s/%s", owner, repo)
        return "", []
    meta.raise_for_status()
    branch = meta.json().get("default_branch", "main")

    tree = _get_with_retry(
        client,
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1",
        headers=HEADERS,
    )
    tree.raise_for_status()
    return branch, tree.json().get("tree", [])


def _should_include(path: str, size: int) -> bool:
    p = path.lower()
    if not p.endswith(".md"):
        return False
    if size > MAX_FILE_BYTES:
        return False
    if any(frag in p for frag in EXCLUDE_FRAGMENTS):
        return False
    # Keep root-level files + files inside allowed dirs
    parts = p.split("/")
    top_dir = parts[0] if len(parts) > 1 else ""
    return top_dir in INCLUDE_DIRS


# ---------------------------------------------------------------------------
# Core ingest
# ---------------------------------------------------------------------------

def _ingest_text(text: str, source: str, url: str = "", dry_run: bool = False) -> int:
    chunks = splitter.split_text(text.strip())
    if not chunks:
        return 0
    if not dry_run:
        metadatas = [{"source": source, "url": url, "chunk": i} for i in range(len(chunks))]
        add_documents(chunks, metadatas)
    return len(chunks)


def ingest_repos(dry_run: bool = False) -> None:
    total_chunks = 0
    total_files  = 0

    with httpx.Client(
            timeout=httpx.Timeout(30.0, connect=15.0),
            follow_redirects=True,
            headers={
                "User-Agent": "mcp-ollama-agent-ingest/1.0"
            },
    ) as client:
        for owner, repo in REPOS:
            log.info("\n[%s/%s]", owner, repo)

            try:
                branch, tree = _get_tree(client, owner, repo)
            except httpx.HTTPError as exc:
                log.warning("  API error: %s — skipped", exc)
                continue

            if not branch:
                continue

            # Filter files
            candidates = [
                entry for entry in tree
                if entry.get("type") == "blob"
                and _should_include(entry["path"], entry.get("size", 0))
            ]

            if not candidates:
                log.info("  no matching docs")
                continue

            repo_chunks = 0
            for entry in candidates:
                path = entry["path"]
                raw_url = f"{RAW_BASE}/{owner}/{repo}/{branch}/{path}"

                try:
                    #r = client.get(raw_url)
                    r = _get_with_retry(client, raw_url)
                    if r.status_code != 200:
                        log.info("  %-50s HTTP %s", path, r.status_code)
                        continue
                    n = _ingest_text(
                        r.text,
                        source=f"github/{owner}/{repo}/{path}",
                        url=f"https://github.com/{owner}/{repo}/blob/{branch}/{path}",
                        dry_run=dry_run,
                    )
                    label = "[dry]" if dry_run else ""
                    log.info("  %-50s %d chunks %s", path, n, label)
                    repo_chunks += n
                    total_files  += 1
                    time.sleep(0.3)  # be polite to raw.githubusercontent.com
                except httpx.HTTPError as exc:
                    log.warning("  %-50s fetch error: %s", path, exc)

            log.info("  → %d chunks from %d files", repo_chunks, len(candidates))
            total_chunks += repo_chunks

    log.info("\n=== Done: %d chunks from %d files across %d repos ===",
             total_chunks, total_files, len(REPOS))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest local-AI ecosystem docs into ChromaDB")
    parser.add_argument("--reset",   action="store_true", help="Wipe collection before ingesting")
    parser.add_argument("--dry-run", action="store_true", help="List files without ingesting")
    args = parser.parse_args()

    if args.reset and not args.dry_run:
        log.info("[reset] Wiping existing collection...")
        reset_vectorstore()
        log.info("[reset] Done\n")

    ingest_repos(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
