"""Backup export and restore endpoints."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .. import settings
from ..db import Database
from ..http_kit import (
    HttpError,
    Request,
    Response,
    Router,
    bad_request,
    file_response,
    json_response,
    parse_multipart,
)
from ..services import transfer

_EXPORT_DIR_NAME = "exports"


def _export_dir() -> Path:
    folder = settings.CACHE_DIR / _EXPORT_DIR_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _resolve_requested_archive(request: Request, files: list) -> Path:
    """Accept either an uploaded archive or a path on the server's disk."""
    for part in files:
        if part.name in {"archive", "file", "backup"}:
            suffix = Path(part.filename).suffix or ".zip"
            target = settings.TEMP_DIR / f"upload_{datetime.now().strftime('%Y%m%d%H%M%S%f')}{suffix}"
            target.write_bytes(part.data)
            return target
    raw = request.q("path")
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_file():
            raise HttpError(404, "指定的备份文件不存在")
        return candidate
    raise bad_request("请上传备份文件或提供 path 参数")


def register(router: Router, database: Database) -> None:
    def export(request: Request) -> Response:
        """Build an archive and hand it back as a download."""
        password = request.q("password") or None
        include_images = not request.q_bool("database_only")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = _export_dir() / f"pixort_backup_{stamp}.zip"
        summary = transfer.build_backup(
            destination, password=password, include_images=include_images
        )
        return file_response(
            destination,
            "application/zip",
            download_name=destination.name,
        )

    def export_status(_request: Request) -> Response:
        folder = _export_dir()
        files = sorted(
            (
                {"name": path.name, "bytes": path.stat().st_size, "modified": path.stat().st_mtime}
                for path in folder.glob("*.zip")
            ),
            key=lambda item: item["modified"],
            reverse=True,
        )
        return json_response({"items": files, "directory": str(folder)})

    def cleanup(_request: Request) -> Response:
        removed = 0
        for path in _export_dir().glob("*.zip"):
            path.unlink(missing_ok=True)
            removed += 1
        return json_response({"removed": removed})

    def download_export(request: Request) -> Response:
        """Serve an archive that already sits in the export folder."""
        name = Path(request.params["name"]).name
        candidate = _export_dir() / name
        if candidate.suffix.lower() != ".zip" or not candidate.is_file():
            raise HttpError(404, "导出文件不存在")
        return file_response(candidate, "application/zip", download_name=candidate.name)

    def inspect(request: Request) -> Response:
        files, _fields = _parse(request)
        password = request.q("password") or None
        archive = _resolve_requested_archive(request, files)
        return json_response({"archive": archive.name, **transfer.inspect_backup(archive, password)})

    def restore(request: Request) -> Response:
        files, _fields = _parse(request)
        password = request.q("password") or None
        archive = _resolve_requested_archive(request, files)
        if not request.q_bool("confirm"):
            info = transfer.inspect_backup(archive, password)
            return json_response(
                {
                    "requires_confirmation": True,
                    "message": "恢复会覆盖当前数据，请附加 confirm=1 重新提交。",
                    "archive": info,
                },
                status=202,
            )
        return json_response(transfer.restore_backup(archive, password=password))

    router.get("/api/transfer/export", export)
    router.get("/api/transfer/exports", export_status)
    router.delete("/api/transfer/exports", cleanup)
    router.get("/api/transfer/exports/{name}", download_export)
    router.post("/api/transfer/inspect", inspect)
    router.post("/api/transfer/restore", restore)


def _parse(request: Request):
    if "multipart/form-data" in request.content_type:
        return parse_multipart(request.body, request.content_type)
    return [], {}
