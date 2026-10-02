# syntax=docker/dockerfile:1.7

FROM debian:bookworm-slim

ARG CHROME_VERSION=154.0.8037.92

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl dumb-init fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 libc6 libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 libu2f-udev libvulkan1 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 unzip \
    && rm -rf /var/lib/apt/lists/* \
    && curl --fail --silent --show-error --location --output /tmp/chrome-headless-shell.zip \
        "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-headless-shell-linux64.zip" \
    && unzip -q /tmp/chrome-headless-shell.zip -d /opt \
    && mv /opt/chrome-headless-shell-linux64 /opt/chrome \
    && rm -f /tmp/chrome-headless-shell.zip \
    && curl --fail --silent --show-error --location --output /tmp/chrome.zip \
        "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip" \
    && unzip -p /tmp/chrome.zip chrome-linux64/chrome_sandbox > /opt/chrome/chrome_sandbox \
    && rm -f /tmp/chrome.zip \
    && groupadd --gid 1000 chrome \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin chrome \
    && chown root:root /opt/chrome/chrome_sandbox \
    && chmod 4755 /opt/chrome/chrome_sandbox \
    && ln -s chrome_sandbox /opt/chrome/chrome-sandbox \
    && mkdir -p /home/chrome/profile \
    && chown -R 1000:1000 /home/chrome

COPY entrypoint.sh /usr/local/bin/browser-runtime
RUN chmod 0555 /usr/local/bin/browser-runtime

USER 1000:1000

EXPOSE 9222

ENTRYPOINT ["/usr/bin/dumb-init", "--", "/usr/local/bin/browser-runtime"]
