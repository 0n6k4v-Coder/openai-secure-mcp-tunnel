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
                    │  browser API            │
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
                    │  credential subsystem   │
                    └────────────┬────────────┘
                                 │
                         Docker driver
                                 │
              ┌──────────────────────┬──────────────────────┐
              │                      │                      │
              ▼                      ▼                      │
       ┌────────────────┐    ┌──────────────────────────┐   │
       │ Default        │    │ Browser                  │   │
       │ sandbox        │    │ sandbox                  │   │
       │                │    │                          │   │
       │ Python         │    │ Chrome for Testing       │   │
       │ Node.js / npm  │    │ Chrome DevTools MCP      │   │
       │ Playwright     │    │ sandbox-local CDP :9222 │   │
       │ workspace      │    │ workspace                │   │
       └────────────────┘    └──────────────────────────┘   │
              │                      │                      │
              └──────── OpenShell lifecycle ────────────────┘
```

### Runtime services

The Docker Compose deployment contains three application services:

```text
openshell-gateway
mcp-server
tunnel-client
```

OpenShell creates and manages sandbox containers through its Docker compute driver. Sandbox containers are created on demand and are not long-running Docker Compose services.

The built-in application runtime `default` is the production runtime and preserves the established Compose project, ports, and legacy configuration/state paths. Do not create a separate application runtime named `production`.

Optional named application runtimes (for example, `development`) are isolated from the default runtime. Select one in its terminal with `export MCP_RUNTIME=development`; omit the variable to use production. See [runtime and cleanup architecture](docs/profile-architecture.md).

The project also supports separate sandbox profiles.

The `default` sandbox profile is used for normal development and command execution.

The `browser` profile provides an isolated Chrome runtime and Chrome DevTools MCP daemon. Browser lifecycle is owned by the OpenShell browser sandbox lifecycle.

The previous `terminal-executor` service is no longer part of the architecture.

### Workspace ACL helper

Host workspace authorization is exposed through `mcpctl workspace` and implemented by the trusted host-side workspace broker module.

When a workspace is authorized, the broker:

```text
validates the host path
provisions POSIX ACLs
creates a host-backed Docker volume
stores an opaque workspace grant
```

The OpenShell sandbox uses:

```text
UID 10001
GID 10001
```

The broker grants the sandbox UID access to the authorized workspace and applies default ACLs to directories so files and directories created inside the sandbox remain accessible to the host user.

During revocation, the broker uses:

```text
local-mcp-workspace-acl-helper:1.0.0
```

The helper is a minimal Alpine image containing `setfacl`.

It runs with:

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

# Quick Start

Install the CLI:

```bash
./scripts/install-cli.sh
```

Synchronize the locked Python environment:

```bash
uv sync --locked --all-groups
```

The project requires:

```text
Python >=3.14,<3.15
```

The sole application operator CLI is:

```bash
uv run mcpctl --help
```

It also includes setup, status, repair, read-only cleanup inventory, uninstall, and configuration commands.

The trusted host-side workspace broker is:

```bash
uv run mcpctl workspace --help
```

---

## Step 1 - Clone the repository

```bash
git clone https://github.com/0n6k4v-Coder/openai-secure-mcp-tunnel.git
cd openai-secure-mcp-tunnel
```

---

## Step 2 - Create the deployment environment

Environment templates are stored under:

```text
deploy/
```

The default deployment environment template is:

```text
deploy/.env.example
```

Create the default deployment environment:

```bash
cp deploy/.env.example deploy/.env
```

For development, use:

```bash
cp deploy/.env.development.example deploy/.env.development
```

For production, use:

```bash
cp deploy/.env.production.example deploy/.env.production
```

The default `deploy/.env` is automatically discovered by Docker Compose when using:

```bash
docker compose -f deploy/compose.yaml ...
```

There is therefore no need to add:

```text
--env-file .env
```

to normal commands.

For an alternate environment file such as:

```text
deploy/.env.development
```

use an explicit environment file:

```bash
docker compose \
  --env-file deploy/.env.development \
  -f deploy/compose.yaml \
  up -d --remove-orphans
