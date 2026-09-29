# Python Local MCP Server — Dockerized Research-to-Runbook

## 1. Revised target architecture

```text
                         INTERNET
                            │
                            │ HTTPS outbound
                            ▼
                  ┌─────────────────────┐
                  │  OpenAI Secure MCP  │
                  │       Tunnel        │
                  └──────────┬──────────┘
                             │
                             │
                   ┌─────────▼─────────┐
                   │  tunnel-client    │
                   │   Docker container│
                   └─────────┬─────────┘
                             │
                    HTTP :8000
                    private network
                             │
                ┌────────────▼────────────┐
                │     mcp-server          │
                │   Docker container      │
                │                         │
                │ Python 3.14.7           │
                │ MCP SDK 2.2.0           │
                │ Streamable HTTP         │
                │                         │
                │  get_system_info()      │
                │  list_allowed_files()   │
                │  read_allowed_file()    │
                └────────────┬────────────┘
                             │
                      read-only mount
                             │
                             ▼
                       ./allowed_data
```

There is **no published MCP port to the Internet**.

The MCP container is reachable only from the private Docker network. The tunnel container has two jobs: reach the MCP container internally and reach OpenAI externally. OpenAI's tunnel documentation says the tunnel requires outbound HTTPS to `api.openai.com:443` and no inbound port for the tunnel itself. ([GitHub][2])

---

# 2. Why Docker changes the design

Previously, stdio was the natural choice:

```text
tunnel-client
      │
      └── launches server.py
```

That works extremely well when both processes live on the same host.

Once we deliberately separate them into containers, this is cleaner:

```text
tunnel-client container
      │
      │ HTTP
      ▼
MCP server container
```

The current MCP Python SDK explicitly describes:

* **stdio** → local subprocess
* **Streamable HTTP** → a real HTTP server you deploy

and says SSE is the older transport and should not be used for new implementations. ([GitHub][1])

OpenAI's tunnel-client also officially supports:

```text
MCP_SERVER_URL
```

for Streamable HTTP and:

```text
MCP_COMMAND
```

for stdio. ([GitHub][3])

For Docker, `MCP_SERVER_URL=http://mcp-server:8000/mcp` gives us clean process/container separation without exposing a host port.

---

# 3. Research findings

