import json
import os
from pathlib import Path
from typing import Any

import httpx

from agent.config import settings


# ---------------------------------------------------------
# MCP configuration
# ---------------------------------------------------------

MCP_CALL_URL = os.getenv(
    "MCP_CALL_URL",
    "http://127.0.0.1:8001/call",
)


# ---------------------------------------------------------
# MCP helpers
# ---------------------------------------------------------

async def _call_tool(
    client: httpx.AsyncClient,
    tool: str,
    arguments: dict,
) -> Any:
    """
    Call one MCP tool directly.

    This workflow intentionally bypasses ReAct for deterministic
    execution steps.
    """

    response = await client.post(
        MCP_CALL_URL,
        json={
            "tool": tool,
            "arguments": arguments,
        },
    )

    response.raise_for_status()

    data = response.json()

    if (
        isinstance(data, dict)
        and data.get("error")
    ):
        raise RuntimeError(
            f"{tool} failed: {data['error']}"
        )

    return data


def _extract_file_content(
    result: Any,
) -> str:
    """
    Normalize file_read output.

    Different MCP implementations may return either:
    - a raw string
    - {"content": "..."}
    """

    if isinstance(result, str):
        return result

    if isinstance(result, dict):
        if "content" in result:
            return str(
                result.get(
                    "content",
                    "",
                )
            )

        if "text" in result:
            return str(
                result.get(
                    "text",
                    "",
                )
            )

    return str(result)


def _extract_json(
    text: str,
) -> dict:
    """
    Extract the first JSON object from an LLM response.

    Handles both raw JSON and fenced JSON output.
    """

    text = text.strip()

    start = text.find("{")
    end = text.rfind("}")

    if (
        start == -1
        or end == -1
        or end < start
    ):
        raise ValueError(
            "LLM did not return a JSON object. "
            f"Raw response: {text}"
        )

    json_text = text[
        start:end + 1
    ]

    try:
        data = json.loads(
            json_text
        )

    except json.JSONDecodeError as exc:
        raise ValueError(
            "LLM returned invalid JSON. "
            f"Raw response: {text}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "LLM diagnosis must be a JSON object."
        )

    return data


# ---------------------------------------------------------
# LLM diagnosis
# ---------------------------------------------------------

async def _diagnose(
    client: httpx.AsyncClient,
    files: dict[str, str],
    test_result: dict,
    source_files: list[str],
) -> dict:
    """
    The LLM performs only the uncertain reasoning step.

    Deterministic operations such as reading files, running tests
    and writing reports are controlled by Python runtime code.
    """

    source_context = "\n\n".join(
        (
            f"===== {name} =====\n"
            f"{content}"
        )
        for name, content in files.items()
    )

    test_context = json.dumps(
        test_result,
        ensure_ascii=False,
        indent=2,
    )

    allowed_source_files = ", ".join(
        source_files
    )

    prompt = f"""
You are diagnosing a small Python repository.

You must use ONLY the source files and the actual runtime test
output provided below.

Do not use web search.
Do not use a knowledge base.
Do not invent missing information.

The candidate implementation source files are:

{allowed_source_files}

The test file is validation evidence. Do not blame the test file
unless the test itself is demonstrably incorrect.

Your task:

1. Identify the exact implementation file containing the bug.
2. Identify the exact faulty expression or logic.
3. Explain how that code caused the observed runtime failure.
4. Recommend the smallest fix.
5. Do NOT modify any files.

SOURCE FILES

{source_context}

ACTUAL TEST OUTPUT

{test_context}

Return RAW JSON only.

Use exactly this schema:

{{
  "root_cause_file": "exact implementation filename",
  "root_cause": "exact faulty expression or logic",
  "evidence": "how the source code caused the observed test failure",
  "recommended_fix": "minimal fix without modifying files"
}}
""".strip()

    ollama_url = (
        settings.ollama_base_url.rstrip("/")
        + "/api/chat"
    )

    response = await client.post(
        ollama_url,
        json={
            "model": settings.ollama_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
            },
        },
    )

    response.raise_for_status()

    payload = response.json()

    content = str(
        payload
        .get("message", {})
        .get("content", "")
    ).strip()

    if not content:
        raise RuntimeError(
            "Ollama returned an empty diagnosis."
        )

    diagnosis = _extract_json(
        content
    )

    required_fields = [
        "root_cause_file",
        "root_cause",
        "evidence",
        "recommended_fix",
    ]

    missing_fields = [
        field
        for field in required_fields
        if not diagnosis.get(field)
    ]

    if missing_fields:
        raise ValueError(
            "Diagnosis is missing required fields: "
            + ", ".join(missing_fields)
        )

    # Normalize possible values such as:
    # hero_repo/calculator.py
    # workspace/hero_repo/calculator.py
    # calculator.py
    root_cause_file = Path(
        str(
            diagnosis[
                "root_cause_file"
            ]
        )
    ).name

    allowed_names = {
        Path(filename).name
        for filename in source_files
    }

    if (
        root_cause_file
        not in allowed_names
    ):
        raise RuntimeError(
            "Diagnosis pointed to an unexpected "
            "root-cause file: "
            f"{diagnosis['root_cause_file']}. "
            "Allowed implementation files: "
            f"{sorted(allowed_names)}"
        )

    diagnosis[
        "root_cause_file"
    ] = root_cause_file

    return diagnosis


# ---------------------------------------------------------
# Report generation
# ---------------------------------------------------------

