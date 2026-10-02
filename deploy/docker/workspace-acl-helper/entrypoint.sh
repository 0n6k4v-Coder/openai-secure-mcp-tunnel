#!/bin/sh
set -eu

usage() {
    echo "usage: provision-sandbox-acl <sandbox-uid> <host-uid>" >&2
    echo "       remove-sandbox-acl <sandbox-uid> <host-uid>" >&2
    exit 2
}

if [ "$#" -ne 3 ]; then
    usage
fi

operation="$1"
sandbox_uid="$2"
host_uid="$3"

case "$operation" in
    provision-sandbox-acl|remove-sandbox-acl)
        ;;
    *)
        usage
        ;;
esac

case "$sandbox_uid" in
    ''|*[!0-9]*)
        echo "sandbox UID must be numeric" >&2
        exit 2
        ;;
esac

case "$host_uid" in
    ''|*[!0-9]*)
        echo "host UID must be numeric" >&2
        exit 2
        ;;
esac

if [ "$sandbox_uid" = "0" ]; then
    echo "sandbox UID must be non-root" >&2
    exit 2
fi

if [ "$host_uid" = "0" ]; then
    echo "host UID must be non-root" >&2
    exit 2
fi

root=/workspace

if [ ! -d "$root" ]; then
    echo "workspace mount is missing" >&2
    exit 1
fi

if [ "$operation" = "provision-sandbox-acl" ]; then
    setfacl -m "u:$sandbox_uid:rwx" "$root"

    if [ "$host_uid" != "$sandbox_uid" ]; then
        setfacl -m "u:$host_uid:rwx" "$root"
    fi

    setfacl -m "d:u:$sandbox_uid:rwx" "$root"

    if [ "$host_uid" != "$sandbox_uid" ]; then
        setfacl -m "d:u:$host_uid:rwx" "$root"
    fi

    find -P "$root" -xdev -mindepth 1 \
        \( \
            -path "$root/.env" \
            -o -path "$root/.secrets" \
            -o -path "$root/.secrets/"'*' \
            -o -path "$root/.state" \
            -o -path "$root/.state/"'*' \
            -o -path "$root/deploy/openshell/jwt" \
            -o -path "$root/deploy/openshell/jwt/"'*' \
            -o -path "$root/.git" \
            -o -path "$root/.git/"'*' \
            -o -path "$root/.venv" \
            -o -path "$root/.venv/"'*' \
            -o -path "$root/.ruff_cache" \
            -o -path "$root/.ruff_cache/"'*' \
            -o -path "$root/.pytest_cache" \
            -o -path "$root/.pytest_cache/"'*' \
            -o -path "$root/.mypy_cache" \
            -o -path "$root/.mypy_cache/"'*' \
            -o -path "$root/.pyright" \
            -o -path "$root/.pyright/"'*' \
            -o -path "$root/deploy/docker/workspace-acl-helper" \
            -o -path "$root/deploy/docker/workspace-acl-helper/"'*' \
            -o -name '__pycache__' \
        \) -prune -o \
        -type d \
        -exec setfacl -m "u:$sandbox_uid:rwx" {} + \
        -exec setfacl -m "d:u:$sandbox_uid:rwx" {} +

    if [ "$host_uid" != "$sandbox_uid" ]; then
        find -P "$root" -xdev -mindepth 1 \
            \( \
                -path "$root/.env" \
                -o -path "$root/.secrets" \
                -o -path "$root/.secrets/"'*' \
                -o -path "$root/.state" \
                -o -path "$root/.state/"'*' \
                -o -path "$root/deploy/openshell/jwt" \
                -o -path "$root/deploy/openshell/jwt/"'*' \
                -o -path "$root/.git" \
                -o -path "$root/.git/"'*' \
                -o -path "$root/.venv" \
                -o -path "$root/.venv/"'*' \
                -o -path "$root/.ruff_cache" \
                -o -path "$root/.ruff_cache/"'*' \
                -o -path "$root/.pytest_cache" \
                -o -path "$root/.pytest_cache/"'*' \
                -o -path "$root/.mypy_cache" \
                -o -path "$root/.mypy_cache/"'*' \
                -o -path "$root/.pyright" \
                -o -path "$root/.pyright/"'*' \
                -o -path "$root/deploy/docker/workspace-acl-helper" \
                -o -path "$root/deploy/docker/workspace-acl-helper/"'*' \
                -o -name '__pycache__' \
            \) -prune -o \
            -type d \
            -exec setfacl -m "u:$host_uid:rwx" {} + \
            -exec setfacl -m "d:u:$host_uid:rwx" {} +
    fi

    find -P "$root" -xdev -mindepth 1 \
        \( \
            -path "$root/.env" \
            -o -path "$root/.secrets" \
            -o -path "$root/.secrets/"'*' \
            -o -path "$root/.state" \
            -o -path "$root/.state/"'*' \
            -o -path "$root/deploy/openshell/jwt" \
            -o -path "$root/deploy/openshell/jwt/"'*' \
            -o -path "$root/.git" \
            -o -path "$root/.git/"'*' \
            -o -path "$root/.venv" \
            -o -path "$root/.venv/"'*' \
            -o -path "$root/.ruff_cache" \
            -o -path "$root/.ruff_cache/"'*' \
            -o -path "$root/.pytest_cache" \
            -o -path "$root/.pytest_cache/"'*' \
            -o -path "$root/.mypy_cache" \
            -o -path "$root/.mypy_cache/"'*' \
            -o -path "$root/.pyright" \
            -o -path "$root/.pyright/"'*' \
            -o -path "$root/deploy/docker/workspace-acl-helper" \
            -o -path "$root/deploy/docker/workspace-acl-helper/"'*' \
            -o -name '__pycache__' \
        \) -prune -o \
        -type f \
        -exec setfacl -m "u:$sandbox_uid:rwX" {} +

    if [ "$host_uid" != "$sandbox_uid" ]; then
        find -P "$root" -xdev -mindepth 1 \
            \( \
                -path "$root/.env" \
                -o -path "$root/.secrets" \
                -o -path "$root/.secrets/"'*' \
                -o -path "$root/.state" \
                -o -path "$root/.state/"'*' \
                -o -path "$root/deploy/openshell/jwt" \
                -o -path "$root/deploy/openshell/jwt/"'*' \
                -o -path "$root/.git" \
                -o -path "$root/.git/"'*' \
                -o -path "$root/.venv" \
                -o -path "$root/.venv/"'*' \
                -o -path "$root/.ruff_cache" \
                -o -path "$root/.ruff_cache/"'*' \
                -o -path "$root/.pytest_cache" \
                -o -path "$root/.pytest_cache/"'*' \
                -o -path "$root/.mypy_cache" \
                -o -path "$root/.mypy_cache/"'*' \
                -o -path "$root/.pyright" \
                -o -path "$root/.pyright/"'*' \
                -o -path "$root/deploy/docker/workspace-acl-helper" \
                -o -path "$root/deploy/docker/workspace-acl-helper/"'*' \
                -o -name '__pycache__' \
            \) -prune -o \
            -type f \
            -exec setfacl -m "u:$host_uid:rwX" {} +
    fi

    exit 0
