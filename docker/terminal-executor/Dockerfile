# syntax=docker/dockerfile:1.7

FROM python:3.14.7-slim-trixie

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOCAL_TERMINAL_EXECUTOR_HOST=0.0.0.0 \
    LOCAL_TERMINAL_EXECUTOR_PORT=8765 \
    LOCAL_TERMINAL_EXECUTOR_TOKEN_FILE=/run/secrets/local_terminal_executor_token \
    LOG_LEVEL=INFO

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
