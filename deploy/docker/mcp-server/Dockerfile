# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.14.7-slim-trixie AS builder

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

COPY pyproject.toml uv.lock .python-version ./
COPY README.md ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-editable

COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --refresh-package local-mcp-server


FROM python:3.14.7-slim-trixie AS runtime

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO

ADD --checksum=sha256:1f5416ea08f32fdc621f20a2cc0324298e60aba8bbe996459d9e3b44195f23df \
    https://github.com/NVIDIA/OpenShell/releases/download/v0.1.2/openshell_0.1.2-1_amd64.deb \
    /tmp/openshell.deb

RUN apt-get update \
    && apt-get install -y --no-install-recommends /tmp/openshell.deb \
    && rm -f /tmp/openshell.deb \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd \
        --gid 10001 \
        appgroup \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --create-home \
        --shell /usr/sbin/nologin \
        appuser

COPY --from=builder --chown=10001:10001 \
    /app/.venv \
    /app/.venv

COPY --from=builder --chown=10001:10001 \
    /app/src \
    /app/src

USER 10001:10001

EXPOSE 8000

CMD ["python", "-m", "local_mcp_server.server"]