```

The deployment environment contains runtime configuration such as:

```text
COMPOSE_PROJECT_NAME
OPENSHELL_WORKSPACE
OPENSHELL_IMAGE_TAG
OPENSHELL_PORT
OPENSHELL_HEALTH_PORT
OPENSHELL_GATEWAY
OPENSHELL_CLI_GATEWAY
MCP_PORT
MCP_CONFIG_DIR
MCP_STATE_DIR
WORKSPACE_GRANTS_DIR
SANDBOX_IMAGE
BROWSER_SANDBOX_IMAGE
WORKSPACE_ACL_HELPER_IMAGE
SANDBOX_DEFAULT_CPU
SANDBOX_DEFAULT_MEMORY
BROWSER_ALLOWED_ENDPOINTS
INSTALLATION_TIMEOUT_SECONDS
LOG_LEVEL
```

The OpenAI tunnel ID and control-plane API key are configured separately through the `mcpctl` OpenAI client configuration command.

---

## Step 3 - Create and Configure the OpenAI Tunnel

Open:

https://platform.openai.com/settings/organization/tunnels

Find **Create tunnel**.

Create a new tunnel with a name such as:

```text
openai-secure-mcp-tunnel
```

After creating the tunnel, copy the Tunnel ID.

The expected format is:

```text
tunnel_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Do not place the tunnel ID in the Docker Compose environment file.

Configure the OpenAI MCP client through:

```bash
uv run mcpctl config mcp-client openai
```

The command prompts for:

```text
CONTROL_PLANE_TUNNEL_ID
CONTROL_PLANE_API_KEY
```

The configuration is stored under:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/local-mcp-server/mcp-clients/openai/
```

The resulting files are:

```text
config.yaml
credentials
```

The configuration file contains the tunnel ID and MCP server URL.

The credentials file contains the control-plane API key.

The files are created with private permissions.

**Do not commit these files to Git.**

---

## Step 4 - Configure OpenShell TLS

The project uses OpenShell Gateway with TLS and mTLS authentication.

Initialize the OpenShell TLS runtime state:

```bash
uv run mcpctl setup
```

Check the TLS state:

```bash
uv run mcpctl status
```

The TLS root is:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/local-mcp-server/openshell/tls
```

The expected structure is:

```text
openshell/tls/
├── ca.crt
├── server/
│   ├── tls.crt
│   └── tls.key
├── client/
│   ├── ca.crt
│   ├── tls.crt
│   └── tls.key
└── jwt/
    ├── signing.pem
    ├── public.pem
    └── kid
```

The MCP server receives the client mTLS material through the Compose mount:

```text
/config/openshell/gateways/local/mtls
```

The OpenShell CLI mTLS bundle is synchronized under:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/openshell/gateways/local/mtls
```

If the TLS state becomes incomplete or has incorrect permissions, repair it with:

```bash
uv run mcpctl repair
```

Check again:

```bash
uv run mcpctl status
```

The OpenShell Gateway is configured with:

```toml
disable_tls = false
```

and mTLS authentication is enabled.

Unauthenticated Gateway users are disabled.

**Do not expose the OpenShell Gateway directly to an untrusted network.**

---

# CLI Reference

The project exposes one host-side CLI entry point: `mcpctl`. Workspace authorization uses its `workspace` subcommands.

## mcpctl application and Compose commands

Run:

```bash
uv run mcpctl --help
```

The current top-level commands include:

```text
start
stop
restart
compose-status
logs
setup
status
repair
cleanup
uninstall
sandbox
credential
workspace
config
```

### Start the Compose stack

```bash
uv run mcpctl start
```

### Stop the Compose stack

```bash
uv run mcpctl stop
```

### Restart the Compose stack

```bash
uv run mcpctl restart
```

### Show Compose service status

```bash
uv run mcpctl compose-status
```

JSON output:

```bash
uv run mcpctl compose-status --json
```

### Show Compose logs

```bash
uv run mcpctl logs
```

Show one service:

```bash
uv run mcpctl logs mcp-server
```

Follow logs:

```bash
uv run mcpctl logs --follow
```

Follow one service:

```bash
uv run mcpctl logs --follow mcp-server
```

The service choices are:

```text
openshell-gateway
mcp-server
tunnel-client
```

---

## Cleanup and uninstall

Preview legacy profile cleanup without changing files:

```bash
uv run mcpctl uninstall
```

Remove only generated legacy profile configuration:

```bash
uv run mcpctl uninstall --yes
```

Preview a full purge of application-owned configuration and state:

```bash
uv run mcpctl uninstall --purge
```

To execute that purge, explicitly confirm it:

```bash
uv run mcpctl uninstall --yes --purge
```

The purge first prints a path-only inventory of the application roots, OpenAI MCP configuration and credentials, installation state, workspace-grant records, and application OpenShell TLS. Credential contents are never printed. When Docker is available, execution checks the Compose runtime and refuses to purge while services are running; stop the stack with `uv run mcpctl stop` and retry. The inventory is repeated at execution time, and the CLI verifies each application root is absent after deletion while reporting partial failures.

The purge removes the `local-mcp-server` directories under the configured XDG config and state roots. It does not delete host workspace files, Docker volumes, or the repository. The OpenShell CLI mTLS bundle under `openshell/gateways/local/mtls` is outside the application root and is preserved because it may be shared. Custom Compose paths outside the application roots are reported as outside scope and preserved; review them separately. Back up anything you may need before purging; this operation is destructive and is not reversible through the CLI.

## Sandbox commands

Run:

```bash
uv run mcpctl sandbox --help
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
restart
repair
delete
recreate
```

The `create` command supports:

```text
--profile default|browser
```

### List sandboxes

```bash
uv run mcpctl sandbox list
```

### Check a sandbox

```bash
uv run mcpctl sandbox status <sandbox-name>
```

JSON output:

```bash
uv run mcpctl sandbox status <sandbox-name> --json
```

### Create a default sandbox

```bash
uv run mcpctl sandbox create \
  <sandbox-name> \
  --workspace <workspace-id>
