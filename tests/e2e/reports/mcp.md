# MCP E2E Test Report

## 1. Purpose

Validate the MCP server's externally observable behavior through a real MCP client and the running server. Cover protocol negotiation, tool discovery, input schemas, tool execution, error handling, security boundaries, workspace file operations, sandbox lifecycle operations, Chrome DevTools commands, health checks, and request logging.

The test suite must:

- Connect through the configured Streamable HTTP endpoint using an MCP client.
- Validate the advertised server identity, protocol version, capabilities, and complete registered tool surface.
- Validate every registered tool's input schema, required arguments, optional arguments, and observable result.
- Exercise success paths and expected failures.
- Verify that destructive operations target only dedicated test resources.
- Verify that workspace file operations cannot escape the selected sandbox workspace.
- Verify that sandbox and browser commands execute only within the intended sandbox.
- Avoid logging or exposing credentials, secret values, or unrelated workspace data.
- Clean up resources even when an assertion or operation fails.
- Record test outcomes from actual execution, not assumptions.

## 2. Status Definitions

| Status | Meaning |
|---|---|
| ⚪ Not implemented | No MCP E2E test currently verifies this case |
| 🟠 Blocked | Test execution is blocked by an unavailable prerequisite or a known defect |
| 🟢 Pass | Test ran and met its expected result |
| 🔴 Fail | Test ran and did not meet its expected result |
| 🟡 Skipped | Test was intentionally not run, with a documented reason |

This draft describes the intended test matrix. All proposed MCP E2E cases begin as **Not implemented** until implemented and executed. Existing integration tests are documented separately and must not be treated as proof that the proposed E2E tests passed.

## 3. Server and Transport Contract

The current source configures the server identity as `local-computer`, version `0.1.0`, with Streamable HTTP at `/mcp`, port `8000`, stateless HTTP mode, JSON responses, and a 1 MiB maximum request body. DNS rebinding protection is enabled and the configured allowed host is `mcp-server:8000`.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-TRANSPORT-001 | Connect to the configured `/mcp` endpoint | An MCP client establishes a valid session/transport connection | 🟠 Blocked |
| MCP-TRANSPORT-002 | Initialize the MCP client | Server initialization succeeds and returns valid protocol metadata | 🟠 Blocked |
| MCP-TRANSPORT-003 | Verify server identity | Server name is `local-computer` and version is `0.1.0` | 🟠 Blocked |
| MCP-TRANSPORT-004 | Verify negotiated protocol version | Client and server negotiate a supported protocol version | 🟠 Blocked |
| MCP-TRANSPORT-005 | Verify server capabilities | Tool capability is advertised | 🟠 Blocked |
| MCP-TRANSPORT-006 | Send a valid tool-list request | Server returns a valid MCP tool-list response | 🟠 Blocked |
| MCP-TRANSPORT-007 | Send a valid tool-call request | Server returns a protocol-valid tool result | 🟠 Blocked |
| MCP-TRANSPORT-008 | Send a malformed protocol request | Server rejects it without crashing or returning a false success | 🟠 Blocked |
| MCP-TRANSPORT-009 | Send a request with an unsupported method | Server returns a protocol-appropriate error | 🟠 Blocked |
| MCP-TRANSPORT-010 | Send an invalid tool-call envelope | Server returns a protocol error or tool error appropriate to the invalid request | 🟠 Blocked |
| MCP-TRANSPORT-011 | Send a request with an invalid JSON body | Request is rejected without terminating the service | 🟠 Blocked |
| MCP-TRANSPORT-012 | Send a request exceeding the configured body-size limit | Request is rejected safely | 🟠 Blocked |
| MCP-TRANSPORT-013 | Connect using the configured allowed host | Request passes host validation | 🟠 Blocked |
| MCP-TRANSPORT-014 | Connect with an unapproved Host header | Request is rejected by transport security | 🟠 Blocked |
| MCP-TRANSPORT-015 | Exercise DNS-rebinding protection | Disallowed host/origin patterns are rejected according to the transport implementation | 🟠 Blocked |
| MCP-TRANSPORT-016 | Send multiple sequential requests | Server remains available and returns valid responses | 🟠 Blocked |
| MCP-TRANSPORT-017 | Send independent requests concurrently | Responses remain valid and request handling does not corrupt shared state | 🟠 Blocked |
| MCP-TRANSPORT-018 | Verify stateless HTTP behavior | Client requests do not rely on an undocumented persistent server-side session | 🟠 Blocked |
| MCP-TRANSPORT-019 | Restart the server and reconnect | A new client can initialize and use the server after restart | 🟠 Blocked |
| MCP-TRANSPORT-020 | Verify transport error handling during server unavailability | Client receives a connection failure rather than a false successful result | 🟢 Pass |

## 4. Health Endpoint and Service Identity

