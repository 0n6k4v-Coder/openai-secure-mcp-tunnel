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
│  │ `workspace-broker`                                                     │  │
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
        ├── application/use-case logic
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
application.sandbox
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
workspace-broker
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

`workspace-broker` is a trusted host-side CLI, not a Compose service. It has access to the host filesystem and Docker CLI because it is the authorization/provisioning boundary for host workspaces.

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

There are three important state categories.

### OpenShell Gateway state

The Gateway stores its SQLite state and credential encryption material under the Compose-mounted MCP configuration directory:

```text
Host: ${MCP_CONFIG_DIR:-/var/lib/local-mcp-server/config}
        │
        ▼
Gateway: /var/lib/local-mcp-server/config
        ├── openshell.db
        └── credentials/
            └── key-encryption-key.bin
```

### MCP installation state

The MCP server stores approval-gated installation state in:

```text
/var/lib/local-mcp-server/installations.json
```

This is backed by the host path configured by `MCP_INSTALLATION_STATE_FILE` and mounted read/write into the MCP container.

### Workspace grants

The host workspace broker stores authorization records in:

```text
${WORKSPACE_GRANTS_DIR:-../.state/workspace-grants}/workspace-grants.json
```

The MCP server receives that directory as read-only and uses opaque `ws_*` IDs to resolve authorized mounts.

## Sandbox security boundary

The sandbox image is built from `deploy/docker/openshell-sandbox/Dockerfile` and is configured by the OpenShell policy generated in `infrastructure/openshell/policy.py`.

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
├── server/
│   ├── app.py              MCP server composition + process entrypoint
│   ├── middleware.py       request/response audit logging
│   ├── health.py           /healthz response
│   └── __main__.py         python -m local_mcp_server.server
│
├── mcp/
│   ├── registration.py     tool registration boundary
│   └── tools.py            MCP tool adapters
│
├── application/
│   ├── credentials.py      application facade for credential operations
│   ├── installation.py     approval + installation orchestration
│   ├── sandbox.py          sandbox application facade
│   └── workspace.py        workspace application facade
│
├── domain/
│   ├── installation.py     installation request state
│   └── workspace.py        host workspace validation rules
│
├── infrastructure/
│   ├── openshell/
│   │   ├── client.py       active OpenShell SDK connection
│   │   ├── sandbox.py      sandbox lifecycle + command execution
│   │   ├── policy.py       sandbox specification/policy
│   │   ├── sandbox_files.py sandbox workspace file operations
│   │   └── credentials.py  OpenShell CLI credential-provider adapter
│   │
│   └── workspace/
│       └── repository.py   workspace grant persistence
│
└── cli/
    ├── main.py             secure-mcp operator CLI
    └── workspace_broker.py trusted host workspace broker
```

### Dependency direction

```text
                    ┌──────────────┐
                    │ MCP adapters │
                    │     CLI      │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Application  │
                    └──────┬───────┘
                           │
                ┌──────────┴──────────┐
                ▼                     ▼
          ┌──────────┐         ┌───────────────┐
          │  Domain  │         │ Infrastructure│
          └──────────┘         └───────┬───────┘
                                       │
                                       ▼
                              OpenShell / Docker /
                              filesystem / subprocess
```

The direction is intentionally asymmetric:

- `mcp/` translates protocol-level requests into application calls.
- `application/` owns use-case orchestration.
- `domain/` contains infrastructure-independent state/rules.
- `infrastructure/` owns OpenShell SDK/CLI, filesystem persistence, and other external-system details.
- `cli/` contains operator interfaces; the workspace broker is trusted host infrastructure rather than an MCP tool implementation.

The application layer should not gain direct Docker or OpenShell SDK calls merely because a use case needs them; those dependencies belong behind the infrastructure boundary.

## Installation execution flow

Software installation is intentionally separate from generic sandbox command execution.

```text
MCP request
   │
   ▼
create_installation_request
   │
   ├── validate package-manager command
   ├── persist pending request
   ▼
approve_installation
   │
   ▼
execute_installation
   │
   ├── consume one approved request
   ├── revalidate command
   ├── OpenShell SandboxClient.exec()
   └── persist completed/failed state
```

The installation command validator only permits approved package-manager entrypoints and requires the corresponding install/add/require operation. It rejects shell chaining and other shell metacharacter syntax before execution.

Generic `execute_sandbox` remains the lower-level sandbox command API. Installation requests must use the approval-gated installation path instead.

## Credential flow

Credential management is also kept outside the generic sandbox command path:

```text
secure-mcp CLI
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

The Python package exposes:

```text
secure-mcp      → local_mcp_server.cli.main:main
workspace-broker → local_mcp_server.cli.workspace_broker:main
```

The first is the operator CLI for Compose/OpenShell/credential operations. The second is the trusted host-side workspace authorization/provisioning tool.

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
| `.secrets/control-plane-api-key` | Docker Compose secret consumed by `tunnel-client` |
| `MCP_CONFIG_DIR` | Gateway persistent OpenShell state/config directory |
| `WORKSPACE_GRANTS_DIR` | Trusted workspace authorization database |
| `MCP_INSTALLATION_STATE_FILE` | Installation approval/execution state |
| `SANDBOX_IMAGE` | OpenShell sandbox workload image |
| `SANDBOX_DEFAULT_CPU` / `SANDBOX_DEFAULT_MEMORY` | Default per-sandbox resource limits |

## Architectural invariants

The following are intentional boundaries of the current design:

1. **OpenAI traffic enters through `tunnel-client`; the MCP server is not directly exposed to the public Internet.**
2. **MCP talks to OpenShell; MCP does not own Docker sandbox lifecycle.**
3. **Only the trusted OpenShell Gateway receives the Docker socket.**
4. **MCP-to-Gateway control traffic uses TLS with client-certificate authentication.**
5. **Host workspace authorization is performed by `workspace-broker`, not by model-supplied host paths.**
6. **The MCP container reads workspace grants but cannot mutate them.**
7. **Sandbox workloads receive an authorized workspace mount rather than arbitrary host filesystem paths.**
8. **Generic command execution is sandbox-scoped; installation uses a separate approval-gated path.**
9. **MCP application code does not directly invoke Docker.**
10. **Sandbox containers are OpenShell-managed workloads, not Compose services.**
