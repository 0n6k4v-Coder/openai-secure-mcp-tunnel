#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

COMPOSE_FILE="deploy/compose.yaml"
MCP_PORT="${MCP_PORT:-8000}"
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

OPENAI_CONFIG_FILE="${XDG_CONFIG_HOME}/local-mcp-server/mcp-clients/openai/config.yaml"
OPENAI_API_KEY_FILE="${XDG_CONFIG_HOME}/local-mcp-server/mcp-clients/openai/credentials"

[[ -f "${OPENAI_CONFIG_FILE}" ]] || { echo "ERROR: OpenAI MCP client configuration is missing: ${OPENAI_CONFIG_FILE}" >&2; exit 1; }
[[ -f "${OPENAI_API_KEY_FILE}" ]] || { echo "ERROR: CONTROL_PLANE_API_KEY secret is missing: ${OPENAI_API_KEY_FILE}" >&2; exit 1; }
[[ "$(stat -c '%a' "${OPENAI_CONFIG_FILE}")" == "600" ]] || { echo "ERROR: OpenAI configuration permissions must be 600." >&2; exit 1; }
[[ "$(stat -c '%a' "${OPENAI_API_KEY_FILE}")" == "600" ]] || { echo "ERROR: CONTROL_PLANE_API_KEY permissions must be 600." >&2; exit 1; }

echo "==> Checking MCP server health"
curl --fail --silent --show-error \
    --header 'Host: 127.0.0.1:8000' \
    "http://127.0.0.1:${MCP_PORT}/healthz"
echo

echo "==> Checking MCP endpoint"
curl --fail --silent --show-error \
    --request POST \
    --header 'Host: mcp-server:8000' \
    --header 'Content-Type: application/json' \
    --data '{
      "jsonrpc": "2.0",
      "id": 1,
      "method": "initialize",
      "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {
          "name": "smoke-test",
          "version": "1.0.0"
        }
      }
    }' \
    "http://127.0.0.1:${MCP_PORT}/mcp" >/tmp/openai-secure-mcp-tunnel-mcp-response.json

test -s /tmp/openai-secure-mcp-tunnel-mcp-response.json

echo "==> Checking Compose service state"
docker compose -f "${COMPOSE_FILE}" ps

echo "==> Smoke test passed"