The current source registers `GET /healthz`. The response includes `status`, `service`, `version`, `instance_id`, and `pid`.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-HEALTH-001 | `GET /healthz` | Returns HTTP 200 when the service is available | 🟠 Blocked |
| MCP-HEALTH-002 | Validate health response JSON | Response is valid JSON and contains the expected fields | 🟠 Blocked |
| MCP-HEALTH-003 | Validate health status | `status` equals `ok` | 🟠 Blocked |
| MCP-HEALTH-004 | Validate service identity | `service` is `local-computer` and `version` is `0.1.0` | 🟠 Blocked |
| MCP-HEALTH-005 | Validate instance metadata | `instance_id` is non-empty and `pid` is a valid process identifier | 🟠 Blocked |
| MCP-HEALTH-006 | Repeated health requests | Endpoint remains responsive across repeated requests | 🟠 Blocked |
| MCP-HEALTH-007 | Health request with the configured Host header | Request succeeds when the host is allowed | 🟠 Blocked |
| MCP-HEALTH-008 | Health request with a disallowed Host header | Request is rejected according to transport host validation | 🟠 Blocked |

## 5. Tool Registry and Discovery

The current registration code registers 22 tools: one system-information tool, eleven sandbox tools, nine workspace tools, and one Chrome DevTools tool.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-REG-001 | List all registered tools | Returns the complete expected tool set | 🟠 Blocked |
| MCP-REG-002 | Verify exact tool count | Registry contains 22 tools | 🟠 Blocked |
| MCP-REG-003 | Verify tool names | Every registered tool has the expected exact name | 🟠 Blocked |
| MCP-REG-004 | Verify tool names are unique | No duplicate tool names are returned | 🟠 Blocked |
| MCP-REG-005 | Verify tool descriptions | Each tool has a useful description matching its implemented behavior | 🟠 Blocked |
| MCP-REG-006 | Verify input schemas | Each tool advertises a valid JSON-compatible input schema | 🟠 Blocked |
| MCP-REG-007 | Verify required arguments | Required schema fields match the callable signature | 🟠 Blocked |
| MCP-REG-008 | Verify optional arguments and defaults | Optional fields and defaults match the implementation | 🟠 Blocked |
| MCP-REG-009 | Verify tool annotations | Read-only, destructive, idempotent, and open-world hints match the intended behavior | 🟠 Blocked |
| MCP-REG-010 | Verify registry stability | Repeated list-tools requests return the same tool names for an unchanged server build | 🟠 Blocked |
| MCP-REG-011 | Call an unknown tool name | Server returns an MCP tool/protocol error and does not execute another tool | 🟠 Blocked |
| MCP-REG-012 | Verify unsupported capabilities | Server does not claim unsupported resources, prompts, or other capabilities | 🟠 Blocked |

## 6. `get_system_info`

Current signature: `get_system_info() -> dict[str, str]`. It returns the operating system, platform, Python version, and Python implementation.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-SYS-001 | Call `get_system_info` with no arguments | Returns system information successfully | 🟠 Blocked |
| MCP-SYS-002 | Validate response fields | Includes `operating_system`, `platform`, `python_version`, and `python_implementation` | 🟠 Blocked |
| MCP-SYS-003 | Validate response value types | All documented values are strings | 🟠 Blocked |
| MCP-SYS-004 | Validate non-empty values | Required environment information is populated | 🟠 Blocked |
| MCP-SYS-005 | Supply an unexpected argument | Invalid input is rejected according to the tool schema | 🟠 Blocked |
| MCP-SYS-006 | Repeat the call | Calls succeed without mutating server or sandbox state | 🟠 Blocked |

## 7. Sandbox Lifecycle Tools

Current registered tools:

- `create_sandbox(name, host_workspace_id=None, profile="default")`
- `list_sandboxes()`
- `sandbox_status(name)`
- `sandbox_logs(name, since="5m")`
- `start_sandbox(name)`
- `stop_sandbox(name)`
- `restart_sandbox(name)`
- `repair_sandbox(name)`
- `recreate_sandbox(name)`
- `delete_sandbox(name)`
- `execute_sandbox_command(name, command)`

Tests involving actual sandbox creation, deletion, restart, or command execution must use a dedicated OpenShell test environment and unique sandbox names.

### 7.1 Create and List

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-SBX-001 | Create a sandbox with a valid name and default profile | Sandbox creation succeeds and returns the service result | 🟠 Blocked |
| MCP-SBX-002 | Create a sandbox using the `default` profile | Default profile is selected | 🟠 Blocked |
| MCP-SBX-003 | Create a sandbox using the `browser` profile | Browser profile is selected | 🟠 Blocked |
| MCP-SBX-004 | Create a standalone sandbox by omitting `host_workspace_id` | Sandbox uses sandbox-local workspace storage | 🟠 Blocked |
| MCP-SBX-005 | Create a sandbox using a valid authorized host workspace ID | Sandbox uses the authorized workspace binding | 🟠 Blocked |
| MCP-SBX-006 | Create a sandbox with an unknown workspace ID | Request fails without creating an unintended sandbox | 🟠 Blocked |
| MCP-SBX-007 | Create a sandbox with an unsupported profile | Profile validation rejects the request | 🟠 Blocked |
| MCP-SBX-008 | Create a sandbox with a missing or invalid name | Request fails clearly without creating a resource | 🟠 Blocked |
| MCP-SBX-009 | Create a sandbox with an existing name | Duplicate-name behavior is handled without corrupting the existing sandbox | 🟠 Blocked |
| MCP-SBX-010 | List sandboxes | Returns the sandbox service's list result | 🟠 Blocked |
| MCP-SBX-011 | List sandboxes in an empty test environment | Returns a valid empty result | 🟠 Blocked |
| MCP-SBX-012 | Create then list a sandbox | Newly created sandbox appears in the list | 🟠 Blocked |
| MCP-SBX-013 | Validate create/list result handling | Successful results are returned without false success on service errors | 🟠 Blocked |

