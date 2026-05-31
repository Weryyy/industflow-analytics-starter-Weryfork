#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pymongo>=4.6", "tabulate>=0.9"]
# ///
"""Top defect codes — the loss-concentration KPI."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from industflow_starter.db import get_db
from industflow_starter.queries import loss_by_defect
from tabulate import tabulate


def main():
    rows = loss_by_defect(get_db(), limit=20)
    print(tabulate(rows, headers="keys", tablefmt="github"))
    print(f"\n{len(rows)} defect codes shown.")
    print("Note: defectcode.descriptions is redacted on export — codes only.")


if __name__ == "__main__":
    main()
