#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pymongo>=4.6", "tabulate>=0.9"]
# ///
"""Most recent shifts: created/finished vs expected, plus downtime minutes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from industflow_starter.db import get_db
from industflow_starter.queries import shift_comparison
from tabulate import tabulate


def main():
    rows = shift_comparison(get_db(), limit=30)
    for r in rows:
        if r.get("date"):
            r["date"] = r["date"].date().isoformat()
        if r.get("creatingFulfillment") is not None:
            r["creatingFulfillment"] = f"{r['creatingFulfillment']:.0%}"
        # Hide line ObjectId from the table — keep first 6 chars for visual grouping
        if r.get("lineId"):
            r["lineId"] = str(r["lineId"])[:6]
    print(tabulate(rows, headers="keys", tablefmt="github"))


if __name__ == "__main__":
    main()
