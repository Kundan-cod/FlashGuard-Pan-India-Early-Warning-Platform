"""
Shared test helpers (master prompt section 66 — prove it runs).

Every test module points PORTABLE_DB_PATH at an isolated temp SQLite file BEFORE
importing app.database.db, so the test run never touches the demo database under
data/portable/. utcnow-free deterministic timestamps keep assertions stable.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def use_temp_db() -> str:
    """Create a unique temp DB path and export it. Call at import time in each
    test module (before importing app.database.db) via bootstrap()."""
    fd, path = tempfile.mkstemp(prefix="flashguard_test_", suffix=".sqlite")
    os.close(fd)
    os.unlink(path)  # let init_db create it fresh
    os.environ["PORTABLE_DB_PATH"] = path
    return path


def bootstrap() -> str:
    """Ensure backend/ is importable and an isolated temp DB is configured.
    Returns the temp DB path. Idempotent within a process."""
    import sys
    backend = Path(__file__).resolve().parents[1]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    if not os.environ.get("PORTABLE_DB_PATH", "").startswith(tempfile.gettempdir()):
        return use_temp_db()
    return os.environ["PORTABLE_DB_PATH"]
