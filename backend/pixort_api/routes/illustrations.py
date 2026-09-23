"""``/api/illustrations`` endpoints, including upload and local folder import."""

from __future__ import annotations

import shutil
from pathlib import Path

from .. import repository, settings
from ..db import Database
from ..http_kit import (
    HttpError,
    Request,
    Response,
    Router,
    bad_request,
    empty_response,
    json_response,
    parse_multipart,
)
from ..services import importer, media
from ._helpers import as_int, decorate, decorate_many

MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 120


def _options_from(payload: dict) -> importer.ImportOptions:
    options = importer.ImportOptions(
        artist=str(payload.get("artist") or ""),
        character=str(payload.get("character") or ""),
        tags=repository.parse_tags(payload.get("tags")),
        rating=int(payload.get("rating") or 0),
        artist_mode=str(payload.get("artist_mode") or "auto"),
        skip_duplicates=bool(payload.get("skip_duplicates", True)),
    )
    options.validate()
    return options


def _summarise(results: list[dict]) -> dict:
    imported = [item for item in results if item["status"] == "imported"]
    skipped = [item for item in results if item["status"] == "skipped"]
    failed = [item for item in results if item["status"] == "failed"]
    return {
        "imported": len(imported),
        "skipped": len(skipped),
        "failed": len(failed),
        "results": results,
        "illustrations": decorate_many([item["illustration"] for item in imported]),
    }


