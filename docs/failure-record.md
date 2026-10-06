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
