"""Application object: wires the router, error handling and static files."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from . import repository, routes, settings
from .db import Database
from .http_kit import (
    HttpError,
    Request,
    Response,
    Router,
    error_response,
    file_response,
    guess_content_type,
    not_found,
    resolve_within,
    text_response,
)

logger = logging.getLogger("pixort.api")

_NO_CACHE = "no-cache, must-revalidate"


class Application:
    """Owns the database handle and the route table."""

    def __init__(self, database: Database | None = None, frontend_dir: Path | None = None) -> None:
        self.database = database or Database()
        self.frontend_dir = Path(frontend_dir or settings.FRONTEND_DIR)
        self.router = Router()
        routes.register_all(self.router, self.database)

    def setup(self) -> None:
        settings.ensure_directories()
        self.database.initialize()

    # ------------------------------------------------------------------ #
    def handle(self, request: Request) -> Response:
        try:
            if request.method == "OPTIONS":
                return Response(status=204, headers=self._cors_headers(request))
            if request.path.startswith("/api/") or request.path == "/api":
                response = self.router.resolve(request)
            else:
                response = self._serve_static(request)
        except HttpError as exc:
            response = error_response(exc.status, exc.message, exc.details)
        except repository.NotFound as exc:
            response = error_response(404, str(exc))
        except ValueError as exc:
            response = error_response(400, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("未处理的异常: %s\n%s", exc, traceback.format_exc())
            response = error_response(500, f"服务器内部错误：{exc}")

        for key, value in self._cors_headers(request).items():
            response.headers.setdefault(key, value)
        return response

    # ------------------------------------------------------------------ #
    @staticmethod
    def _cors_headers(request: Request) -> dict[str, str]:
        return {
            "Access-Control-Allow-Origin": settings.CORS_ORIGIN,
            "Access-Control-Allow-Methods": "GET, POST, PATCH, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-Requested-With",
            "Access-Control-Max-Age": "600",
            "Vary": "Origin",
        }

    def _serve_static(self, request: Request) -> Response:
        if request.method not in ("GET", "HEAD"):
            raise HttpError(405, "静态资源只支持 GET/HEAD")
        if not self.frontend_dir.is_dir():
            return text_response(
                "前端目录不存在，请检查 frontend/ 是否完整。", status=404
            )

        relative = request.path.lstrip("/") or "index.html"
        candidate = resolve_within(self.frontend_dir, relative)
        if candidate is None:
            raise HttpError(403, "非法路径")
        if candidate.is_dir():
            candidate = candidate / "index.html"

        if not candidate.is_file():
            # single-page-app fallback: unknown extension-less routes render the shell
            if Path(relative).suffix:
                raise not_found(f"未找到 {request.path}")
            candidate = self.frontend_dir / "index.html"
            if not candidate.is_file():
                raise not_found("index.html 不存在")

        stat = candidate.stat()
        etag = f'W/"{int(stat.st_mtime)}-{stat.st_size}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status=304, headers={"ETag": etag, "Cache-Control": _NO_CACHE})

        response = file_response(
            candidate,
            guess_content_type(candidate),
            cache_seconds=None,
            etag=etag,
        )
        response.headers["Cache-Control"] = _NO_CACHE
        return response
