# About the data

A short cookbook for developers about to poke at this dataset. Built around
"try this" — paste the snippets into whatever Mongo client you use (Compass,
a notebook with `pymongo`, DataGrip, `mongosh`…), see real numbers. Pair this
with the more reference-shaped `RECEIVER.md` shipped with the data drop.

> The dataset uses field names inherited from the source MES/ERP — for
> example `abas` (a product-type identifier), `tankForm` (a form/mold
> reference), `navicertSN`. Don't try to read company or product identity
> into them; they're internal taxonomy from the **Industflow** platform
> by **Industware**, not customer-identifying values. Aliased fields in
> the data drop add another layer (`prod_17`, `line_3`, etc.).

> **Setup.** Run `uv run mip import` first. All snippets below assume the
> resulting `mip` database (whatever client you connect with).

---

## What you're looking at

A connected production floor running **Industflow** (a manufacturing-
intelligence platform built by Industware s.r.o.). The platform tracks
every produced piece end-to-end: it knows which station built it, which
configured steps were executed against it (with timing, status, and
captured measurements), which operator-defined defect code is attributed
to it, and which shift on which line it was made on — plus how that shift
compared to its expected output and how downtime entries reduced it.

The data here captures a window of real production with all of that
recorded: every product made, every step run on it, every shift on every
line, every defect, every downtime entry.

The mental model:

```
line  ──has──▶ stations              (a line groups stations: terminals)
line  ──has──▶ workshifts            (3 shifts/day: 06–14, 14–22, 22–06)
                │
                └─created/finished──▶ products

product ──passes through──▶ steps    (per product: forming → assembly → test → pack)
                                │
                                ├──lastData    (latest measurement snapshot)
                                └──stepData[]  (full attempt history)

product ──may have──▶ productDefect (a coded reason it's NOK)
                          │
                          └──defectCode  →  defectcode.code  (codebook join)
```

A **step instance** carries a snapshot of how it was *defined* at the time
it ran (`persistedStepDefinition`) — name, type, approval rules, special-
product-type gating. Steps are configured per product type by quality and
process operators in the platform's admin UI; that configuration is not in
this dataset (customer IP), but the snapshot is enough to label and group.

---

## The 7 collections

| Collection | One doc = | Volume tip |
|---|---|---|
| `products` | one piece off the line | thousands per shift on a fast line |
| `products.steps` | one step instance on a product | ~10–30× the product count |
| `products.defect_history` | a defect-code change on a product | rare; only when QA edits a code |
| `workshifts` | one (line × date × shift) | ~3/day × #lines |
| `lines` | a production line definition | dozens at most |
| `stations` | a terminal | low hundreds |
| `defectcode` | one entry in the defect codebook | dozens to hundreds |

```javascript
// First sanity check
db.getCollectionNames().sort()
db.products.countDocuments()
db["products.steps"].countDocuments()
```

---

## Try this

### 1. What does a product look like?

```javascript
db.products.findOne({ done: true, status: false })  // a scrapped product
```

Read top-down:
- `_id`, `createdAt`, `createdFrom` (station ObjectId).
- `abas` — the *aliased* product type (`prod_17`).
- `done` — false until the piece is fully packed; `status` — true=OK, false=NOK.
- `groups.<groupId>` — a stage of the build (forming, assembly…). Each
  group has `persistedSteps[]` (DBRefs to step docs).
- `productDefect.defectCode` — present iff this product was tagged with a
  reason. Joins to `defectcode.code` where `entityType: "PRODUCT"`.
- `qaStatus: "SUSPECT"` — quality team flagged this for follow-up.
- `specialProductTypes: ["FIRST"]` — first-piece-off-form, gets extra checks.

### 2. What does a step look like?

```javascript
db["products.steps"].findOne({ status: false, done: true })  // a NOK step
```

Important shape detail:
- `lastData` is the **most recent attempt** (a snapshot, single object).
- `stepData[]` is the **full history** of attempts — each retry / rework
  pushes a new entry. For First-Pass-Yield, you want `stepData[0]`.
- `lastData.tightness.value` (and similar for `thickness`, `resistance`) —
  the actual measurement that was made. `*.status` is the OK/NOK verdict.
- `persistedStepDefinition.name` — the step label (use this to group).
- `persistedStepDefinition.{nokPossible, nokContinue, skipPossible}` —
  the flow rules: can this step legally be NOK? does NOK halt production?

### 3. Scrap rate this week

```javascript
db.products.aggregate([
  { $match: { deleted: false, done: true,
              createdAt: { $gte: new Date(Date.now() - 7*86400000) } }},
  { $group: {
      _id: null,
      total: { $sum: 1 },
      nok: { $sum: { $cond: [{ $eq: ["$status", false] }, 1, 0] } }
  }},
  { $project: { _id: 0, total: 1, nok: 1,
                rate: { $divide: ["$nok", "$total"] } }}
])
```

### 4. Which step fails the most?

```javascript
db["products.steps"].aggregate([
  { $match: { deleted: false, done: true, status: false } },
  { $group: { _id: "$persistedStepDefinition.name", nok: { $sum: 1 } } },
  { $sort: { nok: -1 } },
  { $limit: 10 }
])
```

### 5. Worst station for scrap

```javascript
db["products.steps"].aggregate([
  { $match: { deleted: false, done: true, status: false } },
  { $group: {
      _id: "$lastData.createdFrom",  // ObjectId of the station
      nokSteps: { $sum: 1 }
  }},
  { $lookup: { from: "stations", localField: "_id",
               foreignField: "_id", as: "station" }},
  { $project: { _id: 0,
                station: { $first: "$station.name" },  // aliased: station_N
                nokSteps: 1 }},
  { $sort: { nokSteps: -1 } },
  { $limit: 10 }
])
```