fi

setfacl -x "u:$sandbox_uid" "$root"

if [ "$host_uid" != "$sandbox_uid" ]; then
    setfacl -x "u:$host_uid" "$root"
fi

setfacl -x "d:u:$sandbox_uid" "$root"

if [ "$host_uid" != "$sandbox_uid" ]; then
    setfacl -x "d:u:$host_uid" "$root"
fi

find -P "$root" -xdev -mindepth 1 \
    \( \
        -path "$root/.env" \
        -o -path "$root/.secrets" \
        -o -path "$root/.secrets/"'*' \
        -o -path "$root/.state" \
        -o -path "$root/.state/"'*' \
        -o -path "$root/deploy/openshell/jwt" \
        -o -path "$root/deploy/openshell/jwt/"'*' \
        -o -path "$root/.git" \
        -o -path "$root/.git/"'*' \
        -o -path "$root/.venv" \
        -o -path "$root/.venv/"'*' \
        -o -path "$root/.ruff_cache" \
        -o -path "$root/.ruff_cache/"'*' \
        -o -path "$root/.pytest_cache" \
        -o -path "$root/.pytest_cache/"'*' \
        -o -path "$root/.mypy_cache" \
        -o -path "$root/.mypy_cache/"'*' \
        -o -path "$root/.pyright" \
        -o -path "$root/.pyright/"'*' \
        -o -path "$root/deploy/docker/workspace-acl-helper" \
        -o -path "$root/deploy/docker/workspace-acl-helper/"'*' \
        -o -name '__pycache__' \
    \) -prune -o \
    -exec setfacl -x "u:$sandbox_uid" {} + \
    -exec setfacl -x "d:u:$sandbox_uid" {} +

if [ "$host_uid" != "$sandbox_uid" ]; then
    find -P "$root" -xdev -mindepth 1 \
        \( \
            -path "$root/.env" \
            -o -path "$root/.secrets" \
            -o -path "$root/.secrets/"'*' \
            -o -path "$root/.state" \
            -o -path "$root/.state/"'*' \
            -o -path "$root/deploy/openshell/jwt" \
            -o -path "$root/deploy/openshell/jwt/"'*' \
            -o -path "$root/.git" \
            -o -path "$root/.git/"'*' \
            -o -path "$root/.venv" \
            -o -path "$root/.venv/"'*' \
            -o -path "$root/.ruff_cache" \
            -o -path "$root/.ruff_cache/"'*' \
            -o -path "$root/.pytest_cache" \
            -o -path "$root/.pytest_cache/"'*' \
            -o -path "$root/.mypy_cache" \
            -o -path "$root/.mypy_cache/"'*' \
            -o -path "$root/.pyright" \
            -o -path "$root/.pyright/"'*' \
            -o -path "$root/deploy/docker/workspace-acl-helper" \
            -o -path "$root/deploy/docker/workspace-acl-helper/"'*' \
            -o -name '__pycache__' \
        \) -prune -o \
        -exec setfacl -x "u:$host_uid" {} + \
        -exec setfacl -x "d:u:$host_uid" {} +
fi