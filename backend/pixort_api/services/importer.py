"""Ingestion pipeline shared by file uploads and server-side folder imports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .. import repository, settings
from ..db import Database
from ..http_kit import bad_request
from . import media

_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitise_component(name: str, fallback: str = "未分类") -> str:
    """Make a string safe to use as one path segment on Windows or POSIX."""
    cleaned = _ILLEGAL_CHARS.sub("_", (name or "").strip()).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return fallback
    if cleaned.upper() in _RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned[:120]


def stored_filename(original: str) -> str:
    """Timestamp prefix keeps names unique without sacrificing readability."""
    stem = sanitise_component(Path(original).stem, "image")
    suffix = Path(original).suffix.lower() or ".png"
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"{stamp}_{stem[:80]}{suffix}"


@dataclass
class ImportOptions:
    artist: str = ""
    character: str = ""
    tags: list[str] = field(default_factory=list)
    rating: int = 0
    # auto  -> derive the artist from the file's folder
    # fixed -> use ``artist`` for every file
    # none  -> leave the work unassigned
    artist_mode: str = "auto"
    skip_duplicates: bool = True

    def validate(self) -> None:
        if self.artist_mode not in {"auto", "fixed", "none"}:
            raise bad_request("artist_mode 只能是 auto、fixed 或 none")
        self.rating = max(0, min(5, int(self.rating or 0)))


def _resolve_artist_name(relative_path: str | None, options: ImportOptions, source: Path) -> str:
    if options.artist_mode == "none":
        return ""
    if options.artist_mode == "fixed":
        return options.artist.strip()
    hint = (relative_path or "").replace("\\", "/")
    if hint:
        parts = [part for part in hint.split("/") if part and part != Path(hint).name]
        if parts:
            return parts[0].strip()
    if options.artist.strip():
        return options.artist.strip()
    parent = source.parent.name
    return "" if parent in ("", ".") else parent


def _ingest(
    database: Database,
    *,
    payload: bytes | None,
    source: Path | None,
    filename: str,
    relative_path: str | None,
    options: ImportOptions,
) -> dict:
    """Write one image into the library and register it."""
    artist_name = _resolve_artist_name(relative_path, options, source or Path(filename))
    checksum = (
        media.checksum_of_bytes(payload)
        if payload is not None
        else media.checksum_of(source)  # type: ignore[arg-type]
    )

    with database.transaction() as conn:
        artist_id = repository.create_artist(conn, artist_name)["id"] if artist_name else None
        if options.skip_duplicates:
            duplicate = repository.find_by_checksum(conn, checksum, artist_id=artist_id)
            if duplicate:
                return {
                    "status": "skipped",
                    "reason": "duplicate",
                    "filename": filename,
                    "existing_id": duplicate["id"],
                    "title": duplicate["title"],
                }

        folder = settings.ILLUSTRATIONS_DIR / sanitise_component(artist_name or "未分类")
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / stored_filename(filename)

        # If the row cannot be written, the copied file must not be left behind
        # as an orphan that nothing in the database points at.
        try:
            if payload is not None:
                target.write_bytes(payload)
            else:
                target.write_bytes(source.read_bytes())  # type: ignore[union-attr]
        except OSError as exc:
            target.unlink(missing_ok=True)
            raise bad_request(f"无法写入图片：{exc}") from exc

        size, width, height = media.probe_image(target)
        character_id = (
            repository.create_character(conn, options.character)["id"]
            if options.character.strip()
            else None
        )
        try:
            illustration = repository.create_illustration(
                conn,
                file_path=str(target.relative_to(settings.DATA_ROOT)).replace("\\", "/"),
                artist_id=artist_id,
                character_id=character_id,
                title=Path(filename).stem,
                tags=options.tags,
                rating=options.rating,
                file_size=size,
                width=width,
                height=height,
                checksum=checksum,
            )
        except Exception:
            target.unlink(missing_ok=True)
            raise

    return {"status": "imported", "filename": filename, "illustration": illustration}


def ingest_upload(
    database: Database,
    *,
    data: bytes,
    filename: str,
    relative_path: str | None,
    options: ImportOptions,
) -> dict:
    return _ingest(
        database,
        payload=data,
        source=None,
        filename=filename,
        relative_path=relative_path,
        options=options,
    )


def ingest_local_file(
    database: Database,
    *,
    source: Path,
    relative_path: str | None,
    options: ImportOptions,
) -> dict:
    return _ingest(
        database,
        payload=None,
        source=source,
        filename=source.name,
        relative_path=relative_path,
        options=options,
    )