```

### Create a browser sandbox

```bash
uv run mcpctl sandbox create \
  <sandbox-name> \
  --workspace <workspace-id> \
  --profile browser
```

The default profile is used for normal development and command execution.

The `browser` profile selects:

```text
local-mcp-browser-sandbox:1.0.0
```

and starts the browser runtime inside the OpenShell sandbox.

### Open an interactive shell

```bash
uv run mcpctl sandbox shell <sandbox-name>
```

### Execute a command

```bash
uv run mcpctl sandbox exec <sandbox-name> -- \
  sh -lc 'echo "OpenShell sandbox is working"'
```

### Show sandbox logs

```bash
uv run mcpctl sandbox logs <sandbox-name>
```

### Start a sandbox

```bash
uv run mcpctl sandbox start <sandbox-name>
```

Start is used for a stopped sandbox or a retained failed sandbox.

### Stop a sandbox

```bash
uv run mcpctl sandbox stop <sandbox-name>
```

Stop retains the sandbox record and workspace association.

### Restart a sandbox

```bash
uv run mcpctl sandbox restart <sandbox-name>
```

Restart is implemented as:

```text
stop
  ↓
start
```

There is no separate custom OpenShell restart API used by the project.

### Repair a sandbox

```bash
uv run mcpctl sandbox repair <sandbox-name>
```

Repair retries OpenShell startup of the existing sandbox.

It does **not** delete and recreate the sandbox.

### Delete a sandbox

```bash
uv run mcpctl sandbox delete <sandbox-name>
```

Deletion permanently removes the OpenShell sandbox.

Deletion does not revoke the associated host workspace grant.

### Recreate a sandbox

```bash
uv run mcpctl sandbox recreate <sandbox-name> --yes
```

Recreate is destructive.

It:

```text
reads the current managed sandbox metadata
        ↓
retains the managed host workspace ID
        ↓
retains the sandbox profile
        ↓
deletes the existing sandbox
        ↓
creates a new sandbox with the same name
```

The `--yes` flag is required.

Recreate does not preserve runtime state from the deleted sandbox.

---

## Credential commands

Run:

```bash
uv run mcpctl credential --help
```

The current credential commands are:

```text
create
list
get
update
delete
grant
revoke
```

Credential operations are host-side OpenShell credential-provider operations.

Credential values are not returned through the CLI's normal inspection operations.

---

## OpenShell TLS CLI

Run:

```bash
uv run mcpctl --help
```

The current configuration commands are:

```text
setup
status
repair
sandbox
credential
workspace
config
```

### OpenShell TLS setup

```bash
uv run mcpctl setup
```

### OpenShell TLS status

```bash
uv run mcpctl status
```

### OpenShell TLS repair

```bash
uv run mcpctl repair
```

### Configure the OpenAI MCP client

```bash
uv run mcpctl config mcp-client openai
```

The command stores:

```text
OpenAI tunnel ID
OpenAI control-plane API key
OpenAI MCP server configuration
```

under the user-local XDG configuration directory.

Sandbox, credential, and workspace commands are available through `mcpctl`; shared service implementations remain internal to the package.

---

## Workspace commands

Workspace authorization is available through the trusted host-side `mcpctl workspace` commands.

Show workspace command help:

```bash
uv run mcpctl workspace --help
```

List all authorized host workspaces:

```bash
uv run mcpctl workspace list
```

List as JSON:

```bash
uv run mcpctl workspace list --json
```

Authorize a workspace:

```bash
uv run mcpctl workspace authorize <host-path>
```

Revoke a workspace:

```bash
uv run mcpctl workspace revoke <workspace-id>
```

The internal workspace broker implementation handles host path validation, protected path validation, workspace authorization, Docker volume creation, POSIX ACL provisioning/revocation, and the workspace grant registry. It is invoked by `mcpctl`; there is no separate `workspace-broker` executable.

---

# Step 5 - Build the Sandbox Images

The OpenShell Gateway uses two sandbox images:

```text
local-mcp-openshell-sandbox:1.0.0
local-mcp-browser-sandbox:1.0.0
```

The default image is used by the `default` profile.

The browser image is used by the `browser` profile.

---

## Build the default sandbox image

```bash
docker build \
  -t local-mcp-openshell-sandbox:1.0.0 \
  deploy/docker/openshell-sandbox
