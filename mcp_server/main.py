"""MCP server — entry point.

Starts a FastAPI app exposing the MCP protocol over SSE transport.
Run with:  python -m mcp_server.main
"""

import logging
import uvicorn
from mcp_server.server import create_app
from mcp_server.config import mcp_settings

logging.basicConfig(level=mcp_settings.log_level)
log = logging.getLogger(__name__)


def main() -> None:
    log.info("Starting MCP server on %s:%s", mcp_settings.mcp_server_host, mcp_settings.mcp_server_port)
    app = create_app()
    uvicorn.run(
        app,
        host=mcp_settings.mcp_server_host,
        port=mcp_settings.mcp_server_port,
        log_level=mcp_settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
