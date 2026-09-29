# Python Local MCP Server — Dockerized Research-to-Runbook

**Repository:** `0n6k4v-Coder/openai-secure-mcp-tunnel`
**Scope:** Private Python MCP server in Docker, connected to ChatGPT through OpenAI Secure MCP Tunnel.
**Research baseline:** September 29, 2026.

---

# 1. Purpose

This playbook defines the complete implementation path for a private/local MCP server built with Python, managed with uv, containerized with Docker, and connected to ChatGPT through OpenAI Secure MCP Tunnel.

The implementation is intentionally layered:

1. Build and verify the Python MCP server.
2. Run the MCP server as a hardened Docker container.
3. Run the official OpenAI `tunnel-client` as a separate container.
4. Connect the two containers over a private Docker network using Streamable HTTP.
5. Connect the tunnel to ChatGPT.
6. Add CI, dependency security, image hardening, SBOM, provenance, and operational controls.

The first server exposes only narrow, read-only capabilities. Higher-risk tools are intentionally excluded until their security boundaries are designed and tested.

---

# 2. Target architecture

```text
                              INTERNET
                                 │
                         HTTPS outbound only
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ OpenAI Secure MCP       │
                    │ Tunnel Service          │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ tunnel-client           │
                    │ Docker container        │
                    │                         │
                    │ MCP_SERVER_URL          │
                    │ http://mcp-server:8000  │
                    └────────────┬────────────┘
                                 │
                         private Docker
                           mcp-internal
                                 │
                         Streamable HTTP
                             /mcp
                                 │
                    ┌────────────▼────────────┐
                    │ mcp-server              │
                    │ Docker container        │
                    │                         │
                    │ Python 3.14.7           │
                    │ MCP SDK 2.2.0           │
                    │                         │
                    │ get_system_info()       │
                    │ list_allowed_files()    │
                    │ read_allowed_text_file()│
                    └────────────┬────────────┘
                                 │
                            read-only mount
                                 │
                                 ▼
                         ./allowed_data
```

There is no published MCP port to the Internet.

The MCP container is reachable only through the private Docker network. The tunnel-client container is the component that reaches OpenAI externally. OpenAI documents outbound HTTPS connectivity for the tunnel and no inbound public MCP listener requirement.

---

# 3. Technology baseline

| Component             | Baseline                       |
| --------------------- | ------------------------------ |
| MCP specification     | **2026-07-28**                 |
| MCP Python SDK        | **2.2.0**                      |
| Development Python    | **3.14.6**                     |
| Container Python      | **3.14.7**                     |
| Project requirement   | `>=3.14,<3.15`                 |
| Python tooling        | uv + uv_build                  |
| Lockfile              | `uv.lock`                      |
| Application transport | Streamable HTTP                |
| HTTP mode             | Stateless HTTP for v1          |
| Container runtime     | Docker                         |
| Orchestration         | Docker Compose                 |
| Tunnel                | OpenAI Secure MCP Tunnel       |
| Tunnel client         | OpenAI `tunnel-client` v0.0.15 |
| MCP endpoint          | `http://mcp-server:8000/mcp`   |
| Secret mechanism      | Docker Compose secret file     |
| Testing               | pytest + ruff + MCP Inspector  |
| Release image         | OCI-compatible Docker image    |
| Supply-chain metadata | SBOM + provenance              |

The development/runtime distinction is deliberate: your installed uv catalog currently provides Python 3.14.6, while Python.org's current 3.14 maintenance release is 3.14.7 and the official Docker image provides 3.14.7.

---

# 4. Research findings