```

The default image contains:

```text
Python
Node.js
npm
Playwright
git
curl
wget
jq
ripgrep
OpenSSH client
procps
```

The image is based on the Playwright Python image and includes Node.js/npm tooling.

The OpenShell policy provides access to the authorized workspace and sandbox filesystem.

---

## Build the browser sandbox image

```bash
docker build \
  -t local-mcp-browser-sandbox:1.0.0 \
  deploy/docker/browser-sandbox
```

The browser image contains:

```text
Chrome for Testing
chrome-devtools-mcp
Chrome runtime dependencies
OpenShell Sandbox CA trust support
```

The browser sandbox runs as:

```text
UID 10001
GID 10001
```

Chrome runs inside the browser sandbox.

The browser CDP endpoint is fixed to:

```text
http://127.0.0.1:9222
```

The caller cannot override the browser connection endpoint.

The `execute_chrome_devtools_command` tool rejects Chrome connection override arguments.

---

# Step 6 - Build the Workspace ACL Helper

Build the trusted host-side ACL helper:

```bash
docker build \
  -t local-mcp-workspace-acl-helper:1.0.0 \
  deploy/docker/workspace-acl-helper
```

The helper is used by the internal workspace broker implementation invoked through `mcpctl workspace` during authorization and revocation.

It does not provide a general-purpose shell or network access.

Its purpose is limited to managing the broker-controlled POSIX ACL entries for the OpenShell sandbox UID.

---

# Step 7 - Start the MCP Server, OpenShell Gateway, and Tunnel

Start the default deployment:

```bash
docker compose \
  -f deploy/compose.yaml \
  up -d --remove-orphans
```

The default command automatically uses:

```text
deploy/.env
```

when that file exists.

The `--remove-orphans` option is intentional.

It removes containers belonging to services that were previously defined in the Compose file but have since been removed.

For the development environment:

```bash
docker compose \
  --env-file deploy/.env.development \
  -f deploy/compose.yaml \
  up -d --remove-orphans
```

For the production environment:

```bash
docker compose \
  --env-file deploy/.env.production \
  -f deploy/compose.yaml \
  up -d --remove-orphans
```

Check the service status:

```bash
docker compose \
  -f deploy/compose.yaml \
  ps
```

The expected application services are:

```text
openshell-gateway
mcp-server
tunnel-client
```

Browser and default OpenShell sandboxes are created and managed separately by OpenShell and do not appear as Compose application services.

---

# Step 8 - Check the MCP Server

Check the MCP server logs:

```bash
docker compose \
  -f deploy/compose.yaml \
  logs --tail=200 mcp-server
```

The MCP server listens inside the container on:

```text
0.0.0.0:8000
```

The MCP endpoint is:

```text
http://mcp-server:8000/mcp
```

The health endpoint is:

```text
http://mcp-server:8000/healthz
```

The Compose healthcheck calls:

```text
http://127.0.0.1:8000/healthz
```

inside the MCP container.

Check the service status:

```bash
docker compose \
  -f deploy/compose.yaml \
  ps
```

The `mcp-server` service should report healthy.

The MCP server is not intended to be directly exposed to the public Internet.

---

# Step 9 - Check the OpenShell Gateway

Check the Gateway logs:

```bash
docker compose \
  -f deploy/compose.yaml \
  logs --tail=200 openshell-gateway
```

The Gateway uses:

```text
compute driver: docker
```

The Gateway configuration is:

```text
deploy/openshell/gateway.toml
```

The Gateway listens on:

```text
127.0.0.1:8080
```

The Gateway health listener is:

```text
127.0.0.1:8081
```

The Gateway uses TLS:

```toml
disable_tls = false
```

and mTLS authentication:

```toml
[openshell.gateway.mtls_auth]
enabled = true
```

Unauthenticated users are disabled:

```toml
[openshell.gateway.auth]
allow_unauthenticated_users = false
```

The MCP server communicates with the Gateway through the private Docker network using mTLS.

The Gateway receives the Docker socket:

```text
/var/run/docker.sock
```

The MCP server does not receive the Docker socket.

---

# Step 10 - Check the Tunnel

Follow the tunnel logs:

```bash
docker compose \
  -f deploy/compose.yaml \
  logs -f tunnel-client
```

The tunnel client uses:

```text
/etc/tunnel-client/openai.yaml
```

inside the container.

The configuration is mounted from the user-local OpenAI MCP client configuration:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/local-mcp-server/mcp-clients/openai/config.yaml
```

The control-plane API key is supplied separately as the Docker secret:

```text
CONTROL_PLANE_API_KEY
```

