# Architecture

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
                         ./workspace
```

There is no published MCP port to the Internet.

The MCP container is reachable only through the private Docker network. The tunnel-client container is the component that reaches OpenAI externally. OpenAI documents outbound HTTPS connectivity for the tunnel and no inbound public MCP listener requirement.