| Finding ID | Area               | Finding                                                                                                                              | Why It Matters                                             | Version / Date  | Implementation Impact                            |
| ---------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------- | --------------- | ------------------------------------------------ |
| **F-001**  | MCP                | Stable MCP specification is **2026-07-28**.                                                                                          | Use the current protocol baseline.                         | 2026-07-28      | Build against SDK v2.                            |
| **F-002**  | MCP protocol       | MCP uses JSON-RPC 2.0 messaging.                                                                                                     | Avoid manual protocol framing.                             | Current         | Let the SDK handle wire protocol.                |
| **F-003**  | Transport          | stdio is for client-launched local subprocesses.                                                                                     | Best for same-process-boundary local servers.              | Current         | Not the primary Docker-to-Docker transport.      |
| **F-004**  | Transport          | Streamable HTTP is the current HTTP deployment transport; SSE is legacy.                                                             | Docker containers naturally communicate over private HTTP. | Current         | Use Streamable HTTP.                             |
| **F-005**  | MCP SDK            | Project is pinned to official MCP Python SDK **2.2.0**.                                                                              | Prevents SDK drift during implementation.                  | Current         | Pin `mcp[cli]==2.2.0`.                           |
| **F-006**  | Python             | MCP SDK supports Python 3.10+ and Python 3.14.                                                                                       | Python 3.14 is supported.                                  | Current         | Use `>=3.14,<3.15`.                              |
| **F-007**  | Python             | Python **3.14.7** is the current 3.14 maintenance release.                                                                           | Use current patch level in the image.                      | Aug. 5, 2026    | Use `python:3.14.7-slim-trixie`.                 |
| **F-008**  | uv                 | uv supports modern Python application projects and the `uv_build` backend.                                                           | Gives standard packaging plus dependency management.       | Current         | Use uv + uv_build.                               |
| **F-009**  | Reproducibility    | `uv.lock` is the resolved dependency source of truth; `uv sync --locked` verifies it.                                                | Prevents silent dependency changes in Docker.              | Current         | Locked sync is mandatory.                        |
| **F-010**  | Docker build       | Multi-stage builds and dependency/project layer separation are recommended.                                                          | Reduces image size and rebuild time.                       | Current         | Builder + runtime stages.                        |
| **F-011**  | Docker build       | Exact image tags improve repeatability; digests provide stronger immutability.                                                       | Prevents base-image drift.                                 | Current         | Use exact tags; digests for controlled releases. |
| **F-012**  | Docker build       | BuildKit cache mounts keep dependency caches out of image layers.                                                                    | Speeds builds without bloating images.                     | Current         | Cache uv downloads.                              |
| **F-013**  | Secrets            | Credentials should not be passed through Docker build args or baked into images.                                                     | Prevents secret leakage.                                   | Current         | Use runtime secrets.                             |
| **F-014**  | Runtime            | Containers should run unprivileged.                                                                                                  | Limits blast radius.                                       | Current         | Non-root app user.                               |
| **F-015**  | Runtime hardening  | Read-only filesystems, dropped capabilities, and `no-new-privileges` reduce attack surface.                                          | Useful for MCP applications.                               | Current         | Apply to the MCP container.                      |
| **F-016**  | Networking         | Docker Compose supports isolated networks and service-name DNS.                                                                      | Keeps MCP server private.                                  | Current         | Internal MCP network.                            |
| **F-017**  | OpenAI tunnel      | Secure MCP Tunnel uses outbound connectivity; MCP server does not need a public listener.                                            | No public MCP port required.                               | Current         | Only tunnel-client needs external egress.        |
| **F-018**  | OpenAI tunnel      | Official tunnel-client provides Docker image and Compose guidance.                                                                   | No need to package tunnel-client into app image.           | v0.0.15         | Separate tunnel-client container.                |
| **F-019**  | OpenAI tunnel      | `MCP_SERVER_URL` configures an HTTP MCP target.                                                                                      | Direct Docker-to-Docker routing is supported.              | Current         | Use `http://mcp-server:8000/mcp`.                |
| **F-020**  | OpenAI secrets     | tunnel-client supports a secret file using `file:/...`.                                                                              | Cleaner secret handling.                                   | Current         | Docker secret file.                              |
| **F-021**  | MCP HTTP security  | Streamable HTTP has Host/Origin validation and DNS-rebinding protection.                                                             | Docker service names must be explicitly allowed.           | SDK v2          | Allow `mcp-server:8000`.                         |
| **F-022**  | Health             | SDK supports custom HTTP routes alongside `/mcp`.                                                                                    | Docker can use a non-MCP health endpoint.                  | SDK v2          | Add `/healthz`.                                  |
| **F-023**  | MCP evolution      | 2026-07-28 moves toward a stateless request/response core.                                                                           | Avoid unnecessary hidden state.                            | 2026-07-28      | Stateless HTTP is suitable for v1.               |
| **F-024**  | Logging            | Application logging should remain separate from protocol traffic.                                                                    | Simplifies diagnostics.                                    | Current         | Use Python logging/container logs.               |
| **F-025**  | OCI                | OCI Image Specification standardizes image manifests/layers/configuration.                                                           | Keeps image portable.                                      | Current         | Use standard OCI/Docker image.                   |
| **F-026**  | OCI runtime        | OCI Runtime Specification defines container runtime behavior.                                                                        | Avoid runtime-specific assumptions.                        | Current         | Standard Docker runtime.                         |
| **F-027**  | Supply chain       | SLSA 1.2 provides a current build-provenance framework.                                                                              | Makes releases traceable.                                  | v1.2            | Generate provenance.                             |
| **F-028**  | Supply chain       | Docker BuildKit supports SBOM and provenance attestations.                                                                           | Gives visibility into contents/build origin.               | Current         | Enable SBOM + provenance.                        |
| **F-029**  | Container security | NIST SP 800-190 is dedicated container-security guidance.                                                                            | Recognized threat/control baseline.                        | Current         | Use as security reference.                       |
| **F-030**  | Container security | OWASP recommends non-root, read-only filesystems, no-new-privileges, resource controls, scanning, and avoiding Docker socket access. | Directly relevant to MCP container.                        | Current         | Apply controls.                                  |
| **F-031**  | Secure development | NIST SSDF integrates security throughout the SDLC.                                                                                   | Runtime hardening is not enough.                           | SP 800-218 v1.1 | Add CI/review/release gates.                     |
| **F-032**  | GitHub CI          | GitHub recommends immutable references such as full commit SHAs for Actions where appropriate.                                       | Protects CI supply chain.                                  | Current         | Pin important Actions.                           |
| **F-033**  | Dependencies       | GitHub Dependency Review can detect risky dependency changes in pull requests.                                                       | Prevents problematic additions.                            | Current         | Enable Dependency Review.                        |
| **F-034**  | Python packaging   | uv projects use `pyproject.toml`, src layout and a build backend.                                                                    | Makes application installable in runtime image.            | Current         | Use uv_build.                                    |
| **F-035**  | MCP SDK API        | In SDK v2, transport options belong on `run()`/app builders, not the `MCPServer` constructor.                                        | Prevents v1 API usage.                                     | v2              | Put transport/security options on `mcp.run()`.   |
| **F-036**  | HTTP limits        | Streamable HTTP supports explicit request-body limits.                                                                               | Limits oversized request abuse.                            | SDK v2          | Set a suitable v1 limit.                         |

