#!/usr/bin/env python
"""Generate a synthetic Industflow data slice as Extended-JSON-v2 .jsonl files.

The output mirrors the real data drop's shape (see ABOUT_DATA.md) closely enough
that `industflow_starter`'s importer and every query in `queries.py` work
unchanged. When the real drop arrives, drop its .jsonl files into data/ and
re-run `mip import` — this generator becomes unnecessary.

Usage:
    uv run python tools/gen_synthetic.py            # defaults
    uv run python tools/gen_synthetic.py --days 14 --products-per-shift 30

Field names and aliasing follow ABOUT_DATA.md: abas=prod_NN, line_N, station_XN,
code_NNN. Nothing here is customer-identifying; it's randomly generated.
"""
from __future__ import annotations

import argparse
import os
import random
from datetime import datetime, timedelta

from bson import DBRef, ObjectId
from bson.json_util import dumps as bson_dumps

# ---------------------------------------------------------------------------
# Domain definitions
# ---------------------------------------------------------------------------

PRODUCT_TYPES = ["prod_11", "prod_17", "prod_23"]

# Ordered build pipeline. Each step definition carries the flow rules that the
# real persistedStepDefinition snapshot would have.
STEP_DEFS = [
    {"name": "form_check",       "type": "FORMING",  "measure": None},
    {"name": "assembly_torque",  "type": "ASSEMBLY", "measure": None},
    {"name": "leak_test",        "type": "TEST",     "measure": "tightness"},
    {"name": "resistance_test",  "type": "TEST",     "measure": "resistance"},
    {"name": "thickness_check",  "type": "TEST",     "measure": "thickness"},
    {"name": "pack",             "type": "PACKING",  "measure": None},
]

DEFECT_REASONS = [f"code_{i:03d}" for i in range(1, 13)]  # code_001..code_012
DOWNTIME_REASONS = [
    "MACHINE_PAUSE", "OPERATOR_BREAK", "MATERIAL_SHORTAGE",
    "PLANNED_MAINTENANCE", "QUALITY_HOLD", "CHANGEOVER",
]

# Shift windows: 1 -> 06-14, 2 -> 14-22, 3 -> 22-06 (next day)
SHIFT_START_HOUR = {1: 6, 2: 14, 3: 22}

SCRAP_RATE = 0.05      # ~5% of completed products are NOK
REWORK_RATE = 0.12     # fraction of OK steps that needed a retry first


def measure_value(kind: str, ok: bool) -> dict:
    """A captured measurement {value, status} with a plausible value per kind."""
    ranges = {
        "tightness":  (0.5, 2.0),    # mbar/s leak-ish
        "resistance": (0.8, 1.4),    # ohm
        "thickness":  (2.0, 4.0),    # mm
    }
    lo, hi = ranges[kind]
    val = round(random.uniform(lo, hi), 3)
    if not ok:  # push NOK values out of band
        val = round(hi + random.uniform(0.1, 0.5), 3)
    return {"value": val, "status": ok}


def make_step(station_id: ObjectId, sdef: dict, base_ts: datetime,
              force_nok: bool) -> tuple[dict, datetime]:
    """Build one products.steps doc. Returns (doc, end_ts)."""
    duration = random.uniform(8, 45)  # seconds, with occasional long tail below
    if random.random() < 0.03:
        duration *= random.uniform(3, 8)  # long-tail anomaly

    needs_rework = (not force_nok) and random.random() < REWORK_RATE
    step_data = []
    cursor = base_ts

    # First attempt
    first_ok = not (force_nok or needs_rework)
    a_start = cursor
    a_end = a_start + timedelta(seconds=duration)
    attempt = {"status": first_ok, "startAt": a_start, "endAt": a_end,
               "createdFrom": station_id}
    if sdef["measure"]:
        attempt[sdef["measure"]] = measure_value(sdef["measure"], first_ok)
    step_data.append(attempt)
    cursor = a_end

    # Optional rework attempt (ends OK)
    if needs_rework:
        cursor += timedelta(seconds=random.uniform(5, 20))
        r_start = cursor
        r_end = r_start + timedelta(seconds=duration)
        attempt = {"status": True, "startAt": r_start, "endAt": r_end,
                   "createdFrom": station_id}
        if sdef["measure"]:
            attempt[sdef["measure"]] = measure_value(sdef["measure"], True)
        step_data.append(attempt)
        cursor = r_end

    last = step_data[-1]
    final_ok = last["status"]

    doc = {
        "_id": ObjectId(),
        "deleted": False,
        "done": True,
        "status": final_ok,
        "lastData": dict(last),
        "stepData": step_data,
        "persistedStepDefinition": {
            "name": sdef["name"],
            "type": sdef["type"],
            "nokPossible": sdef["type"] == "TEST",
            "nokContinue": False,
            "skipPossible": False,
            "mustBeApproved": sdef["name"] == "form_check",
        },
    }
    return doc, cursor


def make_product(abas: str, station_id: ObjectId, created_at: datetime,
                 is_nok: bool) -> tuple[dict, list[dict]]:
    """Build one product plus its step instances."""
    pid = ObjectId()
    steps = []
    cursor = created_at

    # Which step fails if this product is NOK
    nok_step_idx = random.randrange(len(STEP_DEFS)) if is_nok else -1

    for i, sdef in enumerate(STEP_DEFS):
        step, cursor = make_step(station_id, sdef, cursor, force_nok=(i == nok_step_idx))
        cursor += timedelta(seconds=random.uniform(2, 10))
        steps.append(step)

    step_ids = [s["_id"] for s in steps]
    group_id = "g_" + abas

    product = {
        "_id": pid,
        "createdAt": created_at,
        "createdFrom": station_id,
        "abas": abas,
        "done": True,
        "status": not is_nok,
        "deleted": False,
        "groups": {
            group_id: {
                "persistedSteps": [DBRef("products.steps", sid) for sid in step_ids],
            }
        },
        "steps": step_ids,  # flat denormalized list
    }
    if is_nok:
        product["productDefect"] = {"defectCode": random.choice(DEFECT_REASONS)}
        if random.random() < 0.3:
            product["qaStatus"] = "SUSPECT"
    if random.random() < 0.02:
        product["specialProductTypes"] = ["FIRST"]

    return product, steps


def make_downtimes(shift_start: datetime) -> list[dict]:
    """0-3 downtime entries within a shift.

    Kept within the same clock-day (no midnight wrap) so the starter query's
    naive (endHour-startHour)*60 + (endMinute-startMinute) stays positive.
    """
    n = random.choices([0, 1, 2, 3], weights=[40, 35, 18, 7])[0]
    out = []
    day_max = 24 * 60 - 1  # 23:59
    base = shift_start.hour * 60
    for _ in range(n):
        start = min(base + random.randint(0, 6 * 60), day_max - 5)
        dur = random.randint(3, 45)
        end = min(start + dur, day_max)
        start_h, start_m = divmod(start, 60)
        end_h, end_m = divmod(end, 60)
        out.append({
            "reason": random.choice(DOWNTIME_REASONS),
            "startHour": start_h, "startMinute": start_m,
            "endHour": end_h, "endMinute": end_m,
            "outputReduction": random.randint(1, 15),
        })
    return out


def write_jsonl(path: str, docs: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for d in docs:
            f.write(bson_dumps(d) + "\n")
    print(f"  {os.path.basename(path):<42s} {len(docs):>8,} docs")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data", help="output directory")
    ap.add_argument("--lines", type=int, default=3)
    ap.add_argument("--stations-per-line", type=int, default=4)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--products-per-shift", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    os.makedirs(args.out, exist_ok=True)

    # --- config collections (span full history; createdAt = onboarding) ---
    onboard = datetime(2022, 1, 1)
    lines, stations = [], []
    line_stations: dict[ObjectId, list[ObjectId]] = {}

    for li in range(1, args.lines + 1):
        lid = ObjectId()
        lines.append({"_id": lid, "name": f"line_{li}", "createdAt": onboard,
                      "deleted": False})
        sids = []
        for si in range(1, args.stations_per_line + 1):
            sid = ObjectId()
            stations.append({
                "_id": sid, "name": f"station_{li}{chr(64 + si)}",
                "line": DBRef("lines", lid), "createdAt": onboard, "deleted": False,
            })
            sids.append(sid)
        line_stations[lid] = sids

    defectcodes = [
        {"_id": ObjectId(), "code": c, "entityType": "PRODUCT",
         "createdAt": onboard, "deleted": False}
        for c in DEFECT_REASONS
    ]
    # a few STEP-scoped codes too (not referenced by loss_by_defect, realistic noise)
    defectcodes += [
        {"_id": ObjectId(), "code": f"scode_{i:03d}", "entityType": "STEP",
         "createdAt": onboard, "deleted": False}
        for i in range(1, 4)
    ]

    # --- time-windowed collections ---
    products, all_steps, workshifts, defect_history = [], [], [], []

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_day = today - timedelta(days=args.days - 1)

    for d in range(args.days):
        day = start_day + timedelta(days=d)
        for lid, sids in line_stations.items():
            for shift in (1, 2, 3):
                shift_start = day + timedelta(hours=SHIFT_START_HOUR[shift])
                n = random.randint(int(args.products_per_shift * 0.7),
                                   int(args.products_per_shift * 1.3))
                created = 0
                nok = 0
                for _ in range(n):
                    abas = random.choice(PRODUCT_TYPES)
                    station = random.choice(sids)
                    offset = random.uniform(0, 7 * 3600)  # within ~7h of shift
                    cat = shift_start + timedelta(seconds=offset)
                    is_nok = random.random() < SCRAP_RATE
                    prod, steps = make_product(abas, station, cat, is_nok)
                    products.append(prod)
                    all_steps.extend(steps)
                    created += 1
                    if is_nok:
                        nok += 1
                        # occasionally QA edits the defect code later (audit trail)
                        if random.random() < 0.15:
                            defect_history.append({
                                "_id": ObjectId(),
                                "productId": str(prod["_id"]),  # STRING of ObjectId
                                "defectCode": prod["productDefect"]["defectCode"],
                                "previousCode": random.choice(DEFECT_REASONS),
                                "changedAt": cat + timedelta(hours=random.randint(1, 48)),
                            })

                expected = int(n * random.uniform(1.0, 1.2))
                workshifts.append({
                    "_id": ObjectId(),
                    "deleted": False,
                    "line": DBRef("lines", lid),
                    "date": day,
                    "shiftNumber": shift,
                    "created": created,
                    "finished": created - random.randint(0, 3),
                    "expectedCreatingOutput": expected,
                    "expectedPackingOutput": expected,
                    "downtimes": make_downtimes(shift_start),
                })

    print(f"Writing synthetic slice to {args.out}/")
    write_jsonl(os.path.join(args.out, "platform_products.jsonl"), products)
    write_jsonl(os.path.join(args.out, "platform_products_steps.jsonl"), all_steps)
    write_jsonl(os.path.join(args.out, "platform_products_defect_history.jsonl"), defect_history)
    write_jsonl(os.path.join(args.out, "platform_workshifts.jsonl"), workshifts)
    write_jsonl(os.path.join(args.out, "platform_lines.jsonl"), lines)
    write_jsonl(os.path.join(args.out, "platform_stations.jsonl"), stations)
    write_jsonl(os.path.join(args.out, "platform_defectcode.jsonl"), defectcodes)
    print(f"\nDone. products={len(products):,} steps={len(all_steps):,} "
          f"workshifts={len(workshifts):,}")


if __name__ == "__main__":
    main()
