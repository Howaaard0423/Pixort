"""Runtime configuration for the Pixort API server.

Every path derives from a single *data root* so that the HTTP backend and the
legacy desktop client operate on the same SQLite file and the same illustration
folders.  Override with environment variables:

    PIXORT_DATA_ROOT      base directory holding the database + illustrations
    PIXORT_DB             explicit path to the SQLite database
    PIXORT_ILLUSTRATIONS  explicit path to the illustration folder
    PIXORT_HOST/PORT      bind address of the API server
    PIXORT_CORS_ORIGIN    allowed origin when the front end is hosted elsewhere

When the code runs from the packaged ``Pixort.exe`` the same rules apply, only
the defaults move: resources such as ``frontend/`` come from inside the bundle,
while the database, the images and the cache sit next to the executable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_VERSION = "2.0.0"

#: True when running from the PyInstaller bundle (``dist/Pixort.exe``).
FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    # A one-file build unpacks its resources into a temporary folder ...
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # ... while the library the user manages belongs next to the executable.
    APP_DIR = Path(sys.executable).resolve().parent
else:
    BACKEND_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = BACKEND_DIR.parent
    APP_DIR = BUNDLE_DIR


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    if not raw:
        return default
    return Path(raw).expanduser().resolve()


DATA_ROOT = _env_path("PIXORT_DATA_ROOT", APP_DIR)
DB_PATH = _env_path("PIXORT_DB", DATA_ROOT / "illustration_manager.db")
ILLUSTRATIONS_DIR = _env_path("PIXORT_ILLUSTRATIONS", DATA_ROOT / "illustrations")
ARCHIVE_DIR = _env_path("PIXORT_ARCHIVE", DATA_ROOT / "archive_illustrations")

FRONTEND_DIR = _env_path("PIXORT_FRONTEND", BUNDLE_DIR / "frontend")
CACHE_DIR = _env_path("PIXORT_CACHE", APP_DIR / ".cache")
THUMBNAIL_DIR = CACHE_DIR / "thumbnails"
TEMP_DIR = CACHE_DIR / "tmp"

HOST = os.environ.get("PIXORT_HOST", "127.0.0.1")
PORT = int(os.environ.get("PIXORT_PORT", "8000"))
CORS_ORIGIN = os.environ.get("PIXORT_CORS_ORIGIN", "*")

# A database row can point anywhere on disk, so files outside the illustration
# folder are refused unless this is switched on explicitly.
ALLOW_EXTERNAL_FILES = _env_bool("PIXORT_ALLOW_EXTERNAL_FILES", False)

MAX_UPLOAD_BYTES = int(os.environ.get("PIXORT_MAX_UPLOAD_MB", "512")) * 1024 * 1024
MAX_BODY_BYTES = MAX_UPLOAD_BYTES + 8 * 1024 * 1024

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".avif", ".tif", ".tiff"}

# Separators accepted inside the free-form ``tags`` column.
TAG_SPLIT_CHARS = ",，、;；"


def ensure_directories() -> None:
    """Create the writable folders the API expects to exist."""
    for folder in (DATA_ROOT, ILLUSTRATIONS_DIR, CACHE_DIR, THUMBNAIL_DIR, TEMP_DIR):
        folder.mkdir(parents=True, exist_ok=True)
