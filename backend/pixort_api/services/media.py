"""Image handling: path resolution, metadata probing and thumbnail caching.

Pillow is used when it is available; every function degrades gracefully so the
API still serves the library on a machine without it.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .. import settings
from ..http_kit import HttpError, guess_content_type

try:  # pragma: no cover - depends on the host environment
    from PIL import Image, ImageFile, ImageOps

    Image.MAX_IMAGE_PIXELS = 400_000_000
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    PILLOW_AVAILABLE = True
except Exception:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageFile = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]
    PILLOW_AVAILABLE = False

_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def content_type_for(path: Path) -> str:
    return _IMAGE_MIME.get(path.suffix.lower()) or guess_content_type(path)


def is_supported_image(path: Path) -> bool:
    return path.suffix.lower() in settings.IMAGE_EXTS


def resolve_illustration_path(file_path: str) -> Path:
    """Turn a stored path into a real one, refusing to leave the data root.

    Rows may hold either an absolute path or the relative
    ``illustrations/<artist>/<file>`` form written by the desktop client.
    """
    raw = (file_path or "").strip()
    if not raw:
        raise HttpError(404, "该作品没有记录文件路径")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = settings.DATA_ROOT / candidate
    candidate = candidate.resolve()

    if not settings.ALLOW_EXTERNAL_FILES:
        root = settings.ILLUSTRATIONS_DIR.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise HttpError(403, "文件位于插画目录之外，已拒绝访问") from exc
    return candidate


def checksum_of(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """SHA-256 of the file contents, used to detect re-imported duplicates."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def checksum_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _apply_orientation(image):
    if ImageOps is None:
        return image
    try:
        return ImageOps.exif_transpose(image) or image
    except Exception:
        return image


def probe_image(path: Path) -> tuple[int | None, int | None, int | None]:
    """Return ``(file_size, width, height)``; dimensions are None without Pillow."""
    try:
        size = path.stat().st_size
    except OSError:
        return None, None, None
    if not PILLOW_AVAILABLE:
        return size, None, None
    try:
        with Image.open(path) as image:  # type: ignore[union-attr]
            width, height = image.size
            orientation = 1
            try:
                orientation = image.getexif().get(0x0112, 1)
            except Exception:
                orientation = 1
        if orientation in (5, 6, 7, 8):
            width, height = height, width
        return size, int(width), int(height)
    except Exception:
        return size, None, None


def thumbnail_for(source: Path, cache_key: str, width: int) -> Path | None:
    """Return a cached, resized copy of ``source`` (None if it cannot be built).

    The cache file name embeds the source mtime and size, so an edited image
    invalidates its own thumbnail without any explicit purge step.
    """
    if not PILLOW_AVAILABLE or not source.is_file():
        return None
    try:
        stat = source.stat()
    except OSError:
        return None

    stem = f"{cache_key}_{width}_{stat.st_mtime_ns}_{stat.st_size}"
    target = settings.THUMBNAIL_DIR / f"{stem}.webp"
    if target.is_file() and target.stat().st_size > 0:
        return target

    settings.THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    scratch = settings.TEMP_DIR / f"{stem}.tmp"
    try:
        with Image.open(source) as image:  # type: ignore[union-attr]
            try:
                image.seek(0)  # first frame of an animated file
            except Exception:
                pass
            image = _apply_orientation(image)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.thumbnail((width, width * 3), Image.LANCZOS)  # type: ignore[union-attr]
            try:
                image.save(scratch, format="WEBP", quality=82, method=4)
            except Exception:
                scratch = scratch.with_suffix(".png")
                target = target.with_suffix(".png")
                image.save(scratch, format="PNG", optimize=True)
    except Exception:
        scratch.unlink(missing_ok=True)
        return None

    try:
        os.replace(scratch, target)
    except OSError:
        scratch.unlink(missing_ok=True)
        return target if target.is_file() else None
    return target


def iter_image_files(root: Path, recursive: bool = True) -> list[Path]:
    """Collect supported images below ``root`` in a stable order."""
    if root.is_file():
        return [root] if is_supported_image(root) else []
    if not root.is_dir():
        return []
    files: list[Path] = []
    if recursive:
        for current, directories, names in os.walk(root):
            directories[:] = sorted(d for d in directories if not d.startswith("."))
            for name in sorted(names):
                candidate = Path(current) / name
                if is_supported_image(candidate):
                    files.append(candidate)
    else:
        files = sorted(
            (entry for entry in root.iterdir() if entry.is_file() and is_supported_image(entry)),
            key=lambda p: p.name,
        )
    return files
