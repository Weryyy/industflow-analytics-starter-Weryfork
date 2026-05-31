#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pymongo>=4.6", "tabulate>=0.9"]
# ///
"""Downtime totals by reason code — where is the line losing minutes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from industflow_starter.db import get_db
from industflow_starter.queries import downtime_by_reason
from tabulate import tabulate


def main():
    rows = downtime_by_reason(get_db())
    print(tabulate(rows, headers="keys", tablefmt="github"))


if __name__ == "__main__":
    main()
