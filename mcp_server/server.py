"""MCP server — tool registration.

Creates the FastAPI app with MCP SSE transport and registers all tools.
"""

from fastapi import FastAPI
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from pydantic import BaseModel
from starlette.routing import Route, Mount

from mcp_server.tools.web_search import web_search
from mcp_server.tools.file_ops import file_read, file_write, file_list
from mcp_server.tools.code_exec import code_exec
from mcp_server.tools.kb_search import query_knowledge_base

import inspect
import json
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = Server("local-agent-mcp")


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="web_search",
            description="Search the web using DuckDuckGo. Returns top results with title, url, and snippet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "default": 5, "description": "Number of results (1-10)"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="file_read",
            description="Read a file from the local workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside workspace/"},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="file_write",
            description="Write content to a file in the local workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside workspace/"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        ),
        Tool(
            name="file_list",
            description="List files in the local workspace directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "default": ".", "description": "Subdirectory to list"},
                },
            },
        ),
        Tool(
            name="code_exec",
            description= "Execute Python code in a sandboxed environment. "
                         "Returns stdout/stderr. A single Python expression is automatically "
                         "evaluated and its result is returned in stdout.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code or expression to execute"},
                    "timeout": {"type": "integer", "default": 10, "description": "Timeout in seconds"},
                },
                "required": ["code"],
            },
        ),
        Tool(
            name="query_knowledge_base",
            description=(
                "Search the local AI ecosystem knowledge base. "
                "Contains documentation for Ollama, llama.cpp, LocalAI, Open WebUI, Jan, "
                "text-generation-webui, AnythingLLM, PrivateGPT, LiteLLM, GPT4All, Continue, and Tabby. "
                "Use this for questions about how to install, configure, or use any of these tools."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language search query (use this field)"},
                    "k": {"type": "integer", "default": 4, "description": "Number of results to return (1-10)"},
                },
                "required": ["query"],
            },
        ),
    ]


def _filter_args(fn, arguments: dict) -> dict:
    """Drop keys that the function doesn't accept."""
    params = inspect.signature(fn).parameters
    return {k: v for k, v in arguments.items() if k in params}


async def _dispatch(name: str, arguments: dict) -> list[TextContent]:
    log.info("Tool call: %s args=%s", name, arguments)
    try:
        if name == "web_search":
            result = await web_search(**_filter_args(web_search, arguments))
        elif name == "file_read":
            result = await file_read(**_filter_args(file_read, arguments))
        elif name == "file_write":
            result = await file_write(**_filter_args(file_write, arguments))
        elif name == "file_list":
            result = await file_list(**_filter_args(file_list, arguments))
        elif name == "code_exec":
            result = await code_exec(**_filter_args(code_exec, arguments))
        elif name == "query_knowledge_base":
            result = await query_knowledge_base(**_filter_args(query_knowledge_base, arguments))
        else:
            result = {"error": f"Unknown tool: {name}"}
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    except Exception as exc:
        log.exception("Tool %s failed", name)
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    return await _dispatch(name, arguments)


# ---------------------------------------------------------------------------
# FastAPI app with SSE transport
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    sse_transport = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await mcp.run(read_stream, write_stream, mcp.create_initialization_options())

    app = FastAPI(title="MCP Server", version="0.1.0")

    app.router.routes.append(Route("/sse", endpoint=handle_sse))
    app.router.routes.append(Mount("/messages", app=sse_transport.handle_post_message))

    @app.get("/")
    async def root():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/docs")

    @app.get("/health")
    async def health():
        return {"status": "ok", "tools": [t.name for t in await list_tools()]}

    @app.get("/tools")
    async def tools_schema():
        return [
            {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
            for t in await list_tools()
        ]

    class CallRequest(BaseModel):
        tool: str
        arguments: dict = {}

    @app.post("/call")
    async def rest_call(req: CallRequest):
        results = await _dispatch(req.tool, req.arguments)
        return json.loads(results[0].text)

    return app
