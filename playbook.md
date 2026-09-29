# OpenAI Secure MCP Tunnel

## Complete ChatGPT Web Setup Runbook

**Document purpose:** Connect a local/private MCP server on your computer or private network to ChatGPT Web without exposing the MCP server to the public Internet.

**Verified against:** OpenAI documentation and the official `openai/tunnel-client` repository, September 29, 2026.

---

# 1. Scope and important limitation

Secure MCP Tunnel is an **MCP connectivity mechanism**.

It does **not** by itself give ChatGPT:

* arbitrary shell access
* unrestricted filesystem access
* remote desktop control
* access to every process on your computer
* access to your camera/microphone
* arbitrary network access

Those capabilities exist only to the extent that **your MCP server exposes corresponding tools**.

For example, you could create an MCP server exposing narrowly defined operations such as:

```text
get_project_status()
read_allowed_file()
run_backup()
query_local_database()
restart_application()
```

ChatGPT can invoke only the tools actually exposed by that MCP server and permitted by the ChatGPT app configuration.

OpenAI explicitly documents that ChatGPT cannot connect directly to a local MCP server; a private/local MCP server should use Secure MCP Tunnel instead.

---

# 2. High-level setup sequence

Follow this order. Do not skip ahead.

```text
1. Confirm ChatGPT/workspace eligibility
        ↓
2. Confirm your local MCP server
        ↓
3. Create/configure the OpenAI tunnel
        ↓
4. Create a restricted runtime API key
        ↓
5. Install tunnel-client
        ↓
6. Configure tunnel-client
        ↓
7. Run tunnel-client doctor
        ↓
8. Start tunnel-client
        ↓
9. Verify /readyz and /ui
        ↓
10. Add the tunnel to ChatGPT
        ↓
11. Scan/discover the MCP tools
        ↓
12. Test read-only functionality
        ↓
13. Test write actions separately
        ↓
14. Harden and operationalize
        ↓
15. Document recovery/teardown
```

The ordering matters because ChatGPT connector discovery depends on a functioning tunnel runtime. OpenAI specifically recommends keeping `tunnel-client run ...` healthy while creating/testing the app.

---

# 3. Prerequisites

You need all of the following:

1. A local/private MCP server that `tunnel-client` can reach.
2. A `tunnel_id`.
3. A runtime API key for `tunnel-client`.
4. Permission to use the tunnel.
5. A supported ChatGPT workspace/account with developer-mode/custom-app access.
6. A computer/network that can make outbound HTTPS connections to OpenAI.

OpenAI's tunnel documentation lists the first three as the fundamental prerequisites.

## Network prerequisite

The host running `tunnel-client` needs:

```text
Outbound:
    api.openai.com:443

Optional when control-plane mTLS is configured:
    mtls.api.openai.com:443

Local/private:
    tunnel-client → your MCP server
```

No inbound Internet connection to your MCP server is required.

---

# 4. Confirm your ChatGPT plan/workspace supports this

Current OpenAI documentation says:

* ChatGPT Business and Enterprise/Edu support developer mode/custom MCP apps on the web.
* Pro users can connect MCPs with read/fetch permissions in developer mode.
* Full MCP, including write/modify capabilities, is currently rolling out to Business and Enterprise/Edu.
* MCP apps are web-only, not mobile.

Availability and permissions are controlled by the workspace/account.

For a managed Business/Enterprise/Edu workspace, an administrator may have to enable developer mode or grant the required RBAC permissions first.

### Check this before doing technical setup

Open ChatGPT Web and look for the developer/custom-app functionality in your workspace.

The current UI terminology is changing between documentation and product surfaces: current Help Center documentation refers to **Apps**, while the Secure MCP Tunnel operator guide currently refers to **Connectors** and `Connection: Tunnel`. Treat the functional option—creating a custom MCP app/connector using a Tunnel—as the important part, rather than relying on one exact menu label.

---

# 5. Confirm that you actually have an MCP server

This is the most important conceptual checkpoint.

You need something like:

```text
Local computer
    │
    ├── tunnel-client
    │
    └── MCP server
           │
           ├── tool A
           ├── tool B
           └── tool C
```

The MCP server may communicate using:

### Option A — stdio

`tunnel-client` starts the MCP process itself.

Example:

```bash
python /path/to/server.py
```

### Option B — HTTP

Your MCP server is already running, for example:

