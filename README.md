# OpenAI Secure MCP Tunnel

**Repository:** `0n6k4v-Coder/openai-secure-mcp-tunnel`
**Scope:** Private Python MCP server in Docker, connected to ChatGPT through OpenAI Secure MCP Tunnel and OpenShell sandbox execution.

---

## Architecture

```text
                              ChatGPT
                                 │
                                 │ MCP
                                 ▼
                    ┌─────────────────────────┐
                    │     OpenAI Tunnel       │
                    │      tunnel-client      │
                    │                         │
                    │       transport         │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │       MCP SERVER        │
                    │                         │
                    │  MCP API                │
                    │  tool authorization     │
                    │  sandbox API            │
                    │  workspace API          │
                    └────────────┬────────────┘
                                 │
                    plaintext internal HTTP
                    OpenShell API
                    (TLS disabled in deployment)
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   OpenShell Gateway     │
                    │                         │
                    │  sandbox lifecycle      │
                    │  policy                 │
                    │  Docker driver          │
                    │  sandbox registry       │
                    └────────────┬────────────┘
                                 │
                         Docker driver
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
       ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
       │  Sandbox A  │    │  Sandbox B  │    │  Sandbox C  │
       │             │    │             │    │             │
       │ Python      │    │ Node        │    │ Playwright  │
       │ Node        │    │ npm         │    │ Chromium    │
       │ workspace   │    │ workspace   │    │ workspace   │
       └─────────────┘    └─────────────┘    └─────────────┘
```

### Runtime services

The Docker Compose deployment contains three application services:

```text
openshell-gateway
mcp-server
tunnel-client
```

OpenShell creates and manages sandbox containers through its Docker compute driver.

The previous `terminal-executor` service is no longer part of the current architecture.

---

# Set Up

## Step 1 - Clone the repository

```bash
git clone https://github.com/0n6k4v-Coder/openai-secure-mcp-tunnel.git
cd openai-secure-mcp-tunnel
```

---

## Step 2 - Create and Configure the OpenAI Tunnel

Open:

https://platform.openai.com/settings/organization/tunnels

Find **Create tunnel**.

Create a new tunnel with a name such as:

```text
openai-secure-mcp-tunnel
```

After creating the tunnel, copy the Tunnel ID:

```text
tunnel_xxx
```

Create a `.env` file at the project root:

```bash
touch .env
```

Add:

```env
CONTROL_PLANE_TUNNEL_ID=<Copied Tunnel ID>
```

---

## Step 3 - Create and Configure the OpenAI Control Plane API Key

Open the OpenAI API Keys page:

https://platform.openai.com/api-keys

Create a new API key with the permissions required for the tunnel.

Copy the API key immediately after creating it.

Create the secrets directory:

```bash
mkdir -p .secrets
```

Create the API key file:

```bash
touch .secrets/control-plane-api-key
```

Open `.secrets/control-plane-api-key` and paste the API key into the file.

The file should contain only the API key:

```text
sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Save the file.

**Do not commit this file to Git.**

---

## Step 4 - Configure the OpenShell Deployment

The project uses OpenShell Gateway with the Docker compute driver.

The current deployment uses:

```text
OpenShell Gateway: ghcr.io/nvidia/openshell/gateway:latest
OpenShell Python SDK: openshell==0.1.1
Python: 3.14
MCP SDK: mcp[cli]==2.2.0
```

The Gateway configuration is located at:

```text
openshell/gateway.toml
```

The current deployment uses the Docker socket to allow OpenShell Gateway to create and manage sandbox containers.

The Gateway is configured for private internal communication:

```text
MCP Server
    │
    │ HTTP
    ▼
OpenShell Gateway
    │
    │ Docker socket
    ▼
Docker
    │
    ▼
