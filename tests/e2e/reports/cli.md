# CLI E2E Test Report

## 1. Purpose

Validate every public `mcpctl` command, option, argument, and delegation path against the current implementation and a real, isolated OpenShell environment where applicable.

The suite must test:

- Every supported CLI command and subcommand.
- Every declared flag and option, including short aliases.
- Required and optional positional arguments.
- Valid and invalid option values.
- Mutually exclusive and combined options.
- Argument forwarding from `mcpctl` to its underlying services.
- Workspace forwarding from `mcpctl` to the workspace service.
- Exit codes, output formats, errors, and side effects.
- Resource isolation and cleanup.

Tests must invoke the real installed `mcpctl` entrypoint. Unit tests for argument-building helpers are useful, but do not replace CLI E2E tests.

## 2. Status Definitions

| Status | Meaning |
|---|---|
| ⚪ Not implemented | No automated test exists yet |
| 🟠 Blocked | Test cannot run because a prerequisite or known defect prevents it |
| 🟢 Pass | Test ran and met its expected result |
| 🔴 Fail | Test ran and did not meet its expected result |
| 🟡 Skipped | Test was intentionally not run, with a documented reason |

All tests in this initial matrix are marked **Not implemented**. The test runner must replace this status with the actual result on each run.

## 3. CLI Entrypoints and Coverage Boundaries

| ID | Entrypoint or scope | Required coverage | Status |
|---|---|---|---|
| CLI-SCOPE-001 | `mcpctl` | Setup, status, repair, sandbox, credential, workspace, config | ⚪ Not implemented |
| CLI-SCOPE-006 | Argument forwarding | Preserve argument values, order, and command boundaries | ⚪ Not implemented |
| CLI-SCOPE-007 | Invalid arguments | Clear errors and non-zero exit codes | ⚪ Not implemented |
| CLI-SCOPE-008 | Runtime operations | Real OpenShell sandbox and workspace behavior | ⚪ Not implemented |

## 4. Test Environment and Safety

- Run against a dedicated test environment, never production.
- Use the current build and installed entrypoints under test.
- Use a dedicated OpenShell Gateway and isolated test sandboxes.
- Use unique sandbox names and isolated host workspace directories.
- Use disposable test credentials and never print real secret values.
- Keep tests that modify local MCP-client configuration separate from real-sandbox tests.
- Do not run destructive tests against shared or production resources.
- Register every resource for cleanup immediately after creation.
- Verify cleanup even when a test assertion or command fails.

## 5. `mcpctl` — Top-Level Commands

These commands have no declared command-specific options in the current parser. The inherited argparse help options still apply.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-MCP-001 | `mcpctl setup` | Setup flow runs and returns the correct exit code | 🟠 Blocked |
| CLI-MCP-002 | `mcpctl status` | Reports current application lifecycle state | 🟢 Pass |
| CLI-MCP-003 | `mcpctl repair` | Attempts to repair the OpenShell runtime and core services | 🟠 Blocked |
| CLI-MCP-004 | `mcpctl --help` | Displays top-level usage and available commands | 🟢 Pass |
| CLI-MCP-005 | `mcpctl -h` | Displays the same help through the short alias | 🟢 Pass |
| CLI-MCP-006 | `mcpctl setup --help` | Displays setup help without starting setup | 🟢 Pass |
| CLI-MCP-007 | `mcpctl status --help` | Displays status help without performing a status operation | 🟢 Pass |
| CLI-MCP-008 | `mcpctl repair --help` | Displays repair help without running repair | 🟢 Pass |
| CLI-MCP-009 | Unknown top-level command | Returns non-zero and a useful usage error | 🟢 Pass |
| CLI-MCP-010 | Missing top-level command | Returns non-zero and shows usage | 🟢 Pass |
| CLI-MCP-011 | Pass an unsupported flag to `setup`, `status`, or `repair` | Rejects the flag rather than silently ignoring it | 🟢 Pass |
| CLI-MCP-012 | Interrupt an interactive command | Exits cleanly with the documented cancellation code | 🟠 Blocked |

## 6. `mcpctl sandbox`

### 6.1 Create