### 7.2 Status and Logs

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-SBX-020 | Query status for an existing sandbox | Returns the current sandbox status | 🟠 Blocked |
| MCP-SBX-021 | Query status for a missing sandbox | Returns a clear error | 🟠 Blocked |
| MCP-SBX-022 | Validate status response content | Response accurately reflects the service result | 🟠 Blocked |
| MCP-SBX-023 | Get logs with the default `since` value | Uses the default duration of `5m` | 🟠 Blocked |
| MCP-SBX-024 | Get logs with a supported duration such as `1h` or `30s` | Requested duration reaches the service unchanged | 🟠 Blocked |
| MCP-SBX-025 | Get logs for a missing sandbox | Returns a clear failure | 🟠 Blocked |
| MCP-SBX-026 | Get logs using an invalid duration | Invalid values are rejected by the appropriate validation/service layer | 🟠 Blocked |
| MCP-SBX-027 | Validate log output handling | Returned log content is preserved and failures are not reported as success | 🟠 Blocked |

### 7.3 Start, Stop, Restart, Repair, Recreate, and Delete

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-SBX-030 | Start a stopped sandbox | Sandbox transitions to a usable running state | 🟠 Blocked |
| MCP-SBX-031 | Start a missing sandbox | Returns a clear failure | 🟠 Blocked |
| MCP-SBX-032 | Stop a running sandbox | Sandbox stops while retaining state | 🟠 Blocked |
| MCP-SBX-033 | Stop a missing sandbox | Returns a clear failure | 🟠 Blocked |
| MCP-SBX-034 | Restart an existing sandbox | Sandbox is restarted and becomes usable | 🟠 Blocked |
| MCP-SBX-035 | Restart a missing sandbox | Returns a clear failure | 🟠 Blocked |
| MCP-SBX-036 | Repair a recoverable sandbox | Recovery is attempted and the resulting state is accurate | 🟠 Blocked |
| MCP-SBX-037 | Repair an unrecoverable sandbox | Reports failure without claiming successful recovery | 🟠 Blocked |
| MCP-SBX-038 | Recreate a host-backed sandbox | Recreated sandbox preserves the intended workspace binding and profile | 🟠 Blocked |
| MCP-SBX-039 | Recreate a standalone sandbox | Recreated sandbox retains standalone mode and profile | 🟠 Blocked |
| MCP-SBX-040 | Recreate a missing sandbox | Returns a clear failure | 🟠 Blocked |
| MCP-SBX-041 | Delete an existing test sandbox | Sandbox is deleted | 🟠 Blocked |
| MCP-SBX-042 | Delete a missing sandbox | Returns a clear failure | 🟠 Blocked |
| MCP-SBX-043 | Verify deletion after delete succeeds | Sandbox no longer appears as an existing resource | 🟠 Blocked |
| MCP-SBX-044 | Interrupt or fail a lifecycle operation | Reports the actual outcome and permits safe recovery | 🟠 Blocked |
| MCP-SBX-045 | Verify lifecycle isolation | Operations affect only the named test sandbox | 🟠 Blocked |
| MCP-SBX-046 | Verify cleanup after a failed lifecycle test | Test-created sandboxes are removed or their retained state is explicitly reported | 🟠 Blocked |

### 7.4 Execute Commands

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-SBX-050 | Execute a harmless command in an existing sandbox | Command runs inside the specified sandbox | 🟠 Blocked |
| MCP-SBX-051 | Execute a command that returns output | Output is returned accurately | 🟠 Blocked |
| MCP-SBX-052 | Execute a command that exits non-zero | Failure is accurately reported and not represented as success | 🟠 Blocked |
| MCP-SBX-053 | Execute a command with spaces and shell-special characters in its command string | Input is handled according to the underlying command execution contract without accidental host execution | 🟠 Blocked |
| MCP-SBX-054 | Execute a command in a missing sandbox | Returns a clear failure | 🟠 Blocked |
| MCP-SBX-055 | Omit required `name` or `command` | Input validation rejects the call | 🟠 Blocked |
| MCP-SBX-056 | Verify command execution boundary | Command executes in the requested sandbox, not on the MCP server host | 🟠 Blocked |
| MCP-SBX-057 | Verify output/error handling for a command failure | Diagnostic information is preserved without leaking unrelated secrets | 🟠 Blocked |

## 8. Workspace File Tools

Current registered tools:

