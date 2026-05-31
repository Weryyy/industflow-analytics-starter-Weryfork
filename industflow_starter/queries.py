"""Reusable analytics queries used by the example scripts.

Every function takes a `db` and returns a list of dicts — easy to print, easy
to feed into pandas / matplotlib if the receiver wants charts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.database import Database


def outcomes(db: Database) -> list[dict[str, Any]]:
    """Product counts grouped by (done, status). Scrap = done=true & status=false."""
    return list(db["products"].aggregate([
        {"$match": {"deleted": False}},
        {"$group": {
            "_id": {"done": "$done", "status": "$status"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.done": 1, "_id.status": 1}},
    ]))


def daily_scrap_rate(db: Database) -> list[dict[str, Any]]:
    """Per-day scrap rate over completed products."""
    return list(db["products"].aggregate([
        {"$match": {"deleted": False, "done": True}},
        {"$group": {
            "_id": {"$dateTrunc": {"date": "$createdAt", "unit": "day"}},
            "total": {"$sum": 1},
            "nok": {"$sum": {"$cond": [{"$eq": ["$status", False]}, 1, 0]}},
        }},
        {"$project": {
            "_id": 0,
            "day": "$_id",
            "total": 1,
            "nok": 1,
            "scrapRate": {"$cond": [
                {"$eq": ["$total", 0]}, None,
                {"$divide": ["$nok", "$total"]},
            ]},
        }},
        {"$sort": {"day": 1}},
    ]))


def loss_by_defect(db: Database, limit: int = 20) -> list[dict[str, Any]]:
    """Top defect codes by frequency, joined to the codebook."""
    return list(db["products"].aggregate([
        {"$match": {
            "deleted": False,
            "productDefect.defectCode": {"$exists": True},
        }},
        {"$group": {
            "_id": "$productDefect.defectCode",
            "count": {"$sum": 1},
        }},
        {"$lookup": {
            "from": "defectcode",
            "let": {"dc": "$_id"},
            "pipeline": [{"$match": {"$expr": {"$and": [
                {"$eq": ["$entityType", "PRODUCT"]},
                {"$eq": ["$code", "$$dc"]},
            ]}}}],
            "as": "code",
        }},
        {"$project": {
            "_id": 0,
            "defectCode": "$_id",
            "count": 1,
            "entityType": {"$first": "$code.entityType"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]))


def shift_comparison(db: Database, line_id: Any | None = None,
                     limit: int = 60) -> list[dict[str, Any]]:
    """Most recent shifts (optionally filtered to one line) with output and downtime totals."""
    pipeline: list[dict[str, Any]] = [{"$match": {"deleted": False}}]
    if line_id is not None:
        pipeline[0]["$match"]["line.$id"] = line_id

    pipeline += [
        {"$project": {
            "_id": 0,
            "lineId": "$line.$id",
            "date": 1,
            "shiftNumber": 1,
            "created": 1,
            "finished": 1,
            "expectedCreatingOutput": 1,
            "expectedPackingOutput": 1,
            "creatingFulfillment": {"$cond": [
                {"$eq": ["$expectedCreatingOutput", 0]}, None,
                {"$divide": ["$created", "$expectedCreatingOutput"]},
            ]},
            "downtimeMinutes": {"$sum": {"$map": {
                "input": {"$ifNull": ["$downtimes", []]},
                "as": "d",
                "in": {"$add": [
                    {"$multiply": [
                        {"$subtract": ["$$d.endHour", "$$d.startHour"]}, 60,
                    ]},
                    {"$subtract": ["$$d.endMinute", "$$d.startMinute"]},
                ]},
            }}},
        }},
        {"$sort": {"date": -1, "shiftNumber": 1}},
        {"$limit": limit},
    ]
    return list(db["workshifts"].aggregate(pipeline))


def first_pass_yield(db: Database) -> list[dict[str, Any]]:
    """FPY per step: outcome of the FIRST attempt in stepData[]."""
    return list(db["products.steps"].aggregate([
        {"$match": {"deleted": False, "stepData.0": {"$exists": True}}},
        {"$project": {
            "stepName": "$persistedStepDefinition.name",
            "firstAttemptOk": {"$arrayElemAt": ["$stepData.status", 0]},
        }},
        {"$group": {
            "_id": "$stepName",
            "total": {"$sum": 1},
            "firstOk": {"$sum": {"$cond": ["$firstAttemptOk", 1, 0]}},
        }},
        {"$project": {
            "_id": 0,
            "stepName": "$_id",
            "total": 1,
            "firstOk": 1,
            "fpy": {"$cond": [
                {"$eq": ["$total", 0]}, None,
                {"$divide": ["$firstOk", "$total"]},
            ]},
        }},
        {"$sort": {"total": -1}},
    ]))


def step_cycle_time(db: Database) -> list[dict[str, Any]]:
    """Mean & approximate-median step duration (seconds) by step name."""
    return list(db["products.steps"].aggregate([
        {"$match": {
            "deleted": False,
            "lastData.startAt": {"$exists": True},
            "lastData.endAt": {"$exists": True},
        }},
        {"$project": {
            "stepName": "$persistedStepDefinition.name",
            "durationSec": {"$divide": [
                {"$subtract": ["$lastData.endAt", "$lastData.startAt"]},
                1000,
            ]},
        }},
        {"$group": {
            "_id": "$stepName",
            "n": {"$sum": 1},
            "avgSec": {"$avg": "$durationSec"},
            "p50Sec": {"$median": {
                "input": "$durationSec", "method": "approximate",
            }},
        }},
        {"$project": {"_id": 0, "stepName": "$_id", "n": 1, "avgSec": 1, "p50Sec": 1}},
        {"$sort": {"n": -1}},
    ]))


def downtime_by_reason(db: Database) -> list[dict[str, Any]]:
    """Total downtime minutes and count by reason code."""
    return list(db["workshifts"].aggregate([
        {"$match": {"deleted": False, "downtimes.0": {"$exists": True}}},
        {"$unwind": "$downtimes"},
        {"$project": {
            "reason": "$downtimes.reason",
            "minutes": {"$add": [
                {"$multiply": [
                    {"$subtract": ["$downtimes.endHour", "$downtimes.startHour"]}, 60,
                ]},
                {"$subtract": ["$downtimes.endMinute", "$downtimes.startMinute"]},
            ]},
            "outputReduction": "$downtimes.outputReduction",
        }},
        {"$group": {
            "_id": "$reason",
            "events": {"$sum": 1},
            "totalMinutes": {"$sum": "$minutes"},
            "totalOutputReduction": {"$sum": "$outputReduction"},
        }},
        {"$project": {
            "_id": 0, "reason": "$_id", "events": 1,
            "totalMinutes": 1, "totalOutputReduction": 1,
        }},
        {"$sort": {"totalMinutes": -1}},
    ]))