| Finding ID | Area                   | Finding                                                                                                                                    | Why It Matters                                                                                | Version / Date                         | Implementation Impact                                            | Source / Standard                                                  |
| ---------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- | -------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------ |
| **F-001**  | MCP                    | Current stable MCP specification is **2026-07-28**.                                                                                        | Avoid implementing against obsolete protocol assumptions.                                     | 2026-07-28                             | Target current MCP behavior.                                     | MCP official release/spec ([Model Context Protocol Blog][4])       |
| **F-002**  | MCP protocol           | MCP uses **JSON-RPC 2.0** messaging.                                                                                                       | The application should use the SDK instead of implementing protocol framing manually.         | Current                                | SDK handles MCP wire protocol.                                   | MCP specification                                                  |
| **F-003**  | MCP transport          | **stdio** is intended for a client-launched local subprocess.                                                                              | Good for same-process-boundary deployments.                                                   | Current                                | Not our primary Docker-to-Docker transport.                      | MCP Python SDK ([GitHub][1])                                       |
| **F-004**  | MCP transport          | **Streamable HTTP** is the current HTTP transport; SSE is superseded for new deployments.                                                  | Docker containers naturally communicate over private HTTP.                                    | Current                                | Use Streamable HTTP.                                             | MCP Python SDK ([GitHub][1])                                       |
| **F-005**  | MCP SDK                | Official Python SDK **v2.2.0** is current.                                                                                                 | v1 tutorials/API can be misleading.                                                           | Sep. 7, 2026                           | Use `MCPServer`.                                                 | Official SDK release ([GitHub][5])                                 |
| **F-006**  | MCP SDK                | Python SDK requires Python **3.10+** and publishes for Python 3.14.                                                                        | Python 3.14 is supported.                                                                     | Current                                | Use Python 3.14.7.                                               | Official SDK/PyPI ([PyPI][6])                                      |
| **F-007**  | Python                 | Python **3.14.7** is the current stable 3.14 maintenance release.                                                                          | Provides a current supported interpreter.                                                     | Aug. 5, 2026                           | Use 3.14.7 in the image.                                         | Python.org ([Python.org][7])                                       |
| **F-008**  | Python tooling         | uv is the recommended modern project/dependency manager for this implementation.                                                           | Simplifies lockfile-based Docker builds.                                                      | Current                                | Use uv inside build stages.                                      | uv Docker guide ([Astral Docs][8])                                 |
| **F-009**  | Dependencies           | `uv.lock` should be used as the source of truth for reproducible dependency installation.                                                  | Prevents Docker builds from silently changing dependencies.                                   | Current                                | Build with `uv sync --locked`.                                   | uv CLI/Docker docs ([Astral Docs][8])                              |
| **F-010**  | Docker                 | Docker recommends trusted/minimal base images and separate build/runtime stages.                                                           | Reduces final image size and attack surface.                                                  | Current                                | Multi-stage Dockerfile.                                          | Docker build best practices ([Docker Documentation][9])            |
| **F-011**  | Docker                 | Docker recommends pinning base image versions; digests provide stronger reproducibility.                                                   | Mutable image tags otherwise change underneath builds.                                        | Current                                | Start with exact patch tags; pin digest for controlled releases. | Docker best practices ([Docker Documentation][9])                  |
| **F-012**  | Docker                 | `RUN --mount=type=cache` supports build-time package caches without baking them into image layers.                                         | Faster secure builds.                                                                         | Current                                | Cache uv downloads.                                              | Dockerfile reference ([Docker Documentation][10])                  |
| **F-013**  | Docker secrets         | Build secrets should use BuildKit secret mounts rather than build arguments.                                                               | Prevents secret values from being persisted/leaked in layers or provenance.                   | Current                                | Never put credentials in Docker build args.                      | Dockerfile reference ([Docker Documentation][10])                  |
| **F-014**  | Container runtime      | Containers should run as an unprivileged user.                                                                                             | Limits impact of application compromise.                                                      | Current                                | `USER` non-root.                                                 | Docker + OWASP ([Docker Documentation][9])                         |
| **F-015**  | Container runtime      | `read_only`, capability dropping, and `no-new-privileges` are supported hardening controls.                                                | Reduces runtime attack surface.                                                               | Current                                | Apply to both containers where compatible.                       | Docker Compose + OWASP ([Docker Documentation][11])                |
| **F-016**  | Container networking   | Docker supports isolated Compose networks and service-to-service networking.                                                               | MCP server can stay private without publishing a host port.                                   | Current                                | Use an internal MCP network.                                     | Docker Compose ([Docker Documentation][11])                        |
| **F-017**  | OpenAI                 | Secure MCP Tunnel requires outbound HTTPS to `api.openai.com:443`; the tunnel itself requires no inbound host port.                        | No public MCP endpoint is necessary.                                                          | Current                                | Tunnel container gets egress only.                               | OpenAI tunnel docs ([GitHub][2])                                   |
| **F-018**  | OpenAI                 | Official tunnel-client provides a Docker image and supports Docker Compose.                                                                | No need to build tunnel-client yourself.                                                      | Current; v0.0.15 latest public release | Use official `ghcr.io/openai/tunnel-client`.                     | OpenAI tunnel-client Docker docs ([GitHub][12])                    |
| **F-019**  | OpenAI                 | Current tunnel-client supports `MCP_SERVER_URL` for Streamable HTTP.                                                                       | Direct Docker-to-Docker integration is supported.                                             | Current                                | Point tunnel-client to `http://mcp-server:8000/mcp`.             | OpenAI tunnel-client configuration ([GitHub][13])                  |
| **F-020**  | OpenAI                 | Runtime API key can be supplied via a secret file using `file:/...`.                                                                       | Better than putting a key directly in environment variables.                                  | Current                                | Use Docker Compose secret.                                       | OpenAI Docker deployment docs ([GitHub][12])                       |
| **F-021**  | MCP HTTP security      | Python SDK enables DNS-rebinding/Host-header protection by default for localhost-style HTTP servers.                                       | A container-to-container hostname such as `mcp-server` otherwise gets rejected with HTTP 421. | SDK v2                                 | Explicitly allowlist `mcp-server:8000`.                          | Python SDK deploy/troubleshooting docs ([GitHub][14])              |
| **F-022**  | MCP health             | `@mcp.custom_route()` can add a plain HTTP health endpoint.                                                                                | Docker can monitor MCP service health separately from MCP protocol traffic.                   | SDK v2                                 | Add `/healthz`.                                                  | Official Python SDK ([GitHub][15])                                 |
| **F-023**  | MCP protocol evolution | The 2026-07-28 protocol is stateless and deprecated roots, sampling, and logging.                                                          | New servers should avoid building around those deprecated capabilities.                       | 2026-07-28                             | Keep first version tool-focused.                                 | MCP release / SDK docs ([Model Context Protocol Blog][4])          |
| **F-024**  | MCP logging            | The current Python SDK recommends ordinary Python logging rather than protocol-level logging for new implementations.                      | Keeps operational logs separate from MCP business traffic.                                    | Current                                | Log to stderr/container logs.                                    | Python SDK ([MCP Python SDK][16])                                  |
| **F-025**  | Docker standard        | OCI Image Specification defines interoperable image manifests, layers, configuration and indexes.                                          | Image should remain OCI-compatible.                                                           | OCI Image 1.1.x                        | Use normal OCI/Docker images; support multi-arch release.        | OCI ([https://opencontainers.github.io][17])                       |
| **F-026**  | Docker standard        | OCI Runtime Specification **1.3.0** is the current runtime standard.                                                                       | Defines runtime configuration/lifecycle expectations.                                         | 1.3.0                                  | Rely on standard container runtime behavior.                     | OCI ([Open Container Initiative][18])                              |
| **F-027**  | Supply chain           | SLSA **1.2** is the current approved specification.                                                                                        | Provenance makes container builds traceable to source/build inputs.                           | v1.2                                   | Generate provenance in CI.                                       | SLSA ([SLSA][19])                                                  |
| **F-028**  | Container supply chain | Docker BuildKit supports SBOM and provenance attestations.                                                                                 | Gives the built image verifiable component/build metadata.                                    | Current                                | Enable SBOM + max provenance for release images.                 | Docker Build attestations ([Docker Documentation][20])             |
| **F-029**  | Container security     | NIST SP 800-190 remains the dedicated NIST guidance for application-container security.                                                    | Gives a recognized security baseline for container threats.                                   | SP 800-190                             | Use it as a container-security reference.                        | NIST ([NIST Computer Security Resource Center][21])                |
| **F-030**  | Container security     | OWASP recommends non-root containers, no-new-privileges, read-only filesystems, resource limits, scanning, and not exposing Docker socket. | These controls map directly to this MCP container.                                            | Current                                | Apply these hardening controls.                                  | OWASP Docker Security Cheat Sheet ([OWASP Cheat Sheet Series][22]) |
| **F-031**  | Secure development     | NIST SSDF encourages security practices across the SDLC.                                                                                   | Security should cover source, build and release, not just runtime.                            | SP 800-218 v1.1                        | Add tests, review, dependency and release controls.              | NIST SSDF                                                          |
| **F-032**  | GitHub CI security     | GitHub recommends pinning third-party Actions to full-length commit SHAs for immutable references.                                         | Protects the build pipeline itself.                                                           | Current                                | Pin CI actions by SHA.                                           | GitHub security guidance ([GitHub Docs][23])                       |
| **F-033**  | Dependency security    | GitHub Dependency Review can detect vulnerable dependency changes in pull requests.                                                        | Prevents known-vulnerable dependency additions.                                               | Current                                | Enable dependency review.                                        | GitHub ([GitHub Docs][24])                                         |

---

# 4. Key design decisions from the research

## Decision A — Dockerized MCP server uses Streamable HTTP

**Decision:** Yes.

```text
MCP container
      │
      │ HTTP
      ▼
tunnel-client container
```

This is different from the first version of the plan because we now have two independently managed containers.

The Python SDK explicitly describes Streamable HTTP as the transport to deploy, while stdio is the subprocess transport. ([GitHub][1])

---

## Decision B — Do not put tunnel-client inside your application image

Use:

```text
ghcr.io/openai/tunnel-client
```

as its own container.

This gives you:

```text
Container A
Python MCP server

Container B
OpenAI tunnel-client
```

rather than:

```text
Container
├── Python
├── MCP
├── tunnel-client
└── everything else
```

The official tunnel-client documentation explicitly provides a Docker image and Compose deployment model. ([GitHub][12])

---

## Decision C — Do not publish the MCP port

Don't do:

```yaml
ports:
  - "8000:8000"
```

in the normal configuration.

Instead:

```text
mcp-server:8000
```

exists only inside Docker's private network.

The tunnel-client reaches it through Docker DNS. OpenAI only needs the tunnel client to make outbound HTTPS to OpenAI. ([GitHub][2])

---

## Decision D — Use two Docker networks

```text
                         ┌───────────────┐
                         │    Internet   │
                         └───────┬───────┘
                                 │
                           egress network
                                 │
                       ┌─────────▼─────────┐
                       │   tunnel-client   │
                       └─────────┬─────────┘
                                 │
                         mcp-internal network
                                 │
                       ┌─────────▼─────────┐
                       │    mcp-server     │
                       └───────────────────┘
```

The MCP server gets **no Internet-facing network path**.

The tunnel container is the only component that needs Internet egress.

---

# 5. Complete Dockerized runbook

## Step 1 — Freeze the target architecture

Use this as the project baseline:

```text
Python                    3.14.7
MCP Python SDK            2.2.0
uv                        0.12.19
MCP protocol              2026-07-28
MCP transport             Streamable HTTP
Container runtime         Docker
Application base image    python:3.14.7-slim-trixie
Tunnel client             OpenAI tunnel-client v0.0.15
Container orchestration   Docker Compose
Testing                   pytest + MCP Inspector
Release                   OCI image
Supply chain              SBOM + provenance
```

The current official Python image publishes a `3.14.7-slim-trixie` tag, and the current MCP/uv versions are documented by their respective projects. ([GitHub][25])

**Related Finding IDs:** `F-001, F-004, F-005, F-007, F-008, F-018, F-025`

---

## Step 2 — Make Docker the host prerequisite

You only need these on the host:

```text
Git
Docker Desktop / Docker Engine
Docker Compose v2
```

You do **not** need Python installed on the host for the containerized runtime.

Verify:

```bash
docker version
```

Then:

```bash
docker compose version
```

Also check Buildx:

```bash
docker buildx version
```

**Related Finding IDs:** `F-010, F-025, F-026`

---

# Step 3 — Create the project structure

Use:

```text
openai-secure-mcp-tunnel/
│
├── local-mcp-server/
│   ├── Dockerfile
│   ├── compose.yaml
│   ├── .dockerignore
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .python-version
│   │
│   ├── src/
│   │   └── local_mcp_server/
│   │       ├── __init__.py
│   │       └── server.py
│   │
│   ├── tests/
│   │   └── test_security.py
│   │
│   └── allowed_data/
│       └── .gitkeep
│
└── .github/
    └── workflows/
```

The important change from the previous design is that `src/` contains a real Python package instead of a standalone `server.py`.

**Related Finding IDs:** `F-009, F-017, F-019`

---

# Step 4 — Create the Python project metadata

Use this baseline `pyproject.toml`:

```toml
[project]
name = "local-mcp-server"
version = "0.1.0"
description = "Private local MCP server for OpenAI Secure MCP Tunnel"
requires-python = ">=3.14,<3.15"
dependencies = [
    "mcp[cli]==2.2.0",
    "starlette",
]

[dependency-groups]
dev = [
    "pytest",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Then generate/update:

```bash
uv lock
```

The important property is that `uv.lock` becomes the exact dependency resolution used by the Docker build. uv's Docker guidance explicitly recommends `uv sync --locked`. ([Astral Docs][8])

**Related Finding IDs:** `F-005, F-008, F-009, F-017, F-019`

---

# Step 5 — Pin the Python version

Create:

```text
.python-version
```

containing:

```text
3.14.7
```

Verify from a uv environment if you want local development:

```bash
uv python install 3.14.7
uv python pin 3.14.7
```

**Related Finding IDs:** `F-007, F-008`

---

# Step 6 — Implement the MCP server

Create:

```text
src/local_mcp_server/server.py
```

Use this structure:

```python
from __future__ import annotations

import logging
import os
import platform
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

mcp = MCPServer("local-computer")

ALLOWED_ROOT = Path(
    os.environ.get("ALLOWED_DATA_DIR", "/app/allowed_data")
).resolve()

MAX_READ_BYTES = 1_000_000


def resolve_allowed_path(relative_path: str) -> Path:
    """Resolve a file path while preventing access outside ALLOWED_ROOT."""
    candidate = (ALLOWED_ROOT / relative_path).resolve()

    try:
        candidate.relative_to(ALLOWED_ROOT)
    except ValueError as exc:
        raise ValueError(
            "Requested path is outside the allowed data directory."
        ) from exc

    return candidate


@mcp.custom_route(
    "/healthz",
    methods=["GET"],
    include_in_schema=False,
)
async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool()
def get_system_info() -> dict[str, str]:
    """Return basic information about the local MCP container."""
    return {
        "operating_system": platform.system(),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
    }


@mcp.tool()
def list_allowed_files() -> list[str]:
    """List files below the configured allowed data directory."""
    if not ALLOWED_ROOT.exists():
        return []

    results: list[str] = []

    for path in ALLOWED_ROOT.rglob("*"):
        try:
            resolved = path.resolve()

            if not resolved.is_file():
                continue

            resolved.relative_to(ALLOWED_ROOT)

            results.append(
                resolved.relative_to(ALLOWED_ROOT).as_posix()
            )

        except (OSError, ValueError):
            continue

    return sorted(results)


@mcp.tool()
def read_allowed_text_file(relative_path: str) -> str:
    """Read a UTF-8 text file under the configured allowed data directory."""
    target = resolve_allowed_path(relative_path)

    if not target.is_file():
        raise ValueError("Requested path is not a regular file.")

    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError("Requested file is too large.")

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Requested file is not valid UTF-8 text."
        ) from exc


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    security = TransportSecuritySettings(
        allowed_hosts=["mcp-server:8000"],
    )

    logger.info("Starting local MCP server")

    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8000,
        streamable_http_path="/mcp",
        transport_security=security,
    )


