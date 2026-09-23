#!/usr/bin/env python3
"""Start the Pixort backend.

    python backend/run.py --open
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pixort_api.cli import main  # noqa: E402  (path set up above)

if __name__ == "__main__":
    argv = sys.argv[1:]
    if getattr(sys, "frozen", False) and not argv:
        # a double-clicked Pixort.exe should open the interface by itself
        argv = ["--open"]
    sys.exit(main(argv))