- `list_workspace_files(sandbox_name)`
- `read_workspace_text_file(sandbox_name, relative_path)`
- `create_workspace_file(sandbox_name, relative_path, content)`
- `write_workspace_file(sandbox_name, relative_path, content)`
- `create_workspace_directory(sandbox_name, relative_path)`
- `rename_workspace_path(sandbox_name, relative_path, new_relative_path)`
- `delete_workspace_file(sandbox_name, relative_path)`
- `delete_workspace_directory(sandbox_name, relative_path)`
- `list_authorized_host_workspaces()`

Workspace file operations target `/workspace/project` inside the selected OpenShell sandbox. The current implementation defines 1,000,000-byte limits for read/write content and a 4,096-byte maximum relative-path limit. Tests must verify the actual boundary behavior of the service rather than assume that all limits are enforced identically by every operation.

### 8.1 List and Read

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-WS-001 | List files in an existing sandbox | Returns a list of regular files under the workspace root | ⚪ Not implemented |
| MCP-WS-002 | List files in an empty workspace | Returns a valid empty list | ⚪ Not implemented |
| MCP-WS-003 | List files with nested directories | Includes eligible nested files using workspace-relative paths | ⚪ Not implemented |
| MCP-WS-004 | List files when symlinks point outside the workspace | Does not follow outside symlinks to expose external files | ⚪ Not implemented |
| MCP-WS-005 | List files for a missing sandbox | Returns a clear failure | ⚪ Not implemented |
| MCP-WS-006 | Read an existing UTF-8 text file | Returns exact file contents | ⚪ Not implemented |
| MCP-WS-007 | Read a nested file | Returns contents using a valid relative path | ⚪ Not implemented |
| MCP-WS-008 | Read a missing file | Returns a clear error | ⚪ Not implemented |
| MCP-WS-009 | Read a directory instead of a file | Rejects the request because the target is not a regular file | ⚪ Not implemented |
| MCP-WS-010 | Read a file containing invalid UTF-8 | Returns a clear validation error | ⚪ Not implemented |
| MCP-WS-011 | Read a file exceeding the read-size limit | Rejects the oversized file | ⚪ Not implemented |
| MCP-WS-012 | Read using an empty path | Rejects the request | ⚪ Not implemented |
| MCP-WS-013 | Read using an absolute path | Rejects the request because paths must be relative | ⚪ Not implemented |
| MCP-WS-014 | Read using `..` path traversal outside the workspace | Rejects the request | ⚪ Not implemented |
| MCP-WS-015 | Read through a symlink resolving outside the workspace | Rejects the request | ⚪ Not implemented |
| MCP-WS-016 | Read using an excessively long path | Enforces the intended path-length boundary or reports a documented failure | ⚪ Not implemented |

### 8.2 Create, Write, and Directory Operations

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-WS-020 | Create a new UTF-8 file | File is created with the requested contents | ⚪ Not implemented |
| MCP-WS-021 | Create a file in a nested directory | Missing parent directories are created as implemented | ⚪ Not implemented |
| MCP-WS-022 | Create a file at an existing path | Operation fails without overwriting the existing file | ⚪ Not implemented |
| MCP-WS-023 | Create a file with content at the maximum supported size | Operation follows the configured size limit | ⚪ Not implemented |
| MCP-WS-024 | Create a file with oversized content | Operation rejects oversized content | ⚪ Not implemented |
| MCP-WS-025 | Create a file with an absolute path | Operation rejects the request | ⚪ Not implemented |
| MCP-WS-026 | Create a file using path traversal | Operation rejects paths escaping the workspace | ⚪ Not implemented |
| MCP-WS-027 | Create a file through a symlink path | Operation rejects a symbolic-link target | ⚪ Not implemented |
| MCP-WS-028 | Write to an existing file | Existing file content is replaced with the requested content | ⚪ Not implemented |
| MCP-WS-029 | Write to a missing file | Operation fails rather than silently creating an absent file | ⚪ Not implemented |
| MCP-WS-030 | Write to a directory | Operation rejects the request | ⚪ Not implemented |
| MCP-WS-031 | Write oversized content | Operation rejects the content | ⚪ Not implemented |
| MCP-WS-032 | Write using path traversal or an absolute path | Operation rejects the request | ⚪ Not implemented |
| MCP-WS-033 | Create a directory | Directory is created at the requested relative path | ⚪ Not implemented |
| MCP-WS-034 | Create nested directories | Parent directories are created as implemented | ⚪ Not implemented |
| MCP-WS-035 | Create a directory where a file or directory already exists | Operation fails without replacing the existing path | ⚪ Not implemented |
| MCP-WS-036 | Create a directory outside the workspace | Operation rejects the request | ⚪ Not implemented |
| MCP-WS-037 | Verify create/write round trip | Reading the created or updated file returns the expected contents | ⚪ Not implemented |

