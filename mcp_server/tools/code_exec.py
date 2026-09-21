"""Tool: code_exec — sandboxed Python execution via subprocess."""

import ast
import asyncio
import os
import sys
import tempfile


def _prepare_code(code: str) -> str:
    """
    If the input is a single Python expression, automatically print its value.

    Example:
        12345 * 6789
    becomes:
        print(repr(12345 * 6789))

    Normal Python scripts containing statements are left unchanged.
    """

    code = code.strip()

    if not code:
        return code

    try:
        # If the entire input is a valid Python expression,
        # make its result observable through stdout.
        ast.parse(code, mode="eval")
        return f"print(repr({code}))"
    except SyntaxError:
        # Multi-line scripts / assignments / statements
        # continue to behave normally.
        return code


async def code_exec(code: str, timeout: int = 10) -> dict:
    """Execute Python code in a subprocess and return stdout/stderr."""

    timeout = max(1, min(timeout, 30))

    prepared_code = _prepare_code(code)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(prepared_code)
        tmp_path = tmp.name

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )

        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()

            return {
                "error": f"Execution timed out after {timeout}s",
                "stdout": "",
                "stderr": "",
            }

        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
        }

    finally:
        os.unlink(tmp_path)