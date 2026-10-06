# Project Command Reference

This document contains the commands relevant to this repository.

It is a reference manual, not an execution sequence. Choose the commands you need for the task you are performing.

> Run commands from the repository root unless otherwise stated.

---

## 1. Docker

### Check Docker installation

```bash
docker --version
docker compose version
````

### Build the MCP server image

```bash
docker compose build mcp-server
```

### Build the OpenShell sandbox image

```bash
docker build \
  -f docker/openshell-sandbox/Dockerfile \
  -t local-mcp-openshell-sandbox:1.0.0 \
  .
```

### Build all project images

```bash
docker compose build
```

### Inspect the Compose configuration

```bash
docker compose config
```

### Start the project

```bash
docker compose up -d
```

### Start and show logs

```bash
docker compose up
```

### View service status

```bash
docker compose ps
```

### View logs

```bash
docker compose logs
```

### View logs for one service

```bash
docker compose logs mcp-server
docker compose logs openshell-gateway
docker compose logs tunnel-client
```

### Follow logs

```bash
docker compose logs -f
```

### Follow logs for one service

```bash
docker compose logs -f mcp-server
```

### Restart a service

```bash
docker compose restart mcp-server
```

### Stop the project

```bash
docker compose stop
```

### Stop and remove project containers

```bash
docker compose down
```

### Stop and remove containers, networks, and volumes created by Compose

```bash
docker compose down -v
```

> Use the `-v` form only when you intentionally want to remove Compose-managed volumes.

### Show running containers

```bash
docker ps
```

### Show all containers

```bash
docker ps -a
```

### Inspect a container

```bash
docker inspect <container>
```

### Open a shell inside the MCP container

```bash
docker compose exec mcp-server sh
```

### Open a shell inside the OpenShell Gateway container

```bash
docker compose exec openshell-gateway sh
```

---

## 2. Python

### Check Python version

```bash
python --version
```

The project requires:

```text
Python >=3.14,<3.15
```

### Check the Python executable

```bash
python -c "import sys; print(sys.executable); print(sys.version)"
```

### Create a virtual environment

```bash
python -m venv .venv
```

### Activate the virtual environment — Linux/macOS

```bash
source .venv/bin/activate
```

### Activate the virtual environment — Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

### Check installed packages

```bash
python -m pip list
```

---

## 3. uv

### Check uv

```bash
uv --version
```

### Install dependencies from the lockfile

```bash
uv sync --locked
```

### Install dependencies and development dependencies

```bash
uv sync --locked --all-groups
```

### Run the application

```bash
uv run python -m local_mcp_server
```

### Run Python through the project environment

```bash
uv run python
```

### Run pytest

```bash
uv run pytest
```

### Run pytest with verbose output

```bash
uv run pytest -v
```

### Run Ruff linting

```bash
uv run ruff check .
```

### Run Ruff formatting check

```bash
uv run ruff format --check .
```

### Format the project with Ruff

```bash
uv run ruff format .
```

### Regenerate the lockfile

```bash
uv lock
```

> `uv.lock` is committed to the repository. Regenerate it only when intentionally changing dependency resolution.

### Verify that the lockfile is already up to date

```bash
uv lock --check
```

---

## 4. Git

### Check repository status

```bash
git status
```

### Show changed files

```bash
git status --short
```

### Show unstaged changes

```bash
git diff
```

### Show a specific file's changes

```bash
git diff -- <path>
```

### Show staged changes

```bash
git diff --cached
```

### Show recent commits

```bash
git log --oneline --decorate -10
```

### Show the current branch

```bash
git branch --show-current
```

### Show all branches

```bash
git branch -a
```

### Add a specific file

```bash
git add <path>
```

### Add all changes

```bash
git add .
```

### Commit changes

```bash
git commit -m "<message>"
```

### Show the current commit

```bash
git rev-parse HEAD
```

### Show files tracked by Git

```bash
git ls-files
```

---

## 5. OpenShell

The project uses OpenShell as the sandbox runtime.

The intended version alignment is:

```text
OpenShell Python SDK   0.1.1
OpenShell Gateway      v0.1.1
OpenShell Supervisor   v0.1.1
```

### Check the OpenShell CLI

```bash
openshell --version
```

### Check available OpenShell commands

```bash
openshell --help
```

### Check Gateway health

The Gateway health endpoint is bound to localhost port `8081`.

```bash
curl http://127.0.0.1:8081/healthz
```

### Check the Gateway HTTP endpoint

```bash
curl http://127.0.0.1:8080
```

The Gateway's normal API is not intended to be a public HTTP service.

### Inspect Gateway logs

```bash
docker compose logs openshell-gateway
```

### Follow Gateway logs

```bash
docker compose logs -f openshell-gateway
```

### Inspect the Gateway configuration inside the container

```bash
docker compose exec openshell-gateway cat /etc/openshell/gateway.toml
```

### Inspect the Gateway persistent data

```bash
docker compose exec openshell-gateway ls -la /var/lib/openshell
```

---

## 6. OpenShell Sandbox Operations

The MCP server exposes sandbox operations through the application.

The supported operations are:

```text
create_sandbox
list_sandboxes
sandbox_status
execute_sandbox_command
delete_sandbox
```

Sandbox resource defaults are controlled through:

```dotenv
SANDBOX_DEFAULT_CPU=1
SANDBOX_DEFAULT_MEMORY=1Gi
```

The sandbox image is controlled through:

```dotenv
SANDBOX_IMAGE=local-mcp-openshell-sandbox:1.0.0
```

These values can be changed through the project's environment configuration.

---

### Package management CLI

Package configuration is stored under the effective `MCP_STATE_DIR`; when unset,
the default is `${XDG_STATE_HOME:-$HOME/.local/state}/local-mcp-server/mcp`.
The initial registry enables npm only, on the default sandbox profile's existing
npm registry network policy. Package creation does not implicitly install.

```bash
uv run mcpctl sandbox create my-sandbox --standalone --packages npm
uv run mcpctl sandbox packages list my-sandbox
uv run mcpctl sandbox packages add my-sandbox express@^5 --ecosystem npm
uv run mcpctl sandbox packages remove my-sandbox express --ecosystem npm
uv run mcpctl sandbox packages lock my-sandbox --ecosystem npm
uv run mcpctl sandbox packages install my-sandbox --ecosystem npm --yes
uv run mcpctl sandbox packages show my-sandbox
uv run mcpctl sandbox packages reset my-sandbox --ecosystem npm --yes
uv run mcpctl runtime show
uv run mcpctl sandbox delete my-sandbox --yes
uv run mcpctl sandbox delete my-sandbox --yes --purge-packages
```

Deletion preserves manifests and lockfiles by default. `--purge-packages` removes
only registered ecosystem package state; unregistered entries are preserved.
npm resolution and installation disable lifecycle scripts. See
[package-management.md](package-management.md) for state semantics, security
constraints, and recovery guidance.

## 7. MCP Server

### Check the MCP server container

```bash
docker compose ps mcp-server
```

### View MCP server logs

```bash
docker compose logs mcp-server
```

### Follow MCP server logs

```bash
docker compose logs -f mcp-server
```

### Check the MCP health endpoint

```bash
curl http://127.0.0.1:8000/healthz
```

> Port `8000` is intentionally not published to the host by Compose. The command above is therefore normally useful from inside the container or another container on the appropriate network.

### Check the MCP endpoint from inside the container

```bash
docker compose exec mcp-server \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/healthz').read().decode())"
```

The MCP endpoint is:

```text
http://mcp-server:8000/mcp
```

It is consumed by the tunnel client over the private Docker network.

---

## 8. MCP Tunnel Client

### Check tunnel-client status

```bash
docker compose ps tunnel-client
```

### View tunnel-client logs

```bash
docker compose logs tunnel-client
```

### Follow tunnel-client logs

```bash
docker compose logs -f tunnel-client
```

The tunnel client connects to:

```text
http://mcp-server:8000/mcp
```

The tunnel ID is supplied through:

```dotenv
CONTROL_PLANE_TUNNEL_ID=<existing-tunnel-id>
```

The control-plane API key is supplied through the Docker secret:

```text
.secrets/control-plane-api-key
```

Do not place the API key in:

* `Dockerfile`
* `compose.yaml`
* `.env`
* `.env.example`
* Git-tracked source files

---

## 9. Environment Configuration

The project template is:

```text
.env.example
```

Relevant settings include:

```dotenv
CONTROL_PLANE_TUNNEL_ID=<existing-tunnel-id>

