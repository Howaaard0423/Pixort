"""Serving illustration bytes: full images, thumbnails and downloads."""

from __future__ import annotations

import hashlib

from .. import repository, settings
from ..db import Database
from ..http_kit import HttpError, Request, Response, Router, file_response
from ..services import media as media_service
from ._helpers import as_int

_THUMBNAIL_DEFAULT = 320


def _load(database: Database, illustration_id: int) -> dict:
    with database.connection() as conn:
        return repository.get_illustration(conn, illustration_id)


def _etag(path, item) -> str:
    try:
        stat = path.stat()
    except OSError as exc:
        raise HttpError(404, "图片文件已丢失") from exc
    digest = hashlib.sha1(
        f"{item['id']}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8")
    ).hexdigest()
    return f'W/"{digest[:24]}"'


def register(router: Router, database: Database) -> None:
    def content(request: Request) -> Response:
        illustration_id = as_int(request.params["illustration_id"], "illustration_id")
        item = _load(database, illustration_id)
        path = media_service.resolve_illustration_path(item["file_path"])
        if not path.is_file():
            raise HttpError(404, "图片文件已丢失")

        width = request.q_int("width")
        if width:
            width = max(64, min(2560, width))
            resized = media_service.thumbnail_for(path, f"ill{illustration_id}", width)
            if resized is not None:
                path = resized

        etag = _etag(path, item)
        if request.headers.get("if-none-match") == etag:
            return Response(
                status=304,
                headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
            )

        download = request.q_bool("download")
        return file_response(
            path,
            media_service.content_type_for(path),
            download_name=item["file_name"] if download else None,
            cache_seconds=86400,
            etag=etag,
        )

    def thumbnail(request: Request) -> Response:
        illustration_id = as_int(request.params["illustration_id"], "illustration_id")
        item = _load(database, illustration_id)
        path = media_service.resolve_illustration_path(item["file_path"])
        if not path.is_file():
            raise HttpError(404, "图片文件已丢失")

        width = request.q_int("width", _THUMBNAIL_DEFAULT) or _THUMBNAIL_DEFAULT
        width = max(64, min(2560, width))
        resized = media_service.thumbnail_for(path, f"ill{illustration_id}", width)
        served = resized if resized is not None else path

        etag = _etag(served, item)
        if request.headers.get("if-none-match") == etag:
            return Response(
                status=304,
                headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
            )
        return file_response(
            served,
            media_service.content_type_for(served),
            cache_seconds=86400,
            etag=etag,
        )

    router.get("/api/illustrations/{illustration_id}/content", content)
    router.get("/api/illustrations/{illustration_id}/thumbnail", thumbnail)

    # Desktop-style direct access, kept for compatibility with existing links.
    def legacy_media(request: Request) -> Response:
        from ..http_kit import resolve_within

        relative = request.path[len("/media/") :]
        candidate = resolve_within(settings.ILLUSTRATIONS_DIR, relative)
        if candidate is None or not candidate.is_file():
            raise HttpError(404, "文件不存在")
        return file_response(
            candidate,
            media_service.content_type_for(candidate),
            cache_seconds=3600,
        )

    router.get("/media/{path:.*}", legacy_media)
