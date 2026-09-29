# Open AI secure MCP Tunnel

**Repository:** `0n6k4v-Coder/openai-secure-mcp-tunnel`     
**Scope:** Private Python MCP server in Docker, connected to ChatGPT through OpenAI Secure MCP Tunnel.

## Quick Start

1. Start the MCP server and tunnel
    ```bash
    docker compose up -d
    ```

2. Check that both services are running
    ```bash
    docker compose ps
    ```

3. Follow the tunnel logs
    ```bash
    docker compose logs -f tunnel-client
    ```

4. Stop and remove the containers and network
    ```bash
    docker compose down
    ```
