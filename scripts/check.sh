#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}"

echo "==> Checking lockfile"
uv lock --check

echo "==> Running Ruff"
uv run --locked ruff check src tests

echo "==> Running unit tests"
uv run --locked pytest tests/unit

echo "==> Validating Compose configuration"

mkdir -p .secrets

if [[ ! -f .secrets/control-plane-api-key ]]; then
    printf '%s\n' 'ci-placeholder' > .secrets/control-plane-api-key
    REMOVE_PLACEHOLDER_SECRET=1
else
    REMOVE_PLACEHOLDER_SECRET=0
fi

CONTROL_PLANE_TUNNEL_ID=ci-placeholder \
    docker compose \
    -f deploy/compose.yaml \
    config >/tmp/openai-secure-mcp-tunnel-compose.yaml

if [[ "${REMOVE_PLACEHOLDER_SECRET}" == "1" ]]; then
    rm -f .secrets/control-plane-api-key
fi

echo "==> Repository checks passed"