The tunnel client should initialize the MCP connection and start the tunnel successfully.

The exact log wording may vary between tunnel-client versions.

Do not depend on a specific emoji or exact startup message.

---

# Connect the Tunnel to ChatGPT

## Step 11 - Create or Configure the MCP Connection

Open ChatGPT and configure the MCP connection using the existing OpenAI Secure MCP Tunnel.

Select:

```text
Tunnel
```

as the connection type.

Select the tunnel created earlier.

Complete the connection.

The MCP server endpoint used by the tunnel client is:

```text
http://mcp-server:8000/mcp
```

The MCP server is reached by the tunnel client over the private Docker network.

---

# Verify the MCP Tools

## Step 12 - Check the Available Tools

The current MCP server registers the following tools:

```text
get_system_info

create_sandbox
list_sandboxes
sandbox_status
sandbox_logs
start_sandbox
stop_sandbox
restart_sandbox
repair_sandbox
recreate_sandbox
delete_sandbox
execute_sandbox_command

list_workspace_files
read_workspace_text_file
create_workspace_file
write_workspace_file
create_workspace_directory
rename_workspace_path
delete_workspace_file
delete_workspace_directory
list_authorized_host_workspaces

request_tool_installation

execute_chrome_devtools_command
```

The sandbox lifecycle tools are:

```text
create_sandbox
list_sandboxes
sandbox_status
sandbox_logs
start_sandbox
stop_sandbox
restart_sandbox
repair_sandbox
recreate_sandbox
delete_sandbox
```

The sandbox execution tool is:

```text
execute_sandbox_command
```

Workspace operations are constrained to the authorized workspace mounted at:

```text
/workspace/project
```

The installation tool provides controlled installation of approved development tools inside the selected sandbox.

The browser tool is:

```text
execute_chrome_devtools_command
```

It only operates against a sandbox using the `browser` profile.

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

## Step 13 - Authorize a Host Workspace

First authorize a host workspace:

```bash
uv run mcpctl workspace authorize "$HOME/path/to/workspace"
```

Record the returned:

```text
workspace_id
```

The workspace ID has the form:

```text
ws_<identifier>
```

The workspace ID is an opaque authorization capability.

The sandbox creation API does not accept arbitrary host filesystem paths.

---

## Step 14 - Create a Sandbox

Create a default sandbox:

```bash
uv run mcpctl sandbox create \
  <sandbox-name> \
  --workspace <workspace-id>
```

For browser automation:

```bash
uv run mcpctl sandbox create \
  <sandbox-name> \
  --workspace <workspace-id> \
  --profile browser
```

Or use the MCP tool:

```text
create_sandbox
```

The MCP tool accepts:

```text
name
host_workspace_id
profile
```

The supported profiles are:

```text
default
browser
```

---

## Step 15 - Check Sandbox Status

Use:

```bash
uv run mcpctl sandbox status <sandbox-name>
```

or:

```text
sandbox_status
```

The status includes information such as:

```text
sandbox name
OpenShell workspace
phase/status
profile
host workspace ID
sandbox ID
```

The exact numeric OpenShell phase/status values are implementation details and should not be hard-coded into operational documentation.

---

## Step 16 - Start, Stop, Restart, or Repair a Sandbox

Start a stopped or retained failed sandbox:

```bash
uv run mcpctl sandbox start <sandbox-name>
```

or:

```text
start_sandbox
```

Stop a running sandbox:

```bash
uv run mcpctl sandbox stop <sandbox-name>
```

or:

```text
stop_sandbox
```

Restart a sandbox:

```bash
uv run mcpctl sandbox restart <sandbox-name>
```

or:

```text
restart_sandbox
```

Restart performs:

```text
stop
↓
start
```

Repair a retained failed sandbox:

```bash
uv run mcpctl sandbox repair <sandbox-name>
```

or:

```text
repair_sandbox
```

Repair performs a fresh OpenShell `start` operation against the existing sandbox.

It does not delete or recreate the sandbox.

---

## Step 17 - Execute a Command in the Sandbox

Use:

```bash
uv run mcpctl sandbox exec <sandbox-name> -- \
  sh -lc 'echo "OpenShell sandbox is working"'
```

or the MCP tool:

```text
execute_sandbox_command
```

The command must execute inside the OpenShell sandbox rather than directly on the MCP server host.

The sandbox command path is separate from the controlled installation workflow.

---

## Step 18 - Verify Host/Sandbox Workspace Editing

The authorized workspace uses POSIX ACLs so that the host user and sandbox user can both modify workspace content.

A useful test is:

```text
Sandbox creates file
       ↓
Host edits file
       ↓
Sandbox reads/edits file
       ↓
Sandbox is stopped or deleted
       ↓
Workspace grant remains separate
```

