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

## Registered ecosystems

The registry enables **npm** and **Python (`uv`)**. Both currently require the
`default` profile because that profile carries their package-index network
policies. The `browser` profile is not eligible for package resolution or
installation. Python is isolated in a managed virtual environment; it does not
install into the sandbox's system Python.

The npm adapter manages:

- `package.json` — requested dependencies.
- `package-lock.json` — resolved dependency graph.
- `.mcp-managed-packages/npm` inside the sandbox workspace — isolated install
target, separate from the user's project manifest.

The Python adapter manages:

- `requirements.json` — requested Python dependencies and version specifiers.
- `requirements.lock` — resolved, hash-pinned wheel requirements. Its first
  comment records a digest of the manifest to detect stale locks.
- `.mcp-managed-packages/python/.venv` — the managed virtual environment.

Both adapters reject URL, VCS, and local-path package references. Python extras
and environment markers are also rejected by the current adapter. Resolution
uses fixed argument arrays. npm lifecycle scripts are disabled with
`--ignore-scripts`; Python resolution/install uses `uv`, `--only-binary :all:`,
and hash validation during sync. These controls reduce execution and supply-chain
risk but do not establish that a third-party package is trustworthy.

The default profile permits the npm registry and the PyPI package index hosts
(`pypi.org` and `files.pythonhosted.org`) over HTTPS. As a consequence, all
sandboxes on the default profile receive these two package-index policies; this
is not an ecosystem-specific per-sandbox network grant. Browser sandboxes do not
receive either package-index policy.

## Configuration lifecycle

Package configuration is persistent host-side application state, separate from
the sandbox runtime. Creating a sandbox with `--packages <ecosystem>` initializes
its base manifest but does not resolve or install dependencies.

For an existing sandbox, the first `packages add` initializes a
missing ecosystem manifest through the same initializer used during sandbox
creation, then adds the requested dependency. Existing valid manifests are
preserved. A symlinked manifest, invalid manifest, unsafe state path, or orphan
lockfile causes the operation to fail rather than overwrite existing state.

Initialization and `packages add` only change configuration. They do not resolve
dependencies, install packages, or claim that the runtime is verified. Run the
explicit lock and install commands after adding dependencies.

## Commands

Initialize npm or Python package configuration when creating a sandbox. This
does not install packages:

```bash
uv run mcpctl sandbox create my-npm-sandbox --standalone --packages npm
uv run mcpctl sandbox create my-python-sandbox --standalone --packages python
```

List configured packages:

```bash
uv run mcpctl sandbox packages list my-npm-sandbox
uv run mcpctl sandbox packages list my-npm-sandbox --ecosystem npm
uv run mcpctl sandbox packages list my-python-sandbox --ecosystem python
```

Add or remove a declaration; these commands do not install or uninstall the
live environment:

```bash
uv run mcpctl sandbox packages add my-npm-sandbox express@^5 --ecosystem npm
uv run mcpctl sandbox packages remove my-npm-sandbox express --ecosystem npm
uv run mcpctl sandbox packages add my-python-sandbox 'requests>=2.31,<3' --ecosystem python
uv run mcpctl sandbox packages remove my-python-sandbox requests --ecosystem python
```

Resolve and write lockfiles:

```bash
uv run mcpctl sandbox packages lock my-npm-sandbox --ecosystem npm
uv run mcpctl sandbox packages lock my-python-sandbox --ecosystem python
```

Install locked dependencies. This operation requires explicit confirmation;
use `--yes` only in an authorized automation environment:

```bash
uv run mcpctl sandbox packages install my-npm-sandbox --ecosystem npm --yes
uv run mcpctl sandbox packages install my-python-sandbox --ecosystem python --yes
```

Inspect configuration, lock, and installation status:

```bash
uv run mcpctl sandbox packages show my-npm-sandbox
uv run mcpctl sandbox packages show my-python-sandbox
uv run mcpctl sandbox status my-python-sandbox
uv run mcpctl runtime show
```

Reset declarations to the adapter's base manifest. The lockfile is invalidated;
installed packages are not claimed to have been removed:

```bash
uv run mcpctl sandbox packages reset my-npm-sandbox --ecosystem npm --yes
uv run mcpctl sandbox packages reset my-python-sandbox --ecosystem python --yes
```

Delete a sandbox while preserving package manifests and lockfiles:

```bash
uv run mcpctl sandbox delete my-python-sandbox --yes
```

Explicitly purge managed package configuration for registered ecosystems:

```bash
uv run mcpctl sandbox delete my-python-sandbox --yes --purge-packages
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