OPENSHELL_WORKSPACE=default

SANDBOX_IMAGE=local-mcp-openshell-sandbox:1.0.0
SANDBOX_DEFAULT_CPU=1
SANDBOX_DEFAULT_MEMORY=1Gi

OPENSHELL_IMAGE_TAG=v0.1.1
OPENSHELL_PORT=8080
OPENSHELL_HEALTH_PORT=8081
```

Do not commit private credentials.

The tunnel API key belongs in:

```text
.secrets/control-plane-api-key
```

---

## 10. Docker Image Inspection

### List local images

```bash
docker images
```

### Inspect the MCP image

```bash
docker image inspect <mcp-image>
```

### Inspect the sandbox image

```bash
docker image inspect local-mcp-openshell-sandbox:1.0.0
```

### Show image history

```bash
docker history <image>
```

### Remove an image

```bash
docker image rm <image>
```

> Remove images only when you intentionally want to delete them from the local Docker image store.

---

## 11. Docker Network Inspection

### List Docker networks

```bash
docker network ls
```

### Inspect the MCP network

```bash
docker network inspect <network>
```

### Inspect the Compose network

```bash
docker compose ps
```

The project uses separate networks for:

```text
mcp-internal
openshell-internal
tunnel-egress
```

The MCP server does not publish its HTTP port to the host.

---

## 12. Docker Resource Inspection

### Show container resource usage

```bash
docker stats
```

### Show resource usage for project containers

```bash
docker compose stats
```

### Inspect container limits

```bash
docker inspect <container>
```

OpenShell sandbox CPU and memory limits are configured at sandbox creation time rather than relying only on the MCP server container's limits.

---

## 13. File and Repository Inspection

### Show repository tree

```bash
find . -maxdepth 3 -type f | sort
```

### Find Python files

```bash
find . -type f -name "*.py" | sort
```

### Find Docker files

```bash
find . -type f \( -name "Dockerfile" -o -name "docker-compose*.yml" -o -name "compose.yaml" \) | sort
```

### Search for a string

```bash
grep -R "<text>" .
```

### Search Python source only

```bash
grep -R "<text>" src tests
```

---

## 14. MCP Inspector

If MCP Inspector is installed and available in the development environment, it can be used to inspect the MCP endpoint.

The project MCP endpoint is:

```text
http://127.0.0.1:8000/mcp
```

However, the Compose configuration intentionally does not publish port `8000` to the host.

When testing through the Docker network, use:

```text
http://mcp-server:8000/mcp
```

from a container that can access the `mcp-internal` network.

---

## 15. Health and Diagnostics

### Check all Compose services

```bash
docker compose ps
```

### Check all service logs

```bash
docker compose logs
```

### Check Gateway health

```bash
curl http://127.0.0.1:8081/healthz
```

### Check MCP container health

```bash
docker inspect --format='{{json .State.Health}}' $(docker compose ps -q mcp-server)
```

### Check Gateway container health

```bash
docker inspect --format='{{json .State.Health}}' $(docker compose ps -q openshell-gateway)
```

### Check tunnel-client logs

```bash
docker compose logs tunnel-client
```

---

## 16. Cleanup

### Stop the application

```bash
docker compose stop
```

### Remove application containers and networks

```bash
docker compose down
```

### Remove containers, networks, and Compose volumes

```bash
docker compose down -v
```

### Remove unused Docker resources

```bash
docker system prune
```

> Review Docker's confirmation prompt carefully. This can remove unused Docker resources beyond this project.

### Remove unused images as well

```bash
docker system prune -a
```

> This is more destructive. Use only when you intentionally want to clean unused Docker images.

---

## 17. Project-Specific Important Paths

```text
.
├── compose.yaml
├── pyproject.toml
├── uv.lock
├── .env.example
├── .secrets/
│   └── control-plane-api-key
├── docker/
│   ├── mcp-server/
│   │   └── Dockerfile
│   └── openshell-sandbox/
│       └── Dockerfile
├── openshell/
│   └── gateway.toml
├── src/
│   └── local_mcp_server/
├── tests/
└── docs/
```

---

## 18. Version Reference

The project currently targets:

```text
Python              >=3.14,<3.15
MCP Python SDK      2.2.0
OpenShell SDK       0.1.1
OpenShell Gateway   v0.1.1
OpenShell Supervisor v0.1.1
Tunnel client       v0.0.15
```

The OpenShell components should remain version-aligned.

---

## 19. Commands Not Intended for This Project

The following are intentionally not documented here because they are not part of this project's current architecture:

```text
Docker-in-Docker
Sysbox
Custom terminal-executor
Host terminal execution
Direct sandbox Docker socket access
Unrestricted dev-egress network
Manual OpenShell installation procedures unrelated to this repository
Kubernetes deployment commands
Podman deployment commands
MicroVM deployment commands
OpenShell development commands unrelated to the Docker deployment
```

This document intentionally focuses on the commands needed to work with this repository's Docker + Python + OpenShell + MCP + Secure MCP Tunnel implementation.

---

## 20. `mcpctl uninstall` — Scope and safety

The uninstall command has two distinct scopes. The default operation removes only
generated legacy profile configuration directories. It does not remove the central
application configuration or retained profile state.

Preview the default operation:

```bash
mcpctl uninstall
```

Execute the default operation:

```bash
mcpctl uninstall --yes
```

Preview removal of the application configuration and state roots:

```bash
mcpctl uninstall --purge
```

Execute the application-root purge:

```bash
mcpctl uninstall --yes --purge
```

The purge reports its preflight inventory, service check, removal results, and
post-removal verification separately. If Compose services are still running,
stop the application and retry:

```bash
mcpctl stop
mcpctl uninstall --yes --purge
```

The purge removes the standard application configuration and state roots under
the effective XDG configuration and state homes. It does not automatically
delete host workspace files, Docker volumes, the repository, the repository-local
CLI environment, or the external OpenShell CLI mTLS bundle.

Compose bind-mount overrides can point to paths outside those roots. The purge
reports supported path overrides for review but does not delete external paths.
Review the effective Compose configuration separately when custom env files,
relative bind mounts, or custom deployment paths are in use.

A successful application-root purge is not proof that OpenShell sandbox
containers, host ACL entries, external mounts, or other Docker resources have
been removed. These resources are intentionally not reported as cleaned up
unless their cleanup and verification are implemented explicitly.

Credential contents are never printed in the uninstall inventory. On partial
failure, inspect the exact failing path, ownership, permissions, and nested
mounts before retrying. Do not recursively change ownership or remove paths
that may contain shared or mounted data without first verifying their scope.
