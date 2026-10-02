# OpenAI Secure MCP Tunnel

**Repository:** `0n6k4v-Coder/openai-secure-mcp-tunnel`  
**Scope:** Private Python MCP server in Docker, connected to ChatGPT through OpenAI Secure MCP Tunnel and OpenShell sandbox execution.

---

# Architecture

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
                    │  installation API       │
                    └────────────┬────────────┘
                                 │
                         TLS + mTLS
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   OpenShell Gateway     │
                    │                         │
                    │  sandbox lifecycle      │
                    │  policy                 │
                    │  Docker driver          │
                    │  sandbox registry       │
                    │  mTLS authentication    │
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

The previous `terminal-executor` service is no longer part of the architecture.

### Workspace ACL helper

Host workspace authorization is handled by the separate trusted host-side:

```text
workspace-broker
```

When a workspace is authorized, the broker provisions POSIX ACLs so that both the host user and the OpenShell sandbox user can work with the mounted workspace.

The sandbox image runs as:

```text
UID 10001
GID 10001
```

The broker grants the sandbox UID access to the authorized workspace and applies default ACLs to directories so files and directories created inside the sandbox remain accessible to the host user.

During revocation, the broker uses:

```text
local-mcp-workspace-acl-helper:1.0.0
```

The helper is a minimal Alpine image containing `setfacl`. It runs with:

```text
network: none
read-only root filesystem
cap-drop: ALL
cap-add: DAC_OVERRIDE
cap-add: FOWNER
user: root
```

It is bind-mounted only to the authorized workspace and removes the sandbox UID ACL entries.

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

The deployment uses:

```text
OpenShell Gateway: ghcr.io/nvidia/openshell/gateway:latest
OpenShell Python SDK: openshell==0.1.1
Python: 3.14
MCP SDK: mcp[cli]==2.2.0
```

The Gateway configuration is located at:

```text
deploy/openshell/gateway.toml
```

The Gateway uses the Docker socket to create and manage sandbox containers.

The current deployment enables Gateway TLS and mTLS authentication:

```text
MCP Server
    │
    │ HTTPS + mTLS
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

The Gateway listens on the host loopback interface:

```text
127.0.0.1:8080
```

and exposes its health endpoint on:

```text
127.0.0.1:8081
```

The Gateway certificates are mounted from:

```text
.secrets/openshell-tls/gateway/
```

The MCP server uses the corresponding client certificates from:

```text
.secrets/openshell-tls/client/
```

The Gateway is configured with:

```toml
disable_tls = false
```

and mTLS authentication is enabled.

**Do not expose the OpenShell Gateway directly to an untrusted network.**

---

# CLI Reference

The project has two separate host-side CLI entry points.

## Secure MCP CLI

Run:

```bash
uv run secure-mcp --help
```

### Sandbox commands

```bash
uv run secure-mcp sandbox --help
```

The current sandbox CLI provides:

```text
create
list
status
shell
exec
logs
start
stop
delete
```

Examples:

```bash
uv run secure-mcp sandbox list
```

```bash
uv run secure-mcp sandbox status <sandbox-name>
```

```bash
uv run secure-mcp sandbox create <sandbox-name> --workspace <workspace-id>
```

```bash
uv run secure-mcp sandbox delete <sandbox-name>
```

### Credential commands

```bash
uv run secure-mcp credential --help
```

Use this command to inspect the currently available credential-management CLI operations.

---

## Workspace Broker CLI

Workspace authorization is intentionally a separate trusted host-side CLI.

Run:

```bash
uv run workspace-broker --help
```

The current commands are:

```text
authorize
revoke
list
```

List all authorized host workspaces:

```bash
uv run workspace-broker list
```

Authorize a workspace:

```bash
uv run workspace-broker authorize <host-path>
```

Revoke a workspace:

```bash
uv run workspace-broker revoke <workspace-id>
```

The workspace broker is responsible for:

```text
host path validation
workspace authorization
Docker volume creation
POSIX ACL provisioning
POSIX ACL revocation
workspace grant registry
```

Do **not** use:

```bash
uv run secure-mcp workspace-broker ...
```

`workspace-broker` is a separate executable.

---

# Step 5 - Build the Sandbox Image

The OpenShell Gateway uses:

```text
local-mcp-openshell-sandbox:1.0.0
```

Build this image before creating OpenShell sandboxes.

The image must exist locally with the exact tag configured in:

```text
deploy/openshell/gateway.toml
```

The current configuration uses:

```toml
[openshell.drivers.docker]
default_image = "local-mcp-openshell-sandbox:1.0.0"
image_pull_policy = "if_not_present"
```

The sandbox image provides:

```text
Python
Node.js
npm
Playwright
Chromium
git
curl
wget
jq
ripgrep
OpenSSH client
```

The sandbox container runs as:

```text
UID 10001
GID 10001
```

---

# Step 6 - Build the Workspace ACL Helper

Build the trusted host-side ACL helper:

```bash
docker build \
  -t local-mcp-workspace-acl-helper:1.0.0 \
  deploy/docker/workspace-acl-helper