```text
http://127.0.0.1:8787/mcp
```

or:

```text
https://mcp.internal.example.com/mcp
```

OpenAI's tunnel-client supports both stdio and HTTP MCP targets.

---

# 6. Recommended first test: use the embedded MCP stub

Before connecting your real local system, it is useful to prove that:

```text
OpenAI tunnel
      ↓
tunnel-client
      ↓
MCP protocol
      ↓
ChatGPT
```

works independently of your application.

The official tunnel-client provides an embedded MCP stub specifically for this type of validation.

This prevents you from debugging two systems at once.

---

# 7. Create the OpenAI tunnel

Open the OpenAI Platform tunnel-management area.

Use:

**Platform → Organization → Tunnels**

OpenAI's operator documentation currently identifies the tunnel-management location as:

`platform.openai.com/settings/organization/tunnels`

Create a tunnel and record:

```text
TUNNEL_ID
```

It will look approximately like:

```text
tunnel_0123456789abcdef0123456789abcdef
```

The tunnel ID is the shared identity used by:

* the OpenAI tunnel service
* `tunnel-client`
* ChatGPT

The local runtime and ChatGPT must use the same tunnel ID.

---

# 8. Associate the tunnel with the correct ChatGPT workspace

This step is easy to miss.

A tunnel can exist in the Platform organization but still not appear in ChatGPT.

When configuring the tunnel, associate it with the **ChatGPT workspace that is supposed to use it**.

OpenAI explicitly notes that a tunnel associated only with a Platform organization does not automatically appear inside an Enterprise/Edu ChatGPT workspace.

Think of the relationship as:

```text
Platform organization
        +
ChatGPT workspace
        +
Tunnel ID
        ↓
ChatGPT can discover/use tunnel
```

---

# 9. Understand the permissions before creating API keys

OpenAI currently separates tunnel permissions into three main capabilities:

| Permission     | Purpose                    |
| -------------- | -------------------------- |
| Tunnels Read   | View tunnel metadata       |
| Tunnels Manage | Create/edit/delete tunnels |
| Tunnels Use    | Run/use an existing tunnel |

Runtime users normally need:

```text
Tunnels Read
Tunnels Use
```

Tunnel administrators who create/edit tunnels need:

```text
Tunnels Read
Tunnels Manage
```

and also `Use` when they personally run the daemon or attach ChatGPT connectors.

---

# 10. Create a restricted runtime API key

This is the key that the long-running `tunnel-client` process uses.

Open:

**Platform → Organization → API Keys**

The official tunnel-client guide recommends creating a **Restricted** runtime key and granting:

```text
Tunnels Read
Tunnels Use
```

Do not use an unrestricted "All" key for the long-lived daemon. Do not substitute an admin key.

Save the key securely.

You will use it as:

```bash
export CONTROL_PLANE_API_KEY="sk-..."
```

Do not put the actual secret in:

* shell history where practical
* source code
* Git repositories
* public configuration files
* screenshots
* ChatGPT messages

---

# 11. Understand the two different key types

There are two different credentials:

## Runtime key

Environment variable:

```text
CONTROL_PLANE_API_KEY
```

Purpose:

```text
tunnel-client doctor
tunnel-client run
polling
response posting
```

## Admin key

Environment variable:

```text
OPENAI_ADMIN_KEY
```

Purpose:

```text
tunnel-client admin tunnels create
tunnel-client admin tunnels list
tunnel-client admin tunnels update
tunnel-client admin tunnels delete
```

Do not use `OPENAI_ADMIN_KEY` as the long-lived daemon credential.

For a normal first setup, you may not need an admin key at all if you create the tunnel through the Platform UI.

---

# 12. Download tunnel-client

Use one of these official sources:

1. The download provided by the OpenAI Platform Tunnels page.
2. The latest release from the official OpenAI GitHub repository.

OpenAI specifically recommends keeping automation pointed at the latest-release mechanism rather than hard-coding a release URL.

The official repository currently lists:

```text
v0.0.15
```

as the latest release.

Official release page:

