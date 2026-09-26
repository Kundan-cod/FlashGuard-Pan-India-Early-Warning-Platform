"""
Track A portable database access layer (SQLite, stdlib only).

This is the DAL "seam" described in docs/architecture.md. Everything above it
(features, models, risk, API) calls these repository functions and does not
know whether the backing store is SQLite (Track A) or PostGIS (Track B). The
Track B implementation exposes the same function names over SQLAlchemy.

No secrets here. Path comes from PORTABLE_DB_PATH env or defaults under data/.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Sequence

# Repo root = four levels up from this file: backend/app/database/db.py
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DB = _REPO_ROOT / "data" / "portable" / "flashflood.sqlite"
_SCHEMA = Path(__file__).resolve().parent / "schema_sqlite.sql"

_local = threading.local()


def db_path() -> Path:
    p = os.environ.get("PORTABLE_DB_PATH")
    return Path(p) if p else _DEFAULT_DB


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_conn() -> sqlite3.Connection:
    """One connection per thread (http.server is threaded)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


@contextmanager
def transaction():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db(reset: bool = False) -> None:
    """Create schema. If reset, drop the file first (used by tests/seed)."""
    path = db_path()
    if reset and path.exists():
        # close any thread-local handle before unlinking
        conn = getattr(_local, "conn", None)
        if conn is not None:
            conn.close()
            _local.conn = None
        import gc
        gc.collect()
        try:
            path.unlink()
        except PermissionError:
            conn = get_conn()
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            for t in tables:
                conn.execute(f'DROP TABLE IF EXISTS "{t[0]}"')
            conn.commit()
    conn = get_conn()
    with open(_SCHEMA, "r", encoding="utf-8") as fh:
        conn.executescript(fh.read())
    conn.commit()


# --------------------------------------------------------------------------
# Low-level helpers
# --------------------------------------------------------------------------
def query(sql: str, params: Sequence[Any] = ()) -> list[dict]:
    cur = get_conn().execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: Sequence[Any] = ()) -> dict | None:
    cur = get_conn().execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    with transaction() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def executemany(sql: str, seq: Iterable[Sequence[Any]]) -> int:
    with transaction() as conn:
        cur = conn.executemany(sql, list(seq))
        return cur.rowcount


# --------------------------------------------------------------------------
# JSON geometry helpers (Track A stores GeoJSON text; Track B uses PostGIS)
# --------------------------------------------------------------------------
def dump_geojson(geom: dict | None) -> str | None:
    return json.dumps(geom) if geom is not None else None


def load_geojson(text: str | None) -> dict | None:
    return json.loads(text) if text else None
