# syntax=docker/dockerfile:1.7

FROM node:lts-bookworm-slim AS node

FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOCAL_TERMINAL_EXECUTOR_HOST=0.0.0.0 \
    LOCAL_TERMINAL_EXECUTOR_PORT=8765 \
    LOCAL_TERMINAL_EXECUTOR_TOKEN_FILE=/run/secrets/local_terminal_executor_token \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    LOG_LEVEL=INFO

COPY --from=node /usr/local /usr/local

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        jq \
        openssh-client \
        procps \
        ripgrep \
        wget \
    && rm -rf /var/lib/apt/lists/*

RUN npm install --global npm@12.1.0 playwright@1.63.0 \
    && npm cache clean --force

RUN chromium_path="$(find /ms-playwright -type f -path '*/chrome-linux64/chrome' -print -quit)" \
    && test -n "${chromium_path}" \
    && ln -sf "${chromium_path}" /usr/local/bin/chromium \
    && ln -sf "${chromium_path}" /usr/local/bin/chrome

RUN groupadd \
        --gid 10001 \
        appgroup \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --create-home \
        --shell /usr/sbin/nologin \
        appuser

COPY --chown=10001:10001 \
    host/terminal_executor.py \
    /app/host/terminal_executor.py

USER 10001:10001

EXPOSE 8765

CMD ["python", "/app/host/terminal_executor.py"]
