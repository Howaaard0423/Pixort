"""Backup export and restore.

Differences from the desktop implementation:

* archives are streamed straight to the destination instead of staging a full
  copy in the system temp folder (which doubled the disk footprint),
* images are stored without deflate - they are already compressed, so the
  attempt only costs CPU time,
* archive members are validated before extraction (no zip-slip, no escalation
  outside the data root),
* a failed restore rolls the previous library back into place.
"""

from __future__ import annotations

import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .. import settings
from ..http_kit import HttpError, bad_request

try:  # AES-encrypted archives when pyzipper is present
    import pyzipper

    AES_AVAILABLE = True
except Exception:  # pragma: no cover
    pyzipper = None  # type: ignore[assignment]
    AES_AVAILABLE = False

Progress = Callable[[int, str], None]
_MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024 * 1024
_MAX_MEMBERS = 200_000

STORE_EXTENSIONS = set(settings.IMAGE_EXTS)


def _zip_module(password: str | None):
    if password and AES_AVAILABLE:
        return pyzipper
    if password and not AES_AVAILABLE:
        raise HttpError(501, "未安装 pyzipper，无法创建加密备份")
    return zipfile


def _notify(progress: Progress | None, percent: int, message: str) -> None:
    if progress is not None:
        progress(percent, message)


