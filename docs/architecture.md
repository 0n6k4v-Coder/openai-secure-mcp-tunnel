# Architecture

This document describes the **current runtime and code topology** of the project as implemented in `deploy/compose.yaml` and `src/local_mcp_server/`.

The important architectural boundary is that the project has two different execution planes:

- **Control / application plane:** OpenAI Secure MCP Tunnel, the MCP server, OpenShell Gateway, and the trusted host-side workspace broker.
- **Workload plane:** OpenShell-managed sandbox containers created by the Gateway's Docker compute driver.

Sandbox containers are **not Docker Compose services** and are not addressed directly by the MCP client. The MCP server talks to the OpenShell Gateway; the Gateway owns sandbox lifecycle and uses the Docker daemon to realize the workload.

## Runtime topology

```text
                               OpenAI Control Plane
                                        │
                              outbound tunnel connection
                                        │
                                        ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│ Docker Compose host                                                            │
│                                                                               │
│  ┌──────────────────────┐       mcp-internal       ┌──────────────────────┐  │
│  │    tunnel-client     │ ───────────────────────► │     mcp-server       │  │
│  │ OpenAI tunnel client │                          │ Python MCP server    │  │
│  │                      │                          │ :8000 /mcp           │  │
│  └──────────┬───────────┘                          └──────────┬───────────┘  │
│             │                                               │              │
│             │ tunnel-egress                                 │ mTLS/TLS     │
│             │                                               │              │
│             │                              openshell-internal│              │
│             │                                               ▼              │
│             │                                  ┌────────────────────────┐   │
│             │                                  │   OpenShell Gateway    │   │
│             │                                  │                        │   │
│             │                                  │ sandbox control plane  │   │
│             │                                  │ policy / registry      │   │
│             │                                  │ Docker compute driver  │   │
│             │                                  └───────────┬────────────┘   │
│             │                                              │                │
│             │                                    /var/run/docker.sock       │
│             │                                              │                │
│             │                                              ▼                │
│             │                                  ┌────────────────────────┐   │
│             │                                  │ Docker-managed         │   │
│             │                                  │ OpenShell sandbox      │   │
│             │                                  │ workloads              │   │
│             │                                  │                        │   │
│             │                                  │ Supervisor + workload  │   │
│             │                                  │ filesystem/policy      │   │
│             │                                  └───────────┬────────────┘   │
│             │                                              │                │
│             │                                      workspace volume         │
│             │                                              │                │
│             │                                              ▼                │
│             │                                  Host-backed Docker volume     │
│             │                                  authorized by workspace grant │
│             │                                                               │
│  ┌──────────▼────────────────────────────────────────────────────────────┐  │
│  │ Trusted host-side workspace broker                                    │  │
│  │ `mcpctl workspace`                                                     │  │
│  │                                                                        │  │
│  │ host path validation → ACL provisioning → Docker volume → grant DB    │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Compose services

The Compose deployment contains exactly three application services:

| Service | Role | Network exposure |
|---|---|---|
| `tunnel-client` | Maintains the outbound OpenAI Secure MCP Tunnel and forwards MCP traffic to `mcp-server`. | `mcp-internal`, `tunnel-egress` |
| `mcp-server` | Hosts the MCP protocol endpoint, tool registry, application logic, workspace authorization reads, and OpenShell SDK client. | `mcp-internal`, `openshell-internal`, `mcp-host-publish` |
| `openshell-gateway` | Owns OpenShell sandbox lifecycle and uses the Docker compute driver to create/manage sandbox workloads. | `openshell-internal`, `openshell-gateway` |

The project no longer has a separate `terminal-executor` service. Arbitrary command execution is performed through OpenShell sandbox APIs instead.

OpenShell-created sandbox containers are **runtime workloads**, not entries in `deploy/compose.yaml`.

## Request and execution flows

### 1. MCP request flow

```text
ChatGPT / OpenAI Control Plane
        │
        ▼
  tunnel-client
        │
        │ http://mcp-server:8000/mcp
        ▼
    mcp-server
        │
        ├── MCP transport + tool registry
        │
        ├── domain services + MCP tool adapters
        │
        └── OpenShell SDK
                 │
                 │ HTTPS + client certificate
                 ▼
          OpenShell Gateway
                 │
                 ▼
        target sandbox workload
```

The MCP server uses Streamable HTTP at `/mcp`, runs stateless HTTP mode, and listens on `0.0.0.0:8000` inside its container. Compose publishes that port only on host loopback (`127.0.0.1:8000`). The tunnel client reaches the server through the private `mcp-internal` network rather than through the host-published port.

### 2. Sandbox lifecycle flow

```text
MCP tool
  │
  ▼