[OpenAI tunnel-client releases](https://github.com/openai/tunnel-client/releases/latest?utm_source=chatgpt.com)

Official tunnel management:

[OpenAI Platform Tunnels](https://platform.openai.com/settings/organization/tunnels?utm_source=chatgpt.com)

---

# 13. Put tunnel-client on your PATH

After downloading the appropriate binary for your operating system, verify that the command works:

```bash
tunnel-client --version
```

Then run:

```bash
tunnel-client help quickstart
```

The official documentation recommends using the CLI itself as the first discovery surface.

Also inspect:

```bash
tunnel-client help doctor
tunnel-client help samples
```

---

# 14. Set the runtime API key

In the shell that will run the tunnel:

```bash
export CONTROL_PLANE_API_KEY="sk-REPLACE_ME"
```

Do not paste the real key into the example documentation you keep in source control.

For a production deployment, prefer a proper secrets manager or protected environment rather than a plaintext configuration file.

---

# 15. Choose your MCP connection model

You now have two main choices.

## Choice A — Local stdio MCP server

Use this when the MCP server is started as a local process.

Example:

```bash
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile local-stdio \
  --tunnel-id tunnel_0123456789abcdef0123456789abcdef \
  --mcp-command "python /path/to/server.py"
```

Then:

```bash
tunnel-client doctor \
  --profile local-stdio \
  --explain
```

Finally:

```bash
tunnel-client run \
  --profile local-stdio
```

These are the current documented first-use commands.

---

# 16. Choice B — Existing HTTP MCP server

If your server already listens over HTTP:

```bash
tunnel-client init \
  --sample sample_mcp_remote_no_auth \
  --profile local-http \
  --tunnel-id tunnel_0123456789abcdef0123456789abcdef \
  --mcp-server-url http://127.0.0.1:8787/mcp
```

For an HTTPS private endpoint, substitute that URL.

Then:

```bash
tunnel-client doctor \
  --profile local-http \
  --explain
```

and:

```bash
tunnel-client run \
  --profile local-http
```

OpenAI documents `--mcp-server-url` as the HTTP equivalent of `--mcp-command`.

---

# 17. Run the health checks before touching ChatGPT

Do this before trying connector discovery.

The tunnel-client exposes:

```text
/healthz
/readyz
/health
/metrics
/ui
```

The default health listener is loopback-oriented. OpenAI recommends checking readiness before relying on ChatGPT connectivity.

Assuming the default health port is 8080:

```bash
curl -fsS http://127.0.0.1:8080/healthz
```

Then:

```bash
curl -fsS http://127.0.0.1:8080/readyz
```

Then:

```bash
curl -fsS 'http://127.0.0.1:8080/health?details=true'
```

Then:

```bash
curl -fsS http://127.0.0.1:8080/metrics | head
```

---

# 18. Open the local tunnel-client dashboard

Open:

```text
http://127.0.0.1:8080/ui
```

Use this order:

```text
1. /readyz
2. /ui#/overview
3. /ui#/metrics
4. /ui#/logs
```

The official end-user guide specifically recommends this sequence when checking a local runtime.

You want to establish:

```text
Process alive
      ↓
Ready
      ↓
Correct tunnel ID
      ↓
MCP target reachable
      ↓
Polling OpenAI
```

Do not interpret "the process started" as "the tunnel works."

---

# 19. Check MCP discovery

For a real MCP server, verify that the MCP server itself is functioning.

The tunnel-client health surface can expose MCP discovery status.

For example:

```bash
curl -fsS http://127.0.0.1:8080/health/mcp
```

A healthy runtime should be able to discover the MCP server and its tools.

The official documentation distinguishes startup readiness from actual stdio protocol discovery, so a `/readyz` success alone is not always proof that the child MCP server has completed initialization.

---

# 20. Only now configure ChatGPT

Once the local tunnel runtime is healthy, open the ChatGPT web settings.

The current tunnel-client operator guide specifies:

```text
ChatGPT Settings
→ Connectors
→ Connection: Tunnel
```

Then:

```text
Select the tunnel
```

or:

```text
Paste the tunnel_id
```

OpenAI also documents this as creating a developer-mode app and selecting **Tunnel** as its connection type.

The exact menu labels may vary as ChatGPT's Apps/Plugins/Connectors UI evolves, but the required configuration is:

```text
MCP app / custom connector
        +
Connection = Tunnel
        +
your tunnel_id
```

---

# 21. Keep tunnel-client running during discovery

This is mandatory.

Keep:

```bash
tunnel-client run --profile local-stdio
```

running while ChatGPT discovers the app and while you test the MCP tools.

OpenAI explicitly states that application discovery and MCP tool calls depend on the tunnel client remaining healthy and running.

---

# 22. Verify that the tunnel appears in ChatGPT

Expected sequence:

```text
Tunnel configured in Platform
        ↓
Tunnel associated with ChatGPT workspace
        ↓
Runtime API key authorized
        ↓
tunnel-client running
        ↓
/readyz = healthy
        ↓
ChatGPT → Connection: Tunnel
        ↓
Tunnel appears/selectable
```

If it does not appear, check in this exact order:

```text
1. Is tunnel-client running?
2. Is /readyz healthy?
3. Is the tunnel associated with the correct ChatGPT workspace?
4. Does the ChatGPT operator have Tunnels Read + Use?
5. Is the tunnel recent enough for control-plane propagation?
```

These are the failure modes called out by the official operator documentation.

---

# 23. Scan/discover the MCP tools

Once ChatGPT has the tunnel connection:

1. Add/select the custom MCP app.
2. Allow ChatGPT to discover the server's tools.
3. Review the tool names/descriptions.
4. Check which tools can read vs. modify data.
5. Do not test destructive operations first.

OpenAI's custom app flow uses tool scanning/discovery before the app becomes usable.

---

# 24. Perform the first ChatGPT test with a harmless read-only operation

Use a prompt that exercises a deterministic read-only tool.

For example, if your MCP server exposes:

```text
get_server_status
```

test:

```text
Use the local MCP app to return the server status.
```

Or:

```text
Use the connected local MCP service to list the test records.
Do not modify anything.
```

Verify:

```text
ChatGPT
  ↓
MCP app
  ↓
OpenAI tunnel
  ↓
tunnel-client
  ↓
local MCP server
  ↓
tool
```

---

# 25. Verify that data is actually coming from your local machine

For a strong end-to-end test, make your local MCP server expose a harmless diagnostic value, for example:

```text
hostname
environment
application version
test record
```

Then ask ChatGPT to retrieve that exact value.

This proves that the response came through the local MCP server rather than from cached/contextual information.

---

# 26. Test write/modify actions separately

Do not test write actions in the same first test.

First establish:

```text
read works
```

Then:

```text
write is correctly authorized
```

Then:

```text
confirmation behavior works
```

OpenAI states that ChatGPT may request confirmation for write/modify actions depending on the app permissions and action context, while especially risky actions can be blocked.

Your MCP server should also independently enforce authorization and validate inputs.

Do not depend on ChatGPT confirmation as your only security boundary.

---

# 27. Recommended security architecture

For a local computer, use this model:

```text
ChatGPT
   │
   │ only the MCP tools you expose
   ▼
OpenAI tunnel
   │
   ▼
tunnel-client
   │
   │ local only
   ▼
Narrow MCP server
   │
   ├── specific directory
   ├── specific commands
   ├── specific API
   └── specific database
```

Avoid creating a generic tool such as:

```text
run_any_shell_command(command)
```

or:

```text
read_any_file(path)
```

unless you have a very deliberate security model.

Prefer:

```text
generate_backup()
get_project_status()
list_allowed_documents()
restart_named_service()
query_read_only_database()
```

The security of the system is therefore strongly influenced by the MCP server you build.

---

# 28. Keep the tunnel-client administrator surface local

The tunnel-client admin UI is intended to be loopback-only by default.

Do not expose `/ui`, `/health`, `/metrics`, etc. publicly unless there is an explicit operational reason and an additional access-control layer.

OpenAI specifically warns that the admin UI is loopback-only by default and recommends exposing it remotely only intentionally.

Prefer:

```text
127.0.0.1:8080
```

rather than:

```text
0.0.0.0:8080
```

unless you genuinely need remote monitoring.

---

# 29. Do not expose your MCP server publicly just to make this work

This is one of the main reasons Secure MCP Tunnel exists.

Do NOT do this merely to integrate ChatGPT:

```text
Internet
    ↓
public HTTPS
    ↓
your MCP server
```

Instead:

```text
Your machine
    ↓ outbound HTTPS
OpenAI tunnel
```

The official OpenAI design goal is precisely to avoid requiring a public MCP listener.

---

# 30. Understand the tunnel's trust boundary

The tunnel is deliberately narrow.

OpenAI describes the architecture as:

* customer-controlled MCP server remains private
* `tunnel-client` initiates outbound connectivity
* OpenAI hosts the tunnel endpoint
* private MCP address is used only inside the customer's environment
* tunnel access is tied to organization/workspace context
* `tunnel-client` supports enterprise networking such as proxies and mTLS

This is not equivalent to giving OpenAI a general-purpose network connection into your LAN.

---

# 31. OAuth consideration

An important advanced case is authentication.

The tunnel can carry MCP OAuth discovery so that the MCP server itself can remain private.

However:

```text
private MCP server
        ≠
private authorization server automatically reachable
```

OpenAI explicitly notes that the authorization server itself is **not automatically tunneled**. If the OAuth authorization server is inaccessible from the relevant components, authentication can still fail.

So if your MCP server uses OAuth, separately verify:

```text
MCP endpoint reachable
+
OAuth discovery reachable
+
authorization server reachable
+
callback/auth flow correct
```

---

# 32. Corporate proxy / private PKI environments

For an enterprise network, the tunnel-client supports configuration for:

```text
HTTPS proxy
custom CA bundles
control-plane client certificates
MCP-side mTLS
```

The official examples include configuring environment variables such as:

```bash
export HTTPS_PROXY="http://proxy.internal.example.com:8080"
```

and a private CA bundle when required.

Do not bypass your corporate proxy/security controls simply to make the tunnel work.

---

# 33. Important stdio rule

For a stdio MCP configuration, do not run multiple active `tunnel-client` instances against the same tunnel ID.

The official repository notes that multiple active stdio tunnel-client instances sharing the same tunnel ID are unsupported because different MCP child processes can otherwise receive different parts of a session.

Therefore:

```text
GOOD

tunnel_ABC
   ↓
one tunnel-client
   ↓
one stdio MCP child
```

Avoid:

```text
tunnel_ABC
 ├── tunnel-client #1
 └── tunnel-client #2
```

Use separate tunnel IDs for genuinely independent instances.

---

# 34. Recommended production operating model

For a workstation:

```text
User logs in
   ↓
MCP server available
   ↓
tunnel-client starts
   ↓
health check
   ↓
ready
   ↓
ChatGPT usable
```

For a server:

```text
system service
       ↓
tunnel-client
       ↓
local/private MCP server
```

For Kubernetes:

```text
Pod
 ├── MCP server
 └── tunnel-client
```

OpenAI documents sidecar, dedicated Kubernetes, VM, and systemd-style deployment patterns.

---

# 35. Operational health checklist

Before declaring the installation successful:

```text
[ ] tunnel exists
[ ] tunnel has correct workspace association
[ ] runtime API key exists
[ ] runtime key has Read + Use
[ ] tunnel-client installed
[ ] tunnel-client version verified
[ ] MCP server works locally
[ ] tunnel-client profile created
[ ] doctor passes
[ ] tunnel-client running
[ ] /healthz = 200
[ ] /readyz = 200
[ ] MCP discovery succeeds
[ ] /ui shows correct tunnel
[ ] ChatGPT can see the tunnel
[ ] ChatGPT discovers MCP tools
[ ] read-only test succeeds
[ ] write test separately verified
[ ] secrets are not embedded in source/config
[ ] local admin UI is not public
```

---

# 36. Troubleshooting decision tree

## Problem A — `doctor` says authentication is missing

Check:

```bash
echo "$CONTROL_PLANE_API_KEY"
```

If empty:

```bash
export CONTROL_PLANE_API_KEY="sk-..."
```

Then:

```bash
tunnel-client doctor --profile local-stdio --explain
```

The runtime key is distinct from the admin key.

---

## Problem B — tunnel exists in Platform but not ChatGPT

Check:

```text
1. Correct ChatGPT workspace association
2. ChatGPT operator has Tunnels Read + Use
3. tunnel-client is running
4. /readyz is healthy
5. enough time has passed for tunnel propagation
```

These are the documented causes to check first.

---

## Problem C — `/readyz` is unhealthy

Run:

```bash
tunnel-client doctor \
  --profile local-stdio \
  --explain
```

Then inspect:

```text
http://127.0.0.1:8080/ui
```

especially the Logs section.

OpenAI recommends `doctor --explain` and the local dashboard as the primary local diagnostics.

---

## Problem D — tunnel is healthy but tool calls fail

Check:

```text
1. MCP server is actually running
2. MCP endpoint/path is correct
3. MCP initialization succeeds
4. tools/list succeeds
5. authentication is valid
6. tunnel-client logs
```

For an HTTP MCP endpoint, test it locally first.

For stdio, test the MCP server directly before adding the tunnel.

---

## Problem E — authentication/OAuth fails

Check:

```text
MCP endpoint
OAuth metadata
authorization server
callback/redirect
refresh token behavior
```

Remember that Secure MCP Tunnel does not automatically make a private authorization server reachable.

---

## Problem F — ChatGPT tool list is stale

For managed custom apps, OpenAI uses a tool/action snapshot and changes may need administrator refresh/review rather than immediately appearing in ChatGPT.

---

# 37. Safe teardown procedure

When you want to disable access:

## Step 1

Stop ChatGPT use of the custom app/connector.

## Step 2

Stop:

```bash
tunnel-client run ...
```

## Step 3

Revoke or rotate the runtime API key if the machine is no longer trusted.

## Step 4

Remove/disable the ChatGPT app if no longer needed.

## Step 5

Delete the tunnel if you are permanently retiring it.

The tunnel itself is the shared anchor used by Platform, ChatGPT, and the local runtime.

---

# 38. Minimum viable first deployment

For the least complicated path, use this exact sequence:

```bash
# 1. Verify the CLI
tunnel-client --version

# 2. Get operator help
tunnel-client help quickstart

# 3. Authenticate the runtime
export CONTROL_PLANE_API_KEY="sk-..."

# 4. Create/configure a profile
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile local-stdio \
  --tunnel-id tunnel_0123456789abcdef0123456789abcdef \
  --mcp-command "python /path/to/server.py"

# 5. Validate it
tunnel-client doctor \
  --profile local-stdio \
  --explain

# 6. Run it
tunnel-client run \
  --profile local-stdio
```

Then, in another terminal:

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/readyz
```

Then open:

```text
http://127.0.0.1:8080/ui
```

Only after those checks succeed should you configure ChatGPT.

This is the same basic flow documented by OpenAI's current Secure MCP Tunnel and tunnel-client operator guides.

---

# 39. The clean mental model

Remember these four pieces:

```text
MCP server
    =
What ChatGPT is allowed to do

tunnel-client
    =
How the local MCP server reaches OpenAI

tunnel_id
    =
Which tunnel both sides are using

runtime API key
    =
Whether the local tunnel-client is authorized to use it
```

And this distinction:

```text
ChatGPT
   ≠
direct localhost access

ChatGPT
   ↓
MCP app
   ↓
Secure MCP Tunnel
   ↓
tunnel-client
   ↓
local MCP server
   ↓
specific local capabilities
```

That is the supported architecture.

---

# 40. Official references

OpenAI Secure MCP Tunnel documentation:

[Secure MCP Tunnel — OpenAI Developers](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels?utm_source=chatgpt.com)

OpenAI MCP servers documentation:

[MCP servers — OpenAI Developers](https://developers.openai.com/api/docs/guides/tools-connectors-mcp?utm_source=chatgpt.com)

OpenAI ChatGPT developer mode/custom MCP documentation:

[Developer mode and MCP apps in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt?utm_source=chatgpt.com)

Official OpenAI tunnel-client repository:

[openai/tunnel-client](https://github.com/openai/tunnel-client?utm_source=chatgpt.com)

Official tunnel-client end-user guide:

[tunnel-client end-user guide](https://github.com/openai/tunnel-client/blob/master/docs/end-user-guide.md?utm_source=chatgpt.com)

Official tunnel-client permissions guide:

[tunnel-client permissions, roles and groups](https://github.com/openai/tunnel-client/blob/master/docs/permissions.md?utm_source=chatgpt.com)

Official latest release:

[Latest tunnel-client release](https://github.com/openai/tunnel-client/releases/latest?utm_source=chatgpt.com)

---

# 41. Recommended implementation order for a real machine

For an actual workstation, I recommend doing the implementation in these phases:

```text
PHASE 1
Prove the tunnel with the embedded MCP stub

PHASE 2
Connect a harmless read-only local MCP server

PHASE 3
Connect the real local service/data

PHASE 4
Add carefully scoped write tools

PHASE 5
Move tunnel-client into a supervised long-running service

PHASE 6
Add monitoring, key rotation and recovery procedures
```

This separates:

```text
network/tunnel problems
```

from:

```text
MCP implementation problems
```

and then from:

```text
permission/security problems
```

That is much easier to operate than attempting all three simultaneously.
