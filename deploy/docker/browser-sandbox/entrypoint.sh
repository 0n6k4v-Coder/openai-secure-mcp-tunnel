#!/bin/sh

set -eu

CHROME="/opt/chrome/chrome"
USER_DATA_DIR="/home/chrome/profile"
DEBUG_URL="http://127.0.0.1:9222"
CHROME_LOG="/tmp/chrome.log"
OPENSSL_CA="/run/openshell-supervisor-ca/material/ca.crt"

cleanup() {
    if [ -n "${CHROME_DEVTOOLS_PID:-}" ]; then
        kill "${CHROME_DEVTOOLS_PID}" 2>/dev/null || true
    fi

    chrome-devtools stop >/dev/null 2>&1 || true

    if [ -n "${CHROME_PID:-}" ]; then
        kill "${CHROME_PID}" 2>/dev/null || true
        wait "${CHROME_PID}" 2>/dev/null || true
    fi
}

trap cleanup INT TERM EXIT

# OpenShell may set HOME to the mounted workspace. Chrome's NSS shared DB is
# resolved from HOME, so keep the browser trust database in its private home.
export HOME="/home/chrome"
NSS_DB_DIR="${HOME}/.local/share/pki/nssdb"

prepare_chrome_trust() {
    if [ ! -s "${OPENSSL_CA}" ]; then
        echo "OpenShell sandbox CA is unavailable." >&2
        exit 1
    fi

    mkdir -p "${NSS_DB_DIR}"

    if ! certutil -L -d "sql:${NSS_DB_DIR}" >/dev/null 2>&1; then
        certutil -N -d "sql:${NSS_DB_DIR}" --empty-password
    fi

    certutil -D \
        -d "sql:${NSS_DB_DIR}" \
        -n "OpenShell Sandbox CA" \
        >/dev/null 2>&1 || true

    certutil -A \
        -d "sql:${NSS_DB_DIR}" \
        -t "C,," \
        -n "OpenShell Sandbox CA" \
        -i "${OPENSSL_CA}"
}

prepare_chrome_trust

rm -rf "${USER_DATA_DIR}"
mkdir -p "${USER_DATA_DIR}"

"${CHROME}" \
    --headless=new \
    --no-sandbox \
    --no-zygote \
    --disable-setuid-sandbox \
    --disable-namespace-sandbox \
    --remote-debugging-address=127.0.0.1 \
    --remote-debugging-port=9222 \
    --user-data-dir="${USER_DATA_DIR}" \
    --no-first-run \
    --no-default-browser-check \
    --disable-background-networking \
    --disable-component-update \
    --disable-gpu \
    --disable-dev-shm-usage \
    --window-size=1280,720 \
    about:blank >"${CHROME_LOG}" 2>&1 &

CHROME_PID=$!

i=0

while [ "${i}" -lt 120 ]; do
    if ! kill -0 "${CHROME_PID}" 2>/dev/null; then
        echo "Chrome exited before exposing CDP." >&2
        cat "${CHROME_LOG}" >&2 || true
        wait "${CHROME_PID}" || true
        exit 1
    fi

    if curl \
        --fail \
        --silent \
        --show-error \
        "${DEBUG_URL}/json/version" \
        >/dev/null 2>&1
    then
        chrome-devtools start --browserUrl="${DEBUG_URL}" >/tmp/chrome-devtools.log 2>&1 &
        CHROME_DEVTOOLS_PID=$!

        if ! kill -0 "${CHROME_DEVTOOLS_PID}" 2>/dev/null; then
            echo "Chrome DevTools MCP daemon failed to start." >&2
            cat /tmp/chrome-devtools.log >&2 || true
            exit 1
        fi

        if wait "${CHROME_PID}"; then
            exit 0
        else
            chrome_exit=$?
            echo "Chrome exited after exposing CDP with status ${chrome_exit}." >&2
            echo "--- chrome.log ---" >&2
            cat "${CHROME_LOG}" >&2 || true
            exit "${chrome_exit}"
        fi
    fi

    i=$((i + 1))
    sleep 0.25
done

echo "Chrome failed to expose CDP at ${DEBUG_URL}." >&2
cat "${CHROME_LOG}" >&2 || true
exit 1