def register(router: Router, database: Database) -> None:
    # ----------------------------------------------------------------- list #
    def list_illustrations(request: Request) -> Response:
        limit = request.q_int("limit", DEFAULT_PAGE_SIZE) or DEFAULT_PAGE_SIZE
        limit = max(1, min(MAX_PAGE_SIZE, limit))
        offset = max(0, request.q_int("offset", 0) or 0)
        sort = request.q("sort") or repository.DEFAULT_SORT
        if sort not in repository.available_sorts():
            raise bad_request(f"未知排序方式：{sort}")

        with database.connection() as conn:
            items, total = repository.list_illustrations(
                conn,
                sort=sort,
                limit=limit,
                offset=offset,
                artist_id=request.q_int("artist_id"),
                artist_name=request.q("artist_name") or None,
                character_id=request.q_int("character_id"),
                q=request.q("q"),
                tag=request.q("tag"),
                rating=request.q_int("rating"),
                rating_min=request.q_int("rating_min"),
                unassigned_artist=request.q_bool("unassigned"),
            )
        return json_response(
            {
                "items": decorate_many(items),
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + len(items) < total,
            }
        )

    def get_illustration(request: Request) -> Response:
        illustration_id = as_int(request.params["illustration_id"], "illustration_id")
        with database.connection() as conn:
            return json_response(decorate(repository.get_illustration(conn, illustration_id)))

    # --------------------------------------------------------------- create #
    def create_illustration(request: Request) -> Response:
        payload = request.json()
        file_path = str(payload.get("file_path") or "").strip()
        if not file_path:
            raise bad_request("缺少 file_path 字段")
        source = media.resolve_illustration_path(file_path)
        if not source.is_file():
            raise HttpError(404, "指定的文件不存在")

        size, width, height = media.probe_image(source)
        with database.transaction() as conn:
            illustration = repository.create_illustration(
                conn,
                file_path=file_path,
                artist_id=payload.get("artist_id"),
                character_id=payload.get("character_id"),
                title=str(payload.get("title") or source.stem),
                tags=payload.get("tags") or "",
                rating=int(payload.get("rating") or 0),
                remark=str(payload.get("remark") or ""),
                file_size=size,
                width=width,
                height=height,
                checksum=media.checksum_of(source),
            )
        return json_response(decorate(illustration), status=201)

    # --------------------------------------------------------------- update #
    def update_illustration(request: Request) -> Response:
        illustration_id = as_int(request.params["illustration_id"], "illustration_id")
        payload = request.json()
        changes = {key: payload[key] for key in repository.updatable_fields() if key in payload}
        if not changes:
            raise bad_request("没有可更新的字段")
        with database.transaction() as conn:
            illustration = repository.update_illustration(conn, illustration_id, changes)
        return json_response(decorate(illustration))

    def bulk_update(request: Request) -> Response:
        """Apply the same change (and optional tag additions) to many works."""
        payload = request.json()
        raw_ids = payload.get("ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise bad_request("ids 必须是非空数组")
        ids = [as_int(value, "id") for value in raw_ids]
        changes = {key: payload[key] for key in repository.updatable_fields() if key in payload}
        tags_add = repository.parse_tags(payload.get("tags_add"))
        tags_remove = set(repository.parse_tags(payload.get("tags_remove")))
        if not changes and not tags_add and not tags_remove:
            raise bad_request("没有可更新的字段")

        updated: list[dict] = []
        with database.transaction() as conn:
            for illustration_id in ids:
                item = repository.get_illustration(conn, illustration_id)
                row_changes = dict(changes)
                if tags_add or tags_remove:
                    tags = [tag for tag in item["tags"] if tag not in tags_remove]
                    row_changes["tags"] = tags + [tag for tag in tags_add if tag not in tags]
                updated.append(
                    decorate(repository.update_illustration(conn, illustration_id, row_changes))
                )
        return json_response({"updated": len(updated), "items": updated})

    # --------------------------------------------------------------- delete #
    def delete_illustration(request: Request) -> Response:
        illustration_id = as_int(request.params["illustration_id"], "illustration_id")
        mode = (request.q("file") or request.q("mode") or "archive").lower()
        if mode in ("1", "true", "yes"):
            mode = "archive"
        if mode in ("0", "false", "no"):
            mode = "keep"
        if mode not in {"archive", "delete", "keep"}:
            raise bad_request("file 只支持 archive、delete 或 keep")

        with database.transaction() as conn:
            item = repository.delete_illustration(conn, illustration_id)

        file_action = {"mode": mode, "path": item["file_path"], "moved_to": None}
        source = None
        try:
            source = media.resolve_illustration_path(item["file_path"])
        except HttpError:
            source = None

        if source is not None and source.is_file() and mode != "keep":
            if mode == "delete":
                source.unlink()
                file_action["mode"] = "deleted"
            else:
                destination = settings.ARCHIVE_DIR / source.parent.name / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    destination = destination.with_name(
                        f"{source.stem}_{repository.now_iso().replace(':', '')}{source.suffix}"
                    )
                shutil.move(str(source), str(destination))
                file_action["mode"] = "archived"
                file_action["moved_to"] = str(destination)
        elif mode != "keep":
            file_action["mode"] = "missing"

        return json_response({"deleted": decorate(item), "file_action": file_action})

    # --------------------------------------------------------------- upload #
    def upload(request: Request) -> Response:
        if "multipart/form-data" not in request.content_type:
            raise bad_request("上传接口需要 multipart/form-data 请求体")
        files, fields = parse_multipart(request.body, request.content_type)
        if not files:
            raise bad_request("没有收到任何文件")

        payload = {key: values[0] for key, values in fields.items() if values}
        options = _options_from(payload)
        relatives = fields.get("relative_path") or []

        results: list[dict] = []
        for index, part in enumerate(files):
            if part.name not in {"files", "file", "images"}:
                continue
            relative = relatives[index] if index < len(relatives) else ""
            filename = Path(part.filename.replace("\\", "/")).name
            if not media.is_supported_image(Path(filename)):
                results.append({"status": "failed", "filename": filename, "reason": "unsupported"})
                continue
            try:
                results.append(
                    importer.ingest_upload(
                        database,
                        data=part.data,
                        filename=filename,
                        relative_path=relative or None,
                        options=options,
                    )
                )
            except HttpError:
                raise
            except Exception as exc:  # keep one bad file from aborting the batch
                results.append({"status": "failed", "filename": filename, "reason": str(exc)})
        return json_response(_summarise(results), status=201)

    def import_local(request: Request) -> Response:
        """Import images that already live on the server's filesystem."""
        payload = request.json()
        raw_paths = payload.get("paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            raise bad_request("paths 必须是非空数组")
        recursive = bool(payload.get("recursive", True))
        options = _options_from(payload)

        results: list[dict] = []
        for raw in raw_paths:
            root = Path(str(raw)).expanduser()
            if not root.exists():
                results.append({"status": "failed", "filename": str(raw), "reason": "路径不存在"})
                continue
            if root.is_dir() and options.artist_mode == "auto":
                children = sorted(entry for entry in root.iterdir() if entry.is_dir())
                sources = (
                    [path for child in children for path in media.iter_image_files(child, recursive)]
                    if children
                    else media.iter_image_files(root, recursive)
                )
            else:
                sources = media.iter_image_files(root, recursive)
            base = root if root.is_dir() else root.parent
            for source in sources:
                try:
                    relative = str(source.relative_to(base)).replace("\\", "/")
                except ValueError:
                    relative = source.name
                try:
                    results.append(
                        importer.ingest_local_file(
                            database,
                            source=source,
                            relative_path=relative,
                            options=options,
                        )
                    )
                except Exception as exc:
                    results.append({"status": "failed", "filename": source.name, "reason": str(exc)})
        return json_response(_summarise(results), status=201)

    def scan_local(request: Request) -> Response:
        """Preview how many images a set of server paths would yield."""
        payload = request.json()
        raw_paths = payload.get("paths") or []
        if not isinstance(raw_paths, list):
            raise bad_request("paths 必须是数组")
        recursive = bool(payload.get("recursive", True))
        folders: list[dict] = []
        total = 0
        for raw in raw_paths:
            root = Path(str(raw)).expanduser()
            found = media.iter_image_files(root, recursive) if root.exists() else []
            total += len(found)
            folders.append(
                {
                    "path": str(root),
                    "exists": root.exists(),
                    "is_dir": root.is_dir(),
                    "count": len(found),
                }
            )
        return json_response({"total": total, "folders": folders})

    def options_probe(_request: Request) -> Response:
        return empty_response(204)

    router.get("/api/illustrations", list_illustrations)
    router.post("/api/illustrations", create_illustration)
    router.post("/api/illustrations/bulk-update", bulk_update)
    router.post("/api/illustrations/upload", upload)
    router.post("/api/illustrations/scan-local", scan_local)
    router.post("/api/illustrations/import-local", import_local)
    router.get("/api/illustrations/{illustration_id}", get_illustration)
    router.patch("/api/illustrations/{illustration_id}", update_illustration)
    router.delete("/api/illustrations/{illustration_id}", delete_illustration)
    router.add("OPTIONS", "/api/illustrations", options_probe)