Sandbox containers
```

TLS is currently disabled for the internal Gateway connection.

**Do not expose the OpenShell Gateway directly to an untrusted network.**

For production or remote exposure, configure appropriate TLS and authentication.

---

## Step 5 - Build the Sandbox Image

The OpenShell Gateway uses the configured sandbox image:

```text
local-mcp-openshell-sandbox:1.0.0
```

Build this image before creating OpenShell sandboxes.

The image must exist locally with the exact tag configured in:

```text
openshell/gateway.toml
```

The current configuration uses:

```toml
[openshell.drivers.docker]
default_image = "local-mcp-openshell-sandbox:1.0.0"
image_pull_policy = "if_not_present"
```

---

## Step 6 - Start the MCP Server, OpenShell Gateway, and Tunnel

Start the stack:

```bash
docker compose up -d --remove-orphans
```

The `--remove-orphans` option is intentional.

It removes containers belonging to services that were previously defined in the Compose file but have since been removed.

For example, older versions of this project used:

```text
terminal-executor
```

That service is no longer used.

Check the service status:

```bash
docker compose ps
```

The expected application services are:

```text
openshell-gateway
mcp-server
tunnel-client
```

The MCP server should become healthy.

---

## Step 7 - Check the MCP Server

Check the MCP server logs:

```bash
docker compose logs --tail=200 mcp-server
```

You should see the server start successfully.

The MCP server exposes:

```text
http://mcp-server:8000/mcp
```

The health endpoint is:

```text
http://mcp-server:8000/healthz
```

The MCP server should report a healthy status in:

```bash
docker compose ps
```

---

## Step 8 - Check the OpenShell Gateway

Check the Gateway logs:

```bash
docker compose logs --tail=200 openshell-gateway
```

The Gateway should report that it is using the Docker compute driver.

Expected log information includes:

```text
Using compute driver driver=docker
Compute driver connected configured_driver=docker advertised_driver=docker
Gateway listener bound
```

The Gateway communicates with the MCP server over the internal Docker network.

---

## Step 9 - Check the Tunnel

Follow the tunnel logs:

```bash
docker compose logs -f tunnel-client
```

The tunnel client should initialize the MCP session and start the tunnel successfully.

You should see information similar to:

```text
MCP session initialized
```

and:

```text
tunnel started successfully
```

The exact log wording may vary between tunnel-client versions.

Do not depend on a specific emoji or exact startup message.

---

# Connect the Tunnel to ChatGPT

## Step 10 - Create the MCP App / Connector

Open ChatGPT and create or configure the MCP connection using the existing OpenAI Secure MCP Tunnel.

Select:

```text
Tunnel
```

as the connection type.

Select the tunnel created in Step 2.

For the current private deployment, use the authentication option configured for the MCP app.

Complete the connection.

---

# Verify the MCP Tools

## Step 11 - Check the Available Tools

After connecting the MCP app, verify that the following tools are available:

```text
create_sandbox
create_workspace_directory
create_workspace_file
delete_sandbox
delete_workspace_directory
delete_workspace_file
execute_sandbox_command
get_system_info
list_sandboxes
list_workspace_files
read_workspace_text_file
rename_workspace_path
sandbox_status
write_workspace_file
```

The sandbox-related tools are backed by OpenShell.

The workspace tools operate within the configured workspace boundary.

---

# Verify OpenShell Sandbox Execution

The most important functional test is to verify the complete path:

```text
ChatGPT
   ↓
OpenAI Secure MCP Tunnel
   ↓
MCP Server
   ↓
OpenShell Gateway
   ↓
