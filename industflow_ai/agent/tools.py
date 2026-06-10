"""LangChain tools the agent can call.

Each predefined tool is a thin wrapper over an aggregation in
`industflow_starter.queries` (read-only, safe, indexed). The `mongo_aggregate`
tool is the sandboxed escape hatch for ad-hoc questions. Every tool returns a
JSON string so the model gets clean, serializable context.
"""
from __future__ import annotations

import json

from bson import ObjectId
from langchain_core.tools import tool
from pymongo.errors import PyMongoError

from industflow_starter import queries
from ..audit.log import record
from ..config import READABLE_COLLECTIONS
from ..mongo import get_db
from ..safety.sandbox import SandboxError, execute_pipeline, validate_pipeline
from ..serialize import jsonable


def _dump(data) -> str:
    return json.dumps(jsonable(data), ensure_ascii=False, default=str)


@tool
def list_lines() -> str:
    """List production lines with their id and alias name (e.g. line_1).
    Use this first when a question mentions a specific line, to resolve its id."""
    db = get_db()
    rows = [{"lineId": str(d["_id"]), "name": d.get("name")}
            for d in db["lines"].find({"deleted": False})]
    return _dump(rows)


@tool
def outcomes() -> str:
    """Product counts grouped by (done, status). Scrap = done=true & status=false.
    Use for a high-level OK vs NOK vs in-flight breakdown."""
    return _dump(queries.outcomes(get_db()))


@tool
def daily_scrap_rate() -> str:
    """Per-day scrap rate (NOK fraction) over completed products, time series."""
    return _dump(queries.daily_scrap_rate(get_db()))


@tool
def loss_by_defect(limit: int = 20) -> str:
    """Top defect codes by frequency, joined to the codebook. `limit` caps rows."""
    return _dump(queries.loss_by_defect(get_db(), limit=limit))


@tool
def shift_comparison(line_id: str | None = None, limit: int = 60) -> str:
    """Most recent shifts with output, fulfillment, and downtime minutes.
    Optionally filter to one line by its id (get ids from list_lines)."""
    oid = ObjectId(line_id) if line_id else None
    return _dump(queries.shift_comparison(get_db(), line_id=oid, limit=limit))


@tool
def first_pass_yield(min_attempts: int = 1, worst_first: bool = True,
                     limit: int = 20) -> str:
    """First-Pass-Yield per step: fraction whose FIRST attempt passed.

    There are ~1500 distinct steps, so always filter/cap. `min_attempts` drops
    low-sample steps (use e.g. 500 for statistically meaningful steps).
    `worst_first=True` sorts by lowest FPY (the problem steps); set False to sort
    by highest volume. `limit` caps the returned rows.
    """
    rows = [r for r in queries.first_pass_yield(get_db())
            if (r.get("total") or 0) >= min_attempts]
    rows.sort(key=(lambda r: r.get("fpy", 1.0)) if worst_first
              else (lambda r: -(r.get("total") or 0)))
    return _dump(rows[:limit])


@tool
def step_cycle_time(min_attempts: int = 1, sort_by: str = "n",
                    limit: int = 20) -> str:
    """Mean and approximate-median step duration (seconds) by step name.

    ~1500 distinct steps, so always filter/cap. `min_attempts` drops low-sample
    steps. `sort_by`: "n" (busiest), "avgSec" (slowest mean), or "p50Sec"
    (slowest median); sorted descending. `limit` caps the returned rows.
    """
    rows = [r for r in queries.step_cycle_time(get_db())
            if (r.get("n") or 0) >= min_attempts]
    key = sort_by if sort_by in {"n", "avgSec", "p50Sec"} else "n"
    rows.sort(key=lambda r: r.get(key) or 0, reverse=True)
    return _dump(rows[:limit])


@tool
def downtime_by_reason() -> str:
    """Total downtime minutes and event count grouped by reason code."""
    return _dump(queries.downtime_by_reason(get_db()))


# Built from config so the collection list can't drift from the sandbox.
_MONGO_AGGREGATE_DESC = (
    "Run a read-only MongoDB aggregation for questions the other tools don't "
    "cover. Use ONLY when no predefined tool fits. `collection` must be one "
    f"of: {', '.join(sorted(READABLE_COLLECTIONS))}. `pipeline` is a standard "
    "aggregation pipeline (list of stage dicts). Write stages "
    "($out/$merge/$function/$where) are rejected and results are capped. "
    "Always include deleted:false in your $match."
)


@tool(description=_MONGO_AGGREGATE_DESC)
def mongo_aggregate(collection: str, pipeline: list) -> str:
    requested = {"collection": collection, "pipeline": jsonable(pipeline)}
    try:
        sanitized = validate_pipeline(collection, pipeline)
    except SandboxError as e:
        record("mongo_aggregate", input=requested,
               result_summary={"rejected": str(e)})
        return json.dumps({"error": str(e)})
    try:
        rows = execute_pipeline(get_db(), collection, sanitized)
    except PyMongoError as e:
        record("mongo_aggregate", input=requested,
               pipelineExecuted=sanitized, result_summary={"error": str(e)})
        return json.dumps({"error": str(e)})
    record("mongo_aggregate", input=requested,
           pipelineExecuted=sanitized, result_summary={"rows": len(rows)})
    return _dump(rows)


# Predefined (safe, fast) tools + the sandboxed escape hatch.
ALL_TOOLS = [
    list_lines,
    outcomes,
    daily_scrap_rate,
    loss_by_defect,
    shift_comparison,
    first_pass_yield,
    step_cycle_time,
    downtime_by_reason,
    mongo_aggregate,
]
