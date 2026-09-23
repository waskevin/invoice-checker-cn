from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from PySide6.QtNetwork import QLocalServer, QLocalSocket


SERVER_NAME = "invoice-checker-cn-main-window"


def encode_paths(paths: list[Path]) -> bytes:
    """Serialize forwarded file paths for the already-running main window."""
    return json.dumps([str(path) for path in paths], ensure_ascii=False).encode("utf-8")


def decode_paths(payload: bytes) -> list[Path]:
    """Read forwarded file paths from another launcher process."""
    data = json.loads(payload.decode("utf-8") or "[]")
    if not isinstance(data, list):
        return []
    return [Path(item) for item in data if isinstance(item, str)]


class SingleInstance:
    """Keep one GUI process while letting later launches pass PDF paths to it."""

    def __init__(self, server_name: str = SERVER_NAME) -> None:
        self.server_name = server_name

    def send_to_existing(self, paths: list[Path], timeout_ms: int = 3000) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        if not socket.waitForConnected(timeout_ms):
            socket.abort()
            return False
        socket.write(encode_paths(paths))
        socket.flush()
        socket.waitForBytesWritten(timeout_ms)
        socket.waitForReadyRead(timeout_ms)
        socket.disconnectFromServer()
        return True

    def listen(self, on_paths: Callable[[list[Path]], None]) -> QLocalServer:
        server = QLocalServer()
        if not server.listen(self.server_name):
            # If a previous process crashed, Windows may leave a stale local
            # server name behind.  We only remove it after connect failed.
            QLocalServer.removeServer(self.server_name)
            if not server.listen(self.server_name):
                raise RuntimeError(f"无法启动单窗口监听：{server.errorString()}")

        sockets: list[QLocalSocket] = []

        def handle_connection() -> None:
            socket = server.nextPendingConnection()
            if socket is None:
                return
            sockets.append(socket)

            def read_socket() -> None:
                on_paths(decode_paths(bytes(socket.readAll())))
                socket.write(b"ok")
                socket.flush()
                socket.disconnectFromServer()

            def remove_socket() -> None:
                if socket in sockets:
                    sockets.remove(socket)

            socket.readyRead.connect(read_socket)
            socket.disconnected.connect(remove_socket)

        server.newConnection.connect(handle_connection)
        return server