sandbox.tools
  │
  ▼
sandbox.service
  │
  ▼
infrastructure.openshell.sandbox
  │
  ▼
OpenShell SandboxClient.from_active_cluster()
  │
  │ HTTPS/mTLS
  ▼
OpenShell Gateway
  │
  │ Docker compute driver
  ▼
Sandbox container
```

The MCP server does not create Docker containers directly. It asks OpenShell to create, inspect, execute in, or delete a sandbox. The Gateway is the component that owns the Docker driver and Docker socket.

Sandbox creation additionally requires an opaque `host_workspace_id`. The trusted workspace grant database resolves that capability to a pre-authorized Docker volume, mount target, and access mode. The model/client never supplies an arbitrary host path to the sandbox API.

### 3. Workspace authorization flow

```text
Trusted host operator
        │
        ▼
mcpctl workspace
        │
        ├── canonicalize + validate host path
        ├── reject protected host paths
        ├── validate protected-path permissions
        ├── provision ACL for sandbox UID/GID
        ├── create host-backed Docker volume
        └── write opaque ws_* grant
                    │
                    ▼
        workspace-grants.json
                    │
             read-only mount
                    │
                    ▼
              mcp-server
                    │
                    ▼
             OpenShell policy
                    │
                    ▼
        sandbox workspace mount
```

`mcpctl workspace` is the trusted host-side CLI interface, not a Compose service. It delegates to the internal workspace broker implementation, which has access to the host filesystem and Docker CLI because it is the authorization/provisioning boundary for host workspaces.

Inside `mcp-server`, `WORKSPACE_GRANTS_READ_ONLY=true` prevents the MCP process from modifying the grant database. The server can resolve an existing capability but cannot create a new host authorization by itself.

## Network topology

Compose defines four networks:

```text
mcp-internal
    tunnel-client <──────► mcp-server
    internal: true

openshell-internal
    mcp-server <──────────► openshell-gateway
    internal: true

mcp-host-publish
    mcp-server :8000 ────► 127.0.0.1:8000 on the host

openshell-gateway
    openshell-gateway :8080/:8081 ───► 127.0.0.1 on the host

tunnel-egress
    tunnel-client ───────► external OpenAI control-plane connectivity
```

The Gateway's normal API is published only on host loopback (`127.0.0.1:8080`), and its health endpoint is published only on `127.0.0.1:8081`. Container-to-container MCP/Gateway traffic uses `openshell-internal` and does not depend on the host-published Gateway port.

The MCP server uses the OpenShell SDK's active-cluster configuration rather than embedding a plaintext Gateway URL in application code. Compose registers the local Gateway as `https://openshell-gateway:8080` and mounts the client mTLS material under the SDK configuration directory.

## TLS and authentication boundary

The Gateway is configured for authenticated TLS/mTLS:

```text
mcp-server
    │
    │ client certificate + CA validation
    │ HTTPS
    ▼
openshell-gateway:8080
    │
    ├── server certificate
    ├── client CA validation
    ├── mTLS authentication enabled
    └── unauthenticated users disabled
```

Relevant Gateway settings are in `deploy/openshell/gateway.toml`:

- `disable_tls = false`
- Gateway certificate/key are mounted from `.secrets/openshell-tls/gateway`.
- The Gateway validates clients against the configured CA.
- `allow_unauthenticated_users = false`.
- OpenShell mTLS authentication is enabled.
- Gateway JWT signing/public-key material is mounted separately under `/etc/openshell/jwt`.

The MCP server's SDK registry metadata is in `deploy/openshell/gateway-metadata.json` and declares the Gateway as `auth_mode: "mtls"`.

## Runtime storage

There are four important storage categories.

### MCP client configuration

User-specific MCP client configuration follows the XDG configuration hierarchy:

```text
Host: ${XDG_CONFIG_HOME:-$HOME/.config}/local-mcp-server/
        │
        └── mcp-clients/
            └── openai/
                ├── config.yaml
                └── credentials
```

The OpenAI tunnel ID is stored in `config.yaml`. The control-plane API key is stored separately in `credentials`. Both files are created with mode `0600`, and the containing application directories are required to be private to the user.

The tunnel client receives `config.yaml` as a read-only bind mount at `/etc/tunnel-client/openai.yaml`. The API key is provided separately through the Compose secret `CONTROL_PLANE_API_KEY`.

