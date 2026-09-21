# TODO

## High priority

- [x] **Windows start script** — `scripts/start.ps1` added.
- [x] **MCP tool descriptions** — adapter fetches real descriptions + typed Pydantic schemas from `/tools`. Fallback `"MCP tool: {name}"` only fires if server omits description.
- [ ] **RAG not tested** — `agent/rag.py` has no test coverage. Add unit tests (mock ChromaDB + embeddings).
- [x] **`query_knowledge_base` MCP tool** — `mcp_server/tools/kb_search.py` added; registered in server; silent RAG injection removed from agent; prompt updated to guide explicit KB use.
- [x] **mcp_adapter not tested** — `tests/test_mcp_adapter.py` added: schema building, `load_mcp_tools`, tool dispatch (9 tests).

## Medium priority

- [ ] **Persistent conversation history** — the agent currently receives only the last user message. Add multi-turn context by passing the full message list.
- [ ] **RAG ingestion entrypoint** — there is no CLI or script to add documents to ChromaDB. Add `scripts/ingest.py`.
- [ ] **Graceful MCP reconnect** — if the MCP server restarts, the agent holds stale tool handles. Add a retry / reload mechanism.
- [ ] **Token usage tracking** — the `/v1/chat/completions` response returns `0` for all token counts. Wire up actual counts from LangChain callbacks.

## Low priority / nice to have

- [x] **Docker Compose** — `docker-compose.yml` added; runs Open WebUI (proxied to agent API) via `docker compose up -d` in `start.sh`.
- [ ] **Structured logging** — switch from `logging.basicConfig` to JSON-structured logs for easier parsing.
- [x] **Model upgrade** — default model changed from `qwen2.5:1.5b` to `qwen2.5:3b` in `agent/config.py` and `scripts/start.sh`.
- [ ] **Streaming from the LLM** — current streaming is simulated (word-by-word split). Wire real token streaming from `ChatOllama`.
- [ ] **Model hot-swap** — allow changing `OLLAMA_MODEL` without restarting the agent (reload on `/v1/models` selection).