### 8.3 Rename and Delete

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-WS-040 | Rename a regular file | File appears at the destination and no longer exists at the source | ⚪ Not implemented |
| MCP-WS-041 | Rename a directory | Directory and its contents appear at the destination | ⚪ Not implemented |
| MCP-WS-042 | Rename a missing source path | Operation fails with a clear error | ⚪ Not implemented |
| MCP-WS-043 | Rename to an existing destination | Operation fails without overwriting the destination | ⚪ Not implemented |
| MCP-WS-044 | Rename with an empty source or destination | Operation rejects the request | ⚪ Not implemented |
| MCP-WS-045 | Rename using absolute paths or path traversal | Operation rejects paths outside the workspace | ⚪ Not implemented |
| MCP-WS-046 | Delete a regular file | File is removed | ⚪ Not implemented |
| MCP-WS-047 | Delete a missing file | Operation fails with a clear error | ⚪ Not implemented |
| MCP-WS-048 | Delete a directory using the file-delete tool | Operation rejects the target as not a regular file | ⚪ Not implemented |
| MCP-WS-049 | Delete a directory tree using the directory-delete tool | Requested directory tree is removed | ⚪ Not implemented |
| MCP-WS-050 | Delete a missing directory | Operation fails with a clear error | ⚪ Not implemented |
| MCP-WS-051 | Delete using an absolute path or traversal path | Operation rejects paths outside the workspace | ⚪ Not implemented |
| MCP-WS-052 | Delete a directory containing nested files | Only the requested in-workspace tree is removed | ⚪ Not implemented |
| MCP-WS-053 | Verify rename/delete side effects | No unrelated workspace paths are changed | ⚪ Not implemented |
| MCP-WS-054 | Verify cleanup after failed workspace operations | Temporary test files and directories are removed when safe to do so | ⚪ Not implemented |

### 8.4 Authorized Host Workspaces

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-WS-060 | Call `list_authorized_host_workspaces` | Returns a list of broker-issued workspace grants | ⚪ Not implemented |
| MCP-WS-061 | Validate grant response schema | Entries contain workspace ID, host path, volume name, target, and read-only status as implemented | ⚪ Not implemented |
| MCP-WS-062 | List grants when none exist | Returns a valid empty list | ⚪ Not implemented |
| MCP-WS-063 | Verify ordering and filtering | Results are consistently ordered and malformed/non-capability entries are excluded as implemented | ⚪ Not implemented |
| MCP-WS-064 | Verify unknown workspace IDs are not exposed as valid grants | Only recognized authorized grants are returned | ⚪ Not implemented |
| MCP-WS-065 | Verify host filesystem isolation | The MCP container does not independently inspect arbitrary host paths when resolving/listing grants | ⚪ Not implemented |

## 10. Chrome DevTools Tool

Current signature: `execute_chrome_devtools_command(sandbox_name, command, arguments=None)`. The implementation delegates to the Chrome DevTools service. Its tool annotations mark the operation destructive and open-world. The caller cannot select or override the Chrome connection endpoint.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-CDP-001 | Execute a supported read-only DevTools command in a browser sandbox | Returns the service result | ⚪ Not implemented |
| MCP-CDP-002 | Execute a command with no optional arguments | Optional `arguments` default is handled correctly | ⚪ Not implemented |
| MCP-CDP-003 | Execute a command with an argument list | Arguments are preserved in order | ⚪ Not implemented |
| MCP-CDP-004 | Omit a required argument | Input validation rejects the request | ⚪ Not implemented |
| MCP-CDP-005 | Target a missing sandbox | Returns a clear error | ⚪ Not implemented |
| MCP-CDP-006 | Target a sandbox without a browser profile | Returns a clear readiness/profile error | ⚪ Not implemented |
| MCP-CDP-007 | Call while DevTools is not ready | Returns the service's actionable readiness error | ⚪ Not implemented |
| MCP-CDP-008 | Cause the DevTools command to fail | Returns an accurate failure result | ⚪ Not implemented |
| MCP-CDP-009 | Attempt to override the Chrome endpoint | Caller cannot redirect execution to an arbitrary endpoint | ⚪ Not implemented |
| MCP-CDP-010 | Pass special characters through arguments | Arguments remain within the intended CLI invocation boundary | ⚪ Not implemented |
| MCP-CDP-011 | Verify execution location | DevTools commands execute in the selected browser sandbox | ⚪ Not implemented |
| MCP-CDP-012 | Verify tool annotations | Tool is marked destructive and open-world as implemented | ⚪ Not implemented |
| MCP-CDP-013 | Verify error propagation | Service validation and execution failures are surfaced without false success | ⚪ Not implemented |

