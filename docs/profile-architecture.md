# Profile architecture and safe cleanup

The profile manager adds isolated Compose projects while preserving the existing default
runtime. Each profile has a unique project name, a non-overlapping set of loopback host
ports, profile-scoped XDG configuration and state directories, and generated OpenShell
gateway configuration/metadata.

## Commands

- mcpctl profile create dev
- mcpctl profile list
- mcpctl profile show dev
- mcpctl profile validate dev
- mcpctl profile up dev
- mcpctl profile down dev
- mcpctl cleanup --plan
- mcpctl uninstall --dry-run
- mcpctl uninstall --purge --yes

Profile creation never overwrites an existing profile. Validation is non-destructive.
Profile down stops only that profile's Compose project and preserves data. Cleanup is a
read-only inventory. Uninstall defaults to a dry run; purge requires an explicit --yes
and removes generated profile configuration only.

## Data retention

Uninstall deliberately preserves profile state, workspace grants, host workspaces,
Docker volumes, the default/legacy runtime, and the repository clone. Review the
reported paths and handle retained state manually when appropriate. Container-to-
container gateway traffic uses the Compose service name openshell-gateway, which is
already present in the TLS server SAN template.
