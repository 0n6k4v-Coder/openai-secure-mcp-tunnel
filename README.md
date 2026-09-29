# Open AI secure MCP Tunnel

**Repository:** `0n6k4v-Coder/openai-secure-mcp-tunnel`     
**Scope:** Private Python MCP server in Docker, connected to ChatGPT through OpenAI Secure MCP Tunnel.

## Quick Start

```bash
# 1. Start the MCP server and tunnel
docker compose up -d

# 2. Check that both services are running
docker compose ps

# 3. Follow the tunnel logs
docker compose logs -f tunnel-client
```