def _build_report(
    test_result: dict,
    diagnosis: dict,
) -> str:
    """
    Build the final Markdown report deterministically.
    """

    returncode = test_result.get(
        "returncode",
        "",
    )

    stdout = str(
        test_result.get(
            "stdout",
            "",
        )
    ).rstrip()

    stderr = str(
        test_result.get(
            "stderr",
            "",
        )
    ).rstrip()

    output_parts = []

    if stdout:
        output_parts.append(
            stdout
        )

    if stderr:
        output_parts.append(
            stderr
        )

    combined_output = "\n".join(
        output_parts
    )

    if not combined_output:
        combined_output = (
            "(no stdout or stderr)"
        )

    # Markdown indented code block.
    # This avoids nested backticks inside the Python source.
    indented_output = "\n".join(
        "    " + line
        for line in combined_output.splitlines()
    )

    report = (
        "# Test Result\n\n"
        f"Return code: {returncode}\n\n"
        f"{indented_output}\n\n"
        "# Root Cause\n\n"
        f"File: `{diagnosis['root_cause_file']}`\n\n"
        f"{diagnosis['root_cause']}\n\n"
        "# Evidence\n\n"
        f"{diagnosis['evidence']}\n\n"
        "# Recommended Fix\n\n"
        f"{diagnosis['recommended_fix']}\n"
    )

    return report


# ---------------------------------------------------------
# Repository debugging workflow
# ---------------------------------------------------------

async def run_repo_debug_workflow(
    repo_dir: str,
    test_file: str,
    source_files: list[str],
    report_path: str,
) -> dict:
    """
    Semi-deterministic repository debugging workflow.

    Runtime controls:
        1. list repository files
        2. read relevant source files
        3. execute the real test
        4. write the final report

    LLM controls only:
        - root-cause reasoning

    This prevents a small ReAct model from wasting tool calls on
    unrelated web/RAG searches or forgetting the final file_write.
    """

    if not repo_dir:
        raise ValueError(
            "repo_dir cannot be empty."
        )

    if not test_file:
        raise ValueError(
            "test_file cannot be empty."
        )

    if not source_files:
        raise ValueError(
            "source_files cannot be empty."
        )

    if not report_path:
        raise ValueError(
            "report_path cannot be empty."
        )

    async with httpx.AsyncClient(
        timeout=180.0,
    ) as client:

        # -------------------------------------------------
        # Step 1: list repository
        # -------------------------------------------------

        listing = await _call_tool(
            client,
            "file_list",
            {
                "directory": repo_dir,
            },
        )

        # -------------------------------------------------
        # Step 2: read files
        # -------------------------------------------------

        files: dict[str, str] = {}

        read_targets = [
            "README.md",
            *source_files,
            test_file,
        ]

        # Remove duplicates while preserving order.
        read_targets = list(
            dict.fromkeys(
                read_targets
            )
        )

        for filename in read_targets:
            path = (
                f"{repo_dir}/{filename}"
            )

            result = await _call_tool(
                client,
                "file_read",
                {
                    "path": path,
                },
            )

            files[
                filename
            ] = _extract_file_content(
                result
            )

        # -------------------------------------------------
        # Step 3: execute the real test
        # -------------------------------------------------
        #
        # code_exec runs from the project root.
        #
        # The repository itself lives inside:
        #
        # workspace/<repo_dir>
        #
        # We therefore start a real Python subprocess with
        # cwd set to that repository. This preserves normal
        # Python import behavior such as:
        #
        # from calculator import add
        # -------------------------------------------------

        workspace_repo = (
            Path("workspace")
            / repo_dir
        )

        execution_code = f"""
import json
import subprocess
import sys

result = subprocess.run(
    [sys.executable, {test_file!r}],
    cwd={str(workspace_repo)!r},
    capture_output=True,
    text=True,
    timeout=20,
)

print(
    json.dumps(
        {{
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }},
        ensure_ascii=False,
    )
)
""".strip()

        execution = await _call_tool(
            client,
            "code_exec",
            {
                "code": execution_code,
            },
        )

        if not isinstance(
            execution,
            dict,
        ):
            raise RuntimeError(
                "code_exec returned an unexpected "
                f"payload: {execution!r}"
            )

        outer_returncode = execution.get(
            "returncode"
        )

        outer_stderr = str(
            execution.get(
                "stderr",
                "",
            )
        ).strip()

        if outer_returncode != 0:
            raise RuntimeError(
                "The code_exec wrapper itself failed. "
                f"stderr: {outer_stderr}"
            )

        stdout = str(
            execution.get(
                "stdout",
                "",
            )
        ).strip()

        if not stdout:
            raise RuntimeError(
                "code_exec returned no test result."
            )

        try:
            test_result = json.loads(
                stdout
            )

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Could not parse test result from "
                f"code_exec stdout: {stdout}"
            ) from exc

        if not isinstance(
            test_result,
            dict,
        ):
            raise RuntimeError(
                "Parsed test result is not a JSON object."
            )

        # -------------------------------------------------
        # Step 4: root-cause reasoning
        # -------------------------------------------------

        diagnosis = await _diagnose(
            client=client,
            files=files,
            test_result=test_result,
            source_files=source_files,
        )

        # -------------------------------------------------
        # Step 5: deterministic report construction
        # -------------------------------------------------

        report = _build_report(
            test_result=test_result,
            diagnosis=diagnosis,
        )

        # -------------------------------------------------
        # Step 6: deterministic file_write
        # -------------------------------------------------

        write_result = await _call_tool(
            client,
            "file_write",
            {
                "path": report_path,
                "content": report,
            },
        )

        # -------------------------------------------------
        # Step 7: return structured workflow result
        # -------------------------------------------------

        return {
            "listing": listing,
            "files_read": list(
                files.keys()
            ),
            "test_result": test_result,
            "diagnosis": diagnosis,
            "write_result": write_result,
            "report_path": report_path,
            "report": report,
        }