```

The helper is used by `workspace-broker` during workspace revocation.

It does not provide a general-purpose shell or network access.

Its only purpose is removing the OpenShell sandbox UID ACL entries from an authorized workspace.

---

# Step 7 - Start the MCP Server, OpenShell Gateway, and Tunnel

Start the stack:

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  up -d --remove-orphans
```

The `--remove-orphans` option is intentional.

It removes containers belonging to services that were previously defined in the Compose file but have since been removed.

Check the service status:

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  ps
```

The expected application services are:

```text
openshell-gateway
mcp-server
tunnel-client
```

---

# Step 8 - Check the MCP Server

Check the MCP server logs:

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  logs --tail=200 mcp-server
```

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
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  ps
```

---

# Step 9 - Check the OpenShell Gateway

Check the Gateway logs:

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  logs --tail=200 openshell-gateway
```

The Gateway should report that it is using the Docker compute driver.

Expected information includes:

```text
Using compute driver driver=docker
Compute driver connected configured_driver=docker advertised_driver=docker
Gateway listener bound
```

The MCP server communicates with the Gateway using the configured TLS/mTLS connection.

---

# Step 10 - Check the Tunnel

Follow the tunnel logs:

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  logs -f tunnel-client
```

The tunnel client should initialize the MCP session and start the tunnel successfully.

The exact log wording may vary between tunnel-client versions.

Do not depend on a specific emoji or exact startup message.

---

# Connect the Tunnel to ChatGPT

## Step 11 - Create the MCP App / Connector

Open ChatGPT and create or configure the MCP connection using the existing OpenAI Secure MCP Tunnel.

Select:

```text
Tunnel
```

as the connection type.

Select the tunnel created in Step 2.

Complete the connection.

---

# Verify the MCP Tools

## Step 12 - Check the Available Tools

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
list_authorized_host_workspaces
list_sandboxes
list_workspace_files
read_workspace_text_file
rename_workspace_path
request_tool_installation
sandbox_status
write_workspace_file
```

The sandbox-related tools are backed by OpenShell.

The workspace tools operate within the selected OpenShell sandbox's mounted workspace:

```text
/workspace/project
```

The installation tool provides controlled installation of approved development tools inside the authorized sandbox.

---

# Verify OpenShell Sandbox Execution

The most important functional path is:

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

## Step 13 - Create a Sandbox

First authorize a host workspace:

```bash
uv run workspace-broker authorize "$HOME/path/to/workspace"
```

Record the returned:

```text
workspace_id
```

Then create the sandbox using the CLI:

```bash
uv run secure-mcp sandbox create \
  <sandbox-name> \
  --workspace <workspace-id>
```

Or use the MCP tool:

```text
create_sandbox
```

---

## Step 14 - Check Sandbox Status

Use:

```bash
uv run secure-mcp sandbox status <sandbox-name>
```

or the MCP tool:

```text
sandbox_status
```

Confirm that the sandbox reaches the expected ready/running state.

---

## Step 15 - Execute a Command in the Sandbox

Use:

```bash
uv run secure-mcp sandbox exec <sandbox-name> -- \
  sh -lc 'echo "OpenShell sandbox is working"'
```

or the MCP tool:

```text
execute_sandbox_command
```

The command must execute inside the OpenShell sandbox rather than directly on the MCP server host.

---

## Step 16 - Verify Host/Sandbox Workspace Editing

The authorized workspace uses POSIX ACLs so that the host user and sandbox user can both modify workspace content.

A useful test is:

```text
Sandbox creates file
       ↓
Host edits file
       ↓
Sandbox reads/edits file
       ↓
Sandbox is deleted
       ↓
Workspace grant is revoked
```

The workspace broker provisions default ACLs on directories so newly created files and directories remain accessible to the host user.

---

## Step 17 - Delete the Sandbox

After testing:

```bash
uv run secure-mcp sandbox delete <sandbox-name>
```

or use:

```text
delete_sandbox
```

Confirm that the sandbox is removed.

---

## Step 18 - Revoke the Workspace

After the sandbox has been deleted:

```bash
uv run workspace-broker revoke <workspace-id>
```

Then verify:

```bash
uv run workspace-broker list
```

The revoked workspace should no longer appear.

---

# Controlled Tool Installation

The MCP server provides:

```text
request_tool_installation
```

