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
   │ internal OpenShell API
   ▼
OpenShell Gateway
   │
   │ Docker compute driver
   ▼
OpenShell Supervisor
   │
   ▼
Per-request sandbox
```

The MCP server does not receive the Docker socket. The trusted OpenShell Gateway owns Docker lifecycle and creates sandbox containers.

## Prerequisites

- Docker Engine and Docker Compose.
- An OpenAI Secure MCP Tunnel.
- OpenShell v0.1.1.
- A writable OpenShell state directory, normally `/var/lib/openshell`.

Install OpenShell:

```bash
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | OPENSHELL_VERSION=v0.1.1 sh
```

Verify:

```bash
openshell --version
openshell status
```

## Configuration

Copy `.env.example` to `.env` and set the existing tunnel ID.

Create `.secrets/control-plane-api-key` containing only the OpenAI control-plane API key.

Before the first build, regenerate the dependency lock because the repository now declares `openshell==0.1.1`:

```bash
uv lock
```

## Build the Sandbox Image

```bash
docker build -f docker/openshell-sandbox/Dockerfile -t local-mcp-openshell-sandbox:1.0.0 .
```

The image contains Python, Node/npm, Playwright, bundled Chromium, Git and common development tools. It does not contain Docker or a Docker socket.

## Start

```bash
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

The old `terminal-executor` service is no longer part of the Compose stack.

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

Create a sandbox:

```text
create_sandbox("my-sandbox")
```

Execute inside it:

```text
execute_sandbox_command("my-sandbox", "python -c \\"print('hello from sandbox')\\"")
```

Delete it when finished:

```text
delete_sandbox("my-sandbox")
```

OpenShell applies the sandbox isolation, filesystem policy, process policy, network policy and credential boundary.

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
Docker
    │
    ▼
OpenShell Supervisor
    │
    ▼
Sandbox workload
```

Only the trusted OpenShell Gateway receives `/var/run/docker.sock`.

## Updating MCP Tools

```bash
uv lock
docker compose build --no-cache mcp-server
docker compose up -d --force-recreate mcp-server
docker compose ps
docker compose logs --tail=200 mcp-server
docker compose logs --tail=100 tunnel-client
```

Then refresh the MCP application/connector in ChatGPT so the tool registry is rediscovered.

## Stop

```bash
docker compose down
```