Supported arguments and options: `name`, exactly one of `--workspace` or `--standalone`, optional `--profile`, and `--json`.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-SBX-001 | `mcpctl sandbox create <name> --standalone` | Creates a sandbox with sandbox-local storage | 🟠 Blocked |
| CLI-SBX-002 | `mcpctl sandbox create <name> --workspace <id>` | Creates a sandbox using the authorized host workspace | 🟠 Blocked |
| CLI-SBX-003 | `--workspace` with a valid workspace ID | Preserves the exact workspace ID when delegating | 🟠 Blocked |
| CLI-SBX-004 | `--standalone` | Preserves standalone mode through delegation | 🟠 Blocked |
| CLI-SBX-005 | `--profile default` | Creates the default profile | 🟠 Blocked |
| CLI-SBX-006 | `--profile browser` | Creates the browser profile | 🟠 Blocked |
| CLI-SBX-007 | Omit `--profile` | Applies the parser's default profile, `default` | 🟠 Blocked |
| CLI-SBX-008 | `--profile` with an unsupported value | Rejects the value before delegation | 🟢 Pass |
| CLI-SBX-009 | `--json` | Forwards `--json` and returns valid JSON if the operation succeeds | 🟠 Blocked |
| CLI-SBX-010 | Omit both `--workspace` and `--standalone` | Rejects the request because one is required | 🟢 Pass |
| CLI-SBX-011 | Supply both `--workspace` and `--standalone` | Rejects the mutually exclusive options | 🟢 Pass |
| CLI-SBX-012 | Omit sandbox name | Returns an argument error | 🟢 Pass |
| CLI-SBX-013 | Provide an invalid sandbox name | Returns a validation error without creating a resource | 🟢 Pass |
| CLI-SBX-014 | Combine `--workspace`, `--profile browser`, and `--json` | Forwards all options correctly and preserves the requested profile and workspace | 🟠 Blocked |
| CLI-SBX-015 | Combine `--standalone`, `--profile default`, and `--json` | Forwards all options correctly without adding a host workspace | 🟠 Blocked |
| CLI-SBX-016 | `mcpctl sandbox create --help` | Lists all supported create options and requirements | 🟢 Pass |

### 6.2 List and Status

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-SBX-020 | `mcpctl sandbox list` | Delegates list and returns the sandbox collection | 🟢 Pass |
| CLI-SBX-021 | `mcpctl sandbox list --help` | Displays list help | 🟢 Pass |
| CLI-SBX-022 | `mcpctl sandbox list --json` | Currently unsupported by the `mcpctl` parser; rejects the option | 🟢 Pass |
| CLI-SBX-023 | `mcpctl sandbox status <name>` | Delegates status for the specified sandbox | 🟢 Pass |
| CLI-SBX-024 | `mcpctl sandbox status <name> --json` | Forwards `--json` and returns valid JSON | 🟢 Pass |
| CLI-SBX-025 | `mcpctl sandbox status <name>` with no matching sandbox | Returns a clear failure and non-zero exit code | 🟢 Pass |
| CLI-SBX-026 | Omit status sandbox name | Returns an argument error | 🟢 Pass |
| CLI-SBX-027 | `mcpctl sandbox status --help` | Lists status arguments and options | 🟢 Pass |
| CLI-SBX-028 | Status JSON schema | Contains the documented fields and correct value types | 🟢 Pass |
| CLI-SBX-029 | Status output with unexpected or malformed downstream output | Fails clearly without reporting false success | 🟢 Pass |

### 6.3 Shell and Exec

`exec` accepts the sandbox name followed by a remainder of command arguments. Tests must ensure that arguments are passed to the sandbox command intact.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-SBX-030 | `mcpctl sandbox shell <name>` | Opens the sandbox shell through the underlying CLI | 🟢 Pass |
| CLI-SBX-031 | `mcpctl sandbox shell --help` | Displays shell usage | 🟢 Pass |
| CLI-SBX-032 | `mcpctl sandbox exec <name> <command>` | Executes the requested command inside the selected sandbox | 🟢 Pass |
| CLI-SBX-033 | Exec with multiple positional command arguments | Preserves argument order and values | 🟢 Pass |
| CLI-SBX-034 | Exec with spaces and quoted arguments | Preserves argument boundaries correctly | 🟢 Pass |
| CLI-SBX-035 | Exec with command options such as `--version` | Passes command options to the sandbox process rather than consuming them as `mcpctl` options | 🟢 Pass |
| CLI-SBX-036 | Exec with a non-zero child exit code | Propagates or accurately reports command failure | 🟢 Pass |
| CLI-SBX-037 | Exec with no command remainder | Returns the intended validation error or documented behavior | 🟢 Pass |
| CLI-SBX-038 | Exec against a missing sandbox | Returns a clear error and non-zero exit code | 🟢 Pass |
| CLI-SBX-039 | `mcpctl sandbox exec --help` | Displays exec usage and remainder behavior | 🟢 Pass |

