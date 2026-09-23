"""Library-wide endpoints: health, statistics, tree index, tags and settings."""

from __future__ import annotations

import json
import platform
import shutil
from datetime import datetime

from .. import repository, settings
from ..db import Database
from ..http_kit import HttpError, Request, Response, Router, bad_request, json_response
from ..services import media as media_service
from ..services.media import PILLOW_AVAILABLE
from ..services.maintenance import scan_library
from ._helpers import decorate_many


def register(router: Router, database: Database) -> None:
    def health(_request: Request) -> Response:
        return json_response(
            {
                "status": "ok",
                "version": settings.PACKAGE_VERSION,
                "time": datetime.now().isoformat(timespec="seconds"),
                "python": platform.python_version(),
                "thumbnailer": "pillow" if PILLOW_AVAILABLE else "none",
                "data_root": str(settings.DATA_ROOT),
            }
        )

    def stats(_request: Request) -> Response:
        with database.connection() as conn:
            payload = repository.statistics(conn)
            rows = conn.execute("SELECT id, file_path FROM illustrations").fetchall()
        missing = 0
        for row in rows:
            try:
                if not media_service.resolve_illustration_path(row["file_path"]).is_file():
                    missing += 1
            except HttpError:
                missing += 1
        payload["missing_files"] = missing
        try:
            usage = shutil.disk_usage(settings.DATA_ROOT)
            payload["disk"] = {"total": usage.total, "used": usage.used, "free": usage.free}
        except OSError:
            payload["disk"] = None
        return json_response(payload)

    def tree(_request: Request) -> Response:
        with database.connection() as conn:
            artists = repository.artist_tree(conn)
        for artist in artists:
            artist["illustrations"] = decorate_many(artist["illustrations"])
        return json_response({"artists": artists})

    def tags(_request: Request) -> Response:
        with database.connection() as conn:
            return json_response({"items": repository.list_tags(conn)})

    def read_settings(_request: Request) -> Response:
        with database.connection() as conn:
            rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        payload = {}
        for row in rows:
            try:
                payload[row["key"]] = json.loads(row["value"])
            except (TypeError, json.JSONDecodeError):
                payload[row["key"]] = row["value"]
        payload.pop("schema_version", None)
        return json_response({"items": payload})

    def write_settings(request: Request) -> Response:
        payload = request.json()
        items = payload.get("items", payload)
        if not isinstance(items, dict) or not items:
            raise bad_request("items 必须是非空对象")
        with database.transaction() as conn:
            for key, value in items.items():
                if key == "schema_version":
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                    (str(key), json.dumps(value, ensure_ascii=False)),
                )
        return json_response({"saved": sorted(key for key in items if key != "schema_version")})

    def formats(_request: Request) -> Response:
        return json_response({"extensions": sorted(settings.IMAGE_EXTS)})

    def maintenance(request: Request) -> Response:
        """Reconcile the database with what is actually on disk."""
        payload = request.json() if request.body else {}
        report = scan_library(
            database,
            repair=bool(payload.get("repair", True)),
            refresh_metadata=bool(payload.get("refresh_metadata", True)),
            dedupe=bool(payload.get("dedupe", False)),
            dry_run=bool(payload.get("dry_run", True)),
        )
        return json_response(report)

    router.get("/api/health", health)
    router.get("/api/stats", stats)
    router.get("/api/tree", tree)
    router.get("/api/tags", tags)
    router.get("/api/formats", formats)
    router.post("/api/library/maintenance", maintenance)
    router.get("/api/settings", read_settings)
    router.put("/api/settings", write_settings)
