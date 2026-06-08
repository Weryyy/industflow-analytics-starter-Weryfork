"""Make Mongo/BSON results JSON-serializable for LLMs and HTTP responses."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import DBRef, ObjectId


def jsonable(obj: Any) -> Any:
    """Recursively convert BSON types (ObjectId, datetime, DBRef) to plain JSON."""
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, DBRef):
        return {"$ref": obj.collection, "$id": str(obj.id)}
    return obj