The workspace broker provisions default ACLs on directories so newly created files and directories remain accessible to the host user.

The sandbox sees the authorized workspace at:

```text
/workspace/project
```

The sandbox does not receive an arbitrary host filesystem path from the MCP caller.

---

## Step 19 - Browser Sandbox Verification

Create a browser sandbox:

```bash
uv run mcpctl sandbox create \
  browser-test \
  --workspace <workspace-id> \
  --profile browser
```

Check its status:

```bash
uv run mcpctl sandbox status browser-test
```

Use:

```text
execute_chrome_devtools_command
```

for Chrome DevTools operations.

The browser runtime uses:

```text
Chrome for Testing
chrome-devtools-mcp
```

The browser endpoint is fixed to:

```text
http://127.0.0.1:9222
```

The caller cannot provide or override the browser endpoint.

Chrome DevTools lifecycle commands such as:

```text
start
stop
status
```

are intentionally not exposed through `execute_chrome_devtools_command`.

Browser lifecycle is controlled by the OpenShell browser sandbox lifecycle.

---

## Step 20 - Controlled Tool Installation

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

The installation request contains:

```text
sandbox_name
tool_name
version
source
install_command
reason
```

The server validates the installation request before executing it.

The installation command is executed inside the selected OpenShell sandbox.

The host filesystem is not used as the installation target.

Browser runtime dependencies are baked into the browser image rather than installed dynamically through this mechanism.

---

## Step 21 - Delete the Sandbox

After testing:

```bash
uv run mcpctl sandbox delete <sandbox-name>
```

or use:

```text
delete_sandbox
```

Sandbox deletion is destructive and requires explicit confirmation when performed through the MCP tool.

Deleting the OpenShell sandbox removes its sandbox runtime.

For a browser sandbox, this also removes the Chrome and Chrome DevTools MCP runtime associated with that sandbox.

Deleting a sandbox does **not** automatically revoke the host workspace grant.

---

## Step 22 - Recreate a Sandbox

When a sandbox needs a fresh runtime while retaining its managed workspace capability and profile:

```bash
uv run mcpctl sandbox recreate <sandbox-name> --yes
```

The MCP tool:

```text
recreate_sandbox
```

requires explicit user approval.

Recreation performs:

```text
inspect current sandbox
        ↓
retain host workspace ID
        ↓
retain profile
        ↓
delete sandbox
        ↓
create sandbox again
```

The following are not preserved:

```text
running processes
runtime state
instance-specific state
static instance state
```

Recreation is a destructive operation.

---

## Step 23 - Revoke the Workspace

After the sandbox has been deleted:

```bash
uv run mcpctl workspace revoke <workspace-id>
```

Then verify:

```bash
uv run mcpctl workspace list
```

The revoked workspace should no longer appear.

Workspace revocation removes:

```text
sandbox UID ACL entries
host-backed Docker volume
workspace grant record
```

The workspace broker performs the ACL removal through the constrained helper container.

---

# Update MCP Server Tools

When MCP server code or tool definitions change, rebuild the MCP server image and recreate the MCP server container.

The Compose file is:

```text
deploy/compose.yaml
```

The default environment file is:

```text
deploy/.env
```

Normal commands therefore do not require:

```text
--env-file .env
```

## 1. Rebuild the MCP server image

```bash
docker compose \
  -f deploy/compose.yaml \
  build --no-cache mcp-server
```

## 2. Recreate the MCP server

For MCP server code or tool-definition changes:

```bash
docker compose \
  -f deploy/compose.yaml \
  up -d --force-recreate --remove-orphans mcp-server
```

Recreate `openshell-gateway` only when its configuration or image has changed:

```bash
docker compose \
  -f deploy/compose.yaml \
  up -d --force-recreate --remove-orphans openshell-gateway
```

Recreate `tunnel-client` only when its configuration or image has changed:

```bash
docker compose \
  -f deploy/compose.yaml \
  up -d --force-recreate --remove-orphans tunnel-client
```

For the development environment, add:

```text
--env-file deploy/.env.development
```

before:

```text
-f deploy/compose.yaml
```

For example:

```bash
docker compose \
  --env-file deploy/.env.development \
  -f deploy/compose.yaml \
  up -d --force-recreate --remove-orphans mcp-server
```

---

## 3. Check the service status

```bash
docker compose \
  -f deploy/compose.yaml \
  ps
```

Expected services:

```text
openshell-gateway
mcp-server
tunnel-client
```

---

## 4. Check the MCP server logs

```bash
docker compose \
  -f deploy/compose.yaml \
  logs --tail=200 mcp-server
```

Or:

```bash
docker compose \
  -f deploy/compose.yaml \
  logs -f mcp-server
```

---

## 5. Check the OpenShell Gateway logs