The official Python SDK documents stdio for local subprocesses and Streamable HTTP for deployed servers; its current v2 docs also specify that transport options belong on `run()`.

---

# 5. Design decisions

## 5.1 Application transport

Use:

```text
Streamable HTTP
```

The current SDK describes stdio as the local subprocess transport and Streamable HTTP as the deployment transport. SSE is retained for compatibility but is not the new implementation choice.

**Related Finding IDs:** `F-003, F-004, F-023`

## 5.2 Two separate containers

Use:

```text
mcp-server
    Python MCP application

tunnel-client
    official OpenAI image
```

Do not combine both applications into one custom image.

**Related Finding IDs:** `F-017, F-018, F-019`

## 5.3 Private networking

```text
mcp-server
    │
    └── mcp-internal ─── tunnel-client
                             │
                             └── tunnel-egress ─── Internet
```

The MCP server does not join the Internet-facing network.

**Related Finding IDs:** `F-016, F-017, F-030`

## 5.4 No public MCP port

Normal Compose configuration must not publish port 8000.

Internal endpoint:

```text
http://mcp-server:8000/mcp
```

For debugging only:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

**Related Finding IDs:** `F-016, F-017, F-030`

## 5.5 Stateless HTTP for v1

The first server is a simple tool server and does not require hidden transport session state.

Use:

```text
stateless_http=True
```

Revisit the decision if future tools need more advanced server-initiated interactions.

**Related Finding IDs:** `F-023, F-035`

## 5.6 Development and container Python

Development:

```text
Python 3.14.6
```

Container:

```text
Python 3.14.7
```

Project requirement:

```toml
requires-python = ">=3.14,<3.15"
```

**Related Finding IDs:** `F-007, F-008, F-009`

---

# 6. Current verified local state

These commands have already succeeded:

```bash
uv lock
uv run python --version
uv sync --locked
```

Current environment:

```text
Python                  3.14.6
MCP SDK                 2.2.0
Dependency resolution   44 packages
uv.lock                 valid
uv sync --locked        successful
pytest                  installed
```

Verify MCP version with:

```bash
uv run python -c "from importlib.metadata import version; print(version('mcp'))"
```

Expected:

```text
2.2.0
```

Do not use `mcp.__version__`; this package does not expose that attribute.

**Related Finding IDs:** `F-005, F-007, F-009`

---

# 7. Repository layout

```text
openai-secure-mcp-tunnel/
│
├── README.md
├── .gitignore
│
├── local-mcp-server/
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
│   │   ├── test_security.py
│   │   └── test_server.py
│   │
│   └── allowed_data/
│       ├── .gitkeep
│       └── hello.txt
│
├── docs/
│   ├── architecture.md
│   ├── security.md
│   ├── operations.md
│   └── troubleshooting.md
│
└── .github/
    └── workflows/
        ├── test.yml
        ├── dependency-review.yml
        └── container-release.yml
```

