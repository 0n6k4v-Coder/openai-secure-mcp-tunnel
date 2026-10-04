# Tests Directory

## Directory Structure

```text
tests/
├── README.md
├── conftest.py
│
├── unit/
│   └── ...
│
├── integration/
│   ├── conftest.py
│   └── ...
│
└── e2e/
    ├── conftest.py
    ├── cli/
    │   └── ...
    ├── mcp/
    │   └── ...
    └── reports/
        ├── cli.md
        └── mcp.md
```

## Directory Structure Explanation

| Path | Purpose |
|---|---|
| `tests/README.md` | Documents the overall test architecture, conventions, and instructions for running tests. |
| `tests/conftest.py` | Shared pytest fixtures and configuration used across multiple test levels. |
| `tests/unit/` | Isolated unit tests for individual modules and functions. |
| `tests/integration/` | Tests interactions between application components. |
| `tests/integration/conftest.py` | Fixtures and configuration specific to integration tests. |
| `tests/e2e/` | End-to-end tests against a real, production-like sandbox. |
| `tests/e2e/conftest.py` | Fixtures and configuration shared by E2E tests. |
| `tests/e2e/cli/` | E2E tests that interact with the system through the CLI. |
| `tests/e2e/mcp/` | E2E tests that interact with the system through MCP tools. |
| `tests/e2e/reports/cli.md` | Automatically generated test evidence and results for CLI E2E tests. |
| `tests/e2e/reports/mcp.md` | Automatically generated test evidence and results for MCP E2E tests. |
| `...` | Represents test files within each directory without listing individual filenames. |