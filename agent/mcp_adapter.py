"""MCP → LangChain tool adapter.

Each MCP tool is exposed to the ReAct agent as a SINGLE string input.
The string contains a JSON object, which is decoded here before being
forwarded to the MCP REST endpoint.

This design avoids unreliable multi-argument parsing in the classic
text-based ReAct agent.
"""

import json
import logging

import httpx
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

from agent.config import settings


log = logging.getLogger(__name__)


def _make_tool(tool_def: dict, server_url: str) -> StructuredTool:
    """Convert one MCP tool definition into a single-input LangChain tool."""

    name: str = tool_def["name"]

    base_description: str = tool_def.get(
        "description",
        f"MCP tool: {name}",
    )

    input_schema: dict = tool_def.get(
        "inputSchema",
        {},
    )

    schema_text = json.dumps(
        input_schema,
        ensure_ascii=False,
    )

    # Classic ReAct produces one textual Action Input.
    # Therefore every LangChain-facing tool accepts one JSON string.
    args_schema = create_model(
        f"{name}_Args",
        input=(
            str,
            Field(
                description=(
                    "A JSON object encoded as a string. "
                    f"It MUST follow this schema: {schema_text}"
                )
            ),
        ),
    )

    description = (
        f"{base_description}\n"
        f"Input must be a JSON object matching this schema:\n"
        f"{schema_text}"
    )

    async def _call(input: str) -> str:
        """Decode the ReAct JSON string and call the MCP REST endpoint."""

        try:
            arguments = json.loads(input)

        except json.JSONDecodeError as exc:
            return json.dumps(
                {
                    "error": "Invalid JSON tool input",
                    "detail": str(exc),
                    "received": input,
                },
                ensure_ascii=False,
            )

        if not isinstance(arguments, dict):
            return json.dumps(
                {
                    "error": "Tool input must decode to a JSON object",
                    "received": arguments,
                },
                ensure_ascii=False,
            )

        payload = {
            "tool": name,
            "arguments": arguments,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{server_url}/call",
                json=payload,
            )

            response.raise_for_status()

            data = response.json()

            # code_exec 的 stdout 就是真实计算结果。
            # 成功后直接把 stdout 返回，不再让小模型重新计算。
            if name == "code_exec" and isinstance(data, dict):
                if data.get("returncode") == 0:
                    stdout = str(data.get("stdout", "")).strip()

                    if stdout:
                        return stdout

            return json.dumps(
                data,
                ensure_ascii=False,
            )

    return StructuredTool.from_function(
        coroutine=_call,
        name=name,
        description=description,
        args_schema=args_schema,
        # Tool completion is controlled by the runtime path.
        # Fast Path returns directly, while ReAct must be able
        # to continue after code_exec in multi-step workflows.
        return_direct=False,
    )


async def load_mcp_tools() -> list[StructuredTool]:
    """Fetch MCP definitions and expose them as LangChain tools."""

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(
                f"{settings.mcp_server_url}/tools"
            )

            response.raise_for_status()

            tool_defs: list[dict] = response.json()

        except Exception as exc:
            log.warning(
                "Could not reach MCP server: %s — using empty tool list",
                exc,
            )
            return []

    tools = [
        _make_tool(
            tool_def,
            settings.mcp_server_url,
        )
        for tool_def in tool_defs
    ]

    log.info(
        "Loaded %d MCP tools: %s",
        len(tools),
        [tool.name for tool in tools],
    )

    return tools