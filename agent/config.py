"""Centralised settings — loaded from .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_embed_model: str = "nomic-embed-text"

    # MCP server
    mcp_server_url: str = "http://localhost:8001"
    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8001

    # Agent API
    agent_api_host: str = "0.0.0.0"
    agent_api_port: int = 8000

    # Storage
    chroma_persist_dir: str = ".chroma"
    file_ops_root: str = "./workspace"

    # Misc
    log_level: str = "INFO"


settings = Settings()