if __name__ == "__main__":
    main()
```

Three details here are important.

### First

The server now uses:

```python
mcp.run(transport="streamable-http")
```

because it is a deployed container rather than a child subprocess. ([GitHub][1])

### Second

This line is essential:

```python
allowed_hosts=["mcp-server:8000"]
```

The current SDK protects Streamable HTTP servers against DNS rebinding by default and otherwise expects localhost. A Docker service named `mcp-server` would otherwise hit the SDK's `421 Invalid Host header` protection. ([GitHub][14])

### Third

`/healthz` is deliberately tiny.

The SDK documents `custom_route()` specifically for health checks and other non-MCP HTTP endpoints, and those routes are not authenticated. Therefore the route must expose **no sensitive information**. ([GitHub][15])

**Related Finding IDs:** `F-004, F-010, F-021, F-022, F-023, F-024, F-030`

---

# Step 7 — Create the controlled local data area

Create:

```text
local-mcp-server/allowed_data/
```

Then create:

```text
allowed_data/hello.txt
```

containing:

```text
Hello from my local MCP server.
```

The container will later mount this directory:

```text
host allowed_data/
        │
        │ :ro
        ▼
container /app/allowed_data/
```

This is much safer than mounting:

```text
/home/username/
```

or:

```text
/
```

into the container.

**Related Finding IDs:** `F-010, F-014, F-018, F-030`

---

# Step 8 — Create the Dockerfile

Use a multi-stage build.

```dockerfile
# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.14.7-slim-trixie AS builder

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock .python-version ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
    --locked \
    --no-install-project

COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
    --locked \
    --no-dev \
    --no-editable


FROM python:3.14.7-slim-trixie AS runtime

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd \
        --gid 10001 \
        appgroup \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --create-home \
        --shell /usr/sbin/nologin \
        appuser

COPY --from=builder --chown=10001:10001 \
    /app/.venv \
    /app/.venv

USER 10001:10001

EXPOSE 8000

ENTRYPOINT ["python", "-m", "local_mcp_server.server"]
```

This follows several current Docker/uv recommendations:

* trusted/minimal Python base image
* multi-stage build
* uv copied from the official uv image
* lockfile validation
* cache mounts
* non-editable installation
* non-root runtime

uv explicitly documents this pattern, including `uv sync --locked`, `--no-editable`, and copying uv from its official image. Docker separately recommends multi-stage builds and non-root execution. ([Astral Docs][8])

**Related Finding IDs:** `F-007, F-008, F-009, F-010, F-011, F-012, F-014`

---

# Step 9 — Create `.dockerignore`

Use:

```dockerignore
.git
.github

.venv
__pycache__
.pytest_cache
.ruff_cache
.mypy_cache

*.py[cod]

.env
.env.*
*.secret
secrets

allowed_data/*
!allowed_data/.gitkeep

Dockerfile*
compose*.yaml

dist
build
*.egg-info
```

The key objective is:

```text
No credentials
No local virtualenv
No private data
No Git metadata
```

should enter the Docker build context.

Docker specifically recommends using `.dockerignore` to keep irrelevant or sensitive files out of builds. ([Docker Documentation][9])

**Related Finding IDs:** `F-010, F-013, F-018, F-030`

---

# Step 10 — Validate the Dockerfile before building

Run:

```bash
docker buildx build --check ./local-mcp-server
```

Docker's current Buildx supports `--check` specifically to evaluate Dockerfile/build configuration without executing the build. ([Docker Documentation][26])

Fix every warning that indicates an actual configuration problem.

**Related Finding IDs:** `F-010, F-011, F-031`

---

# Step 11 — Build the MCP image

From the repository root:

```bash
docker build \
  --pull \
  -t local-mcp-server:dev \
  ./local-mcp-server
```

For a fully clean validation build:

```bash
docker build \
  --pull \
  --no-cache \
  -t local-mcp-server:dev \
  ./local-mcp-server
```

Docker recommends `--pull` when you want a fresh base image and distinguishes that from `--no-cache`, which rebuilds layers without using the local build cache. ([Docker Documentation][9])

**Related Finding IDs:** `F-010, F-011, F-012`

---

# Step 12 — Create the Docker Compose architecture

Create:

```text
local-mcp-server/compose.yaml
```

Use:

```yaml
services:
  mcp-server:
    build:
      context: .
      dockerfile: Dockerfile

    image: local-mcp-server:dev

    restart: unless-stopped

    read_only: true

    security_opt:
      - no-new-privileges:true

    cap_drop:
      - ALL

    tmpfs:
      - /tmp:rw,noexec,nosuid,nodev

    environment:
      ALLOWED_DATA_DIR: /app/allowed_data
      LOG_LEVEL: INFO

    volumes:
      - ./allowed_data:/app/allowed_data:ro

    networks:
      - mcp-internal

    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).read()"
        ]
      interval: 10s
      timeout: 3s
      retries: 10
      start_period: 15s


  tunnel-client:
    image: ghcr.io/openai/tunnel-client:v0.0.15

    restart: unless-stopped

    command:
      - run
      - --control-plane.api-key=file:/run/secrets/control_plane_api_key

    environment:
      CONTROL_PLANE_TUNNEL_ID: ${CONTROL_PLANE_TUNNEL_ID}
      MCP_SERVER_URL: http://mcp-server:8000/mcp
      LOG_LEVEL: info
      LOG_FORMAT: json
      MCP_CONNECTION_MAX_TTL: 10m

    secrets:
      - control_plane_api_key

    depends_on:
      mcp-server:
        condition: service_healthy

    networks:
      - mcp-internal
      - tunnel-egress

    security_opt:
      - no-new-privileges:true

    cap_drop:
      - ALL


networks:
  mcp-internal:
    internal: true

  tunnel-egress:


secrets:
  control_plane_api_key:
    file: .secrets/control-plane-api-key
```

This is the most important new piece of the design.

---

# 13. Understand the Compose network

The networks are intentionally asymmetric:

```text
mcp-server
    │
    │
    ▼
mcp-internal
    │
    ▼
tunnel-client
    │
    ▼
tunnel-egress
    │
    ▼
Internet → api.openai.com:443
```

The MCP server **does not belong to the Internet-facing network**.

Docker Compose supports service networking, read-only filesystems, dropped capabilities and security options; OWASP recommends the corresponding container hardening controls. ([Docker Documentation][11])

**Related Finding IDs:** `F-015, F-016, F-017, F-030`

---

# Step 14 — Create the runtime secret

Create:

```text
local-mcp-server/.secrets/control-plane-api-key
```

Put **only** the OpenAI runtime key inside it.

For example:

```text
sk-xxxxxxxxxxxxxxxx
```

Do not put quotes around it.

Then add:

```gitignore
.secrets/
```

to `.gitignore`.

OpenAI's tunnel-client documentation explicitly supports passing the runtime credential as a file using `file:/...`. ([GitHub][12])

**Related Finding IDs:** `F-013, F-018, F-020, F-030`

---

# Step 15 — Configure the tunnel ID

Create a local `.env` file:

```text
CONTROL_PLANE_TUNNEL_ID=tunnel_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Docker Compose reads this value for:

```yaml
CONTROL_PLANE_TUNNEL_ID: ${CONTROL_PLANE_TUNNEL_ID}
```

Do not commit `.env`.

**Related Finding IDs:** `F-017, F-018, F-020`

---

# Step 16 — Verify the Compose configuration

Run:

```bash
docker compose \
  -f local-mcp-server/compose.yaml \
  config
```

Inspect the output.

Make sure you see:

```text
MCP_SERVER_URL: http://mcp-server:8000/mcp
```

and:

```text
CONTROL_PLANE_TUNNEL_ID
```

but **not the literal secret value** in a committed file.

**Related Finding IDs:** `F-013, F-016, F-020`

---

# Step 17 — Start only the MCP container first

Do not start the tunnel yet.

Run:

```bash
docker compose \
  -f local-mcp-server/compose.yaml \
  up -d --build mcp-server
```

Check:

```bash
docker compose \
  -f local-mcp-server/compose.yaml \
  ps
```

You want:

```text
mcp-server    healthy
```

Inspect:

```bash
docker compose \
  -f local-mcp-server/compose.yaml \
  logs mcp-server
```

**Related Finding IDs:** `F-009, F-015, F-022`

---

# Step 18 — Test the health endpoint

Because the MCP port is deliberately not published to the host, the cleanest first test is from another container on the internal network.

For example:

```bash
docker run --rm \
  --network container:<mcp-container-id> \
  python:3.14.7-slim-trixie \
  python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/healthz').read().decode())"
```

Alternatively, for easier local development, temporarily expose:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

and test:

```bash
curl http://127.0.0.1:8000/healthz
```

Do **not** expose:

```yaml
- "8000:8000"
```

on a machine where you do not want LAN access.

**Related Finding IDs:** `F-015, F-016, F-022, F-030`

---

# Step 19 — Verify the MCP endpoint

With a temporary localhost debug port, test:

```text
http://127.0.0.1:8000/mcp
```

The important thing to verify is that the server does **not** return:

```text
421 Invalid Host header
```

If it does, check:

```python
TransportSecuritySettings(
    allowed_hosts=["mcp-server:8000"]
)
```

The current SDK explicitly documents this DNS-rebinding/Host-header behavior. ([GitHub][14])

**Related Finding IDs:** `F-004, F-021`

---

# Step 20 — Test with MCP Inspector

For the debug configuration, connect MCP Inspector to:

```text
http://127.0.0.1:8000/mcp
```

You should see:

```text
Tools
├── get_system_info
├── list_allowed_files
└── read_allowed_text_file
```

MCP Inspector is the official interactive testing tool for MCP servers. ([GitHub][1])

Test all three tools.

**Related Finding IDs:** `F-005, F-015, F-023`

---

# Step 21 — Test path security

Use:

```json
{
  "relative_path": "../server.py"
}
```

Then:

```json
{
  "relative_path": "../../pyproject.toml"
}
```

Both must be rejected.

Also test a symlink inside `allowed_data` that points outside it.

That last test is important because the code calls:

```python
Path.resolve()
```

before checking the allowed root.

**Related Finding IDs:** `F-010, F-018, F-030`

---

# Step 22 — Run automated tests

Use tests such as:

```python
import pytest

from local_mcp_server.server import (
    ALLOWED_ROOT,
    read_allowed_text_file,
    resolve_allowed_path,
)


def test_allowed_file_is_inside_root():
    result = resolve_allowed_path("hello.txt")
    assert result.parent == ALLOWED_ROOT


def test_parent_traversal_is_rejected():
    with pytest.raises(ValueError):
        resolve_allowed_path("../server.py")


def test_nested_parent_traversal_is_rejected():
    with pytest.raises(ValueError):
        resolve_allowed_path("../../pyproject.toml")


def test_allowed_file_can_be_read():
    result = read_allowed_text_file("hello.txt")
    assert result == "Hello from my local MCP server.\n"
```

Run them either with your local uv environment:

```bash
uv run pytest
```

or add a Docker test target in CI.

**Related Finding IDs:** `F-018, F-019, F-031`

---

# Step 23 — Start the tunnel-client container

Once the MCP server is healthy:

```bash
docker compose \
  -f local-mcp-server/compose.yaml \
  up -d tunnel-client
```

Or simply:

```bash
docker compose \
  -f local-mcp-server/compose.yaml \
  up -d
```

Compose will honor:

```text
mcp-server healthy
        ↓
tunnel-client starts
```

**Related Finding IDs:** `F-017, F-018, F-019`

---

# Step 24 — Check tunnel-client logs

Run:

```bash
docker compose \
  -f local-mcp-server/compose.yaml \
  logs -f tunnel-client
```

You are looking for successful:

```text
control-plane connection
tunnel authentication
MCP target connection
readiness
```

OpenAI's tunnel-client provides health/readiness/operator surfaces for this purpose. ([GitHub][27])

**Related Finding IDs:** `F-017, F-018, F-019, F-020`

---

# Step 25 — Verify tunnel-client readiness

For troubleshooting, optionally expose the tunnel-client health port only to localhost:

```yaml
environment:
  HEALTH_LISTEN_ADDR: ":8080"

ports:
  - "127.0.0.1:8080:8080"
```

Then:

```bash
curl http://127.0.0.1:8080/healthz
```

and:

```bash
curl http://127.0.0.1:8080/readyz
```

OpenAI documents these runtime endpoints and specifically warns that exposing the health listener should be done only intentionally. ([GitHub][12])

For normal operation, you can omit the published port.

**Related Finding IDs:** `F-017, F-018`

---

# Step 26 — Verify internal connectivity

The effective connection should now be:

```text
tunnel-client
      │
      │ http://mcp-server:8000/mcp
      ▼
mcp-server
```

No host routing is involved.

If the tunnel reports that the MCP target is unreachable, troubleshoot:

```text
1. mcp-server healthy?
2. Both services on mcp-internal?
3. Correct service name?
4. Port 8000?
5. Host allowlist?
6. Container logs?
```

**Related Finding IDs:** `F-016, F-019, F-021`

---

# Step 27 — Create/configure the ChatGPT tunnel connection

Use the OpenAI Platform tunnel/workspace configuration from the previous runbook.

The tunnel must be associated with the correct ChatGPT workspace and the runtime credential must have the required tunnel permissions.

OpenAI documents the tunnel runtime permissions as **Read + Use** for a normal runtime principal; tunnel managers additionally require Manage. ([GitHub][28])

**Related Finding IDs:** `F-017, F-018, F-020`

---

# Step 28 — Test from ChatGPT

Use only read-only operations first.

Test:

```text
get_system_info
```

Then:

```text
list_allowed_files
```

Then:

```text
read_allowed_text_file("hello.txt")
```

The final path is:

```text
ChatGPT
   ↓
OpenAI Tunnel Service
   ↓
tunnel-client container
   ↓
Docker private network
   ↓
Python MCP container
   ↓
MCP tool
```

**Related Finding IDs:** `F-004, F-010, F-017, F-019, F-023`

---

# Step 29 — Test container isolation

Verify the MCP container:

```bash
docker inspect <mcp-container>
```

Check:

```text
read-only root filesystem
non-root user
no-new-privileges
capabilities dropped
only expected volume mounted
```

Also verify you did **not** mount:

```text
/var/run/docker.sock
```

OWASP explicitly warns that access to the Docker socket is effectively host-level root access and should not be exposed to containers. ([OWASP Cheat Sheet Series][22])

**Related Finding IDs:** `F-014, F-015, F-030`

---

# Step 30 — Add container resource limits

After measuring real usage, add limits such as:

```yaml
deploy:
  resources:
    limits:
      cpus: "0.50"
      memory: 512M
```

or Compose runtime-specific limits where supported.

Don't blindly choose extremely small limits; the MCP server's actual tools may have different requirements.

OWASP explicitly recommends resource limits as a container DoS-control measure. ([OWASP Cheat Sheet Series][22])

**Related Finding IDs:** `F-018, F-029, F-030`

---

# Step 31 — Pin the base image for release builds

For development:

```dockerfile
FROM python:3.14.7-slim-trixie
```

is reasonable.

For a controlled release, resolve the image digest and use:

```dockerfile
FROM python:3.14.7-slim-trixie@sha256:<DIGEST>
```

Do the same for:

```text
ghcr.io/astral-sh/uv
```

and use an exact tunnel-client image version/digest.

Docker explicitly recommends digest pinning when reproducibility and supply-chain control are important. ([Docker Documentation][9])

**Related Finding IDs:** `F-008, F-011, F-027`

---

# Step 32 — Use the official OpenAI tunnel image

Do not rebuild tunnel-client unless you have a specific reason.

Use:

```text
ghcr.io/openai/tunnel-client:v0.0.15
```

for the current public release baseline.

The official release is currently **v0.0.15**, published September 25, 2026, and the project publishes multi-architecture Docker images. ([GitHub][29])

The tunnel-client's own Docker publishing pipeline includes SBOM and provenance information. ([GitHub][30])

**Related Finding IDs:** `F-018, F-025, F-028`

---

# Step 33 — Add CI Dockerfile validation

Your CI should at minimum perform:

```bash
docker buildx build --check ./local-mcp-server
```

Docker documents the Buildx check mode specifically for validating Docker build configuration before executing the build. ([Docker Documentation][26])

**Related Finding IDs:** `F-010, F-031`

---

# Step 34 — Add automated tests to GitHub Actions

At minimum:

```text
pytest
Dockerfile validation
Docker image build
dependency security review
```

GitHub Dependency Review can identify vulnerable dependency changes in pull requests. ([GitHub Docs][24])

**Related Finding IDs:** `F-009, F-019, F-031, F-033`

---

# Step 35 — Build release images with provenance and SBOM

For release images, use Docker Buildx and enable:

```text
provenance: mode=max
sbom: true
```

Docker documents both mechanisms; provenance describes how the image was built, while SBOM describes what software is contained in it. ([Docker Documentation][20])

The current SLSA specification is **v1.2**, which defines build provenance levels and verification concepts. ([SLSA][19])

---

# Step 36 — Pin GitHub Actions

When creating the CI workflow, don't leave important third-party actions at floating tags if you want a stronger supply-chain posture.

GitHub specifically recommends pinning Actions to **full-length commit SHAs** when immutable references are required. ([GitHub Docs][23])

For example, instead of only:

```yaml
uses: docker/build-push-action@v7
```

a hardened workflow can pin:

```yaml
uses: docker/build-push-action@<full-40-character-commit-sha>
```

while recording the corresponding human-readable version in a comment.

**Related Finding IDs:** `F-027, F-032`

---

# Step 37 — Build multi-architecture images

For publishing:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --push \
  ...
```

The official OpenAI tunnel-client Docker release itself publishes Linux `amd64` and `arm64` images. ([GitHub][12])

Your Python image can follow the same architecture model.

**Related Finding IDs:** `F-025, F-026`

---

# Step 38 — Do not use Docker socket access

Do not add:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

to the MCP server.

Do not expose the Docker daemon over TCP.

OWASP explicitly treats Docker socket access as equivalent to unrestricted host-root-level control. ([OWASP Cheat Sheet Series][22])

**Related Finding IDs:** `F-018, F-030`

---

# Step 39 — Define the tool security model before adding real capabilities

Every new tool should answer:

```text
What resource does it access?
What is the smallest permission needed?
Is it read-only?
Can its input escape its intended boundary?
Can it cause destructive side effects?
Does it need human confirmation?
Does it expose secrets?
```

For example:

### Good

```text
read_allowed_text_file(relative_path)
get_project_status(project_name)
list_allowed_files()
```

### High-risk

```text
run_shell(command)
execute_python(code)
read_file(path)
delete_file(path)
send_http_request(url)
```

The MCP tool model gives the server the ability to expose arbitrary capabilities, so least privilege is a fundamental application-security boundary. MCP itself emphasizes human control and authorization, while OWASP recommends least privilege. ([Model Context Protocol Blog][4])

**Related Finding IDs:** `F-010, F-018, F-030`

---

# Step 40 — Establish the production lifecycle

Your operational lifecycle should be:

```text
Source change
     ↓
pytest
     ↓
Dockerfile --check
     ↓
dependency review
     ↓
Docker build
     ↓
container security scan
     ↓
SBOM
     ↓
provenance
     ↓
publish image
     ↓
run pinned image
     ↓
Secure MCP Tunnel
     ↓
ChatGPT
```

This is considerably stronger than:

```text
edit Python
    ↓
docker build
    ↓
docker run
```

NIST SSDF and SLSA both support treating build/release provenance and secure development practices as part of the software lifecycle, not just runtime. ([SLSA][19])

**Related Finding IDs:** `F-027, F-028, F-031, F-032, F-033`

---

# 6. Final repository structure

I recommend evolving your repository toward this:

```text
openai-secure-mcp-tunnel/
│
├── README.md
├── .gitignore
│
├── local-mcp-server/
│   │
│   ├── Dockerfile
│   ├── compose.yaml
│   ├── .dockerignore
│   ├── .python-version
│   ├── pyproject.toml
│   ├── uv.lock
│   │
│   ├── src/
│   │   └── local_mcp_server/
│   │       ├── __init__.py
│   │       └── server.py
│   │
│   ├── tests/
│   │   └── test_security.py
│   │
│   └── allowed_data/
│       └── .gitkeep
│
├── docs/
│   ├── architecture.md
│   ├── security.md
│   ├── research.md
│   └── operations.md
│
└── .github/
    └── workflows/
        ├── test.yml
        ├── dependency-review.yml
        └── container-release.yml
```

---

# 7. Revised visual workflow

```text
                         ┌──────────────────────┐
                         │   Research / Standards│
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Python MCP Server    │
                         │ SDK 2.2.0            │
                         └──────────┬───────────┘
                                    │
                         Streamable HTTP
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Docker Image         │
                         │ non-root             │
                         │ read-only FS         │
                         │ capabilities dropped │
                         └──────────┬───────────┘
                                    │
                         private Docker network
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ tunnel-client        │
                         │ official OpenAI image│
                         └──────────┬───────────┘
                                    │
                            HTTPS :443 outbound
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ OpenAI Secure MCP    │
                         │ Tunnel               │
                         └──────────┬───────────┘
                                    │
                                    ▼
                              ChatGPT Web
```

---

# 8. Strict implementation sequence

This is the sequence I would actually follow:

|   Step | Action                                        | Related Findings             |
| -----: | --------------------------------------------- | ---------------------------- |
|  **1** | Confirm Dockerized two-container architecture | `F-004, F-017, F-018, F-019` |
|  **2** | Install Docker + Compose + Buildx             | `F-010, F-025, F-026`        |
|  **3** | Create repository/project structure           | `F-009, F-017`               |
|  **4** | Create `pyproject.toml` + lockfile            | `F-005, F-008, F-009`        |
|  **5** | Pin Python 3.14.7                             | `F-006, F-007`               |
|  **6** | Implement MCPServer                           | `F-001, F-005, F-010, F-011` |
|  **7** | Implement Streamable HTTP                     | `F-004, F-023`               |
|  **8** | Implement Host allowlist                      | `F-021`                      |
|  **9** | Implement `/healthz`                          | `F-022`                      |
| **10** | Implement least-privilege filesystem access   | `F-010, F-018, F-030`        |
| **11** | Create Dockerfile                             | `F-010, F-011, F-012, F-014` |
| **12** | Create `.dockerignore`                        | `F-013, F-018`               |
| **13** | Validate Dockerfile                           | `F-010, F-031`               |
| **14** | Build MCP image                               | `F-010, F-011`               |
| **15** | Create isolated Compose networks              | `F-015, F-016`               |
| **16** | Add read-only data mount                      | `F-010, F-030`               |
| **17** | Add secret-file handling                      | `F-013, F-020`               |
| **18** | Start MCP container                           | `F-022`                      |
| **19** | Verify `/healthz`                             | `F-022`                      |
| **20** | Test MCP through Inspector                    | `F-005, F-015`               |
| **21** | Test path traversal/security                  | `F-018, F-030`               |
| **22** | Run automated tests                           | `F-019, F-031`               |
| **23** | Start OpenAI tunnel-client container          | `F-017, F-018, F-019`        |
| **24** | Verify tunnel readiness                       | `F-017, F-018`               |
| **25** | Connect tunnel to ChatGPT                     | `F-017, F-018, F-020`        |
| **26** | Execute read-only end-to-end tests            | `F-010, F-014, F-019`        |
| **27** | Harden runtime                                | `F-014, F-015, F-030`        |
| **28** | Add CI/dependency review                      | `F-031, F-033`               |
| **29** | Add image scanning/SBOM                       | `F-028, F-030`               |
| **30** | Add signed/provenance release                 | `F-027, F-028, F-032`        |
| **31** | Publish multi-architecture image              | `F-025, F-026`               |
| **32** | Establish update/rotation process             | `F-009, F-027, F-031`        |

---

# 9. The three layers you should think about

This is the biggest conceptual improvement to the original plan.

```text
┌─────────────────────────────────────┐
│ Layer 1 — MCP Application Security │
│                                     │
│ tools                               │
│ input validation                    │
│ authorization                       │
│ data boundaries                     │
└──────────────────┬──────────────────┘
                   │
┌──────────────────▼──────────────────┐
│ Layer 2 — Container Security        │
│                                     │
│ non-root                            │
│ read-only filesystem                │
│ dropped capabilities                │
│ no-new-privileges                   │
│ private network                     │
│ resource limits                     │
└──────────────────┬──────────────────┘
                   │
┌──────────────────▼──────────────────┐
│ Layer 3 — Tunnel / Network Security│
│                                     │
│ outbound HTTPS                     │
│ tunnel authentication               │
│ no public MCP port                  │
│ ChatGPT workspace authorization     │
└─────────────────────────────────────┘
```

A secure tunnel does **not** make an unsafe MCP server safe.

A hardened container does **not** make an over-privileged MCP tool safe.

And a carefully designed MCP server does **not** eliminate the need to protect the tunnel credentials.

You need all three layers.

---

# 10. What I would specifically change from the old plan

| Old approach                   | Revised approach                                          |
| ------------------------------ | --------------------------------------------------------- |
| Local Python process           | **Python MCP container**                                  |
| stdio as final transport       | **Streamable HTTP between containers**                    |
| tunnel-client on host          | **official tunnel-client container**                      |
| One process boundary           | **two independent containers**                            |
| Public/host HTTP debugging     | **no published port by default**                          |
| Broad Docker network           | **private MCP network + tunnel egress network**           |
| Environment API key            | **Docker secret file**                                    |
| Root container                 | **non-root**                                              |
| Writable container FS          | **read-only root FS + tmpfs**                             |
| No container supply-chain plan | **SBOM + provenance + image scanning**                    |
| Generic dependency lock        | **`uv.lock` + locked Docker install**                     |
| Basic tunnel test              | **layered MCP → container → tunnel → ChatGPT validation** |

---

## The final baseline

I would now make this the official design for your repository:

```text
Language:
    Python 3.14.7

MCP:
    MCP specification 2026-07-28
    MCP Python SDK 2.2.0

Application transport:
    Streamable HTTP

Python tooling:
    uv 0.12.19

Application container:
    python:3.14.7-slim-trixie

Container:
    non-root
    read-only filesystem
    no-new-privileges
    cap_drop=ALL
    private Docker network

OpenAI:
    Secure MCP Tunnel
    tunnel-client v0.0.15

Tunnel architecture:
    separate official OpenAI container

Secrets:
    Docker secret file

Testing:
    pytest
    MCP Inspector
    Docker buildx --check

Supply chain:
    pinned images
    uv.lock
    SBOM
    SLSA-compatible provenance
    dependency review
    pinned GitHub Actions
```

The **most important architectural decision** is therefore:

> **Python MCP server container → private Streamable HTTP → OpenAI tunnel-client container → outbound Secure MCP Tunnel → ChatGPT.**

That is the version of the plan I would use going forward.

[1]: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/index.md?utm_source=chatgpt.com "python-sdk/docs/run/index.md at main · modelcontextprotocol/python-sdk · GitHub"
[2]: https://github.com/openai/tunnel-client/blob/master/docs/deployment/overview.md?utm_source=chatgpt.com "tunnel-client/docs/deployment/overview.md at master · openai/tunnel-client · GitHub"
[3]: https://github.com/openai/tunnel-client/blob/master/docs/connectors.md?utm_source=chatgpt.com "tunnel-client/docs/connectors.md at master · openai/tunnel-client · GitHub"
[4]: https://blog.modelcontextprotocol.io/posts/2026-07-28/?utm_source=chatgpt.com "The 2026-07-28 Specification | Model Context Protocol Blog"
[5]: https://github.com/modelcontextprotocol/python-sdk/releases?utm_source=chatgpt.com "Releases · modelcontextprotocol/python-sdk · GitHub"
[6]: https://pypi.org/project/mcp/?utm_source=chatgpt.com "mcp · PyPI"
[7]: https://www.python.org/downloads/release/python-3147/?utm_source=chatgpt.com "Python Release Python 3.14.7 | Python.org"
[8]: https://docs.astral.sh/uv/guides/integration/docker/?utm_source=chatgpt.com "Using uv in Docker | uv"
[9]: https://docs.docker.com/build/building/best-practices/?utm_source=chatgpt.com "Building best practices | Docker Docs"
[10]: https://docs.docker.com/reference/dockerfile?utm_source=chatgpt.com "Dockerfile reference | Docker Docs"
[11]: https://docs.docker.com/reference/compose-file/services/?utm_source=chatgpt.com "Define services in Docker Compose | Docker Docs"
[12]: https://github.com/openai/tunnel-client/blob/master/docs/deployment/docker.md?utm_source=chatgpt.com "tunnel-client/docs/deployment/docker.md at master · openai/tunnel-client · GitHub"
[13]: https://github.com/openai/tunnel-client/blob/master/docs/configuration.md?utm_source=chatgpt.com "tunnel-client/docs/configuration.md at master · openai/tunnel-client · GitHub"
[14]: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/troubleshooting.md?utm_source=chatgpt.com "python-sdk/docs/troubleshooting.md at main · modelcontextprotocol/python-sdk · GitHub"
[15]: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/asgi.md?utm_source=chatgpt.com "python-sdk/docs/run/asgi.md at main · modelcontextprotocol/python-sdk · GitHub"
[16]: https://py.sdk.modelcontextprotocol.io/handlers/logging/?utm_source=chatgpt.com "Logging - MCP Python SDK"
[17]: https://specs.opencontainers.org/image-spec/?utm_source=chatgpt.com "The OpenContainers Image Spec"
[18]: https://opencontainers.org/release-notices/overview/?utm_source=chatgpt.com "Release notices - Open Container Initiative"
[19]: https://slsa.dev/spec/v1.2/?utm_source=chatgpt.com "SLSA • SLSA specification"
[20]: https://docs.docker.com/build/metadata/attestations/?utm_source=chatgpt.com "Build attestations | Docker Docs"
[21]: https://csrc.nist.gov/pubs/sp/800/190/final?utm_source=chatgpt.com "SP 800-190, Application Container Security Guide | CSRC"
[22]: https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html?utm_source=chatgpt.com "Docker Security - OWASP Cheat Sheet Series"
[23]: https://docs.github.com/en/actions/reference/security/secure-use?utm_source=chatgpt.com "Secure use reference - GitHub Docs"
[24]: https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/configure-dependency-review-action?utm_source=chatgpt.com "Configuring the dependency review action - GitHub Docs"
[25]: https://github.com/docker-library/official-images/blob/master/library/python?utm_source=chatgpt.com "official-images/library/python at master · docker-library/official-images · GitHub"
[26]: https://docs.docker.com/reference/cli/docker/buildx/build/?utm_source=chatgpt.com "docker buildx build | Docker Docs"
[27]: https://github.com/openai/tunnel-client/blob/master/docs/end-user-guide.md?utm_source=chatgpt.com "tunnel-client/docs/end-user-guide.md at master · openai/tunnel-client · GitHub"
[28]: https://github.com/openai/tunnel-client/blob/master/docs/permissions.md?utm_source=chatgpt.com "tunnel-client/docs/permissions.md at master · openai/tunnel-client · GitHub"
[29]: https://github.com/openai/tunnel-client/releases?utm_source=chatgpt.com "Releases · openai/tunnel-client · GitHub"
[30]: https://github.com/openai/tunnel-client/blob/master/.github/workflows/release.yml?utm_source=chatgpt.com "tunnel-client/.github/workflows/release.yml at master · openai/tunnel-client · GitHub"