Docker sandbox
```

## Step 12 - Create a Sandbox

Use the MCP tool:

```text
create_sandbox
```

Confirm that the sandbox is created successfully.

---

## Step 13 - Check Sandbox Status

Use:

```text
sandbox_status
```

Confirm that the sandbox reaches the expected ready/running state.

---

## Step 14 - Execute a Command in the Sandbox

Use:

```text
execute_sandbox_command
```

Run a simple command such as:

```bash
echo "OpenShell sandbox is working"
```

The command must execute inside the OpenShell sandbox rather than directly on the MCP server host.

---

## Step 15 - Delete the Sandbox

After testing, use:

```text
delete_sandbox
```

Confirm that the sandbox is removed.

---

# Update MCP Server Tools

When MCP server code or tool definitions change, rebuild the MCP server image and recreate the MCP server container.

## Docker

### 1. Rebuild the MCP server image

```bash
docker compose build --no-cache mcp-server
```

This rebuilds the image using the current MCP source code.

### 2. Recreate the MCP server

```bash
docker compose up -d --force-recreate --remove-orphans mcp-server
```

The `--remove-orphans` option ensures that old Compose services, such as the former `terminal-executor`, are cleaned up.

### 3. Check the service status

```bash
docker compose ps
```

Expected services:

```text
openshell-gateway
mcp-server
tunnel-client
```

The MCP server should become healthy.

### 4. Check the MCP server logs

```bash
docker compose logs --tail=200 mcp-server
```

Or follow the logs:

```bash
docker compose logs -f mcp-server
```

Check for startup errors.

### 5. Check the tunnel client

```bash
docker compose logs --tail=100 tunnel-client
```

Confirm that the tunnel client remains connected to the existing tunnel.

---

# Update the MCP Tool List in ChatGPT

After changing the MCP tools:

```text
ChatGPT
  ↓
Settings
  ↓
Apps / Connectors
  ↓
Your MCP App
  ↓
Refresh
```

Refresh the MCP connection so ChatGPT can rediscover the current MCP tool list.

The MCP server must be running and reachable through the tunnel before refreshing.

---

# If Refresh Does Not Show the New Tool

Do **not** immediately create a new API key or OpenAI tunnel.

First:

1. Confirm the MCP server is healthy.
2. Confirm the new tool appears in the MCP server's discovery/registry logs.
3. Refresh the MCP app/connector.
4. If necessary, delete only the MCP app/connector.
5. Create the MCP app/connector again.
6. Select the **same existing tunnel**.
7. Check the tool list again.

The preferred workflow is:

```text
Change MCP code
      ↓
Rebuild
      ↓
Recreate MCP server
      ↓
Check MCP logs
      ↓
Check tunnel
      ↓
Refresh MCP app
      ↓
Verify tools
```

There is normally no reason to create a new tunnel simply because the MCP tool list changed.

---

# Handling Old Orphan Containers

If Compose reports:

```text
Found orphan containers
```

for example:

```text
openai-secure-mcp-tunnel-terminal-executor-1
```

the service exists from an older version of the Compose configuration.

Remove obsolete services with:

```bash
docker compose up -d --remove-orphans
```

Then verify:

```bash
docker compose ps
```

The current deployment should contain:

```text
openshell-gateway
mcp-server
tunnel-client
```

---

# Quick Start

## 1. Start the stack

```bash
docker compose up -d --remove-orphans
```

## 2. Check the services

```bash
docker compose ps
```

Expected:

```text
openshell-gateway
mcp-server
tunnel-client
```

## 3. Check the MCP server

```bash
docker compose logs --tail=200 mcp-server
```

## 4. Check OpenShell Gateway

```bash
docker compose logs --tail=200 openshell-gateway
```

## 5. Check the tunnel

```bash
docker compose logs --tail=100 tunnel-client
```

## 6. Verify the MCP tools in ChatGPT

Confirm that the current sandbox and workspace tools are available.

## 7. Test sandbox execution

Use:

```text
create_sandbox
sandbox_status
execute_sandbox_command
delete_sandbox
```

---

# Stop

Stop and remove the current Compose containers and network:

```bash
docker compose down
```

This does not remove Docker images.

---

# Restart

Start the stack again:

```bash
docker compose up -d --remove-orphans
```

Check the status:

```bash
docker compose ps
```

Check the MCP server:

```bash
docker compose logs --tail=200 mcp-server
```

Check the Gateway:

```bash
docker compose logs --tail=200 openshell-gateway
```

Check the tunnel:

```bash
docker compose logs --tail=100 tunnel-client
```

---

# Rebuild the MCP Server

When source code or dependencies change:

```bash
docker compose build --no-cache mcp-server
```

Then:

```bash
docker compose up -d --force-recreate --remove-orphans mcp-server
```

Check:

```bash
docker compose ps
```

And:

```bash
docker compose logs --tail=200 mcp-server
```

---

# Troubleshooting

## Tunnel is not starting

Check:

```bash
docker compose logs --tail=100 tunnel-client
```

Verify that `.env` contains:

```env
CONTROL_PLANE_TUNNEL_ID=<Correct Tunnel ID>
```

Also verify that:

```text
.secrets/control-plane-api-key
```

exists and contains the correct API key.

---

## MCP server is unhealthy

Check:

```bash
docker compose ps
```

Then:

```bash
docker compose logs --tail=200 mcp-server
```

The MCP server health endpoint is:

```text
/mcp
```

for MCP traffic and:

```text
/healthz
```

for health checks.

---

## OpenShell Gateway is not starting

Check:

```bash
docker compose logs --tail=200 openshell-gateway
```

Verify:

```text
openshell/gateway:latest
```

is configured as the Gateway image.

Verify that:

```text
openshell/gateway.toml
```

contains the current OpenShell v2 configuration.

The Docker socket must also be available to the Gateway:

```text
/var/run/docker.sock
```

---

## Sandbox creation fails

Check both the MCP server and Gateway logs:

```bash
docker compose logs --tail=200 mcp-server
```

```bash
docker compose logs --tail=200 openshell-gateway
```

Verify that the configured sandbox image exists locally:

```text
local-mcp-openshell-sandbox:1.0.0
```

Also verify that the Gateway is configured with:

```toml
compute_driver = "docker"
```

and:

```toml
image_pull_policy = "if_not_present"
```

---

## ChatGPT shows an old tool list

First verify that the MCP server itself exposes the new tools.

Then:

```text
Rebuild
    ↓
