# Failure Record & Post-Mortem

This document records operational, configuration, and architectural failures encountered during development and deployment, detailing the exact root cause, resolution, and preventative guidelines.

---

## FR-001: OpenShell Gateway Unreachable from Host CLI (`host.openshell.internal:8080`)

| Field | Detail |
|---|---|
| **Incident ID** | FR-001 |
| **Component** | Host CLI (`mcpctl sandbox list`, `openshell sandbox list`) / OpenShell Gateway |
| **Date** | 2026-10-07 |
| **Environment** | Linux (WSL2), Docker Compose, OpenShell SDK 0.1.2 |
| **Severity** | Medium (Blocked host-side sandbox CLI queries) |
| **Status** | Resolved (Permanent) |

---

### 1. Incident Description & Symptoms

When running `mcpctl sandbox list` or `openshell sandbox list` from the host shell, the command terminated with exit code `2` (or `1`) and the following gRPC error:

```text
ERROR: Failed to list OpenShell sandboxes: GatewayError: <_InactiveRpcError of RPC that terminated with:
        status = StatusCode.UNAVAILABLE
        details = "errors resolving host.openshell.internal:8080: [field:hostname lookup error:address lookup failed for host.openshell.internal:8080: Domain name not found]"
        debug_error_string = "UNAVAILABLE:errors resolving host.openshell.internal:8080: [field:hostname lookup error:address lookup failed for host.openshell.internal:8080: Domain name not found]"
>
```

---

### 2. Root Cause Analysis

```text
                                HOST NETWORK                                       DOCKER NETWORK
                     ┌────────────────────────────────┐                 ┌─────────────────────────────────┐
                     │                                │                 │                                 │
mcpctl sandbox list ─┼─► reads metadata.json          │                 │                                 │
                     │   endpoint: host.openshell.internal:8080         │                                 │
                     │                 │              │                 │                                 │
                     │                 ▼              │                 │                                 │
                     │        DNS resolution FAILS    │                 │   extra_hosts:                  │
                     │    (Domain name not found)     │                 │   "host.openshell.internal:     │
                     │                                │                 │    host-gateway" (works inside) │
                     │   Correct target:              │  port publish   │                                 │
                     │   https://127.0.0.1:8080 ──────┼─────────────────┼─► deploy-openshell-gateway-1    │
                     │                                │  127.0.0.1:8080 │   (listening on :8080)          │
                     └────────────────────────────────┘                 └─────────────────────────────────┘
```

Three factors combined to cause this failure:

1. **Context Confusion Between Container & Host:**
   * Inside Docker containers, `host.openshell.internal` resolves via Compose `extra_hosts: ["host.openshell.internal:host-gateway"]`.
   * On the **host machine**, `host.openshell.internal` is not registered in system DNS.
   * OpenShell CLI's active gateway metadata (`~/.config/openshell/gateways/local/metadata.json`) had been registered using the container-oriented hostname `https://host.openshell.internal:8080` instead of the host loopback `https://127.0.0.1:8080`.

2. **Ephemeral Nature of Previous Workaround:**
   * An earlier temporary workaround added `127.0.0.1 host.openshell.internal` manually to `/etc/hosts`.
   * In WSL2, `/etc/hosts` is automatically overwritten and regenerated on every WSL restart/reboot. When the system restarted, the workaround was lost and hostname resolution broke again.

3. **Certificate SAN Availability:**
   * The OpenShell Gateway server TLS certificate already contains valid Subject Alternative Names (SANs) for both `127.0.0.1` and `localhost`:
     ```text
     X509v3 Subject Alternative Name:
         DNS:openshell, DNS:localhost, IP Address:127.0.0.1, DNS:host.openshell.internal, DNS:openshell-gateway
     ```
   * Using `https://127.0.0.1:8080` completely satisfies TLS validation without needing custom hostnames or DNS overrides.

---

### 3. Resolution (Permanent Fix)

The fix directly updates the persistent user configuration on the host filesystem:

#### Step 1: Update Gateway Endpoint
Edit `~/.config/openshell/gateways/local/metadata.json`:

```json
{
  "name": "local",
  "gateway_endpoint": "https://127.0.0.1:8080",
  "is_remote": false,
  "gateway_port": 0,
  "auth_mode": "mtls"
}
```

*Alternatively, register it via CLI:*
```bash
openshell gateway add https://127.0.0.1:8080 --local --name local
```

#### Step 2: Verification
Verify that the gateway is recognized and accessible:

```bash
# 1. Verify registered gateway endpoint
openshell gateway list

# Expected output:
#   NAME   ENDPOINT                TYPE   SOURCE  AUTH
# * local  https://127.0.0.1:8080  local  user    mtls

# 2. Verify mcpctl sandbox list
mcpctl sandbox list

# Expected output:
# NAME         STATUS  PROFILE  HOST WORKSPACE ID                    ID                                    PACKAGE CONFIG  INSTALLATION
# -----------  ------  -------  -----------------------------------  ------------------------------------  --------------  ------------
# jupyter-dev  3       default  ws_3d3f2ed2a53a4e6a8fd34cf6f13352be  3eca86f0-9eba-4669-8ba6-b997a4423a34  CONFIGURED      NONE

# 3. Verify mcpctl status
mcpctl status
```

---

### 4. Why This Fix Is Permanent

* **Storage Location:** `~/.config/openshell/gateways/local/metadata.json` is located on the host Linux filesystem (`ext4`) and persists across reboots, container restarts, and WSL resets.
* **No DNS / `/etc/hosts` Dependency:** Pointing directly to `127.0.0.1:8080` uses the loopback IP directly, making it immune to `/etc/hosts` regeneration.
* **Lifecycle Command Safety:** `mcpctl` lifecycle commands (`start`, `stop`, `restart`, `repair`, `setup`) only sync TLS keys into `~/.config/openshell/gateways/local/mtls/` and do not alter or overwrite `metadata.json`.