### 6. Shift performance — a single line

```javascript
const aLine = db.lines.findOne()._id
db.workshifts.aggregate([
  { $match: { "line.$id": aLine, deleted: false } },
  { $project: {
      date: 1, shiftNumber: 1, created: 1, finished: 1,
      expectedCreatingOutput: 1,
      fulfillment: { $cond: [
        { $eq: ["$expectedCreatingOutput", 0] }, null,
        { $divide: ["$created", "$expectedCreatingOutput"] }
      ]}
  }},
  { $sort: { date: -1, shiftNumber: 1 } },
  { $limit: 21 }    // last 7 days × 3 shifts
])
```

### 7. Where is downtime coming from?

```javascript
db.workshifts.aggregate([
  { $unwind: "$downtimes" },
  { $group: {
      _id: "$downtimes.reason",
      events: { $sum: 1 },
      minutes: { $sum: { $add: [
        { $multiply: [
          { $subtract: ["$downtimes.endHour", "$downtimes.startHour"] }, 60
        ]},
        { $subtract: ["$downtimes.endMinute", "$downtimes.startMinute"] }
      ]}}
  }},
  { $sort: { minutes: -1 } }
])
```

`reason` is a coded enum (e.g. `MACHINE_PAUSE`). It's not free text.

### 8. Walk a product's full step history

```javascript
const p = db.products.findOne({ done: true, status: true })
db["products.steps"].find({
  _id: { $in: p.steps }
}).sort({ "lastData.startAt": 1 }).toArray()
```

`p.steps` is the flat denormalized list of all step ObjectIds on the product —
shortcut over walking `groups.<key>.persistedSteps[]`.

### 9. Anomaly hint — long-tail step durations

```javascript
db["products.steps"].aggregate([
  { $match: { "lastData.startAt": { $exists: true },
              "lastData.endAt": { $exists: true } }},
  { $project: {
      stepName: "$persistedStepDefinition.name",
      durationSec: { $divide: [
        { $subtract: ["$lastData.endAt", "$lastData.startAt"] }, 1000
      ]}
  }},
  { $group: {
      _id: "$stepName",
      n: { $sum: 1 },
      p50: { $median: { input: "$durationSec", method: "approximate" } },
      p99: { $percentile: { input: "$durationSec", p: [0.99],
                            method: "approximate" } }
  }},
  { $project: { stepName: "$_id", _id: 0, n: 1, p50: 1, p99: 1,
                spread: { $divide: [{ $first: "$p99" }, "$p50"] }}},
  { $sort: { spread: -1 } },
  { $limit: 10 }
])
```

A high `p99 / p50` ratio is a smell: this step usually finishes fast but has
a long tail. Often a candidate for "operator needed help" or "machine
hesitation". Requires Mongo 7.0+ (`$median`, `$percentile`).

---

## Joining patterns to know

References come in three shapes — the gotcha is in spotting which one:

| Shape | Example field | How to match |
|---|---|---|
| **DBRef** `{ $ref, $id }` | `workshifts.line`, `stations.line`, `workshifts.createdProducts[]` | `{ "line.$id": ObjectId(...) }` |
| **Plain ObjectId** | `products.createdFrom`, `steps.lastData.createdFrom`, `products.materialId` | `{ createdFrom: ObjectId(...) }` |
| **String of an ObjectId** | `defect_history.productId` | convert: `{ $expr: { $eq: ["$productId", { $toString: "$$pid" }] } }` |

`steps[]` on `products` is the **flat** denormalized list — easier to use than
walking nested groups. Both contain the same step ids.

---

## Gotchas

- **`abas`, `orderNumber`, `name` (on lines/stations) are aliased.** You'll
  see `prod_17`, `order_42`, `line_3`, `station_A1`. The mapping isn't in
  this data — counts and joins still work; the *labels* are anonymous.

- **Process telemetry was scrubbed.** PLC values, screw torques, machine
  payloads, component serials — all dropped on export. What remains is
  pass/fail status plus a few headline numeric fields (`tightness.value`,
  `thickness.value`, `resistance.value`).

- **`stepData[]` order matters.** The first element is the first attempt;
  use `$arrayElemAt: ["$stepData", 0]` for FPY, not `$last`. There's no
  guarantee of array length — many steps have just one attempt.

- **Soft deletes everywhere.** Always include `deleted: false` in matches
  unless you specifically want the audit trail.

- **`createdFrom` ≠ `createdBy`.** `createdFrom` is the **station** that
  produced the doc; operator user ids were dropped on export.

- **Window asymmetry.** The data window cuts on `createdAt`. A workshift in
  the window can reference a product whose creation predates the window —
  the sender should have backfilled most of those, but a small floor of
  cross-references may still be orphan. Filter on the join side if it
  matters: `{ "abas": { $exists: true } }` after a `$lookup`.

- **`platform.products.definitions` is intentionally absent.** That
  collection holds customer-side IP (drawings, customer numbers, recipes).
  Each step instance carries an embedded `persistedStepDefinition` snapshot,
  which is enough for analytics. The same step might be defined slightly
  differently across products if operators changed it between batches —
  group by `persistedStepDefinition.name` rather than by definition `_id`.

- **Configuration collections (`lines`, `stations`, `defectcode`) span
  the full history**, not just the data window. Their `createdAt` is the
  onboarding date — often years before the data window.

---

## When in doubt

- For a field's meaning, open `SCHEMA.md` (or `schema.json`) from the data
  drop — every entry has type, presence frequency, and a description where
  one was extractable.
- For domain orientation and joining patterns, see `RECEIVER.md` from the
  data drop.
- For implementation details of the redactions and aliasing, ask the data
  sender — those scripts live in a separate, private repo.
- For a runnable version of the queries above, see `examples/*.py`.
