"""HTTP route registration."""

from __future__ import annotations

from ..db import Database
from ..http_kit import Router
from . import artists, characters, illustrations, library, media, transfer


def register_all(router: Router, database: Database) -> None:
    """Attach every route group to ``router``."""
    for module in (library, artists, characters, illustrations, media, transfer):
        module.register(router, database)
