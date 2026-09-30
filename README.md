# OpenAI Secure MCP Tunnel

Private Python MCP server connected to ChatGPT through OpenAI Secure MCP Tunnel.

## Architecture

```text
ChatGPT
   │ MCP
   ▼
OpenAI tunnel-client
   │
   ▼
MCP server
   │
   │ internal HTTP
   ▼
OpenShell Gateway
   │
   │ host Docker socket
   ▼
Docker Engine
   │
   ▼
OpenShell Supervisor
   │
   ▼
Per-request sandbox
```

The MCP server never receives the Docker socket. Only the trusted OpenShell Gateway receives it and uses the Docker compute driver to create sibling sandbox containers. OpenShell Supervisor provides the sandbox enforcement boundary. This follows NVIDIA's documented container-Gateway pattern. citeturn0search0turn16search1

## Prerequisites

- Docker Engine 28.0 or later and Docker Compose.
- An OpenAI Secure MCP Tunnel.
- OpenShell CLI v0.1.1.
- A writable host directory at `/var/lib/openshell`.
- Access to the host Docker socket.

The OpenShell Python SDK is installed in the MCP server from PyPI. The SDK should be kept on the same OpenShell release as the Gateway when possible. citeturn8search0

## Configuration

Copy `.env.example` to `.env`.

Set `CONTROL_PLANE_TUNNEL_ID` to the existing tunnel ID. Adjust the sandbox resource defaults only if needed.

Create `.secrets/control-plane-api-key` containing only the OpenAI control-plane API key.

The Gateway state directory is intentionally fixed to `/var/lib/openshell` on both the host and inside the Gateway container. NVIDIA requires the supervisor path to resolve identically from the Gateway and the host Docker daemon. citeturn0search0turn16search1

## OpenShell CLI

The OpenShell installer normally starts its own local Gateway. This project instead runs the Gateway in Docker Compose, so do not leave a second OpenShell Gateway competing for the same host resources.

Install/use the OpenShell CLI at v0.1.1, then register this Compose Gateway:

```bash
openshell gateway add http://127.0.0.1:8080 --local --name local-mcp
openshell gateway select local-mcp
openshell status
```

NVIDIA documents this registration flow for a containerized Gateway. citeturn0search0

## Python Dependency Lock

The repository pins `openshell==0.1.1`. Regenerate the lock file before the first Docker build:

```bash
uv lock
```

The Docker build intentionally uses `--locked`, so it will reject a stale lock file.

## Build the Sandbox Image

```bash
docker build \
  -f docker/openshell-sandbox/Dockerfile \
  -t local-mcp-openshell-sandbox:1.0.0 \
  .
```

The sandbox image contains:

- Python
- Node.js 24.21.0
- npm 12.1.0
- Playwright 1.63.0
- bundled Playwright browsers
- Git and common development tools

It does not contain Docker and does not receive the Docker socket.

## Start

```bash
docker compose config
docker compose build --no-cache mcp-server
docker compose up -d
docker compose ps
```

Expected services:

```text
openshell-gateway
mcp-server
tunnel-client
```

There is no `terminal-executor` service.

## MCP Tools

```text
get_system_info
list_workspace_files
read_workspace_text_file
create_workspace_file
write_workspace_file
create_workspace_directory
rename_workspace_path
delete_workspace_file
delete_workspace_directory

create_sandbox
list_sandboxes
sandbox_status
execute_sandbox_command
delete_sandbox
```

The old `execute_terminal_command` tool is no longer registered.

## Sandbox Workflow

Create:

```text
create_sandbox("my-sandbox")
```

Execute:

```text
execute_sandbox_command(
    "my-sandbox",
    "python -c \\"print('hello from sandbox')\\"",
)
```

Delete:

```text
delete_sandbox("my-sandbox")
```

OpenShell manages sandbox lifecycle and applies its filesystem, process, network, and credential controls. citeturn11search1turn8search1

## Security Boundary

```text
MCP server
   │
   │ no Docker socket
   ▼
OpenShell Gateway
   │
   │ Docker socket
   ▼
Docker Engine
   │
   ▼
OpenShell Supervisor
   │
   ▼
Sandbox workload
```

The Gateway is the only service that can control the host Docker daemon. The sandbox image itself cannot create sibling Docker containers.

The Docker driver has arbitrary host bind mounts disabled with `enable_bind_mounts = false`. NVIDIA warns that arbitrary host bind mounts can negate sandbox isolation. citeturn15search1

## Updating MCP Tools

```bash
uv lock
uv run ruff format .
uv run ruff check . --fix
uv run pytest
uv run python -m compileall src tests

docker compose build --no-cache mcp-server
docker compose up -d --force-recreate mcp-server
docker compose ps
docker compose logs --tail=200 mcp-server
docker compose logs --tail=200 openshell-gateway
docker compose logs --tail=100 tunnel-client
```

Then refresh the existing MCP application/connector in ChatGPT.

## Stop

```bash
docker compose down
```

## Important Security Note

The Gateway is configured with plaintext HTTP because the MCP server and Gateway communicate only over the private Compose network and the host-published listener is bound to `127.0.0.1`. NVIDIA documents that disabling TLS removes Gateway authentication; do not expose this Gateway beyond the trusted local host without enabling mTLS/OIDC and appropriate network controls. citeturn0search0
