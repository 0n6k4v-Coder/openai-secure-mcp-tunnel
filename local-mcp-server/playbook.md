# Python Local MCP Server

## Research Findings and Complete Implementation Runbook

**Research baseline:** September 29, 2026
**Target:** Private/local MCP server on a user's computer
**Primary language:** Python
**Primary transport:** stdio
**Primary MCP SDK:** Official MCP Python SDK v2.2.0
**Python baseline:** 3.14.7
**Project/dependency manager:** uv 0.12.19
**Integration target:** OpenAI Secure MCP Tunnel

---

# Part 1 — Research Findings

| Finding ID | Area                     | Finding                                                                                                                                                                                                                            | Why It Matters                                                                                                                           | Version / Date                | Implementation Impact                                                       | Source / Standard                  |
| ---------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- | --------------------------------------------------------------------------- | ---------------------------------- |
| **F-001**  | MCP protocol             | The current stable MCP specification is **2026-07-28**.                                                                                                                                                                            | The implementation should target the current protocol rather than older tutorials/spec revisions.                                        | 2026-07-28                    | Use an SDK version supporting the 2026-07-28 spec.                          | Official MCP specification/release |
| **F-002**  | MCP protocol             | MCP uses **JSON-RPC 2.0** as its message format.                                                                                                                                                                                   | We should not implement a custom RPC/message protocol. The SDK should handle it.                                                         | Current                       | Use the official SDK rather than writing JSON-RPC handling manually.        | MCP spec + JSON-RPC 2.0            |
| **F-003**  | Transport                | MCP defines **stdio** as newline-delimited messages over a client-launched subprocess.                                                                                                                                             | This is specifically suited to a local MCP server.                                                                                       | 2026-07-28                    | Choose stdio for the first local implementation.                            | MCP Transports                     |
| **F-004**  | Transport                | **Streamable HTTP** is the current HTTP transport; SSE is the older transport and should not be used for new implementations.                                                                                                      | Avoid building a new local server around obsolete SSE.                                                                                   | Current                       | Do not add FastAPI/HTTP initially.                                          | MCP Python SDK run guide           |
| **F-005**  | Python SDK               | The official Python SDK is on **v2**, and **v2.2.0** is the current release as of this research.                                                                                                                                   | Older tutorials using v1 APIs can be misleading.                                                                                         | v2.2.0, Sep. 7, 2026          | Use `MCPServer`, not the old v1 `FastMCP` API.                              | Official SDK/PyPI/GitHub           |
| **F-006**  | Python SDK               | The SDK requires **Python 3.10+** and the current package publishes for Python 3.14.                                                                                                                                               | Establishes the supported Python range.                                                                                                  | SDK v2.2.0                    | Python 3.14 is a supported implementation target.                           | Official SDK/PyPI                  |
| **F-007**  | Python                   | Python **3.14.7** is the current stable maintenance release of Python 3.14.                                                                                                                                                        | Use a maintained stable interpreter rather than an EOL or preview version.                                                               | Aug. 5, 2026                  | Pin project development/runtime to Python 3.14.7.                           | Python.org                         |
| **F-008**  | Project tooling          | uv currently gives Tier-1 support to Python 3.14 and CPython, and the current uv release is **0.12.19**.                                                                                                                           | Gives us a current, supported project/dependency toolchain.                                                                              | uv 0.12.19, Sep. 24, 2026     | Use uv for environment and dependency management.                           | Astral uv                          |
| **F-009**  | Reproducibility          | uv maintains an `uv.lock` containing exact resolved dependency information and recommends checking it into version control.                                                                                                        | Prevents dependency drift between machines/runs.                                                                                         | Current                       | Commit `uv.lock`; use locked installs in CI/controlled deployments.         | uv project/lock documentation      |
| **F-010**  | Tool design              | MCP tools are model-controlled capabilities; the MCP spec says applications should keep a human in the loop and provide clear authorization/confirmation.                                                                          | A tool should not be designed as unrestricted remote computer control.                                                                   | 2026-07-28                    | Start with narrowly scoped, read-only tools.                                | MCP Tools/Security                 |
| **F-011**  | Tool schema              | Python SDK generates tool definitions from Python function names, docstrings, and type hints, including JSON Schema input definitions.                                                                                             | We can use normal typed Python functions instead of hand-writing MCP schemas.                                                            | SDK v2                        | Require typed parameters and useful docstrings.                             | Official Python SDK tools docs     |
| **F-012**  | stdio reliability        | A stdio MCP server must **never write normal output to stdout**, because stdout carries MCP protocol messages. Logging should go to stderr.                                                                                        | A single stray `print()` can corrupt the protocol stream.                                                                                | Current                       | Use Python `logging`; do not use `print()` for diagnostics.                 | Official MCP build-server guide    |
| **F-013**  | Authentication           | MCP authorization is primarily specified for HTTP transports; stdio implementations should not use the HTTP MCP authorization flow and should retrieve credentials from the environment instead.                                   | Avoid unnecessary OAuth infrastructure for a local stdio server.                                                                         | 2026-07-28                    | Keep local-server credentials in environment/secret storage.                | MCP Authorization specification    |
| **F-014**  | OpenAI integration       | Secure MCP Tunnel provides an outbound-only path from a private host to OpenAI and can forward requests to a private MCP server; no inbound Internet access is required.                                                           | This is the intended bridge from ChatGPT to a private local MCP server.                                                                  | Current; tunnel-client 0.0.15 | Configure tunnel-client to launch the local stdio server.                   | OpenAI Secure MCP Tunnel           |
| **F-015**  | MCP testing              | MCP Inspector v2 is the current Inspector line; the current release is **2.8.0** and v2 requires Node **22.19.0+**.                                                                                                                | Provides a supported interactive tool-discovery/testing path.                                                                            | v2.8.0, Sep. 23, 2026         | Use Inspector for local protocol/tool testing.                              | Official MCP Inspector             |
| **F-016**  | JSON                     | JSON-RPC/JSON interoperability relies on standard JSON; RFC 8259 requires UTF-8 for JSON exchanged between systems outside a closed ecosystem.                                                                                     | Reinforces using the SDK/protocol implementation rather than custom encodings.                                                           | RFC 8259                      | Let the MCP SDK handle serialization.                                       | IETF RFC 8259                      |
| **F-017**  | Python packaging         | `pyproject.toml` is the standardized modern Python project metadata/configuration mechanism; dependency specifications use established PEP formats.                                                                                | Keeps the project aligned with the Python packaging ecosystem.                                                                           | PEP 621 / PEP 508 / PEP 440   | Use uv-managed `pyproject.toml` rather than legacy setup files.             | Python Packaging Authority / PEPs  |
| **F-018**  | Security                 | OWASP Top 10:2025 emphasizes Broken Access Control, Security Misconfiguration, Software Supply Chain Failures, Injection, Insecure Design, Logging failures, and related risks.                                                    | These map directly to local MCP tools that may expose data or execute operations.                                                        | OWASP Top 10:2025             | Use least privilege, strict inputs, dependency locking, and useful logging. | OWASP Top 10:2025                  |
| **F-019**  | Secure development       | NIST SSDF 1.1 recommends integrating secure software practices into the SDLC to reduce vulnerabilities and their impact.                                                                                                           | The server should be tested, versioned, dependency-controlled, and reviewed like normal software.                                        | NIST SP 800-218, v1.1         | Include tests, dependency lock, code review, and update process.            | NIST SP 800-218                    |
| **F-020**  | Network security         | Current TLS 1.3 standard is RFC 9846, which supersedes RFC 8446.                                                                                                                                                                   | Relevant to the outbound HTTPS tunnel; TLS should be delegated to the official tunnel client/platform rather than reimplemented locally. | RFC 9846, July 2026           | Do not implement custom tunnel cryptography.                                | IETF RFC 9846                      |
| **F-021**  | HTTP/OAuth — conditional | If the MCP server later becomes an HTTP server with authorization, current MCP authorization aligns with modern OAuth metadata/security standards such as RFC 8414, RFC 9728, RFC 9207, RFC 7636, and OAuth security BCP RFC 9700. | Important for a future HTTP deployment, but unnecessary for the initial local stdio server.                                              | Current IETF standards        | Keep HTTP/OAuth as a later architecture phase.                              | IETF OAuth standards               |

