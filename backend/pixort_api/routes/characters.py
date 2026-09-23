"""``/api/characters`` endpoints."""

from __future__ import annotations

from .. import repository
from ..db import Database
from ..http_kit import Request, Response, Router, bad_request, conflict, json_response
from ._helpers import as_int


def register(router: Router, database: Database) -> None:
    def list_characters(_request: Request) -> Response:
        with database.connection() as conn:
            return json_response({"items": repository.list_characters(conn)})

    def create_character(request: Request) -> Response:
        name = str(request.json().get("name", "")).strip()
        if not name:
            raise bad_request("角色名称不能为空")
        with database.transaction() as conn:
            character = repository.create_character(conn, name)
        return json_response(character, status=201)

    def update_character(request: Request) -> Response:
        character_id = as_int(request.params["character_id"], "character_id")
        payload = request.json()
        if "name" not in payload:
            raise bad_request("缺少 name 字段")
        try:
            with database.transaction() as conn:
                character = repository.rename_character(conn, character_id, str(payload["name"]))
        except ValueError as exc:
            raise conflict(str(exc)) from exc
        return json_response(character)

    def delete_character(request: Request) -> Response:
        character_id = as_int(request.params["character_id"], "character_id")
        with database.transaction() as conn:
            character = repository.get_character(conn, character_id)
            detached = repository.delete_character(conn, character_id)
        return json_response({"deleted": character, "detached_works": detached})

    router.get("/api/characters", list_characters)
    router.post("/api/characters", create_character)
    router.patch("/api/characters/{character_id}", update_character)
    router.delete("/api/characters/{character_id}", delete_character)
