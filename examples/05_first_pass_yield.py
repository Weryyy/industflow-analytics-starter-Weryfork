#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pymongo>=4.6", "tabulate>=0.9"]
# ///
"""FPY by step: percentage of step instances whose FIRST attempt was OK."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from industflow_starter.db import get_db
from industflow_starter.queries import first_pass_yield
from tabulate import tabulate


def main():
    rows = first_pass_yield(get_db())
    for r in rows:
        if r.get("fpy") is not None:
            r["fpy"] = f"{r['fpy']:.2%}"
    print(tabulate(rows[:40], headers="keys", tablefmt="github"))
    print(f"\nShowing top {min(40, len(rows))} of {len(rows)} step types.")


if __name__ == "__main__":
    main()
