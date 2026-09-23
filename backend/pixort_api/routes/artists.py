"""``/api/artists`` endpoints."""

from __future__ import annotations

from .. import repository
from ..db import Database, now_iso
from ..http_kit import (
    Request,
    Response,
    Router,
    bad_request,
    conflict,
    json_response,
)
from ._helpers import as_int, remove_folder_if_unreferenced


def register(router: Router, database: Database) -> None:
    def list_artists(_request: Request) -> Response:
        with database.connection() as conn:
            return json_response({"items": repository.list_artists(conn)})

    def create_artist(request: Request) -> Response:
        name = str(request.json().get("name", "")).strip()
        if not name:
            raise bad_request("画师名称不能为空")
        with database.transaction() as conn:
            artist = repository.create_artist(conn, name)
        return json_response(artist, status=201)

    def update_artist(request: Request) -> Response:
        artist_id = as_int(request.params["artist_id"], "artist_id")
        payload = request.json()
        if "name" not in payload:
            raise bad_request("缺少 name 字段")
        try:
            with database.transaction() as conn:
                artist = repository.rename_artist(conn, artist_id, str(payload["name"]))
        except ValueError as exc:
            raise conflict(str(exc)) from exc
        return json_response(artist)

    def delete_artist(request: Request) -> Response:
        artist_id = as_int(request.params["artist_id"], "artist_id")
        delete_files = request.q_bool("delete_files", True)
        with database.transaction() as conn:
            artist = repository.get_artist(conn, artist_id)
            detached = repository.delete_artist(conn, artist_id)
        removed = remove_folder_if_unreferenced(database, artist["name"]) if delete_files else 0
        return json_response(
            {
                "deleted": artist,
                "detached_works": detached,
                "files_removed": removed,
                "folder_kept": bool(delete_files and removed == 0 and detached == 0),
            }
        )

    def merge_artist(request: Request) -> Response:
        """Move every work from one artist onto another, then drop the source."""
        payload = request.json()
        source_id = as_int(payload.get("source_id"), "source_id")
        target_id = as_int(payload.get("target_id"), "target_id")
        if source_id == target_id:
            raise bad_request("源画师与目标画师不能相同")
        with database.transaction() as conn:
            repository.get_artist(conn, source_id)
            repository.get_artist(conn, target_id)
            conn.execute(
                "UPDATE illustrations SET artist_id = ?, updated_at = ? WHERE artist_id = ?",
                (target_id, now_iso(), source_id),
            )
            conn.execute("DELETE FROM artists WHERE id = ?", (source_id,))
            target = repository.get_artist(conn, target_id)
        return json_response({"merged_into": target})

    router.get("/api/artists", list_artists)
    router.post("/api/artists", create_artist)
    router.patch("/api/artists/{artist_id}", update_artist)
    router.delete("/api/artists/{artist_id}", delete_artist)
    router.post("/api/artists/merge", merge_artist)
