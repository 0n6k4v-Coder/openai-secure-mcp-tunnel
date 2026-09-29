# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.14.7-slim-trixie AS builder

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_NO_MANAGED_PYTHON=1

COPY pyproject.toml uv.lock .python-version ./
COPY README.md ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-editable

COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable


FROM python:3.14.7-slim-trixie AS runtime

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALLOWED_DATA_DIR=/app/allowed_data \
    LOG_LEVEL=INFO

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

USER 10001:10001

EXPOSE 8000

ENTRYPOINT ["python", "-m", "local_mcp_server.server"]
