# Command

## OpenShell Commands

### OpenShell — Version

```bash
openshell --version
```

### OpenShell — Status

```bash
openshell status
```

### OpenShell — List Sandboxes

```bash
openshell sandbox list
```

### OpenShell — Delete Sandbox

```bash
openshell sandbox delete <sandbox-name>
```

---

## Docker Commands

### Docker — Build OpenShell Sandbox Image

Build the workload image used by OpenShell:

```bash
docker build \
  -f docker/openshell-sandbox/Dockerfile \
  -t local-mcp-openshell-sandbox:1.0.0 \
  .
```

### Docker — Build Compose Services

Build the locally maintained Compose images:

```bash
docker compose build
```

### Docker — Start

Start the complete stack:

```bash
docker compose up -d
```

### Docker — Status

Check the running Compose services:

```bash
docker compose ps
```

Expected services:

```text
openshell-gateway
mcp-server
tunnel-client
```

There should be no `terminal-executor` service.

### Docker — MCP Server Logs

```bash
docker compose logs -f mcp-server
```

### Docker — OpenShell Gateway Logs

```bash
docker compose logs -f openshell-gateway
```

### Docker — Tunnel Client Logs

```bash
docker compose logs -f tunnel-client
```

### Docker — All Logs

```bash
docker compose logs -f
```

### Docker — Stop

Stop the Compose stack:

```bash
docker compose down
```

---

## Python Commands

### Python — Update Dependency Lock

Run this after changing Python dependencies:

```bash
uv lock
```

### Python — Auto-format + Auto-fix Linting

```bash
uv run ruff format . && \
uv run ruff check . --fix
```

### Python — Run Tests

```bash
uv run pytest
```

### Python — Compile Check

```bash
uv run python -m compileall src tests
```

---

## Verification Commands

### Verify — Compose Configuration

Validate the final Compose configuration before starting:

```bash
docker compose config
```

### Verify — Compose Services

```bash
docker compose ps
```

Expected:

```text
openshell-gateway
mcp-server
tunnel-client
```

### Verify — OpenShell

```bash
openshell status
```

### Verify — Sandboxes

```bash
openshell sandbox list
```

### Verify — MCP Server

```bash
docker compose logs --tail=200 mcp-server
```

The MCP server should start without Python import or configuration errors.

### Verify — OpenShell Gateway

```bash
docker compose logs --tail=200 openshell-gateway
```

The Gateway should start successfully and initialize its Docker compute driver.

### Verify — Tunnel Client

```bash
docker compose logs --tail=100 tunnel-client
```

The tunnel client should connect to the existing OpenAI tunnel and reach:

```text
http://mcp-server:8000/mcp
```

---

## Git Commands

### Git — Review Changes

```bash
git status --short && \
git diff HEAD
```

### Git — Review Only Changed Files

```bash
git status --short
```

### Git — Review Full Diff

```bash
git diff HEAD
```

### Git — Review Staged Diff

```bash
git diff --cached
```

### Git — Add Changes

```bash
git add .
```

### Git — Review Staged Changes

```bash
git diff --cached
```

### Git — Commit

```bash
git commit -m "Replace terminal executor with OpenShell sandboxes"
```

---

## Recommended Execution Order

### 1. Update Python dependency lock

```bash
uv lock
```

### 2. Format and lint

```bash
uv run ruff format . && \
uv run ruff check . --fix
```

### 3. Run tests

```bash
uv run pytest
```

### 4. Compile-check Python

```bash
uv run python -m compileall src tests
```

### 5. Review Git changes

```bash
git status --short && \
git diff HEAD
```

### 6. Build the OpenShell sandbox image

```bash
docker build \
  -f docker/openshell-sandbox/Dockerfile \
  -t local-mcp-openshell-sandbox:1.0.0 \
  .
```

### 7. Validate Compose configuration

```bash
docker compose config
```

### 8. Build Compose services

```bash
docker compose build
```

### 9. Start the stack

```bash
docker compose up -d
```

### 10. Check Compose status

```bash
docker compose ps
```

### 11. Check OpenShell

```bash
openshell status
```

### 12. Check existing sandboxes

```bash
openshell sandbox list
```

### 13. Check MCP server

```bash
docker compose logs --tail=200 mcp-server
```

### 14. Check OpenShell Gateway

```bash
docker compose logs --tail=200 openshell-gateway
```

### 15. Check tunnel client

```bash
docker compose logs --tail=100 tunnel-client
```

### 16. Refresh the MCP application/connector in ChatGPT

Refresh the existing MCP connection so the new sandbox tools are discovered.

### 17. Review final Git state

```bash
git status --short && \
git diff HEAD
```

### 18. Commit

```bash
git add .
```

```bash
git diff --cached
```

```bash
git commit -m "Replace terminal executor with OpenShell sandboxes"
```