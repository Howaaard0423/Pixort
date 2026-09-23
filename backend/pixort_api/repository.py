"""Data access for artists, characters and illustrations.

Everything in this module talks to SQLite and returns plain dictionaries; no
HTTP or filesystem side effects live here.  Compared with the original desktop
code this layer removes the per-row lookups (N+1) and escapes search input
before it reaches a ``LIKE`` clause.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable, Sequence

from . import settings
from .db import now_iso

LIKE_ESCAPE = "\\"

ILLUSTRATION_SELECT = """
    SELECT i.id, i.artist_id, i.character_id, i.title, i.file_path, i.tags,
           i.rating, i.remark, i.created_at, i.updated_at, i.file_size,
           i.width, i.height, i.checksum, i.sort_order,
           a.name AS artist_name, c.name AS character_name
    FROM illustrations i
    LEFT JOIN artists a ON a.id = i.artist_id
    LEFT JOIN characters c ON c.id = i.character_id
"""

_SORT_CLAUSES = {
    "created_desc": "i.created_at DESC, i.id DESC",
    "created_asc": "i.created_at ASC, i.id ASC",
    "updated_desc": "i.updated_at DESC, i.id DESC",
    "title_asc": "i.title COLLATE NOCASE ASC, i.id ASC",
    "title_desc": "i.title COLLATE NOCASE DESC, i.id DESC",
    "rating_desc": "i.rating DESC, i.created_at DESC",
    "artist_asc": "a.name COLLATE NOCASE ASC, i.sort_order ASC, i.id ASC",
    "manual": "i.sort_order ASC, i.id ASC",
}
DEFAULT_SORT = "manual"
UNASSIGNED_LABEL = "未分类"


def available_sorts() -> tuple[str, ...]:
    """Sort keys accepted by :func:`list_illustrations`."""
    return tuple(_SORT_CLAUSES)


def updatable_fields() -> tuple[str, ...]:
    """Field names that :func:`update_illustration` accepts."""
    return tuple(_UPDATABLE_FIELDS)


class NotFound(LookupError):
    """Raised when a requested row does not exist."""


def like_pattern(text: str) -> str:
    """Escape ``%``/``_`` so user input cannot act as a wildcard."""
    return f"%{escape_like(text)}%"


def escape_like(text: str) -> str:
    """Escape the ``LIKE`` metacharacters so text is matched literally."""
    escaped = text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
    return escaped.replace("%", LIKE_ESCAPE + "%").replace("_", LIKE_ESCAPE + "_")


# Tags live in one comma separated column, so a single tag is matched by
# wrapping both the column and the needle in delimiters.  Spaces are stripped
# on both sides because ``join_tags`` writes "a, b" - without that, every tag
# but the first would be unfindable.
TAG_MATCH_SQL = (
    "',' || REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(i.tags, '，', ','), '、', ','), "
    "';', ','), '；', ','), ' ', '') || ','"
)


def normalise_tag(tag: str) -> str:
    """Fold a tag exactly the way :data:`TAG_MATCH_SQL` folds the column."""
    text = tag
    for separator in settings.TAG_SPLIT_CHARS:
        text = text.replace(separator, ",")
    return "".join(text.split())


def _normalise_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("名称不能为空")
    return cleaned


def _row_to_illustration(row: sqlite3.Row) -> dict[str, Any]:
    path = row["file_path"] or ""
    return {
        "id": row["id"],
        "artist_id": row["artist_id"],
        "artist_name": row["artist_name"],
        "character_id": row["character_id"],
        "character_name": row["character_name"],
        "title": row["title"],
        "file_path": path,
        "file_name": path.replace("\\", "/").rsplit("/", 1)[-1],
        "tags": split_tags(row["tags"]),
        "tags_raw": row["tags"] or "",
        "rating": row["rating"] or 0,
        "remark": row["remark"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "file_size": row["file_size"],
        "width": row["width"],
        "height": row["height"],
        "checksum": row["checksum"],
        "sort_order": row["sort_order"] or 0,
    }


def split_tags(raw: str | None) -> list[str]:
    """Turn the free-form ``tags`` column into a de-duplicated list."""
    if not raw:
        return []
    text = raw
    for separator in settings.TAG_SPLIT_CHARS:
        text = text.replace(separator, ",")
    seen: list[str] = []
    for chunk in text.split(","):
        tag = chunk.strip()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def join_tags(tags: Iterable[str] | str | None) -> str:
    """Normalise a tag list (or raw string) for storage."""
    if tags is None:
        return ""
    if isinstance(tags, str):
        return ", ".join(split_tags(tags))
    return ", ".join(split_tags(", ".join(str(t) for t in tags)))


def parse_tags(value: Any) -> list[str]:
    """Read a tag field coming from JSON, which may be a list or a string.

    ``str(["a"])`` yields ``"['a']"``, so a list must never be coerced through
    ``str`` before being split.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return split_tags(", ".join(str(item) for item in value))
    return split_tags(str(value))


