# Technology Stack

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