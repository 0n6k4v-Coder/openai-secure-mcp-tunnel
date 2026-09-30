# syntax=docker/dockerfile:1.7

FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

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

RUN python -m pip install --no-cache-dir \
        playwright==1.63.0

RUN groupadd \
        --gid 10001 \
        appgroup \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --create-home \
        --shell /usr/sbin/nologin \
        appuser

RUN mkdir -p /workspace \
    && chown 10001:10001 /workspace

USER 10001:10001

CMD ["sleep", "infinity"]