---

# Part 2 — Research-Based Design Decision

The evidence leads to this initial stack:

```text
Python 3.14.7
       │
       ▼
uv 0.12.19
       │
       ▼
MCP Python SDK 2.2.0
       │
       ▼
MCPServer
       │
       ▼
stdio
       │
       ▼
MCP Inspector 2.8.0
       │
       ▼
OpenAI tunnel-client 0.0.15
       │
       ▼
ChatGPT / OpenAI product
```

The important design choice is **not to introduce FastAPI, OAuth, a local HTTP listener, or a shell-execution interface in the first version**.

That follows from three separate pieces of evidence:

1. MCP defines stdio specifically for client-launched local subprocesses.
2. The official Python SDK calls stdio the default transport for local servers and says not to build new systems on SSE.
3. OpenAI Secure MCP Tunnel directly supports forwarding to a local stdio MCP command.

---

# Part 3 — Visual Implementation Plan

```text
PHASE 1
Install runtime/tooling
        │
        ▼
PHASE 2
Create Python project
        │
        ▼
PHASE 3
Install + lock MCP SDK
        │
        ▼
PHASE 4
Implement safe MCP tools
        │
        ▼
PHASE 5
Run local tests
        │
        ▼
PHASE 6
Test with MCP Inspector
        │
        ▼
PHASE 7
Harden + document
        │
        ▼
PHASE 8
Connect Secure MCP Tunnel
        │
        ▼
PHASE 9
Test from ChatGPT
```

