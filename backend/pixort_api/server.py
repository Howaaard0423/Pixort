"""The threaded HTTP server that exposes :class:`Application`."""

from __future__ import annotations

import logging
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import settings
from .app import Application
from .http_kit import Request, Response, error_response, normalise_path

logger = logging.getLogger("pixort.server")


class PixortHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(self, address: tuple[str, int], application: Application, quiet: bool = False):
        self.application = application
        self.quiet = quiet
        super().__init__(address, PixortRequestHandler)


class PixortRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"Pixort/{settings.PACKAGE_VERSION}"
    sys_version = ""

    # -- plumbing ---------------------------------------------------------- #
    def log_message(self, fmt: str, *args) -> None:  # noqa: D102 - quiet by design
        if not getattr(self.server, "quiet", False):
            logger.debug("%s - %s", self.address_string(), fmt % args)

    def _read_body(self) -> bytes:
        raw_length = self.headers.get("Content-Length")
        if not raw_length:
            return b""
        try:
            length = int(raw_length)
        except ValueError:
            return b""
        if length <= 0:
            return b""
        if length > settings.MAX_BODY_BYTES:
            raise _PayloadTooLarge(length)
        return self.rfile.read(length)

    def _dispatch(self, method: str) -> None:
        started = time.perf_counter()
        status = 500
        try:
            path, query = normalise_path(self.path)
            try:
                body = self._read_body()
            except _PayloadTooLarge as exc:
                self._write(
                    error_response(413, f"请求体过大（{exc.length} 字节），上限为 {settings.MAX_BODY_BYTES} 字节"),
                    method,
                )
                return

            request = Request(
                method=method,
                raw_path=self.path,
                path=path,
                query=query,
                headers={key.lower(): value for key, value in self.headers.items()},
                body=body,
                remote=self.address_string(),
            )
            response = self.server.application.handle(request)
            status = response.status
            self._write(response, method)
        except (BrokenPipeError, ConnectionResetError):
            status = 499
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("请求处理失败: %s", exc)
            try:
                self._write(error_response(500, "服务器内部错误"), method)
            except Exception:
                pass
        finally:
            if not getattr(self.server, "quiet", False):
                duration = (time.perf_counter() - started) * 1000
                logger.info("%s %s -> %s (%.1f ms)", method, self.path, status, duration)

    def _write(self, response: Response, method: str) -> None:
        self.send_response_only(response.status)
        self.send_header("Server", self.version_string())
        self.send_header("Date", self.date_time_string())
        for key, value in response.headers.items():
            self.send_header(key, value)

        if response.status not in (204, 304) and "Content-Length" not in response.headers:
            length = (
                response.file_path.stat().st_size
                if response.file_path is not None
                else len(response.body)
            )
            self.send_header("Content-Length", str(length))
        self.end_headers()

        if method == "HEAD" or response.status in (204, 304):
            return
        for chunk in response.iter_body():
            self.wfile.write(chunk)

    # -- verbs -------------------------------------------------------------- #
    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_OPTIONS(self) -> None:
        self._dispatch("OPTIONS")


class _PayloadTooLarge(Exception):
    def __init__(self, length: int) -> None:
        super().__init__(length)
        self.length = length


def create_server(
    host: str | None = None,
    port: int | None = None,
    *,
    application: Application | None = None,
    quiet: bool = False,
) -> PixortHTTPServer:
    """Build (but do not start) the HTTP server."""
    app = application or Application()
    app.setup()
    address = (host or settings.HOST, port if port is not None else settings.PORT)
    server = PixortHTTPServer(address, app, quiet=quiet)
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return server
