#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pymongo>=4.6", "tabulate>=0.9"]
# ///
"""Cycle time per step: mean and approximate median in seconds.

Requires MongoDB 7.0+ for $median. On older Mongo, drop the p50 field.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from industflow_starter.db import get_db
from industflow_starter.queries import step_cycle_time
from tabulate import tabulate


def main():
    rows = step_cycle_time(get_db())
    for r in rows:
        for k in ("avgSec", "p50Sec"):
            if r.get(k) is not None:
                r[k] = f"{r[k]:.1f}"
    print(tabulate(rows[:40], headers="keys", tablefmt="github"))


if __name__ == "__main__":
    main()
