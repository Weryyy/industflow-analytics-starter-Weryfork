"""Append-only audit log in `ai.audit`.

The project brief requires all query generation and execution to be logged and
auditable. Every agent answer and every generated report writes one record here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..config import AGENT_MODEL, AUDIT_COLLECTION
from ..mongo import get_db
from ..serialize import jsonable


def record(kind: str, *, input: Any = None, tools_used: list | None = None,
           result_summary: Any = None, model: str = AGENT_MODEL,
           **extra) -> str:
    """Write one audit record. `kind` is e.g. 'qa' or 'report'. Returns its id."""
    doc = {
        "ts": datetime.now(timezone.utc),
        "kind": kind,
        "model": model,
        "input": jsonable(input),
        "toolsUsed": tools_used or [],
        "resultSummary": jsonable(result_summary),
        **{k: jsonable(v) for k, v in extra.items()},
    }
    res = get_db()[AUDIT_COLLECTION].insert_one(doc)
    return str(res.inserted_id)


def recent(limit: int = 50) -> list[dict]:
    """Most recent audit records (JSON-able)."""
    cur = get_db()[AUDIT_COLLECTION].find().sort("ts", -1).limit(limit)
    return [jsonable(d) for d in cur]