---

# Part 4 — Complete Step-by-Step Runbook

## Step 1 — Confirm the implementation target

Decide that version 1 of the server will be:

```text
Language       Python
Python         3.14.7
MCP SDK        2.2.0
Transport      stdio
Project tool   uv
Testing        MCP Inspector + pytest
Exposure       private/local only
```

Do **not** add HTTP or OAuth yet.

**Related Finding IDs:** `F-001, F-003, F-004, F-005, F-007, F-008, F-013`

---

## Step 2 — Install Python 3.14.7

Download/install the current stable Python release from Python.org.

Verify:

```bash
python --version
```

or on systems where Python 3 is invoked separately:

```bash
python3 --version
```

Expected baseline:

```text
Python 3.14.7
```

Python 3.14.7 is the current stable 3.14 maintenance release as of this research.

**Related Finding IDs:** `F-006, F-007`

---

## Step 3 — Install uv

### macOS/Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Windows PowerShell

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart the terminal, then:

```bash
uv --version
```

The current uv release is 0.12.19 as of September 24, 2026.

**Related Finding IDs:** `F-008, F-009`

---

## Step 4 — Pin Python for the project

Create your project directory:

```bash
mkdir local-mcp-server
cd local-mcp-server
```

Initialize the project:

```bash
uv init
```

Pin the project interpreter:

```bash
uv python install 3.14.7
uv python pin 3.14.7
```

Verify:

```bash
uv run python --version
```

Expected:

```text
Python 3.14.7
```

This gives the project a reproducible Python selection without relying on whichever system Python happens to be first on PATH.

**Related Finding IDs:** `F-007, F-008, F-017`

---

## Step 5 — Create the virtual environment

Run:

```bash
uv venv --python 3.14.7
```

You should now have:

```text
local-mcp-server/
├── .venv/
├── .python-version
├── pyproject.toml
└── README.md
```

You do not need to activate the environment manually for this runbook. We will consistently use `uv run`, which runs commands in the project environment and keeps it synchronized with the lockfile.

**Related Finding IDs:** `F-008, F-009, F-017`

---

## Step 6 — Install the official MCP Python SDK

Install the current SDK and CLI:

```bash
uv add "mcp[cli]==2.2.0"
```

This intentionally pins the version to the current research baseline rather than allowing future dependency resolution to silently change the MCP SDK.

