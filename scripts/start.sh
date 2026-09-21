#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."

echo ""
echo "=== MCP - Ollama - LangChain Agent ==="
echo ""

# ---------------------------------------------------------------------------
# 1. Python environment
# ---------------------------------------------------------------------------

if [ ! -d ".venv" ]; then
  echo "[..] Creating virtual environment..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[..] Installing dependencies..."
pip install -r requirements.txt
echo "[ok] Dependencies ready"

# ---------------------------------------------------------------------------
# 2. Ollama
# ---------------------------------------------------------------------------

if ! command -v ollama &>/dev/null; then
  echo "[ERROR] Ollama is not installed."
  echo "        Run: curl -fsSL https://ollama.com/install.sh | sh"
  exit 1
fi

if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
  echo "[ok] Ollama already running"
else
  echo "[..] Starting Ollama..."
  ollama serve &>/dev/null &
  sleep 3
fi

for model in qwen2.5:3b nomic-embed-text; do
  if ollama list 2>/dev/null | grep -q "$model"; then
    echo "[ok] $model already pulled"
  else
    echo "[..] Pulling $model (first run, this may take a while)..."
    ollama pull "$model"
  fi
done

# ---------------------------------------------------------------------------
# 3. Start services
# ---------------------------------------------------------------------------

echo ""
echo "[..] Starting MCP server on :8001"
python -m mcp_server.main &
MCP_PID=$!

sleep 2

echo "[..] Starting Agent API on :8000"
python -m agent.main &
AGENT_PID=$!

sleep 2

echo "[..] Starting Open WebUI on :3000"
docker compose up -d

echo ""
echo "All services running"
echo "  Open WebUI  -> http://localhost:3000"
echo "  Agent API   -> http://localhost:8000/docs"
echo "  MCP server  -> http://localhost:8001/health"
echo ""
echo "Press Ctrl+C to stop"

cleanup() {
  echo ""
  echo "Stopping..."
  kill "$MCP_PID" "$AGENT_PID" 2>/dev/null
  docker compose down
  exit 0
}

trap cleanup INT TERM
wait
