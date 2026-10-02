# syntax=docker/dockerfile:1.7

FROM python:3.14-alpine

RUN addgroup -S relay \
    && adduser -S -G relay relay

WORKDIR /app

COPY relay.py /app/relay.py

RUN chown -R relay:relay /app \
    && chmod 0555 /app/relay.py

USER relay:relay

ENV CDP_UPSTREAM_HOST=198.18.0.2
ENV CDP_UPSTREAM_PORT=9222
ENV CDP_LISTEN_HOST=0.0.0.0
ENV CDP_LISTEN_PORT=9223
ENV CDP_PUBLIC_HOST=host.openshell.internal
ENV CDP_PUBLIC_PORT=9223

EXPOSE 9223

ENTRYPOINT ["python", "/app/relay.py"]