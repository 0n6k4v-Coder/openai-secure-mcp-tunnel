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
COPY host ./host

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable


FROM python:3.14.7-slim-trixie AS runtime

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WORKSPACE_DIR=/app/workspace \
    LOG_LEVEL=INFO \
    LOCAL_TERMINAL_EXECUTOR_HOST=0.0.0.0 \
    LOCAL_TERMINAL_EXECUTOR_PORT=8765 \
    LOCAL_TERMINAL_EXECUTOR_TOKEN_FILE=/run/secrets/local_terminal_executor_token

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

COPY --from=builder --chown=10001:10001 \
    /app/host \
    /app/host

USER 10001:10001

EXPOSE 8000 8765

CMD ["python", "-m", "local_mcp_server.server"]