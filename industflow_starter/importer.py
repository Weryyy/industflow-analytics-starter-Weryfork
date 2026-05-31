"""Import the JSONL slice into MongoDB.

Uses bson.json_util to parse Extended JSON v2 — that's how the export was
serialized, so ObjectId / Date / NumberLong come back as native BSON types.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from bson.json_util import loads as bson_loads
from pymongo import ASCENDING, DESCENDING

from .db import COLLECTIONS, coll, file_for_collection, get_db


def _import_one(db, cname: str, path: str, batch_size: int) -> int:
    if not os.path.exists(path):
        print(f"  SKIP {cname}: {path} not found", file=sys.stderr)
        return 0

    target = coll(db, cname)
    target.drop()  # idempotent runs: clear before import

    inserted = 0
    batch = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            batch.append(bson_loads(line))
            if len(batch) >= batch_size:
                target.insert_many(batch, ordered=False)
                inserted += len(batch)
                batch = []
        if batch:
            target.insert_many(batch, ordered=False)
            inserted += len(batch)
    print(f"  {cname:<40s} {inserted:>10,} docs")
    return inserted


def import_all(data_dir: str = "data", uri: str | None = None,
               batch_size: int = 1000) -> None:
    db = get_db(uri)
    print(f"Importing into {db.name} from {data_dir}/")
    total = 0
    for cname in COLLECTIONS:
        path = file_for_collection(data_dir, cname)
        total += _import_one(db, cname, path, batch_size)
    print(f"\nTotal: {total:,} documents")


# Indexes that make the example queries fast. Created idempotently after import.
INDEX_PLAN = {
    "products": [
        [("createdAt", DESCENDING)],
        [("abas", ASCENDING), ("createdAt", DESCENDING)],
        [("status", ASCENDING), ("done", ASCENDING)],
        [("productDefect.defectCode", ASCENDING)],
    ],
    "products.steps": [
        [("lastData.createdFrom", ASCENDING)],
        [("persistedStepDefinition.name", ASCENDING)],
        [("status", ASCENDING), ("done", ASCENDING)],
    ],
    "workshifts": [
        [("date", DESCENDING), ("shiftNumber", ASCENDING)],
        [("line.$id", ASCENDING), ("date", DESCENDING)],
    ],
    "products.defect_history": [
        [("productId", ASCENDING)],
    ],
}


def create_indexes(uri: str | None = None) -> None:
    db = get_db(uri)
    print(f"Creating indexes in {db.name}")
    for cname, plans in INDEX_PLAN.items():
        target = db[cname]
        for keys in plans:
            name = target.create_index(keys)
            print(f"  {cname}: {name}")
