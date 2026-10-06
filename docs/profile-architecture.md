# Application lifecycle and retained data

## Application runtimes

The built-in `default` runtime is the production runtime. It preserves the
established Compose project name (`openai-secure-mcp-tunnel`), ports, and legacy
XDG configuration/state paths. Do not create a separate runtime named
`production`.

Named runtimes such as `development` are optional isolated environments. Select
one per terminal with `export MCP_RUNTIME=development`; omit `MCP_RUNTIME` or
set it to `default` to operate the production runtime. Each named runtime has its
own Compose project, ports, configuration/state roots, and OpenShell workspace
name. This application-level isolation is separate from sandbox profiles.

If a previous version already registered a named `production` runtime, stop it
before removing its registry entry:

```bash
MCP_RUNTIME=production mcpctl stop
mcpctl runtime delete production --yes
```

This removes only the registry entry, not the old runtime's files, credentials,
or Docker resources. Review and clean up those resources separately; do not run
the legacy production stack and the built-in default stack at the same time.

## Sandbox profiles

Sandbox profiles are a separate OpenShell feature and remain supported:

- `default` is used for normal development and command execution.
- `browser` provides the isolated Chrome runtime and Chrome DevTools MCP daemon.

Use `mcpctl sandbox create NAME --workspace WORKSPACE_ID --profile default` or
`mcpctl sandbox create NAME --workspace WORKSPACE_ID --profile browser` to select
a sandbox profile.

## Cleanup and uninstall

`mcpctl cleanup` (or `mcpctl cleanup --json`) inventories generated legacy
application-profile configuration without changing files.

`mcpctl uninstall` is a dry run by default. `mcpctl uninstall --yes` removes only
legacy generated configuration directories that contain a regular `profile.json`
marker. It does not delete legacy profile state, credentials, workspace grants, host
workspaces, Docker volumes, central application configuration, or the repository clone.

Review the inventory before explicitly confirming removal. Migration or deletion of
retained state is a separate, manual operation.
