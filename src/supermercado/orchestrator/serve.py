"""Serve a directory over HTTP on a free local port in a background thread."""

from __future__ import annotations

import threading
from collections.abc import Callable
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib signature
        pass


def serve_directory(directory: Path) -> tuple[str, Callable[[], None]]:
    """Start serving `directory` on 127.0.0.1; return its URL and a function that stops it."""
    handler = partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def stop() -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return f"http://127.0.0.1:{server.server_port}/", stop