The official SDK's current stable release is v2.2.0, released September 7, 2026.

Check:

```bash
uv tree
```

Then:

```bash
uv run python -c "import mcp; print(mcp.__version__)"
```

Expected:

```text
2.2.0
```

**Related Finding IDs:** `F-005, F-006, F-009`

---

## Step 7 — Add the test dependency

Install pytest as a development dependency:

```bash
uv add --dev pytest
```

Your project now has:

```text
local-mcp-server/
├── .venv/
├── .python-version
├── pyproject.toml
├── uv.lock
└── README.md
```

The `uv.lock` file should be committed to source control. uv documents it as the exact resolved dependency set for reproducible environments.

**Related Finding IDs:** `F-009, F-017, F-019`

---

## Step 8 — Create the server file

Create:

```text
server.py
```

Put this in it:

```python
from __future__ import annotations

import logging
import platform
import sys
from pathlib import Path

from mcp.server import MCPServer

logger = logging.getLogger(__name__)

mcp = MCPServer("local-computer")

PROJECT_ROOT = Path(__file__).resolve().parent
ALLOWED_ROOT = (PROJECT_ROOT / "allowed_data").resolve()

MAX_READ_BYTES = 1_000_000


def resolve_allowed_path(relative_path: str) -> Path:
    """Resolve a path while preventing access outside allowed_data."""
    candidate = (ALLOWED_ROOT / relative_path).resolve()

    try:
        candidate.relative_to(ALLOWED_ROOT)
    except ValueError as exc:
        raise ValueError("Path is outside the allowed data directory.") from exc

    return candidate


@mcp.tool()
def get_system_info() -> dict[str, str]:
    """Return basic information about the local MCP host."""
    return {
        "operating_system": platform.system(),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
    }


@mcp.tool()
def list_allowed_files() -> list[str]:
    """List files inside the server's allowed_data directory."""
    if not ALLOWED_ROOT.exists():
        return []

    results: list[str] = []

    for path in ALLOWED_ROOT.rglob("*"):
        try:
            resolved = path.resolve()

            if not resolved.is_file():
                continue

            resolved.relative_to(ALLOWED_ROOT)
            results.append(resolved.relative_to(ALLOWED_ROOT).as_posix())

        except (OSError, ValueError):
            continue

    return sorted(results)


@mcp.tool()
def read_allowed_text_file(relative_path: str) -> str:
    """Read a UTF-8 text file from the allowed_data directory."""
    target = resolve_allowed_path(relative_path)

    if not target.is_file():
        raise ValueError("Requested path is not a regular file.")

    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError("Requested file exceeds the maximum allowed size.")

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Requested file is not valid UTF-8 text.") from exc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting local MCP server")
    mcp.run()
```

This implementation intentionally exposes **three narrow tools**:

```text
get_system_info()
list_allowed_files()
read_allowed_text_file()
```

It does **not** expose:

```text
run_shell(command)
execute_python(code)
read_any_file(path)
delete_file(path)
```

This is directly motivated by MCP's tool-safety guidance and OWASP's access-control/injection/insecure-design concerns.

**Related Finding IDs:** `F-010, F-011, F-012, F-018`

---

## Step 9 — Create the allowed data boundary

Create:

```text
allowed_data/
```

Then create:

```text
allowed_data/hello.txt
```

Put:

```text
Hello from my local MCP server.
```

inside it.

Your project should now look like:

```text
local-mcp-server/
│
├── .venv/
├── .python-version
├── pyproject.toml
├── uv.lock
├── server.py
│
└── allowed_data/
    └── hello.txt
```

The purpose of this directory is to establish a **least-privilege data boundary**.

The MCP server can read files under this directory, but the tool deliberately rejects paths that resolve outside it.

**Related Finding IDs:** `F-010, F-018, F-019`

---

## Step 10 — Add logging correctly

For a stdio MCP server, stdout is part of the MCP protocol stream.

Therefore, do **not** write:

```python
print("Server started")
```

Use:

```python
logger.info("Server started")
```