## 11. Error Handling and Input Validation

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-ERR-001 | Call a tool with missing required fields | MCP returns an appropriate validation/tool error | ⚪ Not implemented |
| MCP-ERR-002 | Call a tool with the wrong JSON value type | Invalid input is rejected without server crash | ⚪ Not implemented |
| MCP-ERR-003 | Supply unexpected extra fields | Behavior follows the advertised input schema and protocol implementation | ⚪ Not implemented |
| MCP-ERR-004 | Supply empty strings for required names or paths | Invalid values are rejected by the appropriate validation layer | ⚪ Not implemented |
| MCP-ERR-005 | Supply extremely long strings within the protocol body limit | Input is handled safely and any applicable domain limits are enforced | ⚪ Not implemented |
| MCP-ERR-006 | Trigger an expected domain validation error | Client receives an MCP tool error or documented failure result | ⚪ Not implemented |
| MCP-ERR-007 | Trigger an underlying OpenShell service failure | Failure is surfaced without a false success result | ⚪ Not implemented |
| MCP-ERR-008 | Trigger a missing-resource error | Error identifies the failed operation without leaking unrelated data | ⚪ Not implemented |
| MCP-ERR-009 | Trigger an unexpected exception in a controlled test | Server logs the failure and remains available where recovery is possible | ⚪ Not implemented |
| MCP-ERR-010 | Verify error result content | Tool errors are represented consistently through the MCP client | ⚪ Not implemented |
| MCP-ERR-011 | Verify malformed results are not silently treated as valid data | Invalid downstream results fail clearly | ⚪ Not implemented |
| MCP-ERR-012 | Retry after a recoverable error | Subsequent valid calls still work | ⚪ Not implemented |

## 12. Security and Isolation

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-SEC-001 | Attempt workspace path traversal through read operations | Cannot read outside `/workspace/project` | ⚪ Not implemented |
| MCP-SEC-002 | Attempt workspace path traversal through create/write operations | Cannot create or overwrite files outside `/workspace/project` | ⚪ Not implemented |
| MCP-SEC-003 | Attempt workspace path traversal through rename/delete operations | Cannot rename or delete paths outside `/workspace/project` | ⚪ Not implemented |
| MCP-SEC-004 | Attempt to access files through an external symlink | External paths are not exposed or modified | ⚪ Not implemented |
| MCP-SEC-005 | Attempt to authorize or use a nonexistent host workspace | No invalid workspace capability is created or used | ⚪ Not implemented |
| MCP-SEC-006 | Attempt to use a revoked or unknown workspace ID | Operation fails and does not create an unintended binding | ⚪ Not implemented |
| MCP-SEC-007 | Attempt to execute a host command through sandbox tools | Command remains confined to the requested sandbox | ⚪ Not implemented |
| MCP-SEC-009 | Attempt to redirect DevTools to an arbitrary endpoint | Caller cannot override the managed Chrome endpoint | ⚪ Not implemented |
| MCP-SEC-010 | Submit requests with a disallowed Host header | Transport security rejects the request | ⚪ Not implemented |
| MCP-SEC-011 | Inspect errors for environment secrets | Errors do not reveal API keys or unrelated credential contents | ⚪ Not implemented |
| MCP-SEC-012 | Inspect server logs for secret leakage | Logs do not contain secret values supplied to tools | ⚪ Not implemented |
| MCP-SEC-013 | Verify tool annotations for destructive operations | Destructive tool hints match the actual behavior | ⚪ Not implemented |
| MCP-SEC-014 | Verify that a tool call affects only its named sandbox | No unrelated sandbox is mutated | ⚪ Not implemented |
| MCP-SEC-015 | Verify test resource cleanup | Test resources do not leak into the shared environment | ⚪ Not implemented |

## 13. Request Logging and Observability

The current middleware logs request metadata, the registered tool names, a registry fingerprint, and success/error response status. The request log fields include instance ID, PID, method, request ID, protocol version, session ID, tool name, whether the tool is registered, registry count, and registry fingerprint.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-LOG-001 | Send a valid tool request | A request log entry is emitted | ⚪ Not implemented |
| MCP-LOG-002 | Verify request metadata fields | Available request metadata is recorded | ⚪ Not implemented |
| MCP-LOG-003 | Verify tool identification | Tool name and registration status are logged when available | ⚪ Not implemented |
| MCP-LOG-004 | Verify registry metadata | Registry count, sorted tool names, and fingerprint are emitted | ⚪ Not implemented |
| MCP-LOG-005 | Verify successful response logging | Response is logged with `status=success` | ⚪ Not implemented |
| MCP-LOG-006 | Trigger an exception in a tool call | Error response is logged with `status=error` and error type | ⚪ Not implemented |
| MCP-LOG-007 | Trigger a registry inspection failure in a controlled test | Failure is logged and the middleware uses its defined fallback values | ⚪ Not implemented |
| MCP-LOG-008 | Verify logs do not contain tool argument secrets | Secret values are not included in request logs | ⚪ Not implemented |
| MCP-LOG-009 | Verify logs do not contain complete file contents | Workspace file contents are not logged by request metadata middleware | ⚪ Not implemented |
| MCP-LOG-010 | Compare registry fingerprint for an unchanged registry | Fingerprint remains stable for the same sorted tool-name set | ⚪ Not implemented |
| MCP-LOG-011 | Change the tool registry in a controlled test | Fingerprint changes when the sorted tool-name set changes | ⚪ Not implemented |
| MCP-LOG-012 | Verify log correlation fields | Request and response entries contain the relevant correlation identifiers when provided | ⚪ Not implemented |

## 14. Cross-Tool Workflows