**Related Finding IDs:** `F-009, F-017, F-031, F-034`

---

# 8. Complete implementation runbook

## Step 1 — Verify Docker tooling

Run:

```bash
docker version
docker compose version
docker buildx version
```

### Expected result

All three commands complete successfully.

### Validation

Do not continue until Docker Engine/Daemon, Compose, and Buildx are working.

**Related Finding IDs:** `F-010, F-025, F-026`

---

## Step 2 — Verify Python and uv

Run:

```bash
uv run python --version
```

Expected:

```text
Python 3.14.6
```

Then:

```bash
uv run python -c "from importlib.metadata import version; print(version('mcp'))"
```

Expected:

```text
2.2.0
```

Then:

```bash
uv sync --locked
```

**Related Finding IDs:** `F-005, F-007, F-009`

---

## Step 3 — Set the project Python version

`.python-version` should contain:

```text
3.14.6
```

Verify:

```bash
cat .python-version
```

**Related Finding IDs:** `F-007, F-008`

---

## Step 4 — Configure `pyproject.toml`

Use:

```toml
[project]
name = "local-mcp-server"
version = "0.1.0"
description = "Private local MCP server for OpenAI Secure MCP Tunnel"
readme = "README.md"
requires-python = ">=3.14,<3.15"
dependencies = [
    "mcp[cli]==2.2.0",
    "starlette",
]

[dependency-groups]
dev = [
    "pytest>=9,<10",
    "ruff>=0.13,<0.14",
]

[build-system]
requires = ["uv_build>=0.12.19,<0.13"]
build-backend = "uv_build"
```

Then:

```bash
uv lock
uv sync --locked
```

Do not hand-edit `uv.lock`.

**Related Finding IDs:** `F-008, F-009, F-017, F-034`

---

## Step 5 — Create the Python package

Create:

```text
src/local_mcp_server/__init__.py
src/local_mcp_server/server.py
```

**Related Finding IDs:** `F-034`

---

## Step 6 — Implement the MCP server

Use the SDK v2 API:

```python
from __future__ import annotations

import logging
import os
import platform
import sys
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

mcp = MCPServer(
    "local-computer",
    version="0.1.0",
)

ALLOWED_ROOT = Path(
    os.environ.get("ALLOWED_DATA_DIR", "/app/allowed_data")
).resolve()

MAX_READ_BYTES = 1_000_000


def resolve_allowed_path(relative_path: str) -> Path:
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

    logger.info("Starting local MCP server")

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["mcp-server:8000"],
    )

    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8000,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        max_request_body_size=1 * 1024 * 1024,
        transport_security=transport_security,
    )


if __name__ == "__main__":
    main()
```

Important SDK v2 rule: transport-specific configuration belongs on `mcp.run()`, not `MCPServer(...)`.

**Related Finding IDs:** `F-001, F-004, F-010, F-011, F-021, F-022, F-035, F-036`

---

## Step 7 — Create the controlled data directory

Create:

```text
allowed_data/hello.txt
```

Contents:

```text
Hello from my local MCP server.
```

The directory will later be mounted read-only.

Do not mount the user's entire home directory or host root.

**Related Finding IDs:** `F-010, F-015, F-030`

---

## Step 8 — Run code tests and quality checks before Docker

First format the code:

```bash
uv run ruff format .
```

Then run the validation suite:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

All checks must pass, and **pytest must collect and execute the repository's tests**. A result of `collected 0 items` does not satisfy this step.

Expected outcome:

```text
pytest                  → tests collected and passed
ruff check              → All checks passed
ruff format --check     → already formatted
```

**Related Finding IDs:** `F-019, F-031`

---

## Step 9 — Verify the lockfile

Run:

```bash
uv lock
uv sync --locked
uv tree
```

Confirm that `mcp[cli] 2.2.0` is present.

**Related Finding IDs:** `F-009, F-031`

---

## Step 10 — Create the Dockerfile

```dockerfile
# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.14.7-slim-trixie AS builder

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

COPY pyproject.toml uv.lock .python-version ./
COPY README.md ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-editable

COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable


FROM python:3.14.7-slim-trixie AS runtime

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALLOWED_DATA_DIR=/app/allowed_data \
    LOG_LEVEL=INFO

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

**Related Finding IDs:** `F-007, F-009, F-010, F-011, F-012, F-014, F-034`

---

## Step 11 — Create `.dockerignore`

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
.secrets/
*.secret

allowed_data/*
!allowed_data/.gitkeep

dist
build
*.egg-info
```

