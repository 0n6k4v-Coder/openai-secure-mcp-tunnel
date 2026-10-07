#!/usr/bin/env bash
# scripts/test-sandbox-lifecycle.sh
# End-to-end testing script that validates all sandbox lifecycle operations
# and browser DevTools against isolated disposable sandboxes without affecting
# production environments like jupyter-dev.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

DISPOSABLE_DEFAULT="sbx-test-e2e"
DISPOSABLE_BROWSER="sbx-brw-e2e"

cleanup() {
    echo "==> Cleaning up test sandboxes..."
    uv run mcpctl sandbox delete --yes "${DISPOSABLE_DEFAULT}" 2>/dev/null || true
    uv run mcpctl sandbox delete --yes "${DISPOSABLE_BROWSER}" 2>/dev/null || true
    echo "==> Cleanup complete."
}

trap cleanup EXIT

echo "=========================================================="
echo " Starting Sandbox Lifecycle & DevTools E2E Test Suite"
echo "=========================================================="

# 1. Test create_sandbox (Default Profile, Standalone)
echo "==> [1/9] Creating standalone default sandbox '${DISPOSABLE_DEFAULT}'..."
uv run mcpctl sandbox create "${DISPOSABLE_DEFAULT}" --standalone --profile default

# 2. Test sandbox status & inspection
echo "==> [2/9] Inspecting sandbox status..."
uv run mcpctl sandbox status "${DISPOSABLE_DEFAULT}"

# 3. Test execute_sandbox_command
echo "==> [3/9] Executing command in sandbox..."
uv run mcpctl sandbox exec "${DISPOSABLE_DEFAULT}" -- echo "E2E_SMOKE_TEST_OK"

# 4. Test stop_sandbox
echo "==> [4/9] Stopping sandbox..."
uv run mcpctl sandbox stop "${DISPOSABLE_DEFAULT}"

# 5. Test start_sandbox
echo "==> [5/9] Starting stopped sandbox..."
uv run mcpctl sandbox start "${DISPOSABLE_DEFAULT}"

# 6. Test restart_sandbox
echo "==> [6/9] Restarting sandbox..."
uv run mcpctl sandbox restart "${DISPOSABLE_DEFAULT}"

# 7. Test recreate_sandbox
echo "==> [7/9] Recreating sandbox..."
uv run mcpctl sandbox recreate --yes "${DISPOSABLE_DEFAULT}"

# 8. Test Browser profile sandbox & Chrome DevTools readiness
echo "==> [8/9] Creating browser sandbox '${DISPOSABLE_BROWSER}'..."
uv run mcpctl sandbox create "${DISPOSABLE_BROWSER}" --standalone --profile browser
echo "==> Checking browser sandbox status..."
uv run mcpctl sandbox status "${DISPOSABLE_BROWSER}"
echo "==> Executing DevTools check in browser sandbox..."
uv run mcpctl sandbox exec "${DISPOSABLE_BROWSER}" -- chrome-devtools status

# 9. Test delete_sandbox
echo "==> [9/9] Deleting test sandboxes..."
uv run mcpctl sandbox delete --yes "${DISPOSABLE_DEFAULT}"
uv run mcpctl sandbox delete --yes "${DISPOSABLE_BROWSER}"

echo "=========================================================="
echo " All lifecycle and browser operations PASSED successfully!"
echo "=========================================================="
