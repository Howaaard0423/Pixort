"""A small HTTP toolkit built on the standard library.

It provides just enough of a framework - routing, JSON helpers, multipart
parsing and static file serving - to run the Pixort API without third-party
dependencies on the machine that hosts the library.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator
from urllib.parse import parse_qs, quote, unquote, urlparse


class HttpError(Exception):
    """An error that maps onto an HTTP status code."""

    def __init__(self, status: int, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


def bad_request(message: str, details: Any = None) -> HttpError:
    return HttpError(400, message, details)


def not_found(message: str = "资源不存在") -> HttpError:
    return HttpError(404, message)


def conflict(message: str, details: Any = None) -> HttpError:
    return HttpError(409, message, details)


# --------------------------------------------------------------------------- #
# request / response
# --------------------------------------------------------------------------- #
@dataclass
class Request:
    method: str
    raw_path: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes = b""
    params: dict[str, str] = field(default_factory=dict)
    remote: str = ""

    # -- query helpers ----------------------------------------------------- #
    def q(self, name: str, default: str | None = None) -> str | None:
        values = self.query.get(name)
        if not values:
            return default
        return values[0]

    def q_all(self, name: str) -> list[str]:
        return list(self.query.get(name, []))

    def q_int(self, name: str, default: int | None = None) -> int | None:
        raw = self.q(name)
        if raw is None or raw == "":
            return default
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise bad_request(f"参数 {name} 必须是整数") from exc

    def q_bool(self, name: str, default: bool = False) -> bool:
        raw = self.q(name)
        if raw is None or raw == "":
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    # -- body helpers ------------------------------------------------------ #
    def json(self) -> dict[str, Any]:
        if not self.body:
            raise bad_request("请求体为空")
        try:
            payload = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise bad_request("请求体不是合法的 JSON") from exc
        if not isinstance(payload, dict):
            raise bad_request("请求体必须是 JSON 对象")
        return payload

    def form(self) -> dict[str, list[str]]:
        """Parse ``application/x-www-form-urlencoded`` bodies."""
        try:
            text = self.body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise bad_request("表单编码无效") from exc
        return parse_qs(text, keep_blank_values=True)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")


@dataclass
class Response:
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    file_path: Path | None = None

    def iter_body(self, chunk_size: int = 256 * 1024) -> Iterator[bytes]:
        if self.file_path is not None:
            with open(self.file_path, "rb") as handle:
                while True:
                    chunk = handle.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        elif self.body:
            yield self.body


def json_response(data: Any, status: int = 200, headers: dict[str, str] | None = None) -> Response:
    payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    merged = {"Content-Type": "application/json; charset=utf-8"}
    merged.update(headers or {})
    return Response(status=status, headers=merged, body=payload)


def text_response(text: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> Response:
    return Response(status=status, headers={"Content-Type": content_type}, body=text.encode("utf-8"))


def error_response(status: int, message: str, details: Any = None) -> Response:
    payload: dict[str, Any] = {"error": {"status": status, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return json_response(payload, status=status)


def empty_response(status: int = 204) -> Response:
    return Response(status=status)


CONTENT_DISPOSITION_SAFE = re.compile(r"[^A-Za-z0-9._\- ]+")


def file_response(
    path: Path,
    content_type: str = "application/octet-stream",
    *,
    download_name: str | None = None,
    cache_seconds: int | None = None,
    etag: str | None = None,
) -> Response:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise not_found("文件不存在") from exc
    if not path.is_file():
        raise not_found("文件不存在")
    headers = {
        "Content-Type": content_type,
        "Content-Length": str(size),
    }
    if download_name:
        ascii_name = CONTENT_DISPOSITION_SAFE.sub("_", download_name) or "download"
        headers["Content-Disposition"] = (
            f"attachment; filename=\"{ascii_name}\"; "
            f"filename*=UTF-8''{quote(download_name, safe='')}"
        )
    if cache_seconds is not None:
        headers["Cache-Control"] = f"public, max-age={cache_seconds}"
    if etag:
        headers["ETag"] = etag
    return Response(status=200, headers=headers, file_path=path)


# --------------------------------------------------------------------------- #
# multipart/form-data
# --------------------------------------------------------------------------- #
@dataclass
class FilePart:
    name: str
    filename: str
    content_type: str
    data: bytes


_DISPOSITION_PAIR = re.compile(r'([a-zA-Z0-9\-_]+)\s*=\s*"([^"]*)"')
_DISPOSITION_TOKEN = re.compile(r"([a-zA-Z0-9\-_]+)\s*=\s*([^;]+)")


def _parse_part_headers(blob: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in blob.decode("utf-8", errors="replace").split("\r\n"):
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()
    return headers


def _disposition_field(header: str, name: str) -> str | None:
    for key, value in _DISPOSITION_PAIR.findall(header):
        if key.lower() == name:
            return value
    for key, value in _DISPOSITION_TOKEN.findall(header):
        if key.lower() == name:
            return value.strip().strip('"')
    return None


def parse_multipart(body: bytes, content_type: str) -> tuple[list[FilePart], dict[str, list[str]]]:
    """Split a multipart body into file parts and form fields.

    Splitting happens on ``\\r\\n--boundary`` so binary payloads that merely
    contain the boundary token are not mistaken for a separator.
    """
    match = re.search(r'boundary="?([^";]+)"?', content_type)
    if not match:
        raise bad_request("缺失 multipart boundary")
    boundary = match.group(1).encode("utf-8")
    marker = b"\r\n--" + boundary

    if not body.startswith(b"--" + boundary):
        raise bad_request("multipart 数据格式不正确")

    # Prepend CRLF so the very first part is also preceded by the marker;
    # otherwise ``chunks[0]`` (the preamble) would swallow it.
    chunks = (b"\r\n" + body).split(marker)
    files: list[FilePart] = []
    fields: dict[str, list[str]] = {}

    for chunk in chunks[1:]:
        if chunk.startswith(b"--"):
            break
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        elif chunk.startswith(b"\n"):
            chunk = chunk[1:]
        separator = chunk.find(b"\r\n\r\n")
        if separator < 0:
            continue
        raw_headers = chunk[:separator]
        data = chunk[separator + 4 :]
        if data.endswith(b"\r\n"):
            data = data[:-2]

        headers = _parse_part_headers(raw_headers)
        disposition = headers.get("content-disposition", "")
        name = _disposition_field(disposition, "name") or ""
        filename = _disposition_field(disposition, "filename")
        if filename is None:
            filename = _disposition_field(disposition, "filename*")
            if filename and "''" in filename:
                filename = unquote(filename.split("''", 1)[1])

        if filename is None:
            fields.setdefault(name, []).append(data.decode("utf-8", errors="replace"))
        else:
            files.append(
                FilePart(
                    name=name,
                    filename=filename,
                    content_type=headers.get("content-type", "application/octet-stream"),
                    data=data,
                )
            )
    return files, fields


# --------------------------------------------------------------------------- #
# routing
# --------------------------------------------------------------------------- #
Handler = Callable[[Request], Response]


class Route:
    __slots__ = ("method", "pattern", "regex", "handler")

    def __init__(self, method: str, pattern: str, handler: Handler) -> None:
        self.method = method.upper()
        self.pattern = pattern
        self.handler = handler
        escaped = re.sub(
            r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([^}]+))?\}",
            lambda m: f"(?P<{m.group(1)}>{m.group(2) or '[^/]+'})",
            pattern,
        )
        self.regex = re.compile(f"^{escaped}$")


class Router:
    """Ordered route table with automatic 404/405 handling."""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        self._routes.append(Route(method, pattern, handler))

    def get(self, pattern: str, handler: Handler) -> None:
        self.add("GET", pattern, handler)

    def post(self, pattern: str, handler: Handler) -> None:
        self.add("POST", pattern, handler)

    def patch(self, pattern: str, handler: Handler) -> None:
        self.add("PATCH", pattern, handler)

    def put(self, pattern: str, handler: Handler) -> None:
        self.add("PUT", pattern, handler)

    def delete(self, pattern: str, handler: Handler) -> None:
        self.add("DELETE", pattern, handler)

    def resolve(self, request: Request) -> Response:
        allowed: set[str] = set()
        for route in self._routes:
            match = route.regex.match(request.path)
            if not match:
                continue
            if route.method != request.method:
                allowed.add(route.method)
                continue
            request.params = {key: unquote(value) for key, value in match.groupdict().items()}
            return route.handler(request)
        if allowed:
            raise HttpError(405, f"{request.method} 不被支持", {"allow": sorted(allowed)})
        raise not_found(f"未找到接口 {request.path}")

    @property
    def routes(self) -> Iterable[Route]:
        return tuple(self._routes)


def normalise_path(raw_path: str) -> tuple[str, dict[str, list[str]]]:
    """Return ``(decoded path, query)`` with the path collapsed safely."""
    parsed = urlparse(raw_path)
    path = unquote(parsed.path or "/")
    if not path.startswith("/"):
        path = "/" + path
    # collapse "." and ".." so a request can never escape a served folder
    segments: list[str] = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(segment)
    return "/" + "/".join(segments), parse_qs(parsed.query, keep_blank_values=True)


# --------------------------------------------------------------------------- #
# static files
# --------------------------------------------------------------------------- #
_MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".txt": "text/plain; charset=utf-8",
    ".webmanifest": "application/manifest+json",
}


def guess_content_type(path: Path) -> str:
    return _MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")


def resolve_within(root: Path, relative: str) -> Path | None:
    """Resolve ``relative`` under ``root``, refusing path traversal."""
    candidate = (root / relative.lstrip("/")).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate
