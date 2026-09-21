"""Tests for agent/mcp_adapter.py — single-input JSON tool adapter."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_client(get_return=None, get_side_effect=None):
    """Mock httpx.AsyncClient for GET requests."""
    mock_instance = AsyncMock()

    if get_side_effect:
        mock_instance.get.side_effect = get_side_effect
    else:
        mock_resp = MagicMock()
        mock_resp.json.return_value = get_return
        mock_resp.raise_for_status = MagicMock()
        mock_instance.get.return_value = mock_resp

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_instance)
    ctx.__aexit__ = AsyncMock(return_value=None)

    return ctx


def _mock_post_client(response_body: dict):
    """Mock httpx.AsyncClient for POST requests."""
    mock_instance = AsyncMock()

    mock_resp = MagicMock()
    mock_resp.json.return_value = response_body
    mock_resp.raise_for_status = MagicMock()

    mock_instance.post.return_value = mock_resp

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_instance)
    ctx.__aexit__ = AsyncMock(return_value=None)

    return ctx, mock_instance


# ---------------------------------------------------------------------------
# load_mcp_tools
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_mcp_tools_builds_single_input_tools():
    fake_defs = [
        {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "code_exec",
            "description": "Execute a Python snippet.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                    }
                },
                "required": ["code"],
            },
        },
    ]

    with patch(
        "agent.mcp_adapter.httpx.AsyncClient",
        return_value=_mock_client(get_return=fake_defs),
    ):
        from agent.mcp_adapter import load_mcp_tools

        tools = await load_mcp_tools()

    assert len(tools) == 2

    names = {tool.name for tool in tools}
    assert names == {"web_search", "code_exec"}

    # Every ReAct-facing tool now exposes exactly one string argument.
    for tool in tools:
        fields = tool.args_schema.model_fields
        assert set(fields.keys()) == {"input"}
        assert fields["input"].is_required()

    web_search = next(
        tool for tool in tools
        if tool.name == "web_search"
    )

    assert "Search the web using DuckDuckGo." in web_search.description
    assert '"query"' in web_search.description
    assert '"max_results"' in web_search.description


@pytest.mark.asyncio
async def test_load_mcp_tools_server_unreachable():
    with patch(
        "agent.mcp_adapter.httpx.AsyncClient",
        return_value=_mock_client(
            get_side_effect=Exception("Connection refused")
        ),
    ):
        from agent.mcp_adapter import load_mcp_tools

        tools = await load_mcp_tools()

    assert tools == []


# ---------------------------------------------------------------------------
# _make_tool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_make_tool_posts_decoded_json_to_call_endpoint():
    tool_def = {
        "name": "code_exec",
        "description": "Execute Python",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code",
                }
            },
            "required": ["code"],
        },
    }

    ctx, mock_instance = _mock_post_client(
        {
            "stdout": "hello\n",
            "returncode": 0,
        }
    )

    with patch(
        "agent.mcp_adapter.httpx.AsyncClient",
        return_value=ctx,
    ):
        from agent.mcp_adapter import _make_tool

        tool = _make_tool(
            tool_def,
            "http://localhost:8001",
        )

        result = await tool.ainvoke(
            {
                "input": json.dumps(
                    {
                        "code": "print('hello')"
                    }
                )
            }
        )

    mock_instance.post.assert_called_once()

    url, = mock_instance.post.call_args.args

    assert url == "http://localhost:8001/call"

    payload = mock_instance.post.call_args.kwargs["json"]

    assert payload["tool"] == "code_exec"
    assert payload["arguments"] == {
        "code": "print('hello')"
    }

    assert result == "hello"

    # Tool execution itself should not terminate the Agent.
    # Fast Path controls direct completion at the runtime layer,
    # while ReAct must be able to continue after code_exec.
    assert tool.return_direct is False


@pytest.mark.asyncio
async def test_make_tool_supports_multiple_arguments():
    tool_def = {
        "name": "file_write",
        "description": "Write a file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    }

    ctx, mock_instance = _mock_post_client(
        {
            "path": "hello.txt",
            "bytes_written": 5,
        }
    )

    with patch(
        "agent.mcp_adapter.httpx.AsyncClient",
        return_value=ctx,
    ):
        from agent.mcp_adapter import _make_tool

        tool = _make_tool(
            tool_def,
            "http://localhost:8001",
        )

        await tool.ainvoke(
            {
                "input": json.dumps(
                    {
                        "path": "hello.txt",
                        "content": "hello",
                    }
                )
            }
        )

    payload = mock_instance.post.call_args.kwargs["json"]

    assert payload == {
        "tool": "file_write",
        "arguments": {
            "path": "hello.txt",
            "content": "hello",
        },
    }


@pytest.mark.asyncio
async def test_make_tool_rejects_invalid_json():
    tool_def = {
        "name": "code_exec",
        "description": "Execute Python",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
            },
            "required": ["code"],
        },
    }

    from agent.mcp_adapter import _make_tool

    tool = _make_tool(
        tool_def,
        "http://localhost:8001",
    )

    result = await tool.ainvoke(
        {
            "input": "this is not json"
        }
    )

    data = json.loads(result)

    assert data["error"] == "Invalid JSON tool input"


@pytest.mark.asyncio
async def test_make_tool_rejects_non_object_json():
    tool_def = {
        "name": "file_list",
        "description": "List files.",
        "inputSchema": {
            "type": "object",
        },
    }

    from agent.mcp_adapter import _make_tool

    tool = _make_tool(
        tool_def,
        "http://localhost:8001",
    )

    result = await tool.ainvoke(
        {
            "input": '["not", "an", "object"]'
        }
    )

    data = json.loads(result)

    assert data["error"] == (
        "Tool input must decode to a JSON object"
    )


@pytest.mark.asyncio
async def test_make_tool_description_contains_server_description_and_schema():
    tool_def = {
        "name": "file_read",
        "description": "Read a file from the workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                }
            },
            "required": ["path"],
        },
    }

    from agent.mcp_adapter import _make_tool

    tool = _make_tool(
        tool_def,
        "http://localhost:8001",
    )

    assert (
        "Read a file from the workspace."
        in tool.description
    )

    assert (
        "Input must be a JSON object matching this schema"
        in tool.description
    )

    assert '"path"' in tool.description


@pytest.mark.asyncio
async def test_make_tool_fallback_description():
    tool_def = {
        "name": "mystery_tool",
        "inputSchema": {},
    }

    from agent.mcp_adapter import _make_tool

    tool = _make_tool(
        tool_def,
        "http://localhost:8001",
    )

    assert "MCP tool: mystery_tool" in tool.description
    assert (
        "Input must be a JSON object matching this schema"
        in tool.description
    )