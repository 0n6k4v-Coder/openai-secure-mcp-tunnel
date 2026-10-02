#!/bin/sh
set -eu

BROWSER_BIND_HOST="${BROWSER_BIND_HOST:-host.openshell.internal}"
BROWSER_PORT="${BROWSER_PORT:-9222}"
BROWSER_USER_DATA_DIR="${BROWSER_USER_DATA_DIR:-/tmp/chrome-profile}"

BROWSER_BIND_IP="$(getent ahostsv4 "$BROWSER_BIND_HOST" | awk 'NR == 1 {print $1; exit}')"

if [ -z "$BROWSER_BIND_IP" ]; then
    echo "browser runtime could not resolve BROWSER_BIND_HOST=$BROWSER_BIND_HOST" >&2
    exit 1
fi

exec /opt/chrome/chrome-headless-shell \
    --remote-debugging-address="$BROWSER_BIND_IP" \
    --remote-debugging-port="$BROWSER_PORT" \
    --user-data-dir="$BROWSER_USER_DATA_DIR" \
    --no-first-run \
    --no-default-browser-check \
    --disable-background-networking \
    --disable-component-update \
    --disable-features=Translate,MediaRouter \
    --disable-sync
