"""
Track B SQLAlchemy engine/session factory (pending local run).

Kept tiny and lazy so importing it never fails in the portable sandbox where
SQLAlchemy isn't installed — the heavy import only happens when get_engine()
is actually called under Track B.
"""
from __future__ import annotations

from functools import lru_cache

from app.config.settings import get_settings


@lru_cache
def get_engine():
    from sqlalchemy import create_engine
    s = get_settings()
    return create_engine(s.database_url, pool_pre_ping=True, future=True)


@lru_cache
def get_sessionmaker():
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False,
                        future=True)


def get_session():
    """FastAPI dependency: yields a session, always closes it."""
    Session = get_sessionmaker()
    db = Session()
    try:
        yield db
    finally:
        db.close()
