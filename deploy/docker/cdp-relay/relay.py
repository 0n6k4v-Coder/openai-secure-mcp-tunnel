from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass


LISTEN_HOST = os.environ.get(
    "CDP_LISTEN_HOST",
    "0.0.0.0",
)
LISTEN_PORT = int(
    os.environ.get(
        "CDP_LISTEN_PORT",
        "9223",
    )
)

UPSTREAM_HOST = os.environ.get(
    "CDP_UPSTREAM_HOST",
    "198.18.0.2",
)
UPSTREAM_PORT = int(
    os.environ.get(
        "CDP_UPSTREAM_PORT",
        "9222",
    )
)

PUBLIC_HOST = os.environ.get(
    "CDP_PUBLIC_HOST",
    "host.openshell.internal",
)
PUBLIC_PORT = int(
    os.environ.get(
        "CDP_PUBLIC_PORT",
        "9223",
    )
)

MAX_HEADER_BYTES = 64 * 1024
BUFFER_SIZE = 64 * 1024


@dataclass(frozen=True)
class RelayConfig:
    upstream_authority: str
    public_authority: str


CONFIG = RelayConfig(
    upstream_authority=f"{UPSTREAM_HOST}:{UPSTREAM_PORT}",
    public_authority=f"{PUBLIC_HOST}:{PUBLIC_PORT}",
)


async def read_headers(
    reader: asyncio.StreamReader,
) -> tuple[bytes, bytes]:
    data = await reader.readuntil(b"\r\n\r\n")

    if len(data) > MAX_HEADER_BYTES:
        raise ValueError("HTTP header block exceeds maximum size")

    header_end = data.index(b"\r\n\r\n")

    return (
        data[:header_end],
        data[header_end + 4 :],
    )


def rewrite_request_headers(header_block: bytes) -> bytes:
    lines = header_block.split(b"\r\n")

    if not lines:
        raise ValueError("empty HTTP request")

    output = [lines[0]]
    host_seen = False

    for line in lines[1:]:
        if not line:
            continue

        name, separator, _value = line.partition(b":")

        if separator and name.lower() == b"host":
            output.append(
                b"Host: " + CONFIG.upstream_authority.encode("ascii")
            )
            host_seen = True
        else:
            output.append(line)

    if not host_seen:
        output.append(
            b"Host: " + CONFIG.upstream_authority.encode("ascii")
        )

    return b"\r\n".join(output) + b"\r\n\r\n"


def rewrite_cdp_body(body: bytes) -> bytes:
    replacements = (
        (
            f"ws://{CONFIG.upstream_authority}".encode("ascii"),
            f"ws://{CONFIG.public_authority}".encode("ascii"),
        ),
        (
            f"http://{CONFIG.upstream_authority}".encode("ascii"),
            f"http://{CONFIG.public_authority}".encode("ascii"),
        ),
        (
            f"ws://{UPSTREAM_HOST}:{UPSTREAM_PORT}".encode("ascii"),
            f"ws://{PUBLIC_HOST}:{PUBLIC_PORT}".encode("ascii"),
        ),
    )

    for old, new in replacements:
        body = body.replace(old, new)

    return body


def response_content_length(
    header_block: bytes,
) -> int | None:
    for line in header_block.split(b"\r\n")[1:]:
        name, separator, value = line.partition(b":")

        if not separator:
            continue

        if name.lower() == b"content-length":
            return int(value.strip())

    return None


def is_chunked_response(
    header_block: bytes,
) -> bool:
    for line in header_block.split(b"\r\n")[1:]:
        name, separator, value = line.partition(b":")

        if not separator:
            continue

        if (
            name.lower() == b"transfer-encoding"
            and value.strip().lower() == b"chunked"
        ):
            return True

    return False


def rewrite_response_headers(
    header_block: bytes,
    body: bytes,
) -> bytes:
    lines = header_block.split(b"\r\n")

    output = [lines[0]]
    content_length_seen = False

    for line in lines[1:]:
        if not line:
            continue

        name, separator, _value = line.partition(b":")

        if (
            separator
            and name.lower() == b"content-length"
        ):
            output.append(
                f"Content-Length: {len(body)}".encode("ascii")
            )
            content_length_seen = True
            continue

        if (
            separator
            and name.lower() == b"transfer-encoding"
        ):
            continue

        output.append(line)

    if not content_length_seen:
        output.append(
            f"Content-Length: {len(body)}".encode("ascii")
        )

    return b"\r\n".join(output) + b"\r\n\r\n"


async def relay_streams(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    upstream_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
) -> None:
    async def forward(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while True:
                data = await reader.read(BUFFER_SIZE)

                if not data:
                    break

                writer.write(data)
                await writer.drain()

        except (
            ConnectionError,
            asyncio.IncompleteReadError,
        ):
            pass

    await asyncio.gather(
        forward(
            client_reader,
            upstream_writer,
        ),
        forward(
            upstream_reader,
            client_writer,
        ),
    )

    for writer in (
        client_writer,
        upstream_writer,
    ):
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def relay_http_response(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    upstream_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
    request_line: bytes,
    response_headers: bytes,
    response_remainder: bytes,
) -> None:
    content_length = response_content_length(
        response_headers
    )

    chunked = is_chunked_response(
        response_headers
    )

    if (
        request_line.startswith(b"GET /json")
        and content_length is not None
        and not chunked
    ):
        body = response_remainder

        while len(body) < content_length:
            chunk = await upstream_reader.read(
                content_length - len(body)
            )

            if not chunk:
                break

            body += chunk

        body = rewrite_cdp_body(body)

        client_writer.write(
            rewrite_response_headers(
                response_headers,
                body,
            )
        )
        client_writer.write(body)

        await client_writer.drain()

        await relay_streams(
            client_reader,
            client_writer,
            upstream_reader,
            upstream_writer,
        )
        return

    client_writer.write(response_headers)
    client_writer.write(response_remainder)
    await client_writer.drain()

    await relay_streams(
        client_reader,
        client_writer,
        upstream_reader,
        upstream_writer,
    )


async def handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    upstream_writer: asyncio.StreamWriter | None = None

    try:
        request_headers, request_remainder = await read_headers(
            client_reader
        )

        request_line = request_headers.split(
            b"\r\n",
            1,
        )[0]

        upstream_reader, upstream_writer = await asyncio.open_connection(
            UPSTREAM_HOST,
            UPSTREAM_PORT,
        )

        upstream_writer.write(
            rewrite_request_headers(
                request_headers
            )
        )

        if request_remainder:
            upstream_writer.write(
                request_remainder
            )

        await upstream_writer.drain()

        if b"upgrade: websocket" in request_headers.lower():
            await relay_streams(
                client_reader,
                client_writer,
                upstream_reader,
                upstream_writer,
            )
            return

        response_headers, response_remainder = await read_headers(
            upstream_reader
        )

        await relay_http_response(
            client_reader,
            client_writer,
            upstream_reader,
            upstream_writer,
            request_line,
            response_headers,
            response_remainder,
        )

    except (
        asyncio.IncompleteReadError,
        ConnectionError,
        OSError,
        ValueError,
    ):
        pass

    finally:
        for writer in (
            client_writer,
            upstream_writer,
        ):
            if writer is None:
                continue

            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


async def main() -> None:
    server = await asyncio.start_server(
        handle_client,
        LISTEN_HOST,
        LISTEN_PORT,
        limit=MAX_HEADER_BYTES,
    )

    addresses = ", ".join(
        str(sock.getsockname())
        for sock in server.sockets or []
    )

    print(
        "CDP relay listening on "
        f"{addresses}; "
        f"upstream={CONFIG.upstream_authority}; "
        f"public={CONFIG.public_authority}",
        flush=True,
    )

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())