# --------------------------------------------------------------------------- #
# artists
# --------------------------------------------------------------------------- #
def list_artists(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT a.id, a.name, a.created_at, COUNT(i.id) AS count
        FROM artists a
        LEFT JOIN illustrations i ON i.artist_id = a.id
        GROUP BY a.id, a.name, a.created_at
        ORDER BY a.name COLLATE NOCASE ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_artist(conn: sqlite3.Connection, artist_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, name, created_at FROM artists WHERE id = ?", (artist_id,)
    ).fetchone()
    if row is None:
        raise NotFound(f"画师 {artist_id} 不存在")
    return dict(row)


def create_artist(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    """Idempotent by name: returns the existing row when it is already there."""
    cleaned = _normalise_name(name)
    conn.execute(
        "INSERT OR IGNORE INTO artists (name, created_at) VALUES (?, ?)",
        (cleaned, now_iso()),
    )
    row = conn.execute(
        "SELECT id, name, created_at FROM artists WHERE name = ?", (cleaned,)
    ).fetchone()
    return dict(row)


def rename_artist(conn: sqlite3.Connection, artist_id: int, name: str) -> dict[str, Any]:
    cleaned = _normalise_name(name)
    get_artist(conn, artist_id)
    try:
        conn.execute("UPDATE artists SET name = ? WHERE id = ?", (cleaned, artist_id))
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"画师「{cleaned}」已存在") from exc
    return get_artist(conn, artist_id)


def delete_artist(conn: sqlite3.Connection, artist_id: int) -> int:
    """Detach the works, then drop the artist. Returns the detached count."""
    get_artist(conn, artist_id)
    detached = conn.execute(
        "SELECT COUNT(*) AS n FROM illustrations WHERE artist_id = ?", (artist_id,)
    ).fetchone()["n"]
    conn.execute("UPDATE illustrations SET artist_id = NULL WHERE artist_id = ?", (artist_id,))
    conn.execute("DELETE FROM artists WHERE id = ?", (artist_id,))
    return detached


# --------------------------------------------------------------------------- #
# characters
# --------------------------------------------------------------------------- #
def list_characters(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.created_at, COUNT(i.id) AS count
        FROM characters c
        LEFT JOIN illustrations i ON i.character_id = c.id
        GROUP BY c.id, c.name, c.created_at
        ORDER BY c.name COLLATE NOCASE ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_character(conn: sqlite3.Connection, character_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, name, created_at FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    if row is None:
        raise NotFound(f"角色 {character_id} 不存在")
    return dict(row)


def create_character(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    cleaned = _normalise_name(name)
    conn.execute(
        "INSERT OR IGNORE INTO characters (name, created_at) VALUES (?, ?)",
        (cleaned, now_iso()),
    )
    row = conn.execute(
        "SELECT id, name, created_at FROM characters WHERE name = ?", (cleaned,)
    ).fetchone()
    return dict(row)


def rename_character(conn: sqlite3.Connection, character_id: int, name: str) -> dict[str, Any]:
    cleaned = _normalise_name(name)
    get_character(conn, character_id)
    try:
        conn.execute("UPDATE characters SET name = ? WHERE id = ?", (cleaned, character_id))
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"角色「{cleaned}」已存在") from exc
    return get_character(conn, character_id)


def delete_character(conn: sqlite3.Connection, character_id: int) -> int:
    get_character(conn, character_id)
    detached = conn.execute(
        "SELECT COUNT(*) AS n FROM illustrations WHERE character_id = ?", (character_id,)
    ).fetchone()["n"]
    conn.execute(
        "UPDATE illustrations SET character_id = NULL WHERE character_id = ?", (character_id,)
    )
    conn.execute("DELETE FROM characters WHERE id = ?", (character_id,))
    return detached


# --------------------------------------------------------------------------- #
# illustrations
# --------------------------------------------------------------------------- #
def _build_filters(
    *,
    artist_id: int | None = None,
    artist_name: str | None = None,
    character_id: int | None = None,
    q: str | None = None,
    tag: str | None = None,
    rating: int | None = None,
    rating_min: int | None = None,
    unassigned_artist: bool = False,
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if unassigned_artist:
        clauses.append("i.artist_id IS NULL")
    elif artist_id is not None:
        clauses.append("i.artist_id = ?")
        params.append(artist_id)
    if artist_name:
        clauses.append("a.name = ?")
        params.append(artist_name)
    if character_id is not None:
        clauses.append("i.character_id = ?")
        params.append(character_id)
    if rating is not None:
        clauses.append("i.rating = ?")
        params.append(rating)
    if rating_min is not None:
        clauses.append("i.rating >= ?")
        params.append(rating_min)
    if tag and tag.strip():
        clauses.append(f"{TAG_MATCH_SQL} LIKE ? ESCAPE '{LIKE_ESCAPE}'")
        params.append(f"%,{escape_like(normalise_tag(tag))},%")
    if q and q.strip():
        pattern = like_pattern(q.strip())
        clauses.append(
            "(i.title LIKE ? ESCAPE '\\' OR i.tags LIKE ? ESCAPE '\\' "
            "OR i.remark LIKE ? ESCAPE '\\' OR a.name LIKE ? ESCAPE '\\' "
            "OR c.name LIKE ? ESCAPE '\\' OR i.file_path LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern] * 6)

    return clauses, params


def list_illustrations(
    conn: sqlite3.Connection,
    *,
    sort: str = DEFAULT_SORT,
    limit: int | None = None,
    offset: int = 0,
    **filters: Any,
) -> tuple[list[dict[str, Any]], int]:
    """Return ``(items, total)`` where ``total`` ignores limit/offset."""
    clauses, params = _build_filters(**filters)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    total = conn.execute(
        f"""
        SELECT COUNT(*) AS n FROM illustrations i
        LEFT JOIN artists a ON a.id = i.artist_id
        LEFT JOIN characters c ON c.id = i.character_id
        {where}
        """,
        params,
    ).fetchone()["n"]

    order = _SORT_CLAUSES.get(sort, _SORT_CLAUSES[DEFAULT_SORT])
    sql = f"{ILLUSTRATION_SELECT} {where} ORDER BY {order}"
    query_params = list(params)
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        query_params.extend([max(0, limit), max(0, offset)])

    rows = conn.execute(sql, query_params).fetchall()
    return [_row_to_illustration(row) for row in rows], total


def get_illustration(conn: sqlite3.Connection, illustration_id: int) -> dict[str, Any]:
    row = conn.execute(f"{ILLUSTRATION_SELECT} WHERE i.id = ?", (illustration_id,)).fetchone()
    if row is None:
        raise NotFound(f"作品 {illustration_id} 不存在")
    return _row_to_illustration(row)


def find_by_path(conn: sqlite3.Connection, file_path: str) -> dict[str, Any] | None:
    """Duplicate detection that is case-insensitive on Windows paths."""
    row = conn.execute(
        f"{ILLUSTRATION_SELECT} WHERE i.file_path = ? COLLATE NOCASE", (file_path,)
    ).fetchone()
    return _row_to_illustration(row) if row else None


def find_by_checksum(
    conn: sqlite3.Connection, checksum: str, *, artist_id: int | None = -1
) -> dict[str, Any] | None:
    """Locate an existing copy of the same bytes (optionally within one artist)."""
    if not checksum:
        return None
    sql = f"{ILLUSTRATION_SELECT} WHERE i.checksum = ?"
    params: list[Any] = [checksum]
    if artist_id != -1:
        sql += " AND i.artist_id IS ?"
        params.append(artist_id)
    row = conn.execute(f"{sql} LIMIT 1", params).fetchone()
    return _row_to_illustration(row) if row else None


def next_sort_order(conn: sqlite3.Connection, artist_id: int | None) -> int:
    """Next manual position inside an artist folder.

    ``artist_id IS ?`` (instead of ``=``) is deliberate: SQLite never matches
    ``NULL`` with ``=``, which is the bug that pinned every unassigned work to
    position 0 in the original implementation.
    """
    row = conn.execute(
        "SELECT MAX(sort_order) AS m FROM illustrations WHERE artist_id IS ?", (artist_id,)
    ).fetchone()
    return (row["m"] or 0) + 1


def create_illustration(
    conn: sqlite3.Connection,
    *,
    file_path: str,
    artist_id: int | None = None,
    character_id: int | None = None,
    title: str | None = None,
    tags: Iterable[str] | str | None = None,
    rating: int = 0,
    remark: str = "",
    file_size: int | None = None,
    width: int | None = None,
    height: int | None = None,
    checksum: str | None = None,
) -> dict[str, Any]:
    artist_id = _validate_reference(conn, "artist_id", artist_id)
    character_id = _validate_reference(conn, "character_id", character_id)
    timestamp = now_iso()
    cursor = conn.execute(
        """
        INSERT INTO illustrations
            (artist_id, character_id, title, file_path, tags, rating, remark,
             created_at, updated_at, file_size, width, height, checksum, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artist_id,
            character_id,
            title,
            file_path,
            join_tags(tags),
            max(0, min(5, int(rating or 0))),
            remark or "",
            timestamp,
            timestamp,
            file_size,
            width,
            height,
            checksum,
            next_sort_order(conn, artist_id),
        ),
    )
    return get_illustration(conn, cursor.lastrowid)


_UPDATABLE_FIELDS = {
    "artist_id": "artist_id",
    "character_id": "character_id",
    "title": "title",
    "tags": "tags",
    "rating": "rating",
    "remark": "remark",
    "sort_order": "sort_order",
}

_REFERENCE_TABLES = {"artist_id": ("artists", "画师"), "character_id": ("characters", "角色")}


def _validate_reference(conn: sqlite3.Connection, field: str, value: Any) -> int | None:
    """Check a foreign key before SQLite does.

    Without this a stale or hand-written id surfaces as a raw
    ``FOREIGN KEY constraint failed`` message and an HTTP 500.
    """
    if value is None:
        return None
    table, label = _REFERENCE_TABLES[field]
    try:
        identifier = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} ID 必须是整数") from exc
    if conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (identifier,)).fetchone() is None:
        raise NotFound(f"{label} {identifier} 不存在")
    return identifier


def update_illustration(
    conn: sqlite3.Connection, illustration_id: int, changes: dict[str, Any]
) -> dict[str, Any]:
    """Patch only the supplied fields, using the sentinel ``MISSING`` for nulls."""
    get_illustration(conn, illustration_id)

    assignments: list[str] = []
    params: list[Any] = []
    for key, column in _UPDATABLE_FIELDS.items():
        if key not in changes:
            continue
        value = changes[key]
        if key == "tags":
            value = join_tags(value)
        elif key == "rating":
            try:
                value = max(0, min(5, int(value or 0)))
            except (TypeError, ValueError) as exc:
                raise ValueError("rating 必须是 0 到 5 之间的整数") from exc
        elif key in _REFERENCE_TABLES:
            value = _validate_reference(conn, key, value)
        elif key in {"title", "remark"}:
            # JSON null would blank the column; the UI treats "" as "unset".
            value = "" if value is None else str(value)
        elif key == "sort_order" and value is not None:
            value = int(value)
        assignments.append(f"{column} = ?")
        params.append(value)

    if not assignments:
        return get_illustration(conn, illustration_id)

    assignments.append("updated_at = ?")
    params.append(now_iso())
    params.append(illustration_id)
    conn.execute(f"UPDATE illustrations SET {', '.join(assignments)} WHERE id = ?", params)
    return get_illustration(conn, illustration_id)


def refresh_file_metadata(
    conn: sqlite3.Connection,
    illustration_id: int,
    *,
    file_size: int | None,
    width: int | None,
    height: int | None,
) -> None:
    """Store size/dimension probes without touching ``updated_at`` semantics."""
    conn.execute(
        "UPDATE illustrations SET file_size = ?, width = ?, height = ? WHERE id = ?",
        (file_size, width, height, illustration_id),
    )


def delete_illustration(conn: sqlite3.Connection, illustration_id: int) -> dict[str, Any]:
    """Remove the row and return the deleted record so the caller can unlink it."""
    item = get_illustration(conn, illustration_id)
    conn.execute("DELETE FROM illustrations WHERE id = ?", (illustration_id,))
    return item


def list_tags(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Aggregate the free-form tag column into ``[{tag, count}]``."""
    counter: dict[str, int] = {}
    for row in conn.execute("SELECT tags FROM illustrations WHERE tags IS NOT NULL AND tags <> ''"):
        for tag in split_tags(row["tags"]):
            counter[tag] = counter.get(tag, 0) + 1
    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def statistics(conn: sqlite3.Connection) -> dict[str, Any]:
    """Library counters used by the masthead and the statistics panel."""
    def scalar(sql: str, params: Sequence[Any] = ()) -> Any:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else 0

    ratings = {str(level): 0 for level in range(0, 6)}
    for row in conn.execute("SELECT rating, COUNT(*) AS n FROM illustrations GROUP BY rating"):
        ratings[str(row["rating"] or 0)] = row["n"]

    return {
        "illustrations": scalar("SELECT COUNT(*) FROM illustrations"),
        "artists": scalar("SELECT COUNT(*) FROM artists"),
        "characters": scalar("SELECT COUNT(*) FROM characters"),
        "unassigned": scalar("SELECT COUNT(*) FROM illustrations WHERE artist_id IS NULL"),
        "total_bytes": scalar("SELECT COALESCE(SUM(file_size), 0) FROM illustrations"),
        "ratings": ratings,
        "latest_created_at": scalar("SELECT MAX(created_at) FROM illustrations"),
    }


def artist_tree(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Artists with their works in one pass (two queries total, no N+1).

    Works without an artist are grouped under ``未分类``.  When an artist with
    that exact name already exists, the orphans join it instead of producing a
    second, identically labelled group.
    """
    artists = list_artists(conn)
    rows = conn.execute(
        f"{ILLUSTRATION_SELECT} ORDER BY a.name COLLATE NOCASE ASC, i.sort_order ASC, i.id ASC"
    ).fetchall()

    buckets: dict[int | None, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(row["artist_id"], []).append(_row_to_illustration(row))

    tree: list[dict[str, Any]] = []
    for artist in artists:
        tree.append({**artist, "illustrations": buckets.get(artist["id"], [])})

    orphans = buckets.get(None, [])
    if orphans:
        # The bucket always stays separate: it maps to the `unassigned` filter,
        # so it must never be folded into a real artist that happens to be
        # called 未分类 - otherwise the shown count and the filter disagree.
        taken = {entry["name"] for entry in tree}
        label = UNASSIGNED_LABEL
        if label in taken:
            label = f"{label}（无画师）"
        tree.append(
            {
                "id": None,
                "name": label,
                "count": len(orphans),
                "created_at": None,
                "synthetic": True,
                "illustrations": orphans,
            }
        )
    return tree