The official MCP server-building documentation explicitly warns that stdout output can corrupt stdio JSON-RPC traffic and recommends Python's `logging` module, which writes to stderr by default.

**Related Finding IDs:** `F-002, F-003, F-012`

---

## Step 11 — Run the server directly

Run:

```bash
uv run python server.py
```

The terminal may appear to wait without displaying anything.

That is expected.

The server is waiting for MCP protocol input on stdin.

Do **not** type ordinary text into the terminal.

Stop it with:

```text
Ctrl+C
```

**Related Finding IDs:** `F-003, F-012`

---

## Step 12 — Run the MCP Inspector

The official Python SDK provides:

```bash
uv run mcp dev server.py
```

This launches the MCP Inspector workflow. The Python SDK explicitly documents this command as the development/testing path.

You should see the Inspector interface.

The Inspector should discover:

```text
Tools

get_system_info
list_allowed_files
read_allowed_text_file
```

**Related Finding IDs:** `F-005, F-015`

---

## Step 13 — Test `get_system_info`

From the Inspector, call:

```text
get_system_info
```

Expected result will contain information such as:

```json
{
  "operating_system": "...",
  "platform": "...",
  "python_version": "3.14.7",
  "python_implementation": "CPython"
}
```

This proves that the MCP request reached your local Python process and executed there.

**Related Finding IDs:** `F-003, F-011, F-015`

---

## Step 14 — Test the allowed file list

Call:

```text
list_allowed_files
```

Expected:

```json
[
  "hello.txt"
]
```

This establishes that the server can inspect the deliberately permitted local directory.

**Related Finding IDs:** `F-010, F-011, F-018`

---

## Step 15 — Test file reading

Call:

```text
read_allowed_text_file
```

with:

```json
{
  "relative_path": "hello.txt"
}
```

Expected result:

```text
Hello from my local MCP server.
```

This is your first end-to-end local data operation.

**Related Finding IDs:** `F-010, F-011, F-015`

---

## Step 16 — Verify path-traversal protection

Try:

```json
{
  "relative_path": "../server.py"
}
```

The server should reject it with:

```text
Path is outside the allowed data directory.
```

Also test:

```text
../../
```

and, where applicable, paths using alternate separators.

The important property is not the exact error text; it is that **the resolved path cannot escape `allowed_data`**.

This is the security boundary we intentionally built into the server.

**Related Finding IDs:** `F-010, F-018, F-019`

---

## Step 17 — Create automated security tests

Create:

```text
tests/
└── test_security.py
```

Use:

```python
import pytest

from server import ALLOWED_ROOT, read_allowed_text_file, resolve_allowed_path


def test_allowed_path_stays_inside_root() -> None:
    result = resolve_allowed_path("hello.txt")

    assert result.parent == ALLOWED_ROOT


def test_parent_traversal_is_rejected() -> None:
    with pytest.raises(ValueError):
        resolve_allowed_path("../server.py")


def test_nested_parent_traversal_is_rejected() -> None:
    with pytest.raises(ValueError):
        resolve_allowed_path("../../pyproject.toml")


def test_allowed_file_can_be_read() -> None:
    result = read_allowed_text_file("hello.txt")

    assert result == "Hello from my local MCP server.\n"
```

Run:

```bash
uv run pytest
```

Expected:

```text
4 passed
```

This turns the important security rule into an automated regression test.

**Related Finding IDs:** `F-018, F-019`

---

## Step 18 — Verify the dependency lock

Run:

```bash
uv lock
```

Then:

```bash
uv tree
```

Check that:

```text
mcp 2.2.0
```

is present.

Commit:

```text
pyproject.toml
uv.lock
.python-version
server.py
tests/
```

Do **not** commit:

```text
.venv/
private credentials
private data
API keys
```

uv explicitly recommends version-controlling `uv.lock` for reproducibility.

**Related Finding IDs:** `F-009, F-017, F-019`

---

## Step 19 — Add the Git ignore rules

Create or update:

```text
.gitignore
```

with:

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/