Recreate MCP server
    ↓
Check MCP logs
    ↓
Check tunnel-client
    ↓
Refresh MCP app
```

If the old tool list remains:

```text
Delete only the MCP App / Connector
        ↓
Create it again
        ↓
Select the same existing tunnel
        ↓
Verify the tools
```

Do not immediately create a new API key or tunnel.

---

## Old `terminal-executor` container still exists

If:

```bash
docker compose ps
```

or Compose startup reports:

```text
Found orphan containers
```

run:

```bash
docker compose up -d --remove-orphans
```

The obsolete `terminal-executor` container should be removed.

---

# Current MCP Tools

The current MCP server provides:

```text
create_sandbox
create_workspace_directory
create_workspace_file
delete_sandbox
delete_workspace_directory
delete_workspace_file
execute_sandbox_command
get_system_info
list_sandboxes
list_workspace_files
read_workspace_text_file
rename_workspace_path
sandbox_status
write_workspace_file
```

Sandbox execution is performed through OpenShell rather than a separate host-level terminal executor.

---

# Security Notes

The current deployment intentionally keeps the OpenShell Gateway on the internal Docker network and uses plaintext HTTP between the MCP server and Gateway.

The Gateway should not be exposed directly to an untrusted network.

The deployment also uses:

```text
read-only MCP container filesystem
no-new-privileges
capability drop
internal Docker networks
workspace boundary controls
OpenShell sandbox isolation
```

Secrets must remain outside Git:

```text
.env
.secrets/control-plane-api-key
```

Do not commit API keys, tunnel credentials, or other secrets.

---

# Current Deployment Summary

```text
ChatGPT
   │
   ▼
OpenAI Secure MCP Tunnel
   │
   ▼
tunnel-client
   │
   ▼
mcp-server
   │
   ▼
openshell-gateway
   │
   ▼
Docker
   │
   ├── OpenShell Sandbox A
   ├── OpenShell Sandbox B
   └── OpenShell Sandbox C
```

The project no longer uses a separate `terminal-executor` service.

The MCP server exposes sandbox operations through OpenShell and keeps workspace operations inside the configured workspace boundary.