This user-local MCP client configuration is intentionally separate from the OpenShell Gateway's mutable application state.

### OpenShell Gateway state

The Gateway stores its SQLite state and credential encryption material under the Compose-mounted state directory:

```text
Host: ${MCP_CONFIG_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/local-mcp-server/config}
        │
        ▼
Gateway: /var/lib/local-mcp-server/config
        ├── openshell.db
        └── credentials/
            └── key-encryption-key.bin
```

`MCP_CONFIG_DIR` therefore identifies Gateway/OpenShell state; it is not the storage location for MCP client credentials.

### Workspace grants

The host workspace broker stores authorization records in:

```text
${WORKSPACE_GRANTS_DIR:-../.state/workspace-grants}/workspace-grants.json
```

The MCP server receives that directory as read-only and uses opaque `ws_*` IDs to resolve authorized mounts.

## Sandbox security boundary

The sandbox image is built from `deploy/docker/openshell-sandbox/Dockerfile` and is configured by the OpenShell policy generated in `sandbox/policy.py`.

Current sandbox defaults include:

- Image: `local-mcp-openshell-sandbox:1.0.0`.
- CPU: `SANDBOX_DEFAULT_CPU`, default `1`.
- Memory: `SANDBOX_DEFAULT_MEMORY`, default `1Gi`.
- Working directory included in the filesystem policy.
- Read-only paths including `/bin`, `/usr`, `/lib`, `/proc`, `/etc`, and `/var/log`.
- Writable `/tmp`, `/dev/null`, and the authorized workspace target.
- Landlock compatibility set to `hard_requirement`.
- Sandbox process limit configured by the Gateway Docker driver as `2048` PIDs.

The sandbox image itself is intentionally separate from the MCP server image. The MCP server is a small Python runtime; the sandbox image contains the developer/runtime tooling needed by workload commands, including Python, Node/npm, Git, ripgrep, and Playwright.

## Python application topology

The current Python package is organized around runtime responsibility:

```text
src/local_mcp_server/
│
├── workspace/                 # workspace domain
│   ├── domain.py              # host workspace validation rules
│   ├── service.py             # workspace application facade
│   ├── tools.py               # workspace MCP tools
│   └── repository.py          # workspace grant persistence
│
├── sandbox/                   # sandbox domain
│   ├── policy.py              # sandbox specification/policy
│   ├── service.py             # sandbox application facade
│   └── tools.py               # sandbox MCP tools
│
├── credentials/               # credential domain
│   └── service.py             # credential application facade
│
├── infrastructure/            # external-system adapters
│   └── openshell/
│       ├── client.py          # active OpenShell SDK connection
│       ├── sandbox.py         # OpenShell sandbox lifecycle + execution
│       ├── sandbox_files.py   # OpenShell workspace file operations
│       └── credentials.py     # OpenShell CLI credential-provider adapter
│
├── mcp/
│   ├── registration.py        # MCP tool composition root
│   └── __init__.py
│
├── server/
│   ├── app.py                 # MCP server composition + process entrypoint
│   ├── middleware.py          # request/response audit logging
│   ├── health.py              # /healthz response
│   └── __main__.py            # python -m local_mcp_server.server
│
└── cli/
    ├── main.py                # mcpctl operator CLI
    └── workspace_broker.py    # trusted host workspace broker
```

### Domain-first dependency direction

```text
                     ┌──────────────────────┐
                     │      MCP tools       │
                     │ workspace / sandbox  │
                     │ installation / ...   │
                     └──────────┬───────────┘
                                │
                                ▼
                     ┌──────────────────────┐
                     │ Domain service layer │
                     │  use-case / rules   │
                     └──────────┬───────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
             ┌──────────────┐       ┌────────────────┐
             │ Domain model │       │ Infrastructure │
             │ + repository │       │ OpenShell/etc. │
             └──────────────┘       └───────┬────────┘
                                            │
                                            ▼
                                  OpenShell / Docker /
                                  filesystem / subprocess
```

The structure is intentionally domain-first: everything a developer needs for one business capability is discoverable under that capability's directory.

- workspace/, sandbox/, and future domains such as news/ own their domain-specific tools, services, models, and persistence interfaces.
- tools.py in a domain is the MCP adapter for that domain; it should stay thin and delegate to service.py.
- service.py owns application/use-case orchestration for that domain.
- domain.py contains infrastructure-independent business state and validation where the domain needs it.
- repository.py contains domain-specific persistence logic where the domain needs durable state.
- infrastructure/ contains adapters for OpenShell and other external systems. It should not become a second home for domain business rules.
- mcp/registration.py only composes the domain tool registrars into the MCP server.
- server/ owns transport/process concerns, while cli/ owns operator-facing interfaces.

