# Application lifecycle and retained data

The application has one central Docker Compose runtime. Application lifecycle commands
operate on that shared runtime; they do not create isolated application-level profiles.

## Runtime and sandbox profiles

The Compose deployment remains the single source of truth for the application services:
`openshell-gateway`, `mcp-server`, and `tunnel-client`.

Sandbox profiles are a separate OpenShell feature and remain supported:

- `default` is used for normal development and command execution.
- `browser` provides the isolated Chrome runtime and Chrome DevTools MCP daemon.

Use `mcpctl sandbox create NAME --workspace WORKSPACE_ID --profile default` or
`mcpctl sandbox create NAME --workspace WORKSPACE_ID --profile browser` to select a
sandbox profile. These sandbox profiles are not application-level configuration profiles.

## Cleanup and uninstall

`mcpctl cleanup` (or `mcpctl cleanup --json`) inventories generated legacy
application-profile configuration without changing files.

`mcpctl uninstall` is a dry run by default. `mcpctl uninstall --yes` removes only
legacy generated configuration directories that contain a regular `profile.json`
marker. It does not delete legacy profile state, credentials, workspace grants, host
workspaces, Docker volumes, central application configuration, or the repository clone.

Review the inventory before explicitly confirming removal. Migration or deletion of
retained state is a separate, manual operation.
