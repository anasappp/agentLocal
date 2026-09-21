"""Tests for the OpenAI-compatible agent API."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("agent.main._agent_executor", new=MagicMock()):
        from agent.main import app
        return TestClient(app)


def test_list_models(client):
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert any(m["id"] == "local-agent" for m in data["data"])


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_completion():
    mock_executor = AsyncMock()
    mock_executor.ainvoke.return_value = {
        "output": "42",
        "intermediate_steps": [],
    }

    with patch("agent.main._agent_executor", new=mock_executor):
        from agent.main import app
        from httpx import AsyncClient, ASGITransport

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/v1/chat/completions", json={
                "model": "local-agent",
                "messages": [{"role": "user", "content": "What is 6x7?"}],
                "stream": False,
            })

    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["role"] == "assistant"
