"""Small local static server for the phone filming coach."""

from __future__ import annotations

import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


_SERVER: ThreadingHTTPServer | None = None
_THREAD: threading.Thread | None = None


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def ensure_mobile_coach_server(directory: str | Path, port: int = 8502) -> dict:
    """Start the coach server once and expose it to devices on the same LAN."""
    global _SERVER, _THREAD
    root = Path(directory).resolve()
    entry = root / "mobile-coach.html"
    if not entry.exists():
        return {"running": False, "error": f"촬영 코치 파일이 없습니다: {entry}"}
    if _SERVER is not None and _THREAD is not None and _THREAD.is_alive():
        return {"running": True, "port": port, "directory": str(root)}
    if _port_is_open(port):
        return {"running": True, "port": port, "directory": str(root), "existing": True}
    try:
        handler = partial(_QuietHandler, directory=str(root))
        _SERVER = ThreadingHTTPServer(("0.0.0.0", port), handler)
        _SERVER.daemon_threads = True
        _THREAD = threading.Thread(target=_SERVER.serve_forever, name="mobile-coach-server", daemon=True)
        _THREAD.start()
        return {"running": True, "port": port, "directory": str(root)}
    except OSError as exc:
        return {"running": False, "port": port, "error": str(exc)}
