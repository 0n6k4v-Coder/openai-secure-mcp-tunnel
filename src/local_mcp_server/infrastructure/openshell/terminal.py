from __future__ import annotations

import queue
import threading
from collections import deque
from collections.abc import Iterator

from openshell._proto import openshell_pb2
from openshell.sandbox import _workspace_scope

from .client import active_client
from .sandbox import OPENSHELL_WORKSPACE, SandboxError, validate_name


class OpenShellTerminalSession:
    """Manages an active bidirectional gRPC streaming session with OpenShell ExecSandboxInteractive."""

    def __init__(
        self,
        sandbox: str,
        command: list[str] | None = None,
        cols: int = 80,
        rows: int = 24,
        workspace: str | None = None,
    ) -> None:
        self.sandbox = validate_name(sandbox)
        self.command = command or ["sh", "-l"]
        self.cols = cols
        self.rows = rows
        self.workspace = workspace or OPENSHELL_WORKSPACE

        self._input_queue: queue.Queue[openshell_pb2.ExecSandboxInput | None] = queue.Queue(maxsize=256)
        self._output_buffer: deque[bytes] = deque()
        self._output_buffer_bytes = 0
        self._max_output_buffer_bytes = 1024 * 1024
        self._max_output_chunks = 2000
        self._exit_code: int | None = None
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._worker_thread: threading.Thread | None = None
        self._error: str | None = None

    def start(self) -> None:
        """Start the interactive execution stream."""
        client = active_client()
        stub = client._stub

        initial_request = openshell_pb2.ExecSandboxRequest(
            workspace_scope=_workspace_scope(self.workspace),
            sandbox=self.sandbox,
            command=self.command,
            tty=True,
            cols=self.cols,
            rows=self.rows,
        )
        initial_input = openshell_pb2.ExecSandboxInput(start=initial_request)
        self._input_queue.put(initial_input)

        def request_generator() -> Iterator[openshell_pb2.ExecSandboxInput]:
            while not self._closed.is_set():
                try:
                    item = self._input_queue.get(timeout=0.2)
                    if item is None:
                        break
                    yield item
                except queue.Empty:
                    continue

        def worker() -> None:
            try:
                stream = stub.ExecSandboxInteractive(request_generator())
                for event in stream:
                    payload = event.WhichOneof("payload")
                    if payload == "stdout":
                        data = bytes(event.stdout.data)
                        self._append_output(data)
                    elif payload == "stderr":
                        data = bytes(event.stderr.data)
                        self._append_output(data)
                    elif payload == "exit":
                        with self._lock:
                            self._exit_code = int(event.exit.exit_code)
                        break
            except Exception as exc:
                with self._lock:
                    self._error = str(exc)
            finally:
                self._closed.set()

        self._worker_thread = threading.Thread(
            target=worker,
            name=f"openshell-term-{self.sandbox}",
            daemon=True,
        )
        self._worker_thread.start()

    def _append_output(self, data: bytes) -> None:
        if not data:
            return
        if len(data) > self._max_output_buffer_bytes:
            data = data[-self._max_output_buffer_bytes:]
        with self._lock:
            self._output_buffer.append(data)
            self._output_buffer_bytes += len(data)
            while self._output_buffer and (
                self._output_buffer_bytes > self._max_output_buffer_bytes
                or len(self._output_buffer) > self._max_output_chunks
            ):
                removed = self._output_buffer.popleft()
                self._output_buffer_bytes -= len(removed)

    def write(self, data: bytes | str) -> None:
        """Send stdin input to the interactive shell."""
        if self._closed.is_set():
            raise SandboxError("Terminal session is closed")

        if isinstance(data, str):
            raw = data.encode("utf-8")
        else:
            raw = bytes(data)

        if len(raw) > 64 * 1024:
            raise SandboxError("Terminal input exceeds the 64 KiB per-write limit")
        msg = openshell_pb2.ExecSandboxInput(stdin=raw)
        try:
            self._input_queue.put_nowait(msg)
        except queue.Full as exc:
            raise SandboxError("Terminal input queue is full; retry after it drains") from exc

    def resize(self, cols: int, rows: int) -> None:
        """Send window resize event to the interactive shell."""
        if self._closed.is_set():
            raise SandboxError("Terminal session is closed")

        if isinstance(cols, bool) or not isinstance(cols, int) or not 20 <= cols <= 300:
            raise SandboxError("Terminal columns must be between 20 and 300")
        if isinstance(rows, bool) or not isinstance(rows, int) or not 5 <= rows <= 200:
            raise SandboxError("Terminal rows must be between 5 and 200")
        resize_msg = openshell_pb2.ExecSandboxWindowResize(cols=cols, rows=rows)
        msg = openshell_pb2.ExecSandboxInput(resize=resize_msg)
        try:
            self._input_queue.put_nowait(msg)
        except queue.Full as exc:
            raise SandboxError("Terminal input queue is full; retry after it drains") from exc
        self.cols = cols
        self.rows = rows

    def read_output(self, clear: bool = True) -> bytes:
        """Read accumulated terminal output bytes."""
        with self._lock:
            if not self._output_buffer:
                return b""
            combined = b"".join(self._output_buffer)
            if clear:
                self._output_buffer.clear()
                self._output_buffer_bytes = 0
            return combined

    def is_alive(self) -> bool:
        return not self._closed.is_set()

    @property
    def exit_code(self) -> int | None:
        with self._lock:
            return self._exit_code

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def close(self) -> None:
        """Close the interactive session."""
        self._closed.set()
        try:
            self._input_queue.put_nowait(None)
        except queue.Full:
            try:
                self._input_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._input_queue.put_nowait(None)
            except queue.Full:
                pass