These tests validate end-to-end behavior across multiple tools. Use unique test resources and ensure cleanup in fixture finalizers.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-FLOW-001 | Create sandbox, inspect status, execute command, delete sandbox | Full lifecycle succeeds and the sandbox is removed | ⚪ Not implemented |
| MCP-FLOW-002 | Create sandbox and list its workspace files | Workspace tool targets the correct sandbox | ⚪ Not implemented |
| MCP-FLOW-003 | Create, read, write, rename, and delete a test file | File contents and paths match each operation | ⚪ Not implemented |
| MCP-FLOW-004 | Create and delete a nested directory tree | Directory operations work as expected and leave no test artifacts | ⚪ Not implemented |
| MCP-FLOW-005 | Authorize host workspace, create host-backed sandbox, inspect binding | Sandbox is bound only to the authorized workspace | ⚪ Not implemented |
| MCP-FLOW-006 | Attempt to use a nonexistent host workspace during creation | Sandbox creation fails safely | ⚪ Not implemented |
| MCP-FLOW-007 | Create a browser sandbox and execute a DevTools command | Browser tool operates against the intended sandbox | ⚪ Not implemented |
| MCP-FLOW-009 | Cause a tool failure and call a different read-only tool afterward | A tool error does not unnecessarily take down the server | ⚪ Not implemented |
| MCP-FLOW-010 | Execute multiple independent tool calls against separate test sandboxes | Results and mutations remain isolated between sandboxes | ⚪ Not implemented |
| MCP-FLOW-011 | Run a multi-step workflow with a failure in the middle | Failure is accurately reported and previously created resources are cleaned up | ⚪ Not implemented |
| MCP-FLOW-012 | Repeat an idempotent read operation | Repeated calls do not cause unexpected state changes | ⚪ Not implemented |

## 15. Existing Integration Test Mapping

The repository currently has `tests/integration/test_mcp_server.py`. These integration checks are separate from the proposed E2E suite and are enabled only when `RUN_MCP_INTEGRATION=1` is set.

| Existing Test | Current Coverage | Execution Requirement |
|---|---|---|
| `test_mcp_health_endpoint` | Health endpoint response and service identity | Running server; `RUN_MCP_INTEGRATION=1` |
| `test_mcp_negotiates_current_protocol` | Protocol version, server identity, and tool capability | Running server; `RUN_MCP_INTEGRATION=1` |
| `test_mcp_exposes_current_tool_surface` | Exact registered tool set | Running server; `RUN_MCP_INTEGRATION=1` |
| `test_mcp_tool_call_round_trip` | Successful `get_system_info` call | Running server; `RUN_MCP_INTEGRATION=1` |

These tests should remain useful as integration checks. The E2E suite should add the broader tool-by-tool and workflow coverage above rather than duplicate these checks without additional value.

## 16. Test Environment, Safety, and Cleanup

- Use a dedicated MCP server instance and a dedicated OpenShell test environment.
- Use only unique sandbox names and disposable workspace directories.
- Never run destructive tests against production or shared user sandboxes.
- Never use real API keys, credentials, or private user files as test inputs.
- Register cleanup immediately after creating a sandbox, workspace file, directory, or other resource.
- Use harmless commands for command-execution tests.
- Avoid browser actions that affect accounts, external websites, or persistent user sessions.
- Capture stdout, stderr, MCP result content, and relevant server logs when diagnosing failures, while redacting secrets.
- Ensure a test failure cannot leave an unexpected sandbox or test file behind.
- Record environmental prerequisites and mark unavailable infrastructure as Blocked rather than Pass.
- Keep integration and E2E outcomes distinct in reports.

## 17. Recommended Execution Order

1. Run unit tests and validate the tool registration/schema contract.
2. Start the dedicated MCP server and run health and transport checks.
3. Run tool registry and read-only tool tests.
4. Run workspace file tests in a disposable sandbox.
5. Run sandbox lifecycle tests with guaranteed cleanup.
7. Run Chrome DevTools tests against a dedicated browser sandbox.
8. Run security-boundary tests.
9. Run cross-tool workflows.
10. Review server logs, verify cleanup, and update each test status using actual execution evidence.

## 18. Completion Criteria

The MCP E2E report is complete when:

- Every registered tool has successful-path and failure-path coverage appropriate to its behavior.
- Transport initialization, health checks, tool discovery, and protocol errors are covered.
- Required and optional inputs are validated against the registered schemas.
- Workspace and sandbox isolation boundaries are tested.
- Destructive operations are tested only with disposable resources.
- Error propagation and log redaction are verified.
- Cross-tool workflows run successfully.
- Every result is backed by an actual test execution.
- Blocked or skipped tests include an explicit reason.
- All test-created resources are cleaned up or explicitly accounted for.


## 19. NEW GROUP — Browser & Website Clone E2E Coverage

### Browser / MCP App

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-BROWSER-NEW-001 | Browser App resource registration | ui://browser/view is registered and returns the Browser App resource | ⚪ Not implemented |
| MCP-BROWSER-NEW-002 | browser_open App flow | Opens the requested browser sandbox/page and returns expected App metadata/resource | ⚪ Not implemented |
| MCP-BROWSER-NEW-003 | browser_pages | Lists browser pages with page IDs, URLs, and titles | ⚪ Not implemented |
| MCP-BROWSER-NEW-004 | browser_navigate valid public URL | Navigates the selected page successfully | ⚪ Not implemented |
| MCP-BROWSER-NEW-005 | browser_navigate unsafe URL | Rejects loopback/private/link-local/reserved, invalid-scheme, and credential-bearing URLs | ⚪ Not implemented |
| MCP-BROWSER-NEW-006 | browser_snapshot | Returns a usable page snapshot | ⚪ Not implemented |
| MCP-BROWSER-NEW-007 | browser_inspect valid selector | Returns inspection data for the requested element | ⚪ Not implemented |
| MCP-BROWSER-NEW-008 | browser_inspect invalid/oversized selector | Returns validation error without unintended browser side effects | ⚪ Not implemented |
| MCP-BROWSER-NEW-009 | browser_evaluate valid script | Evaluates the script and returns the result | ⚪ Not implemented |
| MCP-BROWSER-NEW-010 | browser_evaluate empty/oversized script | Rejects invalid input before execution | ⚪ Not implemented |
| MCP-BROWSER-NEW-011 | browser_screenshot | Returns a valid image and cleans temporary artifacts | ⚪ Not implemented |
| MCP-BROWSER-NEW-012 | Invalid browser sandbox/page ID | Returns a clear validation error without touching an unintended page | ⚪ Not implemented |
| MCP-BROWSER-NEW-013 | Browser App action flow | Snapshot, inspect, screenshot, and clone actions invoke intended server tools | ⚪ Not implemented |
| MCP-BROWSER-NEW-014 | Browser App CSP/resource loading | App loads without undeclared external resource dependencies | ⚪ Not implemented |

### Website Clone

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-CLONE-NEW-001 | clone_preview full page | Returns clone metadata/payload without unexpected file writes | ⚪ Not implemented |
| MCP-CLONE-NEW-002 | clone_preview valid selector | Returns preview for the selected DOM region | ⚪ Not implemented |
| MCP-CLONE-NEW-003 | clone_preview missing selector | Returns a clear validation error | ⚪ Not implemented |
| MCP-CLONE-NEW-004 | clone_region valid selector | Writes a sanitized index.html for the selected region | ⚪ Not implemented |
| MCP-CLONE-NEW-005 | clone_page | Writes a sanitized full-page clone with expected output metadata | ⚪ Not implemented |
| MCP-CLONE-NEW-006 | Clone preserves safe markup | Expected structural HTML and safe attributes are retained | ⚪ Not implemented |
| MCP-CLONE-NEW-007 | Clone strips executable content | Scripts, iframes, inline event handlers, and other executable content are removed | ⚪ Not implemented |
| MCP-CLONE-NEW-008 | Clone sanitizes dangerous URLs | Dangerous URL schemes are removed or neutralized | ⚪ Not implemented |
| MCP-CLONE-NEW-009 | Clone sanitizes CSS | CSS size/breakout constraints are enforced | ⚪ Not implemented |
| MCP-CLONE-NEW-010 | Clone title/filename safety | Generated title and filesystem slug cannot cause HTML/path injection | ⚪ Not implemented |
| MCP-CLONE-NEW-011 | Clone output isolation | Output is written only inside the requested sandbox workspace | ⚪ Not implemented |
| MCP-CLONE-NEW-012 | External asset reporting | External stylesheet/assets are surfaced according to current V1 behavior | ⚪ Not implemented |
| MCP-CLONE-NEW-013 | End-to-end website clone | Navigate → inspect → preview → clone produces a usable sanitized artifact | ⚪ Not implemented |

### Registry / Integration / Security

| ID | Test | Expected Result | Status |
|---|---|---|---|
| MCP-REG-NEW-001 | Browser and clone tools in MCP registry | New tools expose expected names and schemas alongside existing tools | ⚪ Not implemented |
| MCP-REG-NEW-002 | Browser tool annotations | Read-only browser tools expose accurate read-only annotations | ⚪ Not implemented |
| MCP-REG-NEW-003 | Clone tool annotations | Clone write tools expose accurate write/destructive semantics | ⚪ Not implemented |
| MCP-REG-NEW-004 | Browser validation round trip | Invalid URL/page input returns service validation error without false success | ⚪ Not implemented |
| MCP-REG-NEW-005 | Clone validation round trip | Invalid selector/page input returns expected validation error | ⚪ Not implemented |
| MCP-REG-NEW-006 | Browser + clone coexistence | Existing terminal/MCP tool behavior remains unchanged | ⚪ Not implemented |
| MCP-REG-NEW-007 | Browser sandbox network policy | Allowed HTTP/HTTPS destinations work and disallowed targets remain blocked | ⚪ Not implemented |
| MCP-REG-NEW-008 | Full MCP website-cloning flow | Real page can be opened, inspected, previewed, and cloned without bypassing sandbox/security boundaries | ⚪ Not implemented |
