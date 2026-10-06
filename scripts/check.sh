#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "==> Checking lockfile"
uv lock --check

echo "==> Running Ruff"
uv run --locked ruff check src tests

echo "==> Running unit tests"
uv run --locked pytest tests/unit tests/e2e/cli/test_mcpctl_runtime.py

echo "==> Validating Compose configuration"
CHECK_CONFIG_DIR="$(mktemp -d)"
trap 'rm -rf "${CHECK_CONFIG_DIR}"' EXIT

mkdir -p "${CHECK_CONFIG_DIR}/local-mcp-server/mcp-clients/openai"
printf '%s\n' 'ci-placeholder' >"${CHECK_CONFIG_DIR}/local-mcp-server/mcp-clients/openai/credentials"

cat >"${CHECK_CONFIG_DIR}/local-mcp-server/mcp-clients/openai/config.yaml" <<'EOF'
config_version: 1
control_plane:
  base_url: https://api.openai.com
  tunnel_id: "tunnel_0123456789abcdef0123456789abcdef"
  api_key: file:/run/secrets/CONTROL_PLANE_API_KEY
mcp:
  server_urls:
    - channel: main
      url: http://mcp-server:8000/mcp
EOF

chmod 700 "${CHECK_CONFIG_DIR}/local-mcp-server" "${CHECK_CONFIG_DIR}/local-mcp-server/mcp-clients" "${CHECK_CONFIG_DIR}/local-mcp-server/mcp-clients/openai"
chmod 600 "${CHECK_CONFIG_DIR}/local-mcp-server/mcp-clients/openai/credentials" "${CHECK_CONFIG_DIR}/local-mcp-server/mcp-clients/openai/config.yaml"

XDG_CONFIG_HOME="${CHECK_CONFIG_DIR}" \
COMPOSE_PROJECT_NAME=ci-openai-secure-mcp-tunnel \
MCP_PORT=18000 \
OPENSHELL_PORT=18080 \
OPENSHELL_HEALTH_PORT=18081 \
    docker compose --env-file deploy/.env.example -f deploy/compose.yaml config >/tmp/openai-secure-mcp-tunnel-compose.yaml

if grep -q 'CONTROL_PLANE_TUNNEL_ID' /tmp/openai-secure-mcp-tunnel-compose.yaml; then
    echo "ERROR: CONTROL_PLANE_TUNNEL_ID must not be configured as a Compose environment variable." >&2
    exit 1
fi

if grep -q 'control-plane-api-key' /tmp/openai-secure-mcp-tunnel-compose.yaml; then
    echo "ERROR: legacy lowercase control-plane-api-key secret path is still present." >&2
    exit 1
fi

echo "==> Repository checks passed"
