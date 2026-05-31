#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pymongo>=4.6", "tabulate>=0.9"]
# ///
"""Product outcomes: scrap = (done=true, status=false). Run after `mip import`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from industflow_starter.db import get_db
from industflow_starter.queries import outcomes
from tabulate import tabulate


def main():
    db = get_db()
    rows = outcomes(db)
    print(tabulate(rows, headers="keys", tablefmt="github"))

    total = sum(r["count"] for r in rows)
    scrap = sum(r["count"] for r in rows
                if r["_id"]["done"] and r["_id"]["status"] is False)
    inflight = sum(r["count"] for r in rows if not r["_id"]["done"])
    good = total - scrap - inflight

    print()
    print(f"Total products:    {total:>10,}")
    print(f"  Good (done OK):  {good:>10,}  ({good/total:.1%})")
    print(f"  Scrap (done NOK):{scrap:>10,}  ({scrap/total:.1%})")
    print(f"  In-flight:       {inflight:>10,}  ({inflight/total:.1%})")


if __name__ == "__main__":
    main()
