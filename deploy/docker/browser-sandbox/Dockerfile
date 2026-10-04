# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim

ARG CHROME_VERSION=154.0.8037.92
ARG CHROME_DEVTOOLS_MCP_VERSION=1.10.1

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        dumb-init \
        fonts-liberation \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libc6 \
        libcairo2 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libglib2.0-0 \
        libgtk-3-0 \
        libnspr4 \
        libnss3-tools \
        libnss3 \
        libpango-1.0-0 \
        libu2f-udev \
        libvulkan1 \
        libx11-6 \
        libx11-xcb1 \
        libxcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        unzip \
    && rm -rf /var/lib/apt/lists/* \
    && curl --fail --silent --show-error --location \
        --output /tmp/chrome.zip \
        "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip" \
    && unzip -q /tmp/chrome.zip -d /opt \
    && mv /opt/chrome-linux64 /opt/chrome \
    && rm -f /tmp/chrome.zip \
    && groupadd --gid 10001 chrome \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --create-home \
        --shell /usr/sbin/nologin \
        chrome \
    && mkdir -p /home/chrome/profile \
    && chown -R 10001:10001 /home/chrome \
    && npm install --global \
        "chrome-devtools-mcp@${CHROME_DEVTOOLS_MCP_VERSION}" \
    && npm cache clean --force

COPY entrypoint.sh /usr/local/bin/browser-runtime

RUN chmod 0555 /usr/local/bin/browser-runtime \
    && mkdir -p \
        /workspace \
        /workspace/project \
    && chown -R 10001:10001 \
        /workspace \
        /workspace/project

ENV CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS=1 \
    CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1 \
    XDG_CACHE_HOME=/tmp/cache

WORKDIR /workspace

USER 10001:10001

CMD ["/usr/bin/dumb-init", "--", "/usr/local/bin/browser-runtime"]