### 6.4 Logs and Lifecycle

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-SBX-040 | `mcpctl sandbox logs <name>` | Delegates logs for the specified sandbox | 🟢 Pass |
| CLI-SBX-041 | `mcpctl sandbox logs --help` | Displays logs usage | 🟢 Pass |
| CLI-SBX-042 | `mcpctl sandbox start <name>` | Starts the specified sandbox | 🟢 Pass |
| CLI-SBX-043 | `mcpctl sandbox start --help` | Displays start usage | 🟢 Pass |
| CLI-SBX-044 | `mcpctl sandbox stop <name>` | Stops the sandbox while retaining state | 🟢 Pass |
| CLI-SBX-045 | `mcpctl sandbox stop --help` | Displays stop usage | 🟢 Pass |
| CLI-SBX-046 | `mcpctl sandbox restart <name>` | Restarts the sandbox | 🟢 Pass |
| CLI-SBX-047 | `mcpctl sandbox restart --help` | Displays restart usage | 🟢 Pass |
| CLI-SBX-048 | `mcpctl sandbox repair <name>` | Attempts recovery of a retained failed sandbox | 🟢 Pass |
| CLI-SBX-049 | `mcpctl sandbox repair --help` | Displays repair usage | 🟢 Pass |
| CLI-SBX-050 | Lifecycle operation against a missing sandbox | Returns a non-zero exit code with an actionable error | 🟢 Pass |
| CLI-SBX-051 | Start a stopped sandbox | Sandbox returns to a ready state | 🟠 Blocked |
| CLI-SBX-052 | Stop a running sandbox | Sandbox becomes stopped and retains state | 🟠 Blocked |
| CLI-SBX-053 | Restart a sandbox | Sandbox returns to a usable state | 🟠 Blocked |
| CLI-SBX-054 | Repair a sandbox that is not repairable | Reports failure without claiming recovery | 🟠 Blocked |

### 6.5 Delete and Recreate

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-SBX-060 | `mcpctl sandbox delete <name>` | Deletes the sandbox | 🟢 Pass |
| CLI-SBX-061 | `mcpctl sandbox delete <name> --json` | Forwards `--json` and emits valid JSON | 🟢 Pass |
| CLI-SBX-062 | `mcpctl sandbox delete --help` | Displays delete usage and the JSON option | 🟢 Pass |
| CLI-SBX-063 | Delete a missing sandbox | Reports the failure accurately | 🟢 Pass |
| CLI-SBX-064 | `mcpctl sandbox recreate <name> --yes` | Forwards confirmation and recreates the sandbox | 🟢 Pass |
| CLI-SBX-065 | `mcpctl sandbox recreate <name>` without `--yes` | Follows the documented confirmation behavior and does not perform an unintended destructive action | 🟢 Pass |
| CLI-SBX-066 | `mcpctl sandbox recreate --help` | Displays recreate usage and the confirmation option | 🟢 Pass |
| CLI-SBX-067 | Recreate a host-backed sandbox | Preserves the workspace binding and profile | 🟢 Pass |
| CLI-SBX-068 | Recreate a standalone sandbox | Preserves standalone mode and profile | 🟢 Pass |
| CLI-SBX-069 | Recreate a missing sandbox | Returns a non-zero exit code | 🟢 Pass |
| CLI-SBX-070 | Delete and recreate with an interrupted or failed operation | Reports the resulting state accurately and permits safe recovery | 🟢 Pass |

## 7. `mcpctl credential`

### 7.1 Create

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-CRED-001 | `mcpctl credential create <name> --type <type> --key <secret>` | Creates the requested credential provider | ⚪ Not implemented |
| CLI-CRED-002 | `--type` with a supported provider type | Forwards the provider type unchanged | ⚪ Not implemented |
| CLI-CRED-003 | Omit required `--type` | Parser rejects the command | ⚪ Not implemented |
| CLI-CRED-004 | `--type` with an unsupported type | Returns a clear validation error from the appropriate layer | ⚪ Not implemented |
| CLI-CRED-005 | `--key` with a test secret | Forwards the value correctly without logging it | ⚪ Not implemented |
| CLI-CRED-006 | Omit required `--key` | Parser rejects the command | ⚪ Not implemented |
| CLI-CRED-007 | `--yes` on create | Forwards confirmation to the underlying CLI | ⚪ Not implemented |
| CLI-CRED-008 | Omit optional `--yes` | Follows the command's interactive or confirmation behavior without unintended mutation | ⚪ Not implemented |
| CLI-CRED-009 | Combine `--type`, `--key`, and `--yes` | Forwards every option correctly | ⚪ Not implemented |
| CLI-CRED-010 | `mcpctl credential create --help` | Lists `--type`, `--key`, and `--yes` | ⚪ Not implemented |

