"""MCP server settings — loaded from .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8001
    file_ops_root: str = "./workspace"
    log_level: str = "INFO"


mcp_settings = MCPSettings()
