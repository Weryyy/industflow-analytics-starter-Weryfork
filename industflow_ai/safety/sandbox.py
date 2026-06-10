"""Sandboxed, read-only MongoDB aggregation.

The agent gets an escape hatch (`mongo_aggregate`) for questions the predefined
queries don't cover. An LLM will happily emit a `$lookup` cross-product or a
write stage, so every pipeline passes through here first:

  - collection must be in config.READABLE_COLLECTIONS
  - every stage operator must be on an allow-list — applied recursively, so
    sub-pipelines inside `$facet` and `$lookup` obey the same rules
  - `$lookup` (and any `from`) may only target READABLE_COLLECTIONS, so a join
    cannot escape the collection allow-list (e.g. into ai.audit)
  - write/exec stages ($out, $merge, $function, $where, ...) are rejected anywhere
    in the pipeline (checked recursively, not just top-level)
  - a $limit is always enforced (appended/capped to MAX_AGGREGATE_RESULTS)
  - execution is bounded by AGGREGATE_TIMEOUT_MS

Raises SandboxError on any violation. Returns a list of JSON-able dicts.
"""
from __future__ import annotations

from typing import Any

from pymongo.database import Database

from ..config import (
    AGGREGATE_TIMEOUT_MS,
    MAX_AGGREGATE_RESULTS,
    READABLE_COLLECTIONS,
)
from ..serialize import jsonable

# Stages an analytics read may legitimately use.
ALLOWED_STAGES = {
    "$match", "$group", "$project", "$sort", "$limit", "$skip",
    "$unwind", "$count", "$addFields", "$set", "$lookup", "$sortByCount",
    "$bucket", "$bucketAuto", "$facet", "$replaceRoot", "$replaceWith",
}

# Operators/stages that can write, execute code, or escape the sandbox.
FORBIDDEN_KEYS = {
    "$out", "$merge", "$function", "$where", "$accumulator",
    "$expr$function", "$listSessions", "$currentOp", "$collStats",
    "$indexStats", "$planCacheStats", "$documents", "$unionWith",
}


class SandboxError(ValueError):
    """A pipeline violated the read-only sandbox rules."""


def _scan_forbidden(node: Any) -> None:
    """Recursively reject any forbidden operator anywhere in the pipeline."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in FORBIDDEN_KEYS:
                raise SandboxError(f"forbidden operator: {k}")
            _scan_forbidden(v)
    elif isinstance(node, list):
        for v in node:
            _scan_forbidden(v)


def _validate_lookup(spec: Any, where: str) -> None:
    """`$lookup` may only join collections on the read allow-list."""
    if not isinstance(spec, dict):
        raise SandboxError(f"{where}: $lookup spec must be a dict")
    src = spec.get("from")
    if src not in READABLE_COLLECTIONS:
        raise SandboxError(
            f"{where}: $lookup from '{src}' not readable; "
            f"allowed: {sorted(READABLE_COLLECTIONS)}"
        )
    if "pipeline" in spec:
        _validate_stages(spec["pipeline"], where=f"{where}.$lookup.pipeline",
                         allow_empty=True)


def _validate_stages(stages: Any, *, where: str = "pipeline",
                     allow_empty: bool = False) -> None:
    """Apply the stage allow-list recursively (top level, $facet, $lookup)."""
    if not isinstance(stages, list) or (not stages and not allow_empty):
        raise SandboxError(f"{where} must be a non-empty list of stages")
    for stage in stages:
        if not isinstance(stage, dict) or len(stage) != 1:
            raise SandboxError(
                f"{where}: each stage must be a single-key dict, got: {stage}")
        (stage_name,) = stage.keys()
        if stage_name not in ALLOWED_STAGES:
            raise SandboxError(f"{where}: stage not allowed: {stage_name}")
        spec = stage[stage_name]
        if stage_name == "$lookup":
            _validate_lookup(spec, where)
        elif stage_name == "$facet":
            if not isinstance(spec, dict) or not spec:
                raise SandboxError(f"{where}: $facet spec must be a non-empty dict")
            for facet_name, sub in spec.items():
                _validate_stages(sub, where=f"{where}.$facet.{facet_name}")


def validate_pipeline(collection: str, pipeline: list[dict]) -> list[dict]:
    """Validate and normalize a pipeline; returns the sanitized pipeline."""
    if collection not in READABLE_COLLECTIONS:
        raise SandboxError(
            f"collection '{collection}' not readable; "
            f"allowed: {sorted(READABLE_COLLECTIONS)}"
        )
    _validate_stages(pipeline)
    _scan_forbidden(pipeline)

    # Enforce a result cap: cap an existing trailing $limit or append one.
    sanitized = list(pipeline)
    if sanitized and "$limit" in sanitized[-1]:
        sanitized[-1] = {"$limit": min(int(sanitized[-1]["$limit"]), MAX_AGGREGATE_RESULTS)}
    else:
        sanitized.append({"$limit": MAX_AGGREGATE_RESULTS})
    return sanitized


def execute_pipeline(db: Database, collection: str,
                     sanitized: list[dict]) -> list[dict]:
    """Execute an already-validated pipeline, JSON-able result."""
    cursor = db[collection].aggregate(sanitized, maxTimeMS=AGGREGATE_TIMEOUT_MS)
    return [jsonable(doc) for doc in cursor]


def safe_aggregate(db: Database, collection: str, pipeline: list[dict]) -> list[dict]:
    """Validate then execute a read-only aggregation, JSON-able result."""
    return execute_pipeline(db, collection, validate_pipeline(collection, pipeline))
