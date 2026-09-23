"""Shared helpers for the route handlers."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .. import settings
from ..http_kit import HttpError, bad_request
from ..services import media as media_service


def as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise bad_request(f"{field} 必须是整数") from exc


def json_int(payload: dict[str, Any], field: str) -> int:
    if field not in payload:
        raise bad_request(f"缺少字段 {field}")
    return as_int(payload[field], field)


def optional_int(payload: dict[str, Any], field: str) -> int | None:
    """None passes through; anything else must be an integer."""
    if field not in payload or payload[field] is None:
        return None
    return as_int(payload[field], field)


def decorate(item: dict[str, Any]) -> dict[str, Any]:
    """Attach the media URLs the front end needs for one illustration."""
    identifier = item["id"]
    exists = False
    if item.get("file_path"):
        try:
            resolved = media_service.resolve_illustration_path(item["file_path"])
            exists = resolved.is_file()
        except HttpError:
            exists = False
    return {
        **item,
        "file_exists": exists,
        "url": f"/api/illustrations/{identifier}/content",
        "thumbnail_url": f"/api/illustrations/{identifier}/thumbnail",
        "download_url": f"/api/illustrations/{identifier}/content?download=1",
    }


def decorate_many(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [decorate(item) for item in items]


def artist_folder(name: str) -> Path | None:
    """Resolve an artist folder inside the illustration root (or None)."""
    folder = (settings.ILLUSTRATIONS_DIR / name).resolve()
    root = settings.ILLUSTRATIONS_DIR.resolve()
    try:
        folder.relative_to(root)
    except ValueError:
        return None
    return folder


def remove_folder_if_unreferenced(database, artist_name: str) -> int:
    """Delete an artist folder only when the database no longer points into it.

    The desktop client removed the folder unconditionally, which could destroy
    files that were still referenced (for example after a failed delete).
    """
    folder = artist_folder(artist_name)
    if folder is None or not folder.is_dir():
        return 0
    with database.connection() as conn:
        rows = conn.execute("SELECT file_path FROM illustrations").fetchall()
    # Compare resolved paths rather than a string prefix: a legacy row may hold
    # an absolute path, which a "illustrations/<artist>/" prefix would miss.
    for row in rows:
        try:
            candidate = media_service.resolve_illustration_path(row["file_path"])
        except HttpError:
            continue
        if candidate == folder or folder in candidate.parents:
            return 0
    removed = sum(1 for path in folder.rglob("*") if path.is_file())
    shutil.rmtree(folder, ignore_errors=True)
    return removed
