# Sandbox Package Management

## Scope

Package configuration is stored outside the sandbox runtime under the effective
MCP state root:

```text
${MCP_STATE_DIR}/sandboxes/<sandbox-name>/packages/<ecosystem-id>/
```

If `MCP_STATE_DIR` is unset, the default is:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/local-mcp-server/mcp
```

An explicitly configured `MCP_STATE_DIR` must be an absolute path. Package
manifests and lockfiles survive sandbox deletion and recreation unless package
purge is explicitly requested.

## Registered ecosystem

The initial registry enables **npm** only. npm operations require a sandbox
using the `default` profile because that profile has the existing npm registry
network policy. The `browser` profile is not eligible for package resolution
or installation. Python and other ecosystems are not enabled by this change;
each requires an adapter, registry entry, runtime checks, and an approved
network policy before it can be registered.

The npm adapter manages:

- `package.json` — requested dependencies.
- `package-lock.json` — resolved dependency graph.
- `.mcp-managed-packages/npm` inside the sandbox workspace — isolated install
  target, separate from the user's project manifest.

URL, Git, and local-path package specs are rejected. Lock resolution and install
commands use fixed argument arrays. npm lifecycle scripts are disabled with
`--ignore-scripts`. Network access remains subject to the sandbox's existing
OpenShell policy.

## Commands

Initialize npm configuration when creating a sandbox. This does not install
packages:

```bash
uv run mcpctl sandbox create my-sandbox --standalone --packages npm
```

List configured packages:

```bash
uv run mcpctl sandbox packages list my-sandbox
uv run mcpctl sandbox packages list my-sandbox --ecosystem npm
```

Add or remove a declaration; these commands do not install or uninstall the
live environment:

```bash
uv run mcpctl sandbox packages add my-sandbox express@^5 --ecosystem npm
uv run mcpctl sandbox packages remove my-sandbox express --ecosystem npm
```

Resolve and write a lockfile:

```bash
uv run mcpctl sandbox packages lock my-sandbox --ecosystem npm
```

Install the lockfile. This operation requires explicit confirmation; use
`--yes` for authorized automation:

```bash
uv run mcpctl sandbox packages install my-sandbox --ecosystem npm --yes
```

Inspect configuration, lock, and installation status:

```bash
uv run mcpctl sandbox packages show my-sandbox
uv run mcpctl sandbox status my-sandbox
uv run mcpctl sandbox list
uv run mcpctl runtime show
```

Reset declarations to the adapter's base manifest. The lockfile is invalidated;
installed packages are not claimed to have been removed:

```bash
uv run mcpctl sandbox packages reset my-sandbox --ecosystem npm --yes
```

Delete a sandbox while preserving package manifests and lockfiles:

```bash
uv run mcpctl sandbox delete my-sandbox --yes
```

Explicitly purge managed package configuration for registered ecosystems:

```bash
uv run mcpctl sandbox delete my-sandbox --yes --purge-packages
```

Purge does not recursively remove unregistered entries found under the package
directory. Such entries are preserved and reported.

## Status semantics

- `NONE`: no package configuration exists for that ecosystem.
- `PRESENT` / `configured`: a manifest exists; this does not mean packages
  are installed.
- `UP TO DATE`: the lockfile's root dependency declarations match the manifest.
- `OUT OF DATE`: the lockfile is missing or no longer matches the manifest.
- `INVALID`: a manifest or lockfile cannot be safely validated.
- `INSTALLED`: the adapter's runtime check verified the environment.
- `PARTIAL`: some packages are present but the environment check failed.
- `NOT INSTALLED`: no direct installed packages were verified.
- `UNKNOWN` / `REQUIRES VERIFICATION`: inspection could not verify the
  environment or the manifest/lock state is stale.

Sandbox lifecycle operations do not implicitly resolve or install packages.
Recreation preserves external package configuration, but the new runtime's
installed environment must be verified or reinstalled.

## Safety and recovery

- Package state paths must remain under the effective MCP state root.
- Managed state paths and sandbox install targets are checked for symlinks
  before mutation.
- Manifest writes use a temporary file and atomic replacement where supported.
- Failed resolution preserves the last valid host lockfile.
- Failed installation reports the observed environment status; it does not
  claim rollback.
- Package configuration changes are scoped to one sandbox and one registered
  ecosystem.
- Sandbox deletion requires `--yes`; package purge is a separate explicit flag.
- A relative `MCP_STATE_DIR` is rejected instead of being silently resolved.