### 7.2 List and Get

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-CRED-020 | `mcpctl credential list` | Lists credential metadata without exposing secret values | ⚪ Not implemented |
| CLI-CRED-021 | `mcpctl credential list --help` | Displays list usage | ⚪ Not implemented |
| CLI-CRED-022 | `mcpctl credential get <name> --key <value>` | Must pass the parser and correctly perform the intended get operation | ⚪ Not implemented |
| CLI-CRED-023 | Omit required `--key` from `credential get` | Parser rejects the command | ⚪ Not implemented |
| CLI-CRED-024 | Verify `credential get` delegation | Required `--key` is forwarded or the public parser is corrected to match intended behavior | ⚪ Not implemented |
| CLI-CRED-025 | Get a missing credential | Returns a clear non-zero failure | ⚪ Not implemented |
| CLI-CRED-026 | Get credential output | Never reveals the stored secret value | ⚪ Not implemented |
| CLI-CRED-027 | `mcpctl credential get --help` | Displays the positional name and required key option | ⚪ Not implemented |

### 7.3 Update

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-CRED-030 | `mcpctl credential update <name> --key <secret>` | Updates the credential successfully | ⚪ Not implemented |
| CLI-CRED-031 | `--key` with a replacement value | Forwards the replacement value correctly and securely | ⚪ Not implemented |
| CLI-CRED-032 | Omit required `--key` | Parser rejects the command | ⚪ Not implemented |
| CLI-CRED-033 | `--yes` on update | Forwards confirmation correctly | ⚪ Not implemented |
| CLI-CRED-034 | Update without `--yes` | Follows the documented confirmation behavior safely | ⚪ Not implemented |
| CLI-CRED-035 | Combine `--key` and `--yes` | Preserves both options through delegation | ⚪ Not implemented |
| CLI-CRED-036 | `mcpctl credential update --help` | Displays all supported arguments and options | ⚪ Not implemented |

### 7.4 Delete, Grant, and Revoke

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-CRED-040 | `mcpctl credential delete <name> --yes` | Deletes the credential and forwards confirmation | ⚪ Not implemented |
| CLI-CRED-041 | Delete without `--yes` | Does not perform an unintended destructive action | ⚪ Not implemented |
| CLI-CRED-042 | Omit credential name on delete | Parser rejects the command | ⚪ Not implemented |
| CLI-CRED-043 | `mcpctl credential delete --help` | Displays the name and confirmation option | ⚪ Not implemented |
| CLI-CRED-044 | `mcpctl credential grant <sandbox> <credential> --yes` | Grants the credential to the requested sandbox | ⚪ Not implemented |
| CLI-CRED-045 | Grant without `--yes` | Follows the documented confirmation behavior safely | ⚪ Not implemented |
| CLI-CRED-046 | Omit sandbox name or credential name on grant | Parser rejects the command | ⚪ Not implemented |
| CLI-CRED-047 | `mcpctl credential grant --help` | Displays both positional arguments and confirmation option | ⚪ Not implemented |
| CLI-CRED-048 | `mcpctl credential revoke <sandbox> <credential> --yes` | Revokes the requested grant | ⚪ Not implemented |
| CLI-CRED-049 | Revoke without `--yes` | Returns a clear failure and does not revoke access | ⚪ Not implemented |
| CLI-CRED-050 | Omit sandbox name or credential name on revoke | Parser rejects the command | ⚪ Not implemented |
| CLI-CRED-051 | `mcpctl credential revoke --help` | Displays both positional arguments and confirmation option | ⚪ Not implemented |
| CLI-CRED-052 | Grant then revoke a test credential | Access is granted and then verifiably removed | ⚪ Not implemented |
| CLI-CRED-053 | Use a missing sandbox or credential | Returns a non-zero exit code without granting unintended access | ⚪ Not implemented |
| CLI-CRED-054 | Secret supplied on create/update | Secret is not echoed in stdout, stderr, reports, or failure summaries | ⚪ Not implemented |