# Local/private data
allowed_data/*
!allowed_data/.gitkeep

# Local secrets
.env
.env.*
*.secret
```

Create:

```text
allowed_data/.gitkeep
```

This keeps the directory in Git without accidentally committing private data.

**Related Finding IDs:** `F-018, F-019`

---

## Step 20 — Decide how secrets will work

For any future tool that talks to another service, do not hard-code:

```python
API_KEY = "sk-..."
```

Use an environment variable instead:

```python
import os

api_key = os.environ["MY_SERVICE_API_KEY"]
```

For a stdio MCP implementation, the MCP authorization specification specifically says HTTP authorization should not be applied to stdio in the same way; credentials can instead be retrieved from the environment.

**Related Finding IDs:** `F-013, F-018, F-019`

---

## Step 21 — Establish the first production boundary

At this point your server should be considered:

```text
LOCAL + READ-ONLY + NARROW
```

Do not add arbitrary command execution yet.

A safe expansion path is:

```text
Phase 1
Read-only tools

        ↓

Phase 2
Specific write tools

        ↓

Phase 3
Explicit confirmation / authorization

        ↓

Phase 4
Long-running operations

        ↓

Phase 5
HTTP deployment, if actually required
```

This matches the MCP principle that tools may provide arbitrary capability and should be treated with caution.

**Related Finding IDs:** `F-010, F-018, F-019`

---

# Part 5 — Connect the Local Server to OpenAI Secure MCP Tunnel

This phase is optional until the local server itself works.

Do not start here.

---

## Step 22 — Create an OpenAI tunnel

Open the OpenAI Platform tunnel settings and create a tunnel.

Record:

```text
TUNNEL_ID
```

Secure MCP Tunnel is designed for private/on-premises/developer-machine MCP servers and uses an outbound connection from the host.

**Related Finding IDs:** `F-014`

---

## Step 23 — Create a restricted runtime credential

Create the runtime credential for `tunnel-client` with only the permissions required to use/read the tunnel.

Keep it separate from administrator credentials.

Store it outside the source repository.

**Related Finding IDs:** `F-014, F-018, F-019`

---

## Step 24 — Install `tunnel-client`

Use the OpenAI Platform download or the latest official GitHub release.

Current public release:

```text
tunnel-client v0.0.15
```

released September 25, 2026.

Verify:

```bash
tunnel-client --version
```

Then:

```bash
tunnel-client help quickstart
```

OpenAI explicitly recommends using the current release mechanism rather than hard-coding a future release URL.

**Related Finding IDs:** `F-014`

---

## Step 25 — Provide the runtime API key

Set the runtime credential in the environment used by `tunnel-client`.

For example:

```bash
export CONTROL_PLANE_API_KEY="YOUR_RESTRICTED_KEY"
```

On PowerShell:

```powershell
$env:CONTROL_PLANE_API_KEY="YOUR_RESTRICTED_KEY"
```

Do not commit this value.

**Related Finding IDs:** `F-013, F-014, F-018`

---

## Step 26 — Configure the tunnel to launch your local MCP server

Your local MCP command is:

```bash
uv run python server.py
```

Configure `tunnel-client` to use that command as its stdio MCP target.

The OpenAI tunnel documentation provides the `sample_mcp_stdio_local` / `--mcp-command` model for local stdio servers.

The resulting conceptual configuration is:

```text
Tunnel
  │
  └── stdio command:
      uv run python server.py
```

Use the exact current CLI syntax shown by:

```bash
tunnel-client help quickstart
```

if the current release's flags differ.

**Related Finding IDs:** `F-003, F-014`

---

## Step 27 — Run the tunnel diagnostic

Run the tunnel client's diagnostic command using your profile:

```bash
tunnel-client doctor --profile YOUR_PROFILE --explain
```

You want:

```text
authentication OK
tunnel available
MCP command reachable
configuration valid
```

**Related Finding IDs:** `F-014`

---

## Step 28 — Start the tunnel

Run:

```bash
tunnel-client run --profile YOUR_PROFILE
```

The resulting architecture should now be:

```text
ChatGPT
   │
   ▼
OpenAI Secure MCP Tunnel
   │
   ▼
tunnel-client
   │
   ▼
uv run python server.py
   │
   ▼
MCPServer
```

OpenAI documents Secure MCP Tunnel as outbound-only; the local machine does not need an inbound Internet port for this architecture.

**Related Finding IDs:** `F-003, F-014, F-020`

---

## Step 29 — Do not expose a local HTTP port

For this architecture, you should **not** need:

```text
0.0.0.0:8000
0.0.0.0:8080
```

or a public reverse proxy.

The MCP server is a local stdio process.

That is one of the main benefits of this architecture.

**Related Finding IDs:** `F-003, F-004, F-014`

---

## Step 30 — Connect the tunnel to ChatGPT

Configure the appropriate custom MCP app/connector in ChatGPT using the tunnel you created.

Keep the local:

```bash
tunnel-client run ...
```

process running while ChatGPT discovers and calls the server.

OpenAI describes the tunnel as providing the normal MCP request path to supported OpenAI products while keeping the MCP server private.

**Related Finding IDs:** `F-014`

---

## Step 31 — Perform the first remote test

Do not start with file modification or shell execution.

Ask ChatGPT to use:

```text
get_system_info
```

Then:

```text
list_allowed_files
```

Then:

```text
read_allowed_text_file("hello.txt")
```

The complete flow should be:

```text
ChatGPT
   │
   ▼
OpenAI MCP Tunnel
   │
   ▼
tunnel-client
   │
   ▼
Python MCPServer
   │
   ▼
tool
   │
   ▼
local computer
```

**Related Finding IDs:** `F-003, F-010, F-011, F-014`

---

# Part 6 — Acceptance Checklist

The implementation is complete when all of these are true:

```text
Runtime
[ ] Python 3.14.7 installed
[ ] uv installed
[ ] Project has .python-version
[ ] Project has pyproject.toml
[ ] Project has uv.lock

MCP
[ ] MCP SDK 2.2.0 installed
[ ] MCPServer imports successfully
[ ] stdio transport works
[ ] No stdout diagnostic logging

Tools
[ ] get_system_info works
[ ] list_allowed_files works
[ ] read_allowed_text_file works
[ ] Path traversal is rejected
[ ] File-size limit is enforced
[ ] No unrestricted shell tool exists

Testing
[ ] pytest passes
[ ] MCP Inspector discovers tools
[ ] MCP Inspector can invoke every tool
[ ] Security tests cover traversal

Security
[ ] Secrets are outside source code
[ ] Private files are not committed
[ ] uv.lock is committed
[ ] Tools follow least privilege
[ ] No unnecessary HTTP listener
[ ] No unnecessary OAuth implementation

OpenAI integration
[ ] OpenAI tunnel exists
[ ] Runtime credential is restricted
[ ] tunnel-client starts successfully
[ ] tunnel-client can launch server.py
[ ] Tunnel has outbound HTTPS connectivity
[ ] ChatGPT discovers the MCP server
[ ] ChatGPT can invoke the read-only tools
```

---

# Part 7 — Troubleshooting Flow

```text
ChatGPT cannot see server
        │
        ├── Is tunnel-client running?
        │       └── No → start it
        │
        ├── Does tunnel-client doctor pass?
        │       └── No → fix tunnel/auth/profile
        │
        ├── Does local MCP Inspector work?
        │       └── No → fix Python MCP server
        │
        ├── Does "uv run python server.py" start?
        │       └── No → fix Python/project
        │
        └── Does Inspector discover tools?
                │
                ├── No → fix MCP server/tool definition
                │
                └── Yes → investigate tunnel/ChatGPT layer
```

The critical diagnostic principle is:

```text
Local server
    ↓
Inspector
    ↓
Tunnel
    ↓
ChatGPT
```

Validate each layer before debugging the next one.

**Related Finding IDs:** `F-003, F-009, F-014, F-015, F-019`

---

# Part 8 — Why this design is the research-backed baseline

The implementation deliberately avoids several seemingly convenient approaches:

| Design choice                | Decision          | Reason                                                                                |
| ---------------------------- | ----------------- | ------------------------------------------------------------------------------------- |
| `MCPServer` vs old `FastMCP` | **MCPServer**     | Current Python SDK v2 API.                                                            |
| stdio vs HTTP                | **stdio**         | Official local-server transport and direct OpenAI tunnel fit.                         |
| FastAPI                      | **Not initially** | Adds an HTTP deployment layer that is unnecessary for a local stdio server.           |
| SSE                          | **No**            | Superseded by Streamable HTTP for new HTTP implementations.                           |
| OAuth for local MCP          | **No**            | MCP authorization spec is for HTTP; stdio should use environment credentials instead. |
| Arbitrary shell execution    | **No**            | Excessive capability conflicts with least-privilege/tool-safety principles.           |
| Public HTTP endpoint         | **No**            | Secure MCP Tunnel is specifically designed to keep the MCP server private.            |
| Unpinned dependencies        | **No**            | Lockfile provides reproducibility.                                                    |
| `print()` logging            | **No**            | stdout is part of stdio protocol traffic.                                             |

---

# Part 9 — End State

When complete, you have:

```text
                  ┌──────────────────┐
                  │    ChatGPT       │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │ OpenAI MCP       │
                  │ Secure Tunnel    │
                  └────────┬─────────┘
                           │
                    outbound HTTPS
                           │
                           ▼
                  ┌──────────────────┐
                  │ tunnel-client    │
                  └────────┬─────────┘
                           │
                         stdio
                           │
                           ▼
       ┌─────────────────────────────────────┐
       │        Python MCP Server            │
       │                                     │
       │   MCPServer("local-computer")       │
       │                                     │
       │   ┌─────────────────────────────┐   │
       │   │ get_system_info()           │   │
       │   │ list_allowed_files()        │   │
       │   │ read_allowed_text_file()    │   │
       │   └─────────────────────────────┘   │
       │                                     │
       │        allowed_data/                │
       └─────────────────────────────────────┘
```

The key security boundary is:

```text
ChatGPT does NOT receive
"access to your computer."

ChatGPT receives access to
"the specific MCP tools you expose."
```

That distinction is fundamental to the MCP security model.

---

# Part 10 — Official Source Set

**MCP**

Official current specification: [MCP 2026-07-28 Specification](https://modelcontextprotocol.io/specification/2026-07-28?utm_source=chatgpt.com)

[MCP Build an MCP Server](https://modelcontextprotocol.io/docs/develop/build-server?utm_source=chatgpt.com)

[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk?utm_source=chatgpt.com)

**Python**

[Python 3.14.7](https://www.python.org/downloads/release/python-3147/?utm_source=chatgpt.com)

**uv**

[uv documentation](https://docs.astral.sh/uv/?utm_source=chatgpt.com)

**Testing**

[MCP Inspector](https://github.com/modelcontextprotocol/inspector?utm_source=chatgpt.com)

**OpenAI**

[OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels?utm_source=chatgpt.com)

[OpenAI tunnel-client](https://github.com/openai/tunnel-client?utm_source=chatgpt.com)

**Standards**

[JSON-RPC 2.0](https://www.jsonrpc.org/specification?utm_source=chatgpt.com)

[RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259.html?utm_source=chatgpt.com)

[RFC 9846 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc9846.html?utm_source=chatgpt.com)

[OWASP Top 10:2025](https://top10.owasp.org/2025/?utm_source=chatgpt.com)

[NIST SP 800-218 SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final?utm_source=chatgpt.com)

---

## Final implementation baseline

```text
Python             3.14.7
uv                 0.12.19
MCP Python SDK     2.2.0
MCP specification  2026-07-28
Transport          stdio
Testing            MCP Inspector 2.8.0 + pytest
Logging            stderr
Secrets            environment / OS secret storage
Data boundary      explicit allowed directory
Dependency control uv.lock
Remote access      OpenAI Secure MCP Tunnel
```

This gives you a **small, private, current, standards-aligned starting point** without prematurely turning the local MCP server into a web application or remote administration system.
