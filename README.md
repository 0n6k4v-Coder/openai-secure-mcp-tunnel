# OpenAI Secure MCP Tunnel

**Repository:** `0n6k4v-Coder/openai-secure-mcp-tunnel`     
**Scope:** Private Python MCP server in Docker, connected to ChatGPT through OpenAI Secure MCP Tunnel.

---

## Set Up

### Step 1 - Clone the repository

```bash
git clone https://github.com/0n6k4v-Coder/openai-secure-mcp-tunnel.git
cd openai-secure-mcp-tunnel
```

### Step 2 - Create and Configure OpenAI Tunnel

* Open: https://platform.openai.com/settings/organization/tunnels
* Find `Create tunnel`.
* Create a new tunnel with a name such as:

```text
openai-secure-mcp-tunnel
```

* After creating the tunnel, copy the Tunnel ID:

```text
tunnel_xxx
```

* Create a `.env` file at the project's root.
* Add:

```env
CONTROL_PLANE_TUNNEL_ID=<Copied Tunnel ID>
```

### Step 3 - Create and Configure OpenAI Control Plane API Key

* Open the OpenAI API Keys page:
  https://platform.openai.com/api-keys

* Create a new API key with the permissions required for the tunnel.

* Copy the API key immediately after creating it.

* Create the secrets directory:

```bash
mkdir -p .secrets
```

* Create the API key file:

```bash
touch .secrets/control-plane-api-key
```

* Open `.secrets/control-plane-api-key` and paste the API key into the file.

The file should contain only the API key:

```text
sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

* Save the file.

* Do not commit this file to Git.

### Step 4 - Create and Configure Terminal Agent Token

* Create the `.secrets` directory if it does not already exist:

```bash
mkdir -p .secrets
```

* Generate a secure token:

```bash
openssl rand -hex 32 > .secrets/terminal-agent-token
```

* Make sure the file contains only the generated token.

* Do not commit this file to Git.

### Step 5 - Start the MCP Server and Tunnel

* Start the services:

```bash
docker compose up -d
```

* Check the service status:

```bash
docker compose ps
```

* Make sure these services are running:

```text
mcp-server
terminal-executor
tunnel-client
```

### Step 6 - Check the Tunnel

* Follow the tunnel logs:

```bash
docker compose logs -f tunnel-client
```

* Wait until you see:

```text
🟢 tunnel-client started
```

* Confirm that the log shows the Tunnel ID created in Step 2.

### Step 7 - Connect the Tunnel to ChatGPT

* Open: [https://chatgpt.com/plugins](https://chatgpt.com/plugins)
* Click the `+` button.
* Select `Create App`.
* Click `Create MCP App`.
* Enter a name for the app.
* Select `Tunnel` for the connection type.
* Select the Tunnel created in Step 2.
* Select `No Auth` for authentication.
* Check `I understand and want to continue`.
* Click `Create`.

### Step 8 - Verify the MCP Tools

* Open the connected MCP connector in ChatGPT.
* Verify that these tools are available:

```text
get_system_info
list_workspace_files
read_workspace_text_file
create_workspace_file
write_workspace_file
create_workspace_directory
rename_workspace_path
delete_workspace_file
execute_terminal_command
```

---

## Update MCP Server Tools

### Docker

1. `docker compose build --no-cache mcp-server`
   → **Rebuild the Docker image** so the latest MCP code and tools are included.

2. `docker compose up -d --force-recreate mcp-server`
   → **Recreate and restart the MCP container** using the newly built image.

3. `docker compose ps`
   → Check that the MCP server and related services are **running and healthy**.

4. `docker compose logs --tail=200 mcp-server`
   or
   `docker compose logs -f mcp-server`
   → Check that the MCP server **started successfully without errors**.

   * `--tail=200` = show the latest 200 log lines
   * `-f` = follow logs in real time

5. `docker compose logs --tail=100 tunnel-client`
   → Check that **tunnel-client is still running and connected to the existing tunnel**.

### ChatGPT

**Settings**      
→ **Apps / Connectors**    
→ **Our MCP App**    
→ **Refresh**

→ This forces ChatGPT to **rediscover the MCP tools** and load the latest tool list.

### If Refresh Still Doesn't Show the New Tool

Do **not** create a new API key or tunnel immediately.

**Delete only the MCP App/Connector**
→ **Create it again**
→ Select the **same existing tunnel**
→ Check the tool list again.

**Remember:**
`Rebuild → Recreate → Check

---

## Quick Start

### 1. Start the MCP server and tunnel

```bash
docker compose up -d
```

### 2. Check that the services are running

```bash
docker compose ps
```

The expected services are:

```text
mcp-server
terminal-executor
tunnel-client
```

`mcp-server` and `terminal-executor` should become `healthy`.

### 3. Check the tunnel logs

```bash
docker compose logs -f tunnel-client
```

Look for:

```text
🟢 tunnel-client started
```

You should also see your Tunnel ID in the tunnel URL:

```text
tunnel_url=https://api.openai.com/v1/tunnel/<Tunnel ID>
```

### 4. Connect the tunnel to ChatGPT

In ChatGPT:

* Add a new MCP Connector.
* Select the OpenAI Secure MCP Tunnel connection.
* Use the Tunnel ID created in Step 2.
* Complete the connection.

### 5. Verify the MCP tools

The MCP server currently provides:

```text
get_system_info
list_workspace_files
read_workspace_text_file
create_workspace_file
write_workspace_file
create_workspace_directory
rename_workspace_path
delete_workspace_file
execute_terminal_command
```

## Stop

Stop and remove the containers and network:

```bash
docker compose down
```

## Restart

Start everything again:

```bash
docker compose up -d
```

Check the status:

```bash
docker compose ps
```

Check the tunnel:

```bash
docker compose logs -f tunnel-client
```

## Troubleshooting

### Tunnel is not starting

Check the tunnel logs:

```bash
docker compose logs --tail=100 tunnel-client
```

Verify that:

```env
CONTROL_PLANE_TUNNEL_ID=<Correct Tunnel ID>
```

is present in `.env`.

### ChatGPT shows an old tool list

Create a **new OpenAI Tunnel** and connect ChatGPT to the new Tunnel ID.

Do not change the MCP server code or Docker configuration until the new tunnel has been tested.

### Rebuild the containers

```bash
docker compose up -d --build
```

### Completely stop the stack

```bash
docker compose down
```