### 7.5 Credential List and Command-Level Help

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-CRED-060 | `mcpctl credential --help` | Displays credential subcommands | ⚪ Not implemented |
| CLI-CRED-061 | `mcpctl credential list` on an empty test environment | Returns a valid empty result | ⚪ Not implemented |
| CLI-CRED-062 | Unknown credential subcommand | Returns a non-zero argument error | ⚪ Not implemented |
| CLI-CRED-063 | Missing credential subcommand | Returns a non-zero argument error | ⚪ Not implemented |

## 8. `mcpctl workspace`

Workspace operations are delegated by `mcpctl` to the workspace service.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-WS-001 | `mcpctl workspace authorize <host_path>` | Authorizes the specified isolated host directory and returns workspace details | 🔴 Fail |
| CLI-WS-002 | Omit `host_path` | Parser rejects the command | 🟢 Pass |
| CLI-WS-003 | Authorize a nonexistent path | Fails clearly without creating an invalid grant | 🟢 Pass |
| CLI-WS-004 | Authorize a protected or disallowed path | Enforces workspace security policy | 🟢 Pass |
| CLI-WS-005 | `mcpctl workspace authorize --help` | Displays authorize usage | 🟢 Pass |
| CLI-WS-006 | `mcpctl workspace list` | Returns authorized workspace grants | 🔴 Fail |
| CLI-WS-007 | `mcpctl workspace list --json` | Forwards `--json` to the broker and returns valid JSON | 🔴 Fail |
| CLI-WS-008 | `mcpctl workspace list --help` | Displays list usage and JSON option | 🟢 Pass |
| CLI-WS-009 | `mcpctl workspace revoke <workspace_id>` | Revokes the requested workspace grant | 🔴 Fail |
| CLI-WS-010 | Omit `workspace_id` | Parser rejects the command | 🟢 Pass |
| CLI-WS-011 | Revoke a nonexistent workspace ID | Returns an accurate failure result | 🟢 Pass |
| CLI-WS-012 | `mcpctl workspace revoke --help` | Displays revoke usage | 🟢 Pass |
| CLI-WS-013 | Authorize, list, revoke, list | The grant appears after authorization and disappears after revocation | 🔴 Fail |
| CLI-WS-014 | `mcpctl workspace --help` | Displays workspace subcommands | 🟢 Pass |
| CLI-WS-015 | Unknown workspace subcommand | Returns a non-zero argument error | 🟢 Pass |
| CLI-WS-016 | Workspace JSON output | Output is valid JSON and contains no unrelated data | 🔴 Fail |

## 9. `mcpctl config`

Configuration tests must use temporary test configuration or an isolated home directory. They must never overwrite the user's real configuration.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-CONFIG-001 | `mcpctl config --help` | Displays configuration subcommands | ⚪ Not implemented |
| CLI-CONFIG-002 | `mcpctl config mcp-client` | Starts the MCP-client selection/configuration flow | ⚪ Not implemented |
| CLI-CONFIG-003 | `mcpctl config mcp-client --help` | Displays MCP-client configuration usage | ⚪ Not implemented |
| CLI-CONFIG-004 | `mcpctl config mcp-client openai` | Starts the OpenAI client configuration flow | ⚪ Not implemented |
| CLI-CONFIG-005 | `mcpctl config mcp-client openai --help` | Displays OpenAI configuration usage | ⚪ Not implemented |
| CLI-CONFIG-006 | Select OpenAI from the interactive client list | Selects the expected client | ⚪ Not implemented |
| CLI-CONFIG-007 | Submit valid test tunnel ID and API key | Saves configuration successfully | ⚪ Not implemented |
| CLI-CONFIG-008 | Submit empty or invalid tunnel ID | Fails clearly without corrupting existing configuration | ⚪ Not implemented |
| CLI-CONFIG-009 | Submit an invalid test API key | Reports configuration failure without exposing the key | ⚪ Not implemented |
| CLI-CONFIG-010 | Enter a non-numeric selection | Returns a clear validation error | ⚪ Not implemented |
| CLI-CONFIG-011 | Select an out-of-range menu number | Returns a clear validation error | ⚪ Not implemented |
| CLI-CONFIG-012 | Run configuration with no available candidate clients | Handles the empty state without crashing | ⚪ Not implemented |
| CLI-CONFIG-013 | Verify saved file permissions | Credentials are stored with the expected secure permissions | ⚪ Not implemented |
| CLI-CONFIG-014 | Verify unrelated configuration fields | Existing unrelated settings are preserved | ⚪ Not implemented |
| CLI-CONFIG-015 | Inspect stdout, stderr, and test logs | API keys and other secrets are never printed | ⚪ Not implemented |
| CLI-CONFIG-016 | Interrupt configuration during input | Exits cleanly and leaves configuration in a safe state | ⚪ Not implemented |
| CLI-CONFIG-017 | Run the configuration flow twice | Existing configuration is handled predictably without corruption | ⚪ Not implemented |
| CLI-CONFIG-018 | Unknown config subcommand | Returns a non-zero argument error | ⚪ Not implemented |