```bash
docker compose \
  -f deploy/compose.yaml \
  logs --tail=200 openshell-gateway
```

---

## 6. Check the tunnel client

```bash
docker compose \
  -f deploy/compose.yaml \
  logs --tail=100 tunnel-client
```

Or:

```bash
docker compose \
  -f deploy/compose.yaml \
  logs -f tunnel-client
```

---

## 7. Verify Compose environment loading

```bash
docker compose \
  -f deploy/compose.yaml \
  config --environment
```

For a specific value:

```bash
docker compose \
  -f deploy/compose.yaml \
  config --environment | grep '^OPENSHELL_WORKSPACE='
```

The default environment is loaded from:

```text
deploy/.env
```

For development:

```bash
docker compose \
  --env-file deploy/.env.development \
  -f deploy/compose.yaml \
  config --environment
```

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

The current MCP endpoint is:

```text
http://mcp-server:8000/mcp
```

---

# If Refresh Does Not Show the New Tool

Do not immediately create a new API key or OpenAI tunnel.

First:

1. Confirm the MCP server is healthy.
2. Confirm the expected tool is registered by the MCP server.
3. Confirm the tunnel client is running.
4. Refresh the MCP app/connector.
5. If necessary, delete only the MCP app/connector.
6. Create the MCP app/connector again.
7. Select the **same existing tunnel**.
8. Check the tool list again.

Preferred workflow:

```text
Change MCP code
      ↓
Rebuild MCP server
      ↓
Recreate MCP server
      ↓
Check MCP logs
      ↓
Check tunnel-client
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
uv run mcpctl workspace list
```

List as JSON:

```bash
uv run mcpctl workspace list --json
```

Authorize a workspace:

```bash
uv run mcpctl workspace authorize "$HOME/path/to/workspace"
```

Revoke a workspace:

```bash
uv run mcpctl workspace revoke <workspace-id>
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

The current writable workspace grant uses:

```text
/workspace/project
```

The sandbox UID/GID is:

```text
10001:10001
```

The broker provisions ACLs for:

```text
host user
sandbox UID 10001
```

Directories also receive default ACLs so newly created content inherits the required access.

Protected project paths are excluded from sandbox workspace authorization.

---

# Handling Old Orphan Containers

If Compose reports:

```text
Found orphan containers
```

for example containers from older services such as:

```text
terminal-executor
browser-runtime
cdp-relay
```

the service may belong to an older version of the Compose configuration.

Remove obsolete services with:

```bash
docker compose \
  -f deploy/compose.yaml \
  up -d --remove-orphans
```

Then verify:

```bash
docker compose \
  -f deploy/compose.yaml \
  ps
```

The current Compose deployment should contain:

```text
openshell-gateway
mcp-server
tunnel-client
```

OpenShell sandbox containers are not Compose services and should not be expected in this list.

---

# Current MCP Tools

The current MCP server provides:

```text
get_system_info

create_sandbox
list_sandboxes
sandbox_status
sandbox_logs
start_sandbox
stop_sandbox
restart_sandbox
repair_sandbox
recreate_sandbox
delete_sandbox
execute_sandbox_command

list_workspace_files
read_workspace_text_file
create_workspace_file
write_workspace_file
create_workspace_directory
rename_workspace_path
delete_workspace_file
delete_workspace_directory
list_authorized_host_workspaces

request_tool_installation

execute_chrome_devtools_command
```

Sandbox lifecycle is performed through OpenShell.

Workspace operations are constrained to the authorized workspace mounted at:

```text
/workspace/project
```

Tool installation is performed through the controlled installation workflow inside the authorized sandbox.

Browser automation is performed through the browser sandbox and:

```text
execute_chrome_devtools_command
```

The browser connection endpoint is fixed to:

```text
http://127.0.0.1:9222
```

and cannot be overridden by the caller.

---

# Current Deployment Configuration

The main deployment files are:

```text
deploy/
├── compose.yaml
├── .env.example
├── .env.development.example
├── .env.production.example
├── openshell/
│   ├── gateway.toml
│   └── gateway-metadata.json
└── docker/
    ├── mcp-server/
    ├── openshell-sandbox/
    ├── browser-sandbox/
    └── workspace-acl-helper/