When a new business capability is added, it should normally start as a new top-level domain directory rather than scattering files across application/, domain/, and mcp/. For example, a future news/ domain can begin with only the files it actually needs (service.py, tools.py, and optionally domain.py or repository.py) and grow incrementally.

## Credential flow

Credential management is also kept outside the generic sandbox command path:

```text
mcpctl CLI
      │
      ▼
infrastructure.openshell.credentials
      │
      ▼
OpenShell CLI
      │
      ▼
OpenShell Gateway credential/provider subsystem
      │
      ▼
sandbox provider attachment
```

Credential values are read interactively by the CLI and passed to the OpenShell CLI subprocess through its environment. The MCP server does not expose credential values through MCP tool results.

## Entrypoints and build boundaries

### MCP server image

`deploy/docker/mcp-server/Dockerfile` builds the Python application with uv and starts:

```text
python -m local_mcp_server.server
```

The runtime image is non-root (`10001:10001`), read-only in Compose, drops all Linux capabilities, enables `no-new-privileges`, and provides a writable `/tmp` tmpfs with `noexec,nosuid,nodev`.

### OpenShell sandbox image

`deploy/docker/openshell-sandbox/Dockerfile` builds the workload environment separately. It runs as the same non-root UID/GID `10001:10001` and starts idle with `sleep infinity`; OpenShell executes requested commands inside the managed sandbox.

### Operator CLIs

The Python package exposes one operator CLI entry point:

```text
mcpctl → local_mcp_server.cli.completion:mcpctl_main
```

It handles Compose/OpenShell/credential operations and exposes workspace authorization through `mcpctl workspace`. The trusted host-side workspace authorization/provisioning implementation remains in `local_mcp_server.cli.workspace_broker`, but it is no longer registered as a separate executable.

## Configuration map

| File / variable | Runtime responsibility |
|---|---|
| `deploy/compose.yaml` | Container services, networks, mounts, secrets, health checks |
| `deploy/openshell/gateway.toml` | Gateway TLS, authentication, JWT, Docker driver, persistent state |
| `deploy/openshell/gateway-metadata.json` | MCP container's local OpenShell Gateway registration |
| `deploy/openshell/policies/default.yaml` | Reference sandbox filesystem policy |
| `.env` | Local deployment variables and tunnel ID |
| `.secrets/openshell-tls/gateway` | Gateway server certificate/key/CA material |
| `.secrets/openshell-tls/client` | MCP/OpenShell client mTLS material |
| `${XDG_CONFIG_HOME:-$HOME/.config}/local-mcp-server/mcp-clients/openai/config.yaml` | User-local OpenAI MCP tunnel client configuration |\n| `${XDG_CONFIG_HOME:-$HOME/.config}/local-mcp-server/mcp-clients/openai/credentials` | User-local OpenAI control-plane API key consumed as a Docker secret |\n| `.secrets/control-plane-api-key` | Docker Compose secret consumed by `tunnel-client` |
| `XDG_CONFIG_HOME` | User-local MCP client configuration root; defaults to `$HOME/.config` |\n| `MCP_CONFIG_DIR` | Gateway persistent OpenShell state/config directory |
| `WORKSPACE_GRANTS_DIR` | Trusted workspace authorization database |
| `SANDBOX_IMAGE` | OpenShell sandbox workload image |
| `SANDBOX_DEFAULT_CPU` / `SANDBOX_DEFAULT_MEMORY` | Default per-sandbox resource limits |

## Architectural invariants

The following are intentional boundaries of the current design:

1. **OpenAI traffic enters through `tunnel-client`; the MCP server is not directly exposed to the public Internet.**
2. **MCP talks to OpenShell; MCP does not own Docker sandbox lifecycle.**
3. **Only the trusted OpenShell Gateway receives the Docker socket.**
4. **MCP-to-Gateway control traffic uses TLS with client-certificate authentication.**
5. **Host workspace authorization is performed through `mcpctl workspace`, not by model-supplied host paths.**
6. **The MCP container reads workspace grants but cannot mutate them.**
7. **Sandbox workloads receive an authorized workspace mount rather than arbitrary host filesystem paths.**
8. **Generic command execution is sandbox-scoped and governed by OpenShell policy.**
9. **MCP application code does not directly invoke Docker.**
10. **Sandbox containers are OpenShell-managed workloads, not Compose services.**