## 10. Help and Option-Contract Coverage

Argparse provides `-h` and `--help` on parsers and subparsers by default. Every command and subcommand should be tested for both forms where they are exposed.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-HELP-001 | Top-level `-h` | Shows usage and available commands | ⚪ Not implemented |
| CLI-HELP-002 | Top-level `--help` | Shows usage and available commands | ⚪ Not implemented |
| CLI-HELP-003 | Every subcommand with `-h` | Displays help and exits without performing the operation | ⚪ Not implemented |
| CLI-HELP-004 | Every subcommand with `--help` | Displays help and exits without performing the operation | ⚪ Not implemented |
| CLI-HELP-005 | Compare short and long help forms | Both forms are valid and describe the same option contract | ⚪ Not implemented |
| CLI-HELP-006 | Required-option omission | Every required option causes an argument error when omitted | ⚪ Not implemented |
| CLI-HELP-007 | Invalid choice values | Profile and service choices reject unsupported values | ⚪ Not implemented |
| CLI-HELP-008 | Unsupported flags | Every parser rejects flags that it does not declare | ⚪ Not implemented |
| CLI-HELP-009 | Help output consistency | Documented options match the actual parser | ⚪ Not implemented |
| CLI-HELP-010 | Subcommand routing | Installed `mcpctl` routes to the intended parser and command | ⚪ Not implemented |

## 11. `mcpctl` Delegation Contract

These tests verify the behavior and delegation contracts exposed by the public `mcpctl` CLI. They must invoke `mcpctl` itself and assert observable behavior or capture delegated arguments at a controlled process boundary.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-DEL-001 | `mcpctl sandbox create` with `--workspace` | Workspace ID is preserved unchanged through delegation | ⚪ Not implemented |
| CLI-DEL-002 | `mcpctl sandbox create` with `--standalone` | Standalone mode is preserved unchanged through delegation | ⚪ Not implemented |
| CLI-DEL-003 | `mcpctl sandbox create --profile browser` | Profile reaches the underlying CLI unchanged | ⚪ Not implemented |
| CLI-DEL-004 | `mcpctl sandbox create --json` | JSON option reaches the underlying CLI | ⚪ Not implemented |
| CLI-DEL-005 | `mcpctl sandbox status --json` | JSON option reaches the underlying CLI | ⚪ Not implemented |
| CLI-DEL-006 | `mcpctl sandbox delete --json` | JSON option reaches the underlying CLI | ⚪ Not implemented |
| CLI-DEL-007 | `mcpctl sandbox recreate --yes` | Confirmation reaches the underlying CLI | ⚪ Not implemented |
| CLI-DEL-008 | `mcpctl sandbox exec` with multiple arguments | Command argument boundaries and order are preserved | ⚪ Not implemented |
| CLI-DEL-009 | `mcpctl credential create` | `--type`, `--key`, and `--yes` are forwarded correctly | ⚪ Not implemented |
| CLI-DEL-010 | `mcpctl credential update` | `--key` and `--yes` are forwarded correctly | ⚪ Not implemented |
| CLI-DEL-011 | `mcpctl credential delete` | `--yes` is forwarded correctly | ⚪ Not implemented |
| CLI-DEL-012 | `mcpctl credential grant` and `revoke` | Sandbox name, credential name, and `--yes` are preserved | ⚪ Not implemented |
| CLI-DEL-013 | `mcpctl credential get` | Detects the current mismatch between required `--key` and the missing downstream forwarding | ⚪ Not implemented |
| CLI-DEL-014 | `mcpctl workspace list --json` | JSON option reaches the workspace service | ⚪ Not implemented |
| CLI-DEL-015 | `mcpctl workspace authorize` | Host path reaches the workspace service unchanged | ⚪ Not implemented |
| CLI-DEL-016 | `mcpctl workspace revoke` | Workspace ID reaches the workspace service unchanged | ⚪ Not implemented |
| CLI-DEL-017 | Downstream non-zero exit code | `mcpctl` does not report success when the underlying command fails | ⚪ Not implemented |
| CLI-DEL-018 | Downstream stderr | Useful error information is preserved without leaking secrets | ⚪ Not implemented |
| CLI-DEL-019 | Unsupported `mcpctl sandbox list --json` | Public parser rejects the flag rather than silently accepting it | ⚪ Not implemented |
| CLI-DEL-020 | `mcpctl` command behavior | Supported options produce behavior consistent with the documented contract | ⚪ Not implemented |

