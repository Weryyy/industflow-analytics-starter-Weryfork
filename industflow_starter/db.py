"""Shared Mongo connection helper used by every example script."""
from __future__ import annotations

import os
from pymongo import MongoClient
from pymongo.database import Database

DEFAULT_URI = "mongodb://localhost:27017/mip"


def get_db(uri: str | None = None) -> Database:
    """Return the target database. URI must include a DB name."""
    uri = uri or os.environ.get("MONGO_URI", DEFAULT_URI)
    client = MongoClient(uri)
    db = client.get_default_database()
    if db is None:
        raise SystemExit("MONGO_URI must include a database name, e.g. .../mip")
    return db


# The export collapses dotted Mongo names to underscored filenames:
#   platform.products.steps  ->  platform_products_steps.jsonl
# We import each as `<basename>` (everything after `platform_` becomes the
# Mongo collection name, with underscores -> dots).
COLLECTIONS = [
    "platform.products",
    "platform.products.steps",
    "platform.products.defect_history",
    "platform.workshifts",
    "platform.lines",
    "platform.stations",
    "platform.defectcode",
]


def file_for_collection(data_dir: str, cname: str) -> str:
    return os.path.join(data_dir, cname.replace(".", "_") + ".jsonl")


def coll(db: Database, dotted_name: str):
    """Get a collection by its dotted name, e.g. 'products.steps'.

    The export uses 'platform.<x>' names; on the import side we strip the
    'platform.' prefix to match what the receiver typically expects.
    """
    return db[dotted_name.removeprefix("platform.")]