**Related Finding IDs:** `F-013, F-030`

---

## Step 12 — Validate the Dockerfile

```bash
docker buildx build --check ./local-mcp-server
```

**Related Finding IDs:** `F-010, F-011, F-031`

---

## Step 13 — Build the MCP image

```bash
docker build \
  --pull \
  -t local-mcp-server:dev \
  ./local-mcp-server
```

For a clean build:

```bash
docker build \
  --pull \
  --no-cache \
  -t local-mcp-server:dev \
  ./local-mcp-server
```

**Related Finding IDs:** `F-010, F-011, F-012`

---

## Step 14 — Inspect the image

Run:

```bash
docker run --rm local-mcp-server:dev \
  python -c "import sys; print(sys.version)"
```

Expected:

```text
3.14.7
```

Then:

```bash
docker run --rm local-mcp-server:dev \
  python -c "from importlib.metadata import version; print(version('mcp'))"
```

Expected:

```text
2.2.0
```

**Related Finding IDs:** `F-005, F-007, F-009`

---

## Step 15 — Create Docker Compose

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
      MCP_STARTUP_WAIT_TIMEOUT: 30s
      MCP_CONNECTION_MAX_TTL: 10m

    secrets:
      - control_plane_api_key

    depends_on:
      mcp-server:
        condition: service_healthy

    networks:
      - mcp-internal
      - tunnel-egress


networks:
  mcp-internal:
    internal: true

  tunnel-egress:


secrets:
  control_plane_api_key:
    file: .secrets/control-plane-api-key
```

**Related Finding IDs:** `F-015, F-016, F-017, F-018, F-019, F-020`

---

## Step 16 — Create the tunnel credential

Create:

```text
.secrets/control-plane-api-key
```

Put only the runtime credential inside.

Add:

```gitignore
.secrets/
```

to `.gitignore`.

**Related Finding IDs:** `F-013, F-020, F-030`

---

## Step 17 — Configure the tunnel ID

Create a local `.env`:

```text
CONTROL_PLANE_TUNNEL_ID=tunnel_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Do not commit it.

Verify:

```bash
docker compose config
```

**Related Finding IDs:** `F-017, F-020`

---

## Step 18 — Start only the MCP container

```bash
docker compose up -d --build mcp-server
```

Then:

```bash
docker compose ps
```

Expected:

```text
mcp-server    healthy
```

**Related Finding IDs:** `F-015, F-022`

---

## Step 19 — Validate `/healthz`

For temporary local testing, publish only to localhost:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

Then:

```bash
curl http://127.0.0.1:8000/healthz
```

Expected:

```json
{"status":"ok"}
```

Remove the port binding for normal operation.

**Related Finding IDs:** `F-016, F-022, F-030`

---

## Step 20 — Validate Streamable HTTP

With the temporary localhost binding:

```text
http://127.0.0.1:8000/mcp
```

If the deployed request arrives with:

```text
Host: mcp-server:8000
```

the configured allowlist should accept it.

A `421 Invalid Host header` indicates a mismatch between the incoming Host value and the transport security allowlist.

**Related Finding IDs:** `F-004, F-021, F-035`

---

## Step 21 — Test with MCP Inspector

Connect MCP Inspector to:

```text
http://127.0.0.1:8000/mcp
```

Verify:

```text
get_system_info
list_allowed_files
read_allowed_text_file
```

**Related Finding IDs:** `F-005, F-015`

---

## Step 22 — Test filesystem security

Test:

```text
hello.txt
../server.py
../../pyproject.toml
/etc/passwd
```

Only the allowed file should succeed.

Also test a symlink inside `allowed_data` pointing outside it.

**Related Finding IDs:** `F-010, F-018, F-030`

---

## Step 23 — Start tunnel-client

After the MCP container is healthy:

```bash
docker compose up -d tunnel-client
```

Then:

```bash
docker compose ps
docker compose logs -f tunnel-client
```

**Related Finding IDs:** `F-017, F-018, F-019`

---

## Step 24 — Verify tunnel readiness

For controlled troubleshooting, optionally expose the tunnel-client health listener only to localhost:

```yaml
environment:
  HEALTH_LISTEN_ADDR: ":8080"

ports:
  - "127.0.0.1:8080:8080"
```

Then:

```bash
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/readyz
```

Do not expose the health listener publicly.

**Related Finding IDs:** `F-017, F-018, F-030`

---

## Step 25 — Create and associate the OpenAI tunnel

Create the tunnel in OpenAI Platform and record its tunnel ID.

Associate it with the intended ChatGPT workspace according to the current OpenAI tunnel configuration.