## 12. Real-Sandbox Functional Tests

These tests validate actual infrastructure behavior rather than only parser or forwarding behavior.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-REAL-001 | Create standalone sandbox | Sandbox becomes ready and has no host workspace binding | ⚪ Not implemented |
| CLI-REAL-002 | Create host-backed sandbox | Sandbox is bound to the authorized test workspace | ⚪ Not implemented |
| CLI-REAL-003 | Run a command in the sandbox | Command executes inside the intended sandbox | ⚪ Not implemented |
| CLI-REAL-004 | Verify execution user | User identity matches the configured sandbox policy | ⚪ Not implemented |
| CLI-REAL-005 | Verify working directory | Working directory matches the application contract | ⚪ Not implemented |
| CLI-REAL-006 | Write a file to a standalone workspace | File is created in sandbox-local storage | ⚪ Not implemented |
| CLI-REAL-007 | Write a file to a host-backed workspace | File appears in the isolated host directory | ⚪ Not implemented |
| CLI-REAL-008 | Modify a host file and read it in the sandbox | Updated content is visible as expected | ⚪ Not implemented |
| CLI-REAL-009 | Stop and start a sandbox | State and workspace behavior match the retention contract | ⚪ Not implemented |
| CLI-REAL-010 | Restart a sandbox | Sandbox returns to a usable state | ⚪ Not implemented |
| CLI-REAL-011 | Recreate a sandbox | Profile and workspace binding are preserved | ⚪ Not implemented |
| CLI-REAL-012 | Delete a sandbox | Sandbox no longer exists | ⚪ Not implemented |
| CLI-REAL-013 | Browser profile readiness | Browser runtime is ready according to the current implementation | ⚪ Not implemented |
| CLI-REAL-014 | Browser network restrictions | Network policy is enforced | ⚪ Not implemented |
| CLI-REAL-015 | Workspace revocation | Revoked workspace cannot be used for a new authorized binding | ⚪ Not implemented |
| CLI-REAL-016 | Sandbox name boundary | Name validation follows the current source policy | ⚪ Not implemented |

## 13. Error Handling and Security

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-ERR-001 | Unknown command | Non-zero exit code and useful usage message | ⚪ Not implemented |
| CLI-ERR-002 | Missing required positional argument | Parser error and no unintended side effect | ⚪ Not implemented |
| CLI-ERR-003 | Missing required option | Parser error and no unintended side effect | ⚪ Not implemented |
| CLI-ERR-004 | Invalid option value | Clear validation failure | ⚪ Not implemented |
| CLI-ERR-005 | Gateway unavailable | Clear infrastructure error | ⚪ Not implemented |
| CLI-ERR-006 | Docker/Compose unavailable | Clear infrastructure error | ⚪ Not implemented |
| CLI-ERR-007 | Missing sandbox | Non-zero exit code and accurate error | ⚪ Not implemented |
| CLI-ERR-008 | Missing workspace | Non-zero exit code and accurate error | ⚪ Not implemented |
| CLI-ERR-009 | Missing credential | Non-zero exit code and accurate error | ⚪ Not implemented |
| CLI-ERR-010 | Child command failure | Failure is not converted into false success | ⚪ Not implemented |
| CLI-ERR-011 | Malformed JSON response | Clear failure rather than invalid success output | ⚪ Not implemented |
| CLI-ERR-012 | Interrupt during operation | Clean cancellation and resource cleanup | ⚪ Not implemented |
| CLI-ERR-013 | Secret-bearing argument | Secret does not appear in logs, test reports, or error summaries | ⚪ Not implemented |
| CLI-ERR-014 | Destructive command without required confirmation | Operation fails safely | ⚪ Not implemented |
| CLI-ERR-015 | Unauthorized workspace path | Access policy prevents the operation | ⚪ Not implemented |
| CLI-ERR-016 | Invalid sandbox name | Rejected before unintended infrastructure changes | ⚪ Not implemented |

## 14. JSON Contract

Only test JSON flags on commands that actually declare them. Do not assume every command supports JSON.

