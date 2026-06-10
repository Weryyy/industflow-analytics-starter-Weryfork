"""Unit tests for BSON -> JSON conversion."""
from datetime import datetime, timezone

from bson import DBRef, ObjectId

from industflow_ai.serialize import jsonable


def test_objectid_becomes_string():
    oid = ObjectId()
    assert jsonable(oid) == str(oid)


def test_datetime_becomes_isoformat():
    dt = datetime(2026, 6, 1, 12, 30, tzinfo=timezone.utc)
    assert jsonable(dt) == dt.isoformat()


def test_dbref_becomes_ref_dict():
    oid = ObjectId()
    assert jsonable(DBRef("lines", oid)) == {"$ref": "lines", "$id": str(oid)}


def test_nested_structures_and_tuples():
    oid = ObjectId()
    doc = {"a": [{"id": oid}], "b": ("x", oid), "c": 3, "d": None}
    out = jsonable(doc)
    assert out == {"a": [{"id": str(oid)}], "b": ["x", str(oid)], "c": 3, "d": None}