Use a restricted runtime credential.

**Related Finding IDs:** `F-017, F-018, F-020`

---

## Step 26 — Connect the tunnel to ChatGPT

Configure the ChatGPT custom MCP app/connector to use the tunnel.

Runtime path:

```text
ChatGPT
   ↓
OpenAI Secure MCP Tunnel
   ↓
tunnel-client
   ↓
http://mcp-server:8000/mcp
   ↓
Python MCP server
   ↓
tool
```

**Related Finding IDs:** `F-017, F-019, F-020`

---

## Step 27 — Perform end-to-end read-only tests

Test in this order:

```text
1. get_system_info
2. list_allowed_files
3. read_allowed_text_file("hello.txt")
```

Expected file content:

```text
Hello from my local MCP server.
```

Do not test destructive operations yet.

**Related Finding IDs:** `F-010, F-017, F-019`

---

## Step 28 — Add CI tests

Required checks:

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
docker buildx build --check ./local-mcp-server
```

**Related Finding IDs:** `F-009, F-031`

---

## Step 29 — Add Dependency Review

Enable GitHub Dependency Review for pull requests.

**Related Finding IDs:** `F-031, F-033`

---

## Step 30 — Build release images with SBOM and provenance

Example:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --sbom=true \
  --provenance=mode=max \
  --push \
  -t <registry>/<image>:<tag> \
  ./local-mcp-server
```

**Related Finding IDs:** `F-025, F-027, F-028`

---

## Step 31 — Pin production image digests

For controlled releases:

```dockerfile
FROM python:3.14.7-slim-trixie@sha256:<DIGEST>
```

Also pin release versions/digests for the uv and OpenAI tunnel-client images.

**Related Finding IDs:** `F-011, F-027`

---

## Step 32 — Pin GitHub Actions

Important third-party GitHub Actions should use immutable full commit SHAs where practical.

**Related Finding IDs:** `F-032`

---

# 10. Tool security rules

Every future MCP tool must answer:

```text
1. What resource does it access?
2. What is the minimum permission?
3. Is it read-only?
4. What input validation is required?
5. Can input escape its intended boundary?
6. Can it cause a destructive side effect?
7. Does it expose credentials?
8. Does it need user confirmation?
9. Is concurrent execution safe?
10. How is failure reported?
```

Prefer:

```text
get_project_status(project_name)
list_allowed_files()
read_allowed_text_file(relative_path)
```

Avoid generic high-authority tools such as:

```text
run_shell(command)
execute_python(code)
read_file(path)
delete_file(path)
send_http_request(url)
```

unless a separate security design explicitly justifies them.

**Related Finding IDs:** `F-010, F-018, F-030, F-031`

---

# 11. Security layers

```text
┌─────────────────────────────────────┐
│ Layer 1 — MCP application           │
│                                     │
│ tools                               │
│ validation                          │
│ authorization                       │
│ data boundaries                     │
│ side-effect control                 │
└──────────────────┬──────────────────┘
                   │
┌──────────────────▼──────────────────┐
│ Layer 2 — Container                 │
│                                     │
│ non-root                            │
│ read-only filesystem                │
│ cap_drop=ALL                        │
│ no-new-privileges                   │
│ private network                     │
│ read-only data mount                │
└──────────────────┬──────────────────┘
                   │
┌──────────────────▼──────────────────┐
│ Layer 3 — Tunnel / network          │
│                                     │
│ outbound HTTPS                      │
│ tunnel credential                   │
│ no public MCP port                  │
│ workspace authorization             │
└─────────────────────────────────────┘
```

No individual layer substitutes for another.

**Related Finding IDs:** `F-010, F-015, F-017, F-029, F-030, F-031`

---

# 12. Runtime operations

### Start

```bash
docker compose up -d --build
```

### Status

```bash
docker compose ps
```

### MCP logs

```bash
docker compose logs -f mcp-server
```

### Tunnel logs

```bash
docker compose logs -f tunnel-client
```

### Restart MCP

```bash
docker compose restart mcp-server
```

### Restart tunnel

```bash
docker compose restart tunnel-client
```

### Stop

```bash
docker compose down
```

### Clean rebuild

```bash
docker compose build --no-cache
docker compose up -d
```

**Related Finding IDs:** `F-017, F-018, F-031`

---

# 13. Troubleshooting

## uv selects Python 3.11

Check:

```bash
cat .python-version
```

Expected:

```text
3.14.6
```

Then:

```bash
uv run python --version
```

**Related Finding IDs:** `F-007, F-008`

## uv.lock parse error