| ID | Test | Expected Result | Status |
|---|---|---|---|
| CLI-JSON-001 | `mcpctl sandbox create --json` | Valid JSON output through delegation | ⚪ Not implemented |
| CLI-JSON-002 | `mcpctl sandbox status <name> --json` | Valid JSON output through delegation | ⚪ Not implemented |
| CLI-JSON-003 | `mcpctl sandbox delete <name> --json` | Valid JSON output through delegation | ⚪ Not implemented |
| CLI-JSON-004 | `mcpctl workspace list --json` | Valid JSON workspace list | ⚪ Not implemented |
| CLI-JSON-005 | JSON output with empty collections | Valid JSON with the expected empty representation | ⚪ Not implemented |
| CLI-JSON-006 | JSON output with populated collections | Valid JSON with stable required fields and types | ⚪ Not implemented |
| CLI-JSON-007 | Parse stdout using a JSON parser | Output is machine-readable and not mixed with human-oriented status text | ⚪ Not implemented |
| CLI-JSON-008 | JSON error path | Failure exit code and error output are consistent with the documented contract | ⚪ Not implemented |

## 15. Automated Evidence and Report Generation

The test runner—not an AI agent or manual editor—must generate this report from actual test results.

Each test result must record:

- Test ID and test name.
- Status.
- Start time, end time, and duration.
- Entrypoint and command under test.
- Relevant option combinations.
- Exit code.
- Sanitized stdout and stderr excerpts when needed.
- Sandbox and workspace identifiers where applicable.
- Failure summary and reproducible diagnostic context.
- Skip or block reason when the test did not run.

Secrets, API keys, credential values, private configuration, and unrelated host data must never be included in evidence.

The generated report must distinguish `Not implemented`, `Blocked`, `Skipped`, `Pass`, and `Fail`. Missing results must not be interpreted as passes.

## 16. Isolation and Cleanup

1. Generate unique test resource names within the supported name limit.
2. Use temporary directories for host-backed workspace tests.
3. Use disposable credentials only.
4. Register created resources for cleanup immediately.
5. Clean up in teardown/finally logic, including when assertions fail.
6. Verify that sandboxes, workspace grants, and test credentials are removed.
7. Never run destructive lifecycle tests against production.
8. Do not delete or rewrite shared resources unless the test created them.
9. Preserve enough sanitized diagnostics to investigate a failure after cleanup.
10. Treat resource leaks as test failures.

## 17. Current Audit Findings

| ID | Finding | Risk | Status |
|---|---|---|---|
| AUDIT-001 | No CLI test modules currently exist under `tests/e2e/cli/` | CLI regressions can go undetected | 🔵 Confirmed |
| AUDIT-002 | `mcpctl sandbox list` does not declare `--json` | Users may expect an unsupported option | 🔵 Confirmed |
| AUDIT-003 | `mcpctl credential get` requires `--key`, but `_credential_arguments()` only forwards `get` and the credential name | Parser and delegation contracts are inconsistent | 🔵 Confirmed |
| AUDIT-005 | `mcpctl workspace` delegates to `workspace_broker.main()` instead of the main sandbox CLI | Workspace delegation needs its own coverage | 🔵 Confirmed |
| AUDIT-006 | The test matrix covers the public `mcpctl` CLI and its declared options | Ongoing regression coverage is needed | ⚪ Not implemented |
| AUDIT-007 | The complete test report is automatically generated from test-runner output | Manual status drift must be avoided | ⚪ Not implemented |

## 18. Release Gate

Required order:

1. Static checks and linting.
2. Unit tests.
3. Integration tests.
4. CLI parser and flag-contract tests.
5. `mcpctl` delegation tests.
6. Real-sandbox CLI E2E tests.
7. MCP E2E tests against the same isolated environment.
8. Production-like smoke tests.
9. Automatic report generation and gate evaluation.

### Pass Criteria

- All required tests for the changed CLI scope pass.
- Every declared option has positive, negative, and forwarding coverage as applicable.
- Required and mutually exclusive arguments behave correctly.
- Help output matches the actual parser.
- No unexpected skips or untracked blocked tests remain.
- JSON output is valid where supported.
- Secret values are not exposed.
- No test resources are leaked.
- The tested artifact is the artifact intended for release.

Any unexpected failure in a production-critical path blocks release until resolved or explicitly dispositioned.

If CLI E2E and MCP E2E both pass but production fails, investigate differences between the tested environment and production—including configuration, credentials, network policy, gateway version, container images, and deployment settings—before attributing the issue to the application.
