# Command Reference

## 1. Prepare OpenShell CLI

The project uses OpenShell v0.1.1. Install that CLI version if it is not already installed.

The official installer normally starts a local Gateway. This project uses the Docker Compose Gateway instead, so only one Gateway should be active for this host.

## 2. Configure the Repository

Copy the example environment file:

```bash
cp .env.example .env
```

Set the existing tunnel ID in `.env`.

Create:

```text
.secrets/control-plane-api-key
```

with only the OpenAI control-plane API key.

## 3. Update the Python Lock

The repository declares `openshell==0.1.1`. Regenerate the lock before building:

```bash
uv lock
```

## 4. Python Quality Checks

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pytest
uv run python -m compileall src tests
```

## 5. Build the OpenShell Sandbox Image

```bash
docker build \
  -f docker/openshell-sandbox/Dockerfile \
  -t local-mcp-openshell-sandbox:1.0.0 \
  .
```

The image provides Python, Node.js 24.21.0, npm 12.1.0, Playwright 1.63.0, browsers, Git, and common development tools.

## 6. Validate Compose

```bash
docker compose config
```

The configuration should show:

```text
openshell-gateway
mcp-server
tunnel-client
```

There must be no `terminal-executor` service.

## 7. Start the Stack

```bash
docker compose up -d
```

Then:

```bash
docker compose ps
```

## 8. Register the Compose Gateway

NVIDIA's documented container-Gateway flow registers the local listener with the CLI:

```bash
openshell gateway add http://127.0.0.1:8080 --local --name local-mcp
openshell gateway select local-mcp
openshell status
```

urlOpenShell container Gateway documentationturn0search0

## 9. List Sandboxes

```bash
openshell sandbox list
```

## 10. Inspect Logs

MCP server:

```bash
docker compose logs --tail=200 mcp-server
```

OpenShell Gateway:

```bash
docker compose logs --tail=200 openshell-gateway
```

Tunnel client:

```bash
docker compose logs --tail=100 tunnel-client
```

All services:

```bash
docker compose logs -f
```

## 11. Test the MCP Sandbox Workflow

From ChatGPT:

```text
create_sandbox("smoke-test")
```

Then:

```text
execute_sandbox_command(
    "smoke-test",
    "python -c \\"print('OpenShell OK')\\"",
)
```

Then:

```text
delete_sandbox("smoke-test")
```

## 12. Stop

```bash
docker compose down
```

## 13. Git Review

```bash
git status --short
git diff HEAD
```

Then stage and review:

```bash
git add .
git diff --cached
```

Commit after all checks pass:

```bash
git commit -m "Harden OpenShell sandbox integration" \
  -m "Align the Docker Gateway with NVIDIA's container deployment model, add the required persistent state path, fix sandbox command execution, restore Node/npm tooling in the sandbox image, and update the setup and verification documentation."
```
