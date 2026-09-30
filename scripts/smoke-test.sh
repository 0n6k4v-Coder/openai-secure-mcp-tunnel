#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}"

COMPOSE_FILE="deploy/compose.yaml"

echo "==> Checking MCP server health"

curl --fail --silent --show-error \
    http://127.0.0.1:8000/healthz

echo

echo "==> Checking MCP endpoint"

curl --fail --silent --show-error \
    --request POST \
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
    http://127.0.0.1:8000/mcp >/tmp/openai-secure-mcp-tunnel-mcp-response.json

test -s /tmp/openai-secure-mcp-tunnel-mcp-response.json

echo "==> Checking Compose service state"

docker compose \
    -f "${COMPOSE_FILE}" \
    ps

echo "==> Smoke test passed"