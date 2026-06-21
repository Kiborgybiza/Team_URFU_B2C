from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_engine = None
_SessionLocal = None


class Base(DeclarativeBase):
    pass


def _get_session_factory():
    global _engine, _SessionLocal
    if _engine is None:
        url = os.getenv("B2C_DATABASE_URL", "sqlite:///./b2c.db")
        kwargs: dict = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
        Base.metadata.create_all(_engine)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _SessionLocal


def get_db():
    Session = _get_session_factory()
    db = Session()
    try:
        yield db
    finally:
        db.close()
