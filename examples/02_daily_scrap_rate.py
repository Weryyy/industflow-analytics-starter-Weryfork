#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pymongo>=4.6", "tabulate>=0.9"]
# ///
"""Daily scrap rate over the export window."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from industflow_starter.db import get_db
from industflow_starter.queries import daily_scrap_rate
from tabulate import tabulate


def main():
    rows = daily_scrap_rate(get_db())
    if not rows:
        print("No completed products in the data.")
        return
    for r in rows:
        r["day"] = r["day"].date().isoformat()
        r["scrapRate"] = f"{r['scrapRate']:.2%}" if r["scrapRate"] is not None else ""
    print(tabulate(rows, headers="keys", tablefmt="github"))


if __name__ == "__main__":
    main()
