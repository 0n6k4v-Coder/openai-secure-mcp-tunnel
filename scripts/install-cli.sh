#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
PYTHON_BIN="${VENV_DIR}/bin/python"
CLI_BIN="${VENV_DIR}/bin/local-mcp-server"
MCPCTL_BIN="${VENV_DIR}/bin/mcpctl"
ACTIVATE_FILE="${VENV_DIR}/bin/activate"

log() { printf '[install-cli] %s\n' "$*"; }
fail() { printf '[install-cli] ERROR: %s\n' "$*" >&2; exit 1; }

cd "${PROJECT_ROOT}"

if [[ ! -f "pyproject.toml" ]]; then fail "pyproject.toml was not found in ${PROJECT_ROOT}"; fi
if ! command -v python3.14 >/dev/null 2>&1; then fail "Python 3.14 is required but python3.14 was not found on PATH."; fi

PYTHON_VERSION="$(python3.14 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
if [[ "${PYTHON_VERSION}" != 3.14.* ]]; then fail "Python 3.14 is required, but python3.14 reported ${PYTHON_VERSION}."; fi
log "Using Python ${PYTHON_VERSION}"

if [[ -x "${PYTHON_BIN}" ]]; then
    VENV_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
    if [[ "${VENV_VERSION}" != 3.14.* ]]; then
        log "Existing .venv uses Python ${VENV_VERSION}; recreating it."
        rm -rf "${VENV_DIR}"
    fi
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
    log "Creating virtual environment at ${VENV_DIR}"
    python3.14 -m venv "${VENV_DIR}"
fi

VENV_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
if [[ "${VENV_VERSION}" != 3.14.* ]]; then fail "The virtual environment is using Python ${VENV_VERSION}, not Python 3.14."; fi

# A virtual environment can exist without pip (for example, if it was created
# with --without-pip or its pip installation was removed). Repair it before
# trying to upgrade or install anything.
if ! "${PYTHON_BIN}" -m pip --version >/dev/null 2>&1; then
    log "pip is missing from .venv; bootstrapping it with ensurepip."
    if ! "${PYTHON_BIN}" -m ensurepip --upgrade; then
        fail "Could not bootstrap pip in ${VENV_DIR}. Ensure this Python 3.14 installation includes ensurepip, or recreate only the virtual environment with 'rm -rf .venv && python3.14 -m venv .venv', then rerun this installer. This removes .venv only; it does not remove profile data."
    fi
fi

if ! "${PYTHON_BIN}" -m pip --version; then
    fail "pip is still unavailable in ${VENV_DIR} after ensurepip. Repair or recreate the virtual environment, then rerun this installer."
fi

log "Upgrading pip"
"${PYTHON_BIN}" -m pip install --upgrade pip
log "Installing local-mcp-server"
"${PYTHON_BIN}" -m pip install -e "${PROJECT_ROOT}"

[[ -x "${CLI_BIN}" ]] || fail "Installation completed but ${CLI_BIN} was not created."
[[ -x "${MCPCTL_BIN}" ]] || fail "Installation completed but ${MCPCTL_BIN} was not created."
[[ -x "${VENV_DIR}/bin/register-python-argcomplete" ]] || fail "argcomplete was not installed; register-python-argcomplete is missing."

COMPLETION_MARKER="# local-mcp-server argcomplete completion"
if ! grep -Fq "${COMPLETION_MARKER}" "${ACTIVATE_FILE}"; then
    cat >>"${ACTIVATE_FILE}" <<'EOF'

# local-mcp-server argcomplete completion
if [[ -n "${BASH_VERSION:-}" ]]; then
    if command -v register-python-argcomplete >/dev/null 2>&1; then
        eval "$(register-python-argcomplete local-mcp-server)"
        eval "$(register-python-argcomplete mcpctl)"
    fi
fi
EOF
elif ! grep -Fq 'register-python-argcomplete mcpctl' "${ACTIVATE_FILE}"; then
    sed -i '/eval "$(register-python-argcomplete local-mcp-server)"/a\        eval "$(register-python-argcomplete mcpctl)"' "${ACTIVATE_FILE}"
fi

log "Verifying CLI completion hook"
"${VENV_DIR}/bin/register-python-argcomplete" local-mcp-server >/dev/null
"${VENV_DIR}/bin/register-python-argcomplete" mcpctl >/dev/null
log "Verifying local-mcp-server"
"${CLI_BIN}" --help >/dev/null
log "Verifying mcpctl"
"${MCPCTL_BIN}" --help >/dev/null
log "Verifying sandbox command"
"${MCPCTL_BIN}" sandbox --help >/dev/null
log "Verifying credential command"
"${MCPCTL_BIN}" credential --help >/dev/null
log "Verifying workspace command"
"${MCPCTL_BIN}" workspace --help >/dev/null
log "Verifying config command"
"${MCPCTL_BIN}" config --help >/dev/null

log "CLI installation successful."
printf '\n'
printf 'CLI: %s\n' "${MCPCTL_BIN}"
printf 'Python: %s\n' "${PYTHON_BIN}"
printf 'Run: %s --help\n' "${MCPCTL_BIN}"
