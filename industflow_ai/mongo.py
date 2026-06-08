"""Cached Mongo handle shared across the AI layer.

`industflow_starter.db.get_db` opens a fresh MongoClient per call; for a
long-running API/scheduler we want one pooled client. This wraps it.
"""
from __future__ import annotations

from functools import lru_cache

from pymongo.database import Database

from industflow_starter.db import get_db as _get_db

from .config import MONGO_URI


@lru_cache(maxsize=1)
def get_db() -> Database:
    """Return a process-wide cached Database handle."""
    return _get_db(MONGO_URI)