def build_backup(
    destination: Path,
    *,
    password: str | None = None,
    include_images: bool = True,
    progress: Progress | None = None,
) -> dict:
    """Write a restorable archive of the database (and optionally the images)."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    entries: list[tuple[Path, str]] = []
    if settings.DB_PATH.is_file():
        entries.append((settings.DB_PATH, settings.DB_PATH.name))
    if include_images and settings.ILLUSTRATIONS_DIR.is_dir():
        for path in settings.ILLUSTRATIONS_DIR.rglob("*"):
            if path.is_file():
                entries.append(
                    (path, f"{settings.ILLUSTRATIONS_DIR.name}/{path.relative_to(settings.ILLUSTRATIONS_DIR).as_posix()}")
                )
    if not entries:
        raise HttpError(400, "没有可备份的数据")

    module = _zip_module(password)
    total = len(entries)
    written = 0
    total_bytes = 0

    _notify(progress, 1, f"准备备份 {total} 个文件")
    kwargs: dict[str, object] = {"compression": module.ZIP_STORED}
    if password:
        kwargs["encryption"] = module.WZ_AES

    with module.ZipFile(destination, "w", **kwargs) as archive:  # type: ignore[arg-type]
        if password:
            archive.setpassword(password.encode("utf-8"))
        for source, arcname in entries:
            info = module.ZipInfo(arcname)
            info.date_time = time.localtime(source.stat().st_mtime)[:6]
            info.compress_type = (
                module.ZIP_STORED if source.suffix.lower() in STORE_EXTENSIONS else module.ZIP_DEFLATED
            )
            try:
                with archive.open(info, "w") as target, open(source, "rb") as handle:
                    shutil.copyfileobj(handle, target, 1024 * 1024)
            except PermissionError as exc:
                raise HttpError(423, f"文件被占用，无法备份：{source.name}") from exc
            written += 1
            total_bytes += info.file_size
            if written % 25 == 0 or written == total:
                _notify(progress, min(99, int(written * 100 / total)), f"已写入 {written}/{total} 个文件")
        archive.comment = (
            f"Pixort backup {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".encode("utf-8")
        )

    _notify(progress, 100, "备份完成")
    return {
        "path": str(destination),
        "files": total,
        "uncompressed_bytes": total_bytes,
        "archive_bytes": destination.stat().st_size if destination.is_file() else 0,
        "encrypted": bool(password),
    }


def _safe_members(archive: zipfile.ZipFile) -> Iterable[zipfile.ZipInfo]:
    """Yield members that stay inside the extraction folder."""
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ".." in Path(name).parts:
            raise bad_request(f"备份文件包含非法路径：{info.filename}")
        yield info


def inspect_backup(archive_path: Path, password: str | None = None) -> dict:
    """Describe an archive without extracting anything."""
    module = _zip_module(password)
    try:
        with module.ZipFile(archive_path, "r") as archive:  # type: ignore[arg-type]
            if password:
                archive.setpassword(password.encode("utf-8"))
            infos = list(_safe_members(archive))
            names = [info.filename for info in infos]
            comment = (archive.comment or b"").decode("utf-8", errors="replace")
    except RuntimeError as exc:
        raise HttpError(400, "密码错误或压缩包已损坏") from exc
    except zipfile.BadZipFile as exc:
        raise HttpError(400, "ZIP 文件损坏") from exc

    databases = [name for name in names if name.lower().endswith(".db") and "/" not in name]
    image_roots = {
        name.split("/", 1)[0]
        for name in names
        if "/" in name and name.split("/", 1)[0] in ("illustrations", "uploads")
    }
    return {
        "members": len(names),
        "databases": databases,
        "image_roots": sorted(image_roots),
        "uncompressed_bytes": sum(info.file_size for info in infos),
        "comment": comment,
        "valid": bool(databases) and bool(image_roots),
    }


def restore_backup(
    archive_path: Path,
    *,
    password: str | None = None,
    progress: Progress | None = None,
) -> dict:
    """Replace the current library with the contents of ``archive_path``."""
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise HttpError(404, "备份文件不存在")

    settings.ensure_directories()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    staging = settings.TEMP_DIR / f"restore_{stamp}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)

    module = _zip_module(password)
    _notify(progress, 5, "正在校验备份文件")
    try:
        with module.ZipFile(archive_path, "r") as archive:  # type: ignore[arg-type]
            if password:
                archive.setpassword(password.encode("utf-8"))
            members = list(_safe_members(archive))
            if len(members) > _MAX_MEMBERS:
                raise bad_request("备份文件包含过多条目，已拒绝解压")
            if sum(info.file_size for info in members) > _MAX_UNCOMPRESSED_BYTES:
                raise bad_request("备份文件解压后体积过大，已拒绝解压")

            _notify(progress, 10, "正在解压")
            for index, info in enumerate(members, start=1):
                target = staging / info.filename.replace("\\", "/")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, open(target, "wb") as handle:
                    shutil.copyfileobj(source, handle, 1024 * 1024)
                if index % 50 == 0:
                    _notify(progress, min(60, 10 + int(index * 50 / len(members))), f"已解压 {index}/{len(members)}")
    except RuntimeError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise HttpError(400, "密码错误或压缩包已损坏") from exc
    except zipfile.BadZipFile as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise HttpError(400, "ZIP 文件损坏") from exc
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    databases = sorted(staging.glob("*.db"))
    if not databases:
        shutil.rmtree(staging, ignore_errors=True)
        raise bad_request("备份文件中缺少数据库文件")
    staged_db = databases[0]

    staged_images = staging / "illustrations"
    if not staged_images.is_dir():
        staged_images = staging / "uploads"
    if not staged_images.is_dir():
        shutil.rmtree(staging, ignore_errors=True)
        raise bad_request("备份文件中缺少图片目录")

    _notify(progress, 65, "正在替换数据")
    previous_db = settings.DB_PATH.with_suffix(settings.DB_PATH.suffix + f".bak-{stamp}")
    previous_images = settings.DATA_ROOT / f"illustrations_old_{stamp}"

    moved_db = False
    moved_images = False
    try:
        if settings.DB_PATH.exists():
            shutil.move(str(settings.DB_PATH), str(previous_db))
            moved_db = True
            for sidecar in ("-wal", "-shm"):
                Path(str(settings.DB_PATH) + sidecar).unlink(missing_ok=True)
        if settings.ILLUSTRATIONS_DIR.exists():
            shutil.move(str(settings.ILLUSTRATIONS_DIR), str(previous_images))
            moved_images = True

        shutil.copy2(staged_db, settings.DB_PATH)
        shutil.copytree(
            staged_images,
            settings.ILLUSTRATIONS_DIR,
            dirs_exist_ok=True,
            copy_function=shutil.copy2,
        )
    except Exception as exc:
        if moved_images and not settings.ILLUSTRATIONS_DIR.exists():
            shutil.move(str(previous_images), str(settings.ILLUSTRATIONS_DIR))
        if moved_db and not settings.DB_PATH.exists():
            shutil.move(str(previous_db), str(settings.DB_PATH))
        shutil.rmtree(staging, ignore_errors=True)
        raise HttpError(500, f"恢复失败，已还原原有数据：{exc}") from exc

    _notify(progress, 90, "正在清理")
    shutil.rmtree(staging, ignore_errors=True)
    image_count = sum(1 for path in settings.ILLUSTRATIONS_DIR.rglob("*") if path.is_file())
    _notify(progress, 100, "恢复完成")

    return {
        "database": settings.DB_PATH.name,
        "images": image_count,
        "previous_database": str(previous_db) if moved_db else None,
        "previous_images": str(previous_images) if moved_images else None,
        "images_restored": image_count,
    }