---

### 5. Prevention Guidelines

1. **Host-Side Gateway Registrations Must Use Loopback:**
   * Always use `https://127.0.0.1:<PORT>` for host-side CLI operations targeting locally published Docker services.
   * Reserve Docker-specific hostnames (`host.openshell.internal`, `host.docker.internal`, `openshell-gateway`) strictly for container-to-host or container-to-container communication.

2. **Never Rely on Manual `/etc/hosts` Edits in WSL2:**
   * WSL2 wipes and regenerates `/etc/hosts` on startup unless `generateHosts = false` is configured in `/etc/wsl.conf`.
   * Configure services and clients with native loopback addresses (`127.0.0.1`) instead of patching hosts files.

3. **Ensure TLS SANs Include Loopback:**
   * Whenever generating TLS certificates for local developer services, always ensure `127.0.0.1` and `localhost` are included in the server SAN list (as implemented in `src/local_mcp_server/infrastructure/openshell/tls.py`).

---

## FR-002: Docker Desktop WSL2 Stale Bind-Mount Volume Invalidation (`ContainerCreateFailed`)

| Field | Detail |
|---|---|
| **Incident ID** | FR-002 |
| **Component** | Workspace Broker (`workspace_broker.py`) / OpenShell Docker Driver / Sandbox Recreate |
| **Date** | 2026-10-07 |
| **Environment** | Linux (WSL2 Ubuntu) with Docker Desktop on Windows |
| **Severity** | High (Prevented creating or recreating sandboxes attached to host workspaces) |
| **Status** | Resolved (Permanent Self-Healing Implementation) |

---

### 1. Incident Description & Symptoms

When running `mcpctl sandbox recreate --yes <sandbox-name>` after a host reboot or Docker Desktop restart, sandbox recreation failed with:

```text
ERROR: Failed to create sandbox 'jupyter-dev': SandboxError: sandbox jupyter-dev entered error phase
```

Inspecting `openshell sandbox get jupyter-dev` revealed:

```text
Conditions:
  - Ready: False (ContainerCreateFailed) - create docker sandbox container failed:
    Docker responded with status code 500: failed to populate volume:
    error while mounting volume '/var/lib/docker/volumes/mcp-ws-3d3f2ed2a53a4e6a8fd34cf6f13352be/_data':
    failed to mount local volume:
    mount /run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/Ubuntu/55d2a49dc84e756f9975fff34790a8d86152f9efc216e25c2ac8769d6c01f451:/var/lib/docker/volumes/mcp-ws-3d3f2ed2a53a4e6a8fd34cf6f13352be/_data, flags: 0x1000: no such file or directory
```

---

### 2. Root Cause Analysis

```text
       WSL2 Ubuntu Filesystem                              Docker Desktop VM
 ┌────────────────────────────────┐                 ┌─────────────────────────────┐
 │ /home/.../workspace            │                 │                             │
 │       ▲                        │  dynamic mount  │                             │
 │       │                        ├─────────────────┼─► /run/desktop/mnt/.../<hash>
 │       │                        │                 │           ▲                 │
 │       │                        │                 │           │ (stale path)    │
 │   host directory               │                 │           │                 │
 │   persists across restarts     │                 │   Docker volume mcp-ws-...  │
 │                                │                 │   (type=none, o=bind)       │
 └────────────────────────────────┘                 └─────────────────────────────┘
                                                    WSL/Docker restart invalidates
                                                    the dynamic path hash in VM!
```

1. **Docker Desktop WSL2 Architecture:**
   * In Docker Desktop on Windows, the Docker daemon runs inside a dedicated lightweight VM (`docker-desktop`), separate from the user's WSL2 distribution (`Ubuntu`).
   * Bind-mount volumes created with `docker volume create --opt type=none --opt o=bind --opt device=/path/in/wsl` rely on a dynamic mount bridge inside Docker's VM: `/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/Ubuntu/<hash>`.
2. **Ephemeral Mount Hashes Across Restarts:**
   * When Docker Desktop or Windows restarts, that dynamic mount hash is invalidated and wiped from the Docker VM.
   * However, Docker's volume database still retains the volume record. `docker volume inspect` succeeds with return code `0`, but any attempt to mount the volume fails with HTTP 500 (`no such file or directory`).
3. **Missing Health Verification:**
   * Previously, `_create_host_backed_volume` only checked `if _docker_volume_exists(volume_name): return`. Because `inspect` succeeded, the broker assumed the volume was healthy and never refreshed the dead bind mount.

---

### 3. Resolution (Permanent Self-Healing Fix)

1. **Active Volume Health Probe (`_docker_volume_healthy`):**
   * Implemented in `src/local_mcp_server/cli/workspace_broker.py`.
   * Inspects the volume and executes a lightweight mount probe container (`docker run --rm --network none -v <vol>:/probe ... true`).
   * If mounting fails with error 500 or "no such file or directory", reports the volume as unhealthy.
2. **Automatic Stale-Volume Refresh in `_create_host_backed_volume`:**
   * If a volume exists but fails the health probe, it is automatically removed (`docker volume rm`) and recreated with the host directory bind.
   * Because it is a bind mount to a host directory, removing Docker's volume record never deletes the user's host files.
3. **Self-Healing Hook in `create_sandbox` and `recreate_sandbox`:**
   * Added `ensure_workspace_volume(workspace_id)` call in `src/local_mcp_server/infrastructure/openshell/sandbox.py`.
   * Automatically verifies and repairs the workspace's Docker volume before OpenShell attempts to create the sandbox container.