During initial setup, if the lockfile is invalid:

```bash
rm uv.lock
uv lock
uv sync --locked
```

Do not hand-edit `uv.lock`.

**Related Finding IDs:** `F-009`

## `mcp.__version__` fails

Use:

```bash
uv run python -c "from importlib.metadata import version; print(version('mcp'))"
```

Expected:

```text
2.2.0
```

**Related Finding IDs:** `F-005`

## Docker build rejects stale lockfile

Run:

```bash
uv lock
uv sync --locked
```

Commit the resulting `uv.lock`.

**Related Finding IDs:** `F-009`

## 421 Invalid Host header

Verify:

```python
TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["mcp-server:8000"],
)
```

and verify the incoming Host header.

**Related Finding IDs:** `F-021, F-035`

## Tunnel cannot reach MCP server

Check:

```text
mcp-server healthy?
mcp-server attached to mcp-internal?
tunnel-client attached to mcp-internal?
MCP_SERVER_URL correct?
port 8000 listening?
Host allowlist correct?
container logs?
```

**Related Finding IDs:** `F-016, F-019, F-021`

## ChatGPT cannot discover the server

Debug from the bottom upward:

```text
Python server
   ↓
MCP container
   ↓
HTTP endpoint
   ↓
Docker network
   ↓
tunnel-client
   ↓
OpenAI tunnel
   ↓
ChatGPT workspace/app
```

**Related Finding IDs:** `F-015, F-017, F-031`

---

# 14. Acceptance checklist

## Development

* [ ] Python 3.14.6 works through uv.
* [ ] `uv.lock` is valid.
* [ ] `uv sync --locked` passes.
* [ ] MCP SDK 2.2.0 is installed.
* [ ] pytest passes.
* [ ] ruff passes.

## MCP

* [ ] `MCPServer` is used.
* [ ] Streamable HTTP is used.
* [ ] `/mcp` works.
* [ ] `/healthz` works.
* [ ] Host allowlist is explicit.
* [ ] Request size limit is configured.
* [ ] Read-only tools work.
* [ ] Path traversal tests pass.
* [ ] Symlink escape test passes.

## Docker

* [ ] Multi-stage build works.
* [ ] Runtime uses Python 3.14.7.
* [ ] Runtime is non-root.
* [ ] Root filesystem is read-only.
* [ ] Capabilities are dropped.
* [ ] `no-new-privileges` is enabled.
* [ ] `allowed_data` is read-only.
* [ ] Docker socket is not mounted.
* [ ] MCP port is not published.
* [ ] MCP container has no direct Internet egress.

## Tunnel

* [ ] Official tunnel-client image is used.
* [ ] Runtime credential is restricted.
* [ ] Credential is supplied through a secret file.
* [ ] `MCP_SERVER_URL` is correct.
* [ ] tunnel-client reaches the MCP server.
* [ ] tunnel-client reaches OpenAI.
* [ ] Tunnel becomes ready.

## ChatGPT

* [ ] Tunnel is associated with the intended workspace.
* [ ] ChatGPT can discover the MCP server.
* [ ] `get_system_info` works.
* [ ] `list_allowed_files` works.
* [ ] `read_allowed_text_file` works.

## Supply chain

* [ ] `uv.lock` is committed.
* [ ] Dependency Review is enabled.
* [ ] Dockerfile validation runs in CI.
* [ ] Image scanning runs in CI.
* [ ] SBOM is generated.
* [ ] Provenance is generated.
* [ ] Important Actions are pinned.
* [ ] Release images can be reproduced/pinned.

---

# 15. Implementation traceability matrix

| Implementation area     | Finding IDs                       |
| ----------------------- | --------------------------------- |
| Python/runtime          | F-005, F-006, F-007, F-008        |
| Project packaging       | F-008, F-009, F-034               |
| MCP protocol/API        | F-001, F-002, F-005, F-011, F-035 |
| Streamable HTTP         | F-004, F-021, F-023, F-035, F-036 |
| Tool security           | F-010, F-018, F-030, F-031        |
| Docker build            | F-009, F-010, F-011, F-012        |
| Docker runtime security | F-014, F-015, F-029, F-030        |
| Docker networking       | F-016, F-017, F-019               |
| OpenAI tunnel           | F-017, F-018, F-019, F-020        |
| Secrets                 | F-013, F-020, F-030               |
| Testing                 | F-015, F-018, F-019, F-031        |
| CI/CD                   | F-028, F-031, F-032, F-033        |
| Supply chain            | F-011, F-025, F-027, F-028        |
| Operations              | F-017, F-018, F-031               |

---

# 16. End-state architecture