Tool installation is performed inside the authorized sandbox rather than directly on the MCP server host.

The workflow is:

```text
ChatGPT
   ↓
request_tool_installation
   ↓
MCP server authorization
   ↓
OpenShell sandbox
   ↓
sandbox network policy
   ↓
package/tool installation
```

For example, a development tool can be installed through the installation request mechanism while remaining inside the sandbox boundary.

The host filesystem is not used as the installation target.

---

# Update MCP Server Tools

When MCP server code or tool definitions change, rebuild the MCP server image and recreate the MCP server container.

All Docker Compose commands in this document use the repository's explicit environment file and Compose file:

```text
--env-file .env
-f deploy/compose.yaml
```

## 1. Rebuild the MCP server image

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  build --no-cache mcp-server
```

## 2. Recreate the MCP server

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  up -d --force-recreate --remove-orphans openshell-gateway
```

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  up -d --force-recreate --remove-orphans mcp-server
```

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  up -d --force-recreate --remove-orphans tunnel-client
```

## 3. Check the service status

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  ps
```

Expected services:

```text
openshell-gateway
mcp-server
tunnel-client
```

## 4. Check the MCP server logs

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  logs --tail=200 mcp-server
```

Or:

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  logs -f mcp-server
```

## 5. Check the tunnel client

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  logs --tail=100 tunnel-client
```

## 6. Verify Compose environment loading

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  config --environment | grep '^CONTROL_PLANE_TUNNEL_ID='
```

The command should print the variable name with a value.

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

Do not immediately create a new API key or OpenAI tunnel.

First:

1. Confirm the MCP server is healthy.
2. Confirm the new tool appears in the MCP server discovery/registry.
3. Refresh the MCP app/connector.
4. If necessary, delete only the MCP app/connector.
5. Create the MCP app/connector again.
6. Select the **same existing tunnel**.
7. Check the tool list again.

Preferred workflow:

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

# Workspace Management

List all authorized workspaces:

```bash
uv run workspace-broker list
```

Authorize a workspace:

```bash
uv run workspace-broker authorize "$HOME/path/to/workspace"
```

Revoke a workspace:

```bash
uv run workspace-broker revoke <workspace-id>
```

The broker records:

```text
workspace ID
host path
host UID
host GID
target
Docker volume name
read-only state
```

For writable workspaces, the broker provisions ACLs for:

```text
host user
sandbox UID 10001
```

Directories also receive default ACLs so newly created content inherits the required access.

Protected project paths such as secrets, state, and Gateway signing material are not granted sandbox ACL access.

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
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  up -d --remove-orphans
```

Then verify:

```bash
docker compose \
  --env-file .env \
  -f deploy/compose.yaml \
  ps
```

The current deployment should contain:

```text
openshell-gateway
mcp-server
tunnel-client
```

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
list_authorized_host_workspaces
list_sandboxes
list_workspace_files
read_workspace_text_file
rename_workspace_path
request_tool_installation
sandbox_status
write_workspace_file
```

Sandbox execution is performed through OpenShell.

Workspace operations are constrained to the authorized workspace mounted at:

```text
/workspace/project
```

Tool installation is performed through the controlled installation workflow inside the authorized sandbox.

---

# Security Notes

The current deployment uses TLS and mTLS for communication between the MCP server and OpenShell Gateway.

The Gateway is bound to the local host interface and should not be exposed directly to an untrusted network.

The deployment also uses:

```text
TLS
mTLS authentication
read-only MCP container filesystem
no-new-privileges
capability drop
internal Docker networks
workspace boundary controls
POSIX ACLs
OpenShell sandbox isolation
controlled tool installation
```

The OpenShell Gateway requires client authentication.

Secrets must remain outside Git:

```text
.env
.secrets/control-plane-api-key
.secrets/openshell-tls/
```

Do not commit API keys, tunnel credentials, TLS private keys, or other secrets.

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
   │ HTTPS + mTLS
   ▼
openshell-gateway
   │
   │ Docker socket
   ▼
Docker
   │
   ├── OpenShell Sandbox A
   ├── OpenShell Sandbox B
   └── OpenShell Sandbox C
```

Host workspace lifecycle:

```text
Host directory
      │
      ▼
workspace-broker authorize
      │
      ├── Docker volume
      ├── workspace grant
      └── POSIX ACLs
              │
              ▼
       OpenShell sandbox
              │
              ▼
       /workspace/project
              │
              ▼
workspace-broker revoke
              │
              ▼
workspace-acl-helper
```

The project no longer uses a separate `terminal-executor` service.

The MCP server exposes sandbox operations through OpenShell, workspace operations through authorized workspace boundaries, and controlled tool installation through the sandbox installation workflow.