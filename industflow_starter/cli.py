"""`mip` CLI: import the JSONL slice and run a few headline queries."""
from __future__ import annotations

import argparse
import sys

from tabulate import tabulate

from .db import get_db
from .importer import create_indexes, import_all
from . import queries


def cmd_import(args: argparse.Namespace) -> int:
    import_all(data_dir=args.data, uri=args.uri, batch_size=args.batch_size)
    if args.indexes:
        print()
        create_indexes(uri=args.uri)
    return 0


def _print_table(rows, headers="keys"):
    if not rows:
        print("(no rows)")
        return
    print(tabulate(rows, headers=headers, floatfmt=".3f", tablefmt="github"))


def cmd_summary(args: argparse.Namespace) -> int:
    db = get_db(args.uri)

    print("\n# Document counts\n")
    counts = []
    for name in sorted(db.list_collection_names()):
        counts.append({"collection": name, "count": db[name].estimated_document_count()})
    _print_table(counts)

    print("\n# Outcomes (done × status)\n")
    _print_table(queries.outcomes(db))

    print("\n# Top defect codes\n")
    _print_table(queries.loss_by_defect(db, limit=10))

    print("\n# Downtime by reason\n")
    _print_table(queries.downtime_by_reason(db))

    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mip")
    ap.add_argument("--uri", help="Mongo URI (default $MONGO_URI or mongodb://localhost:27017/mip)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_import = sub.add_parser("import", help="Drop & reload all collections from data/")
    p_import.add_argument("--data", default="data", help="Directory holding the .jsonl files")
    p_import.add_argument("--batch-size", type=int, default=1000)
    p_import.add_argument("--no-indexes", dest="indexes", action="store_false",
                          help="Skip index creation after import")
    p_import.set_defaults(func=cmd_import)

    p_summary = sub.add_parser("summary", help="Quick health check + headline numbers")
    p_summary.set_defaults(func=cmd_summary)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