```

The default environment file is:

```text
deploy/.env
```

The development environment file is:

```text
deploy/.env.development
```

The production environment file is:

```text
deploy/.env.production
```

These local files are deployment configuration and should not contain secret API keys.

---

# Current Runtime Versions

The Python project requires:

```text
Python >=3.14,<3.15
```

The current project dependencies include:

```text
MCP Python SDK: mcp[cli]==2.2.0
OpenShell Python SDK: openshell==0.1.2
argcomplete: 3.7.2
```

The OpenAI tunnel client is:

```text
ghcr.io/openai/tunnel-client:v0.0.15
```

The OpenShell Gateway image is configured as:

```text
ghcr.io/nvidia/openshell/gateway:${OPENSHELL_IMAGE_TAG:-latest}
```

The default OpenShell sandbox image is:

```text
local-mcp-openshell-sandbox:1.0.0
```

The browser sandbox image is:

```text
local-mcp-browser-sandbox:1.0.0
```

The workspace ACL helper image is:

```text
local-mcp-workspace-acl-helper:1.0.0
```

---

# Security Notes

The current deployment uses TLS and mTLS for communication between the MCP server and OpenShell Gateway.

The Gateway is bound to local host interfaces and should not be exposed directly to an untrusted network.

The deployment uses:

```text
TLS
mTLS authentication
unauthenticated Gateway users disabled
read-only MCP container filesystem
no-new-privileges
capability drop
internal Docker networks
workspace boundary controls
POSIX ACLs
OpenShell sandbox isolation
OpenShell browser policy isolation
fixed sandbox-local Chrome CDP endpoint
blocked caller-controlled Chrome connection overrides
controlled tool installation
Docker secret delivery for the tunnel API key
```

The Gateway is the only Compose service that receives:

```text
/var/run/docker.sock
```

The MCP server does not receive the Docker socket.

The browser sandbox does not expose a separate host-side browser runtime or CDP relay.

Chrome runs inside the OpenShell browser sandbox.

The browser endpoint is fixed to:

```text
http://127.0.0.1:9222
```

The `execute_chrome_devtools_command` implementation blocks caller-supplied browser connection overrides.

The OpenShell Gateway uses:

```text
server certificate
server private key
client CA
client certificates
JWT signing material
```

from the XDG OpenShell TLS state directory.

The host-side TLS root is:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/local-mcp-server/openshell/tls
```

The MCP server receives only the client mTLS material required for its Gateway connection.

The OpenAI MCP client configuration is stored under:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/local-mcp-server/mcp-clients/openai/
```

The control-plane API key is stored in:

```text
${XDG_CONFIG_HOME:-$HOME/.config}/local-mcp-server/mcp-clients/openai/credentials
```

and supplied to `tunnel-client` through the Docker Compose secret:

```text
CONTROL_PLANE_API_KEY
```

Do not commit:

```text
deploy/.env
deploy/.env.development
deploy/.env.production
OpenAI credentials
TLS private keys
TLS client keys
TLS server keys
JWT signing keys
OpenShell credential encryption keys
```

Do not put the OpenAI API key in:

```text
compose.yaml
Dockerfile
README.md
tracked source files
```

The OpenAI tunnel ID is configuration data and is stored in the user-local OpenAI MCP client configuration rather than as a Docker Compose secret.

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
   ├── OpenShell default sandboxes
   │      ├── Python
   │      ├── Node.js / npm
   │      ├── Playwright
   │      ├── Git
   │      └── authorized workspace
   │
   └── OpenShell browser sandboxes
          ├── Chrome for Testing
          ├── Chrome DevTools MCP
          ├── sandbox-local CDP :9222
          └── authorized workspace
```

Host workspace lifecycle:

```text
Host directory
      │
      ▼
mcpctl workspace authorize
      │
      ├── validate host path
      ├── POSIX ACL provisioning
      ├── Docker volume
      └── workspace grant
              │
              ▼
       OpenShell sandbox
              │
              ▼
       /workspace/project
              │
              ▼
mcpctl workspace revoke
              │
              ▼
workspace-acl-helper
              │
              ▼
       ACL removal
```

Sandbox lifecycle:

```text
create
  │
  ▼
OpenShell sandbox
  │
  ├── start
  ├── stop
  ├── restart
  ├── repair
  ├── recreate
  └── delete
```

The project no longer uses a separate:

```text
terminal-executor
browser-runtime
CDP relay
```

Compose service.

The MCP server exposes sandbox operations through OpenShell, workspace operations through authorized workspace boundaries, controlled tool installation through the sandbox installation workflow, and browser automation through the isolated browser sandbox.

The trusted host-side workspace broker remains separate from the MCP server and is responsible for host filesystem authorization, Docker volume provisioning, and POSIX ACL lifecycle.

---

# Workspace CLI Output

The workspace CLI keeps its default output focused on user-relevant fields:

```bash
mcpctl workspace list
mcpctl workspace list --json
```

The public workspace schema contains `id`, `host_path`, `sandbox_path`, and `read_only`. Use `--verbose` when debugging or inspecting host-side infrastructure details:

```bash
mcpctl workspace list --verbose
mcpctl workspace list --verbose --json
```

Verbose output includes internal identifiers and infrastructure metadata such as host UID/GID and Docker volume name. Treat this output as operational detail and avoid sharing it unnecessarily.
