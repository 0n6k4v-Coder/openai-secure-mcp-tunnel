# Architecture

```text
                              ChatGPT
                                 │
                                 │ MCP
                                 ▼
                    ┌─────────────────────────┐
                    │     OpenAI Tunnel       │
                    │      tunnel-client      │
                    │                         │
                    │       transport         │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │       MCP SERVER        │
                    │                         │
                    │  MCP API                │
                    │  tool authorization     │
                    │  sandbox API            │
                    │  request audit          │
                    └────────────┬────────────┘
                                 │
                          authenticated
                          OpenShell API
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   OpenShell Gateway     │
                    │                         │
                    │  sandbox lifecycle      │
                    │  policy                 │
                    │  Docker driver          │
                    │  sandbox registry       │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
       ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
       │ Supervisor  │    │ Supervisor  │    │ Supervisor  │
       │      A      │    │      B      │    │      C      │
       └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
              │                  │                  │
              ▼                  ▼                  ▼
       ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
       │ Sandbox A   │    │ Sandbox B   │    │ Sandbox C   │
       │             │    │             │    │             │
       │ Python      │    │ Node        │    │ Playwright  │
       │ Node        │    │ npm         │    │ Chromium    │
       │ workspace   │    │ workspace   │    │ workspace   │
       └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 │
                         OpenShell network
                              policy
                                 │
                                 ▼
                              Internet
```