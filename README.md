# OpenAI Secure MCP Tunnel

Private Python MCP server connected to ChatGPT through OpenAI Secure MCP Tunnel.

## OpenShell version policy

This repository pins the OpenShell stack to **v0.1.1**:

- Python SDK: `openshell==0.1.1`
- Gateway image: `ghcr.io/nvidia/openshell/gateway:v0.1.1`
- Supervisor image: `ghcr.io/nvidia/openshell/supervisor:v0.1.1`

Keeping these components on the same release avoids mixing incompatible Gateway, Supervisor, and SDK schemas.

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
   │ private Compose network
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

The MCP server never receives the Docker socket. Only the trusted OpenShell Gateway receives it and uses the Docker compute driver to create sibling sandbox containers.

## Sandbox resource limits

Each sandbox is created with explicit CPU and memory limits.

Defaults:

```text
SANDBOX_DEFAULT_CPU=1
SANDBOX_DEFAULT_MEMORY=1GiB
```

Override them in `.env` when required.

The Python integration builds an OpenShell `SandboxSpec` with:

```text
template.image
template.resources.limits.cpu
template.resources.limits.memory
```

The values are validated before the create request is sent to the Gateway.

## Prerequisites

- Docker Engine and Docker Compose.
- An OpenAI Secure MCP Tunnel.
- OpenShell CLI v0.1.1.
- A writable host directory at `/var/lib/openshell`.
- Access to the host Docker socket.

## Configuration

Copy `.env.example` to `.env`.

Set `CONTROL_PLANE_TUNNEL_ID` to the existing tunnel ID.

Create `.secrets/control-plane-api-key` containing only the OpenAI control-plane API key.

The Gateway state directory is fixed to `/var/lib/openshell` on both the host and inside the Gateway container.

## OpenShell CLI

This project runs its Gateway in Docker Compose, so do not run a second Gateway on the same host.

Install the matching CLI:

```bash
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | OPENSHELL_VERSION=v0.1.1 sh
```

Register the Compose Gateway:

```bash
openshell gateway add http://127.0.0.1:8080 --local --name local-mcp
openshell gateway select local-mcp
openshell status
```

## Python Dependency Lock

The MCP server uses:

- `mcp[cli]==2.2.0`
- `openshell==0.1.1`

Regenerate `uv.lock` after dependency changes:

```bash
uv lock
```

## Build the Sandbox Image

```bash
docker build \
  -f docker/openshell-sandbox/Dockerfile \
  -t local-mcp-openshell-sandbox:1.0.0 \
  .
```

The sandbox image contains Python, Node.js 24.21.0, npm 12.1.0, Playwright 1.63.0, Git and common development tools.

It does not contain Docker and does not receive the Docker socket.

## Start

```bash
docker compose config
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

OpenShell manages sandbox lifecycle and applies its filesystem, process, network and credential controls.

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

The Gateway is the only service that can control the host Docker daemon.

The Docker driver has arbitrary host bind mounts disabled with `enable_bind_mounts = false`.

## Verification

```bash
uv lock
uv run ruff format .
uv run ruff check . --fix
uv run pytest
uv run python -m compileall src tests

docker compose config
docker compose build --no-cache mcp-server
docker compose up -d
docker compose ps
docker compose logs --tail=200 openshell-gateway
docker compose logs --tail=200 mcp-server
docker compose logs --tail=100 tunnel-client
```

Then test the sandbox lifecycle through ChatGPT:

```text
create_sandbox("smoke-test")
execute_sandbox_command(
    "smoke-test",
    "python -c \\"print('OpenShell OK')\\"",
)
delete_sandbox("smoke-test")
```

## Stop

```bash
docker compose down
```

## Important Security Note

The Gateway uses plaintext HTTP only for this trusted local deployment. Its published listeners are bound to `127.0.0.1`, and the internal MCP-to-Gateway connection is restricted to the private Compose network.

Do not expose this Gateway beyond the trusted local host without enabling TLS/mTLS or an appropriate authenticated deployment.
