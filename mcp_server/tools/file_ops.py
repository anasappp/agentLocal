"""Tool: file_ops — sandboxed read/write inside workspace/."""

import os
import aiofiles
from pathlib import Path
from mcp_server.config import mcp_settings

WORKSPACE = Path(mcp_settings.file_ops_root).resolve()


def _safe_path(relative: str) -> Path:
    """Resolve and ensure path stays inside WORKSPACE."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    target = (WORKSPACE / relative).resolve()
    if not str(target).startswith(str(WORKSPACE)):
        raise ValueError(f"Path traversal denied: {relative}")
    return target


async def file_read(path: str) -> dict:
    target = _safe_path(path)
    if not target.exists():
        return {"error": f"File not found: {path}"}
    async with aiofiles.open(target, "r", encoding="utf-8", errors="replace") as f:
        content = await f.read()
    return {"path": path, "content": content, "size": len(content)}


async def file_write(path: str, content: str) -> dict:
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(target, "w", encoding="utf-8") as f:
        await f.write(content)
    return {"path": path, "bytes_written": len(content.encode())}


async def file_list(directory: str = ".") -> dict:
    target = _safe_path(directory)
    if not target.exists():
        return {"error": f"Directory not found: {directory}"}
    entries = []
    for entry in sorted(target.iterdir()):
        entries.append({
            "name": entry.name,
            "type": "dir" if entry.is_dir() else "file",
            "size": entry.stat().st_size if entry.is_file() else None,
        })
    return {"directory": directory, "entries": entries}