```text
                            ChatGPT Web
                                │
                                ▼
                   OpenAI Secure MCP Tunnel
                                │
                         outbound tunnel
                                │
                                ▼
                  ┌────────────────────────┐
                  │ tunnel-client          │
                  │ OpenAI official image  │
                  │ v0.0.15                │
                  └───────────┬────────────┘
                              │
                         mcp-internal
                              │
                     Streamable HTTP
                        /mcp :8000
                              │
                  ┌───────────▼────────────┐
                  │ local-mcp-server       │
                  │ Python 3.14.7          │
                  │ MCP SDK 2.2.0          │
                  │ non-root               │
                  │ read-only root FS      │
                  │ cap_drop=ALL            │
                  │ no-new-privileges      │
                  └───────────┬────────────┘
                              │
                            :ro
                              │
                       allowed_data/
```

Trust boundaries:

```text
ChatGPT
   │
   │ OpenAI tunnel authorization
   ▼
tunnel-client
   │
   │ Docker network isolation
   ▼
MCP server
   │
   │ tool authorization + input validation
   ▼
allowed local resources
```

ChatGPT receives the tools intentionally exposed by the MCP server. It does not receive unrestricted host access.

---

# 17. Official references

### MCP

* [MCP 2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28)
* [MCP 2026-07-28 release](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
* [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
* [Python SDK v2.2.0](https://github.com/modelcontextprotocol/python-sdk/tree/v2.2.0)
* [Running the server](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs/run/index.md)
* [ASGI deployment](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs/run/asgi.md)
* [Deployment](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs/run/deploy.md)
* [Migration guide](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs/migration.md)

### OpenAI

* [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
* [OpenAI tunnel-client](https://github.com/openai/tunnel-client)
* [Docker deployment](https://github.com/openai/tunnel-client/blob/master/docs/deployment/docker.md)
* [Configuration](https://github.com/openai/tunnel-client/blob/master/docs/configuration.md)
* [Connectors](https://github.com/openai/tunnel-client/blob/master/docs/connectors.md)
* [Permissions](https://github.com/openai/tunnel-client/blob/master/docs/permissions.md)
* [Releases](https://github.com/openai/tunnel-client/releases)

### Python / uv

* [Python 3.14.7](https://www.python.org/downloads/release/python-3147/)
* [uv projects](https://docs.astral.sh/uv/concepts/projects/init/)
* [uv syncing and locking](https://docs.astral.sh/uv/concepts/projects/sync/)
* [uv in Docker](https://docs.astral.sh/uv/guides/integration/docker/)
* [uv build backend](https://docs.astral.sh/uv/configuration/build-backend/)

### Docker / standards

* [Docker build best practices](https://docs.docker.com/build/building/best-practices/)
* [Dockerfile reference](https://docs.docker.com/reference/dockerfile/)
* [Docker Compose services](https://docs.docker.com/reference/compose-file/services/)
* [Docker build attestations](https://docs.docker.com/build/metadata/attestations/)
* [OCI Image Specification](https://specs.opencontainers.org/image-spec/)
* [Open Container Initiative](https://opencontainers.org/)

### Security

* [OWASP Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
* [NIST SP 800-190](https://csrc.nist.gov/pubs/sp/800/190/final)
* [NIST SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final)
* [SLSA 1.2](https://slsa.dev/spec/v1.2/)
* [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use)
* [GitHub Dependency Review](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/configure-dependency-review-action)

---

# 18. Final implementation baseline

```text
MCP specification
    2026-07-28

MCP Python SDK
    2.2.0

Development Python
    3.14.6

Container Python
    3.14.7

Project requirement
    >=3.14,<3.15

Python tooling
    uv + uv_build

MCP transport
    Streamable HTTP

HTTP mode
    stateless HTTP for v1

MCP endpoint
    http://mcp-server:8000/mcp

Application image
    python:3.14.7-slim-trixie

Application hardening
    non-root
    read-only root filesystem
    cap_drop=ALL
    no-new-privileges
    read-only data mount

OpenAI tunnel
    Secure MCP Tunnel

Tunnel image
    ghcr.io/openai/tunnel-client:v0.0.15

Secrets
    Docker secret file

Networks
    mcp-internal
    tunnel-egress

Testing
    pytest
    ruff
    MCP Inspector
    docker buildx --check

Supply chain
    uv.lock
    dependency review
    image scanning
    SBOM
    provenance
    pinned CI Actions
```

**Primary architecture:**

> **Python MCP server container → private Streamable HTTP → official OpenAI tunnel-client container → outbound Secure MCP Tunnel → ChatGPT.**
