"""End-to-end tests for the Pixort API.

Run with:  python -m unittest discover -s backend/tests -v

The suite boots a real HTTP server on an ephemeral port against a throwaway
data root, so nothing in the user's library is touched.
"""

from __future__ import annotations

import base64
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pixort_api import settings  # noqa: E402
from pixort_api.app import Application  # noqa: E402
from pixort_api.server import create_server  # noqa: E402

# 1x1 transparent PNG - small enough to inline, valid enough for Pillow.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="pixort-test-"))
        settings.DATA_ROOT = cls.tmp
        settings.DB_PATH = cls.tmp / "library.db"
        settings.ILLUSTRATIONS_DIR = cls.tmp / "illustrations"
        settings.ARCHIVE_DIR = cls.tmp / "archive_illustrations"
        settings.CACHE_DIR = cls.tmp / ".cache"
        settings.THUMBNAIL_DIR = settings.CACHE_DIR / "thumbnails"
        settings.TEMP_DIR = settings.CACHE_DIR / "tmp"

        cls.app = Application()
        cls.server = create_server("127.0.0.1", 0, application=cls.app, quiet=True)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        import shutil

        shutil.rmtree(cls.tmp, ignore_errors=True)

    # -- helpers ----------------------------------------------------------- #
    def request(self, method, path, body=None, headers=None, expect=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        payload = response.read()
        status = response.status
        conn.close()
        if expect is not None:
            self.assertEqual(
                status,
                expect,
                msg=f"{method} {path} -> {status}: {payload[:400]!r}",
            )
        return status, response.getheaders(), payload

    def json_request(self, method, path, payload=None, expect=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        status, _, raw = self.request(method, path, body, headers, expect=expect)
        return status, json.loads(raw.decode("utf-8")) if raw else None

    def upload(self, filename, data=PNG_BYTES, **fields):
        boundary = "----pixorttestboundary"
        chunks: list[bytes] = []
        for key, value in fields.items():
            chunks.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
            )
        chunks.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
                f'filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'
            ).encode()
            + data
            + b"\r\n"
        )
        chunks.append(f"--{boundary}--\r\n".encode())
        body = b"".join(chunks)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        }
        status, _, raw = self.request("POST", "/api/illustrations/upload", body, headers)
        return status, json.loads(raw.decode("utf-8"))

    def get(self, path, expect=200):
        return self.json_request("GET", path, expect=expect)

    # -- tests ------------------------------------------------------------- #
    def test_01_health(self):
        status, payload = self.json_request("GET", "/api/health", expect=200)
        self.assertEqual(payload["status"], "ok")

    def test_02_artist_lifecycle_is_idempotent(self):
        _, first = self.json_request("POST", "/api/artists", {"name": "mechari"}, expect=201)
        _, second = self.json_request("POST", "/api/artists", {"name": "mechari"}, expect=201)
        self.assertEqual(first["id"], second["id"], "重复创建应返回同一条记录")

        _, listing = self.json_request("GET", "/api/artists", expect=200)
        self.assertEqual(len(listing["items"]), 1)
        self.assertEqual(listing["items"][0]["count"], 0)

    def test_03_reject_blank_names(self):
        self.json_request("POST", "/api/artists", {"name": "   "}, expect=400)
        self.json_request("POST", "/api/characters", {}, expect=400)

    def test_04_upload_and_deduplicate(self):
        status, payload = self.upload("artwork.png", artist="mechari", tags="科幻, 机械", rating="4")
        self.assertEqual(status, 201, payload)
        self.assertEqual(payload["imported"], 1)
        item = payload["illustrations"][0]
        self.assertEqual(item["artist_name"], "mechari")
        self.assertEqual(item["tags"], ["科幻", "机械"])
        self.assertEqual(item["rating"], 4)
        self.assertTrue(item["file_exists"])
        stored = settings.ILLUSTRATIONS_DIR / "mechari"
        self.assertTrue(any(stored.iterdir()))

        _, again = self.upload("artwork-copy.png", artist="mechari")
        self.assertEqual(again["skipped"], 1, "相同内容不应重复入库")

    def test_05_local_folder_import_infers_artist(self):
        source = self.tmp / "incoming" / "Wistariaiai"
        source.mkdir(parents=True, exist_ok=True)
        (source / "p0.png").write_bytes(PNG_BYTES + b"\x00")

        _, preview = self.json_request(
            "POST", "/api/illustrations/scan-local", {"paths": [str(self.tmp / "incoming")]}, expect=200
        )
        self.assertEqual(preview["total"], 1)

        _, payload = self.json_request(
            "POST", "/api/illustrations/import-local", {"paths": [str(self.tmp / "incoming")]}, expect=201
        )
        self.assertEqual(payload["imported"], 1)
        self.assertEqual(payload["illustrations"][0]["artist_name"], "Wistariaiai")

    def test_06_filters_search_and_sort(self):
        _, listing = self.json_request("GET", "/api/illustrations", expect=200)
        self.assertGreaterEqual(listing["total"], 2)

        _, by_tag = self.get(f"/api/illustrations?tag={quote('科幻')}")
        self.assertEqual(by_tag["total"], 1)

        _, search = self.get("/api/illustrations?q=mechari")
        self.assertEqual(search["total"], 1, "搜索应按画师名匹配")

        _, wildcard = self.get("/api/illustrations?q=%25")
        self.assertEqual(wildcard["total"], 0, "% 应当被转义而不是当作通配符")

        self.get(f"/api/illustrations?sort={quote('不存在的排序')}", expect=400)

        _, page = self.get("/api/illustrations?limit=1&offset=0")
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["limit"], 1)

    def test_07_update_bulk_and_delete(self):
        _, listing = self.get("/api/illustrations?q=p0")
        target = listing["items"][0]

        _, updated = self.json_request(
            "PATCH",
            f"/api/illustrations/{target['id']}",
            {"title": "改写标题", "rating": 5, "tags": "科幻, 新标签"},
            expect=200,
        )
        self.assertEqual(updated["title"], "改写标题")
        self.assertEqual(updated["rating"], 5)
        self.assertIn("新标签", updated["tags"])

        _, bulk = self.json_request(
            "POST",
            "/api/illustrations/bulk-update",
            {"ids": [target["id"]], "rating": 2, "tags_add": ["批量"]},
            expect=200,
        )
        self.assertEqual(bulk["updated"], 1)
        self.assertEqual(bulk["items"][0]["rating"], 2)
        self.assertIn("批量", bulk["items"][0]["tags"])

        self.json_request("POST", "/api/illustrations/bulk-update", {"ids": []}, expect=400)
        self.json_request("PATCH", "/api/illustrations/999999", {"title": "x"}, expect=404)

    def test_08_media_endpoints(self):
        _, listing = self.json_request("GET", "/api/illustrations", expect=200)
        item = listing["items"][0]

        status, headers, body = self.request("GET", item["thumbnail_url"], expect=200)
        self.assertTrue(body)
        etag = dict((k.lower(), v) for k, v in headers)["etag"]

        status, _, cached = self.request(
            "GET", item["thumbnail_url"], headers={"If-None-Match": etag}
        )
        self.assertEqual(status, 304)
        self.assertEqual(cached, b"")

        status, headers, _ = self.request("GET", item["download_url"], expect=200)
        self.assertIn("attachment", dict((k.lower(), v) for k, v in headers)["content-disposition"])

    def test_09_tree_tags_and_stats(self):
        _, tree = self.json_request("GET", "/api/tree", expect=200)
        groups = {artist["name"]: artist for artist in tree["artists"]}
        self.assertIn("mechari", groups)
        self.assertIn("Wistariaiai", groups)
        mechari = groups["mechari"]
        self.assertEqual(len(mechari["illustrations"]), mechari["count"])

        _, tags = self.json_request("GET", "/api/tags", expect=200)
        self.assertTrue(any(entry["tag"] == "科幻" for entry in tags["items"]))

        _, stats = self.json_request("GET", "/api/stats", expect=200)
        _, artists = self.get("/api/artists")
        self.assertGreaterEqual(stats["illustrations"], 2)
        self.assertEqual(stats["artists"], len(artists["items"]))
        for artist in artists["items"]:
            self.assertIn(artist["name"], groups, "树形索引应包含所有画师")

    def test_10_settings_round_trip(self):
        self.json_request("PUT", "/api/settings", {"items": {"theme": "dark"}}, expect=200)
        _, payload = self.json_request("GET", "/api/settings", expect=200)
        self.assertEqual(payload["items"]["theme"], "dark")
        self.assertNotIn("schema_version", payload["items"])

    def test_11_backup_round_trip(self):
        status, headers, archive = self.request("GET", "/api/transfer/export", expect=200)
        self.assertTrue(archive.startswith(b"PK"))

        backup_file = self.tmp / "backup.zip"
        backup_file.write_bytes(archive)

        _, info = self.json_request(
            "POST", f"/api/transfer/inspect?path={backup_file}", expect=200
        )
        self.assertTrue(info["valid"], info)

        _, pending = self.json_request(
            "POST", f"/api/transfer/restore?path={backup_file}", expect=202
        )
        self.assertTrue(pending["requires_confirmation"])

        _, result = self.json_request(
            "POST", f"/api/transfer/restore?path={backup_file}&confirm=1", expect=200
        )
        self.assertGreaterEqual(result["images"], 1)

        _, listing = self.json_request("GET", "/api/illustrations", expect=200)
        self.assertGreaterEqual(listing["total"], 2, "恢复后数据应可用")

    def test_12_delete_artist_archives_files(self):
        _, listing = self.get("/api/illustrations?artist_name=mechari")
        item = listing["items"][0]
        _, result = self.json_request("DELETE", f"/api/illustrations/{item['id']}", expect=200)
        self.assertEqual(result["file_action"]["mode"], "archived")
        self.assertTrue(Path(result["file_action"]["moved_to"]).is_file())

    def test_13_missing_and_invalid_requests(self):
        self.json_request("GET", "/api/does-not-exist", expect=404)
        self.json_request("DELETE", "/api/illustrations/987654", expect=404)
        status, _, _ = self.request("POST", "/api/artists", b"{not json", {"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.get("/api/illustrations?artist_id=abc", expect=400)

    def test_14_static_shell_and_traversal(self):
        status, _, body = self.request("GET", "/../backend/run.py")
        self.assertEqual(status, 404)
        self.assertNotIn(b"pixort_api", body)

    def test_15_unassigned_works_get_a_synthetic_group(self):
        status, payload = self.upload(
            "orphan.png", data=PNG_BYTES + b"\x01\x02", artist_mode="none"
        )
        self.assertEqual(status, 201, payload)
        item = payload["illustrations"][0]
        self.assertIsNone(item["artist_id"])
        self.assertEqual(item["artist_name"], None)

        _, listing = self.get("/api/illustrations?unassigned=1")
        self.assertEqual(listing["total"], 1)

        _, tree = self.json_request("GET", "/api/tree", expect=200)
        bucket = next(artist for artist in tree["artists"] if artist["id"] is None)
        self.assertEqual(bucket["name"], "未分类")
        self.assertEqual(bucket["count"], 1)

        # rules out the NULL-comparison bug that pinned unassigned works to 0
        self.assertGreater(item["sort_order"], 0)

    def test_16_maintenance_relinks_renamed_files(self):
        status, payload = self.upload(
            "renamed.png", data=PNG_BYTES + b"\x09\x09", artist="mechari"
        )
        self.assertEqual(status, 201, payload)
        item = payload["illustrations"][0]
        original = Path(settings.DATA_ROOT) / item["file_path"]
        self.assertTrue(original.is_file())

        # simulate a re-import that renamed the same picture
        moved = original.with_name(f"20990101000000999999_{original.name.split('_', 1)[1]}")
        original.rename(moved)

        _, before = self.json_request(
            "GET", "/api/illustrations", expect=200
        )
        target = next(entry for entry in before["items"] if entry["id"] == item["id"])
        self.assertFalse(target["file_exists"])

        _, preview = self.json_request(
            "POST", "/api/library/maintenance", {"dry_run": True}, expect=200
        )
        self.assertTrue(any(entry["id"] == item["id"] for entry in preview["relinked"]))
        self.assertFalse(Path(settings.DATA_ROOT) / preview["relinked"][0]["to"] == original)

        _, applied = self.json_request(
            "POST", "/api/library/maintenance", {"dry_run": False}, expect=200
        )
        self.assertTrue(applied["applied"]["relinked"] >= 1)

        _, after = self.get(f"/api/illustrations/{item['id']}")
        self.assertTrue(after["file_exists"], "重命名后的文件应被重新关联")
        self.assertTrue(after["width"], "维护应补全图片尺寸")

    def test_17_tag_filter_and_reference_guards(self):
        _, listing = self.get("/api/illustrations?q=renamed")
        target = listing["items"][0]
        self.json_request(
            "PATCH",
            f"/api/illustrations/{target['id']}",
            {"tags": ["第一个", "第二个"]},
            expect=200,
        )

        # every tag must be findable, not just the first one in the column
        for tag in ("第一个", "第二个"):
            _, filtered = self.get(f"/api/illustrations?tag={quote(tag)}")
            self.assertEqual(filtered["total"], 1, f"标签「{tag}」应当能被筛出")

        _, wildcard = self.get("/api/illustrations?tag=%25")
        self.assertEqual(wildcard["total"], 0, "标签里的 % 应被转义")

        # a bad reference is a client error, never a 500 from SQLite
        self.json_request(
            "PATCH", f"/api/illustrations/{target['id']}", {"artist_id": 999999}, expect=404
        )
        self.json_request(
            "PATCH", f"/api/illustrations/{target['id']}", {"artist_id": "abc"}, expect=400
        )
        _, failure = self.json_request(
            "POST",
            "/api/illustrations",
            {"file_path": target["file_path"], "artist_id": 999999},
            expect=404,
        )
        self.assertIn("不存在", failure["error"]["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
