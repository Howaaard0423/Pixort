"""Library maintenance: relink moved files, refresh metadata, drop duplicates.

Real libraries drift.  Re-importing a folder creates new copies with new
timestamp prefixes while the old rows keep pointing at names that no longer
exist, and rows written by the desktop client carry no size or dimension data.
This module reconciles both without touching anything until it is asked to.

The stored file name is always ``<timestamp>_<original name>``, so a row can be
matched back to a file on disk by comparing the original names.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .. import repository, settings
from ..db import Database, now_iso
from ..http_kit import bad_request
from . import media

_TIMESTAMP_PREFIX = re.compile(r"^\d{10,20}_")


def original_name(stored_name: str) -> str:
    """Strip the import timestamp from a stored file name."""
    return _TIMESTAMP_PREFIX.sub("", Path(stored_name).name, count=1)


def _relative(path: Path) -> str:
    try:
        return path.relative_to(settings.DATA_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _keeper_score(row) -> tuple:
    """Prefer the duplicate that carries artist, character, tags and rating."""
    return (
        1 if row["artist_id"] else 0,
        1 if row["character_id"] else 0,
        1 if (row["tags"] or "").strip() else 0,
        1 if (row["remark"] or "").strip() else 0,
        row["rating"] or 0,
        -row["id"],
    )


def _merge_metadata(keeper, duplicates) -> dict[str, Any]:
    """Combine the surviving row with everything the duplicates knew.

    Deleting a duplicate must never lose an artist assignment, so the fields of
    the discarded rows are folded into the record that stays.
    """
    rows = [keeper, *duplicates]

    def first(column):
        if keeper[column] not in (None, "", 0):
            return keeper[column]
        for row in rows[1:]:
            if row[column] not in (None, "", 0):
                return row[column]
        return keeper[column]

    tags: list[str] = []
    for row in rows:
        for tag in repository.split_tags(row["tags"]):
            if tag not in tags:
                tags.append(tag)

    timestamps = [row["created_at"] for row in rows if row["created_at"]]
    return {
        "artist_id": first("artist_id"),
        "character_id": first("character_id"),
        "tags": ", ".join(tags),
        "rating": max((row["rating"] or 0) for row in rows),
        "remark": first("remark"),
        "created_at": min(timestamps) if timestamps else keeper["created_at"],
    }


def _index_disk() -> dict[str, dict[str, list[Path]]]:
    """Index every image on disk by artist folder and original file name."""
    index: dict[str, dict[str, list[Path]]] = {}
    if not settings.ILLUSTRATIONS_DIR.is_dir():
        return index
    for path in settings.ILLUSTRATIONS_DIR.rglob("*"):
        if not path.is_file() or not media.is_supported_image(path):
            continue
        folder = index.setdefault(path.parent.name, {})
        folder.setdefault(original_name(path.name), []).append(path)
    return index


def scan_library(
    database: Database,
    *,
    repair: bool = True,
    refresh_metadata: bool = True,
    dedupe: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Reconcile the database with the files on disk.

    ``dedupe`` is deliberately opt-in: it deletes rows that point at a file
    another row already owns.
    """
    if dedupe and not repair:
        raise bad_request("去重需要同时开启 repair")

    disk = _index_disk()
    relinked: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    refreshed = 0
    duplicates: list[dict[str, Any]] = []
    scanned = 0
    broken_paths: list[dict[str, Any]] = []

    with database.transaction() as conn:
        rows = conn.execute(
            """
            SELECT id, artist_id, character_id, title, file_path, tags, rating,
                   remark, created_at, file_size, width, height, checksum
            FROM illustrations ORDER BY id
            """
        ).fetchall()
        scanned = len(rows)

        resolved: dict[int, Path] = {}
        for row in rows:
            stored = row["file_path"] or ""
            try:
                candidate = media.resolve_illustration_path(stored)
            except Exception:
                broken_paths.append({"id": row["id"], "file_path": stored})
                continue
            resolved[row["id"]] = candidate

        for row in rows:
            identifier = row["id"]
            stored = row["file_path"] or ""
            candidate = resolved.get(identifier)

            # 1. relink rows whose file was renamed by a later re-import
            if (candidate is None or not candidate.is_file()) and repair and stored:
                folder = Path(stored.replace("\\", "/")).parent.name
                wanted = original_name(stored)
                matches = list(disk.get(folder, {}).get(wanted, []))
                if not matches:
                    matches = [
                        path
                        for other_folder in disk.values()
                        for path in other_folder.get(wanted, [])
                    ]
                if len(matches) == 1:
                    new_path = _relative(matches[0])
                    relinked.append({"id": identifier, "from": stored, "to": new_path})
                    resolved[identifier] = matches[0]
                    if not dry_run:
                        conn.execute(
                            "UPDATE illustrations SET file_path = ?, updated_at = ? WHERE id = ?",
                            (new_path, now_iso(), identifier),
                        )
                elif len(matches) > 1:
                    ambiguous.append(
                        {"id": identifier, "file_path": stored, "candidates": [_relative(p) for p in matches]}
                    )

            # 2. refresh size / dimensions / checksum for reachable files
            target = resolved.get(identifier)
            if target is not None and target.is_file() and refresh_metadata:
                needs_size = row["file_size"] in (None, 0)
                needs_dims = row["width"] is None or row["height"] is None
                needs_checksum = not row["checksum"]
                if needs_size or needs_dims or needs_checksum:
                    size, width, height = media.probe_image(target)
                    checksum = media.checksum_of(target) if needs_checksum else row["checksum"]
                    refreshed += 1
                    if not dry_run:
                        conn.execute(
                            "UPDATE illustrations SET file_size = ?, width = ?, height = ?, checksum = ? WHERE id = ?",
                            (size, width, height, checksum, identifier),
                        )

            if target is None or not target.is_file():
                if identifier not in {entry["id"] for entry in ambiguous}:
                    missing.append({"id": identifier, "file_path": stored})

        # 3. rows that survive all of the above and still share one file
        owners: dict[str, list[int]] = {}
        for row in rows:
            target = resolved.get(row["id"])
            if target is None or not target.is_file():
                continue
            owners.setdefault(str(target).lower(), []).append(row["id"])

        by_id = {row["id"]: row for row in rows}
        for file_key, identifiers in owners.items():
            if len(identifiers) < 2:
                continue
            # keep the record carrying the most information, not merely the oldest
            keeper_id = max(identifiers, key=lambda identifier: _keeper_score(by_id[identifier]))
            others = [identifier for identifier in identifiers if identifier != keeper_id]
            merged = _merge_metadata(by_id[keeper_id], [by_id[identifier] for identifier in others])
            duplicates.append(
                {
                    "kept": keeper_id,
                    "removed": sorted(others),
                    "file_path": _relative(resolved[keeper_id]),
                    "merged_fields": sorted(
                        field
                        for field, value in merged.items()
                        if value != by_id[keeper_id][field]
                    ),
                }
            )
            if dedupe and not dry_run:
                conn.execute(
                    """
                    UPDATE illustrations
                    SET artist_id = ?, character_id = ?, tags = ?, rating = ?,
                        remark = ?, created_at = ?
                    WHERE id = ?
                    """,
                    (
                        merged["artist_id"],
                        merged["character_id"],
                        merged["tags"],
                        merged["rating"],
                        merged["remark"],
                        merged["created_at"],
                        keeper_id,
                    ),
                )
                conn.executemany(
                    "DELETE FROM illustrations WHERE id = ?",
                    [(identifier,) for identifier in others],
                )

    return {
        "dry_run": dry_run,
        "scanned": scanned,
        "relinked": relinked,
        "ambiguous": ambiguous,
        "missing": missing,
        "unreadable_paths": broken_paths,
        "metadata_refreshed": refreshed,
        "duplicates": duplicates,
        "applied": {
            "relinked": 0 if dry_run else len(relinked),
            "metadata_refreshed": 0 if dry_run else refreshed,
            "removed_duplicates": 0
            if dry_run or not dedupe
            else sum(len(group["removed"]) for group in duplicates),
        },
    }
