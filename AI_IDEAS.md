# What you can build with this data + AI

The dataset is small enough to fit a laptop, structured enough to feed a
notebook, and rich enough that several useful AI projects fall out
naturally. This is a starter list of what's realistic on this slice — not
a roadmap, just ideas.

> **Ground rule from the project brief.** AI here is meant for
> *interpretation* and *summarization* — surfacing patterns, narrating
> trends, flagging deviations. It does **not** make operational decisions,
> override production data, or define KPIs autonomously. Every project
> below respects that boundary.

## 1. Shift-end narrative writer

**Goal.** A 2–3 paragraph plain-language briefing at the end of every
shift: "Shift 2 on line_1 produced 312 of 350 expected (89%). Scrap rate
was 4.7%, up from the 7-day average of 3.1%. The dominant defect was
`code_034` (12 of 19 NOKs). 28 minutes of downtime were logged against
`MACHINE_PAUSE`. Step `<step_name>` had a notably long p99 cycle time."

**What feeds it.** A few of the existing aggregations from
`industflow_starter/queries.py` — `outcomes`, `daily_scrap_rate`,
`loss_by_defect`, `shift_comparison`, `downtime_by_reason` — windowed to
the last shift, plus a 7-day rolling baseline.

**Implementation sketch.**

```python
from industflow_starter.db import get_db
from industflow_starter.queries import outcomes, loss_by_defect, downtime_by_reason
import anthropic   # or openai, ollama, etc.

db = get_db()
context = {
    "shift": shift_comparison(db, line_id=line, limit=1)[0],
    "defects": loss_by_defect(db, limit=5),
    "downtime": downtime_by_reason(db),
    "baseline": daily_scrap_rate(db)[-7:],
}
prompt = f"Write a 2-paragraph shift briefing from this JSON: {context}"
# call your model of choice
```

**Caveats.** The model needs *only* the aggregated numbers; never feed it
raw documents (overkill, slow, leaks). Keep its output advisory, not
prescriptive — phrase as "worth checking" rather than "fix this".

## 2. Anomaly flagging on step cycle time

**Goal.** A weekly report of step instances whose duration falls outside
the normal distribution for that step + station combination — a candidate
for "operator needed help" or "machine hesitation".

**What feeds it.** `products.steps` documents where `lastData.startAt`
and `lastData.endAt` exist (~95% of completed steps). The query in
`examples/06_step_cycle_time.py` already computes mean/p50; extend with
a z-score per `(persistedStepDefinition.name, lastData.createdFrom)` group.

**Implementation sketch.**

- Pure-stats version: compute mean and stdev per group, flag where
  `(duration - mean) / stdev > 3`. No ML required.
- LLM-on-top version: feed the top-20 outliers to a model and ask it to
  spot patterns ("most outliers happen on shift 3" / "all on the same
  station").

**Caveats.** Cycle time is noisy when sample size is small. Filter groups
with `n >= 50` before computing thresholds. Also: a long step is not
always a problem — it can mean a manual approval was waiting; the
`mustBeApproved` flag on `persistedStepDefinition` tells you when.

## 3. Defect-pattern clustering by step-failure sequence

**Goal.** Discover natural "defect families": groups of products that
failed in similar ways, even if they got different defect codes.

**What feeds it.** For each NOK product, the ordered sequence of step
names where `status: false` — built by joining `products.steps` to its
parent product and sorting by `lastData.startAt`.

**Implementation sketch.**

1. For each NOK product, build a string like
   `"forming_check NOK -> assembly_torque NOK -> tightness_test NOK"`.
2. Embed those sequences with a sentence-transformer or OpenAI
   embeddings. (Sequences are short — embedding works well even though
   the tokens are made-up step names.)
3. Cluster (k-means or HDBSCAN). Each cluster is a candidate "failure
   mode".
4. Optionally: ask an LLM to invent a short label for each cluster from
   the constituent sequences.

**Caveats.** Step names are aliased *labels*, not natural language —
embeddings will cluster on co-occurrence patterns, which is exactly what
you want. Don't expect human-meaningful semantic similarity.

## 4. Natural-language Q&A over the dataset

**Goal.** Let a plant manager ask questions in plain language: "What's
our worst-performing line this week?" "Which station has the most leak
failures?" "How does shift 3 compare to shift 1?"

**What feeds it.** A function-calling LLM (Claude, GPT-4, local model
via ollama) wired to a small set of read-only tools — basically the
functions in `industflow_starter/queries.py`, plus a generic "run an aggregation"
escape hatch for queries you didn't pre-build.

**Implementation sketch.**

```python
TOOLS = [
    {"name": "outcomes",          "fn": queries.outcomes},
    {"name": "loss_by_defect",    "fn": queries.loss_by_defect},
    {"name": "shift_comparison",  "fn": queries.shift_comparison},
    {"name": "first_pass_yield",  "fn": queries.first_pass_yield},
    {"name": "downtime_by_reason","fn": queries.downtime_by_reason},
    # plus a `mongo_aggregate(collection, pipeline)` for ad-hoc
]
```

The LLM picks tools, you run them, feed the result back, it answers.
This pattern (function-calling + read-only Mongo) is well-trodden.

**Caveats.** Strongly limit the ad-hoc aggregation tool — sandbox the
allowed pipeline stages, cap result size, time-out long queries. An LLM
will happily emit a `$lookup` cross-product that scans every step doc.

## 5. Predict step outcome from measurement

**Goal.** Given the captured measurement on a step (`tightness.value`,
`thickness.value`, `resistance.value`), predict the OK/NOK outcome — and
identify the threshold each measurement is implicitly being compared
against.

**What feeds it.** Steps where the relevant measurement field exists.
The simplest model is logistic regression per step + measurement type;
the second-simplest is a decision tree, which directly tells you the
threshold.

**Caveats.** This is the **most redacted** project on this list. The
heavy process telemetry (PLC values, screw torques, machine payloads,
fuel-gauge serials) was dropped on export, so you're working with three
or four kept numerics. That's enough for a *demonstration* — train a
classifier on `tightness.value → status`, show the implicit threshold —
but not enough for production prediction across all step types. Don't
oversell it.

## 6. Trend narrator (scheduled summarizer)

**Goal.** Run nightly. Compare yesterday's KPIs to the 30-day rolling
baseline. Write a short note flagging anything that moved meaningfully.
Email or Slack it to the ops lead.

**What feeds it.** A handful of windowed aggregations + an LLM doing
the "is this delta worth mentioning?" judgment call.

**Why it works on this dataset.** The data has clear time signatures
(shift boundaries, day boundaries, weekday/weekend patterns). Comparing
"this shift vs last 21 of the same shift type" is a natural unit of
analysis and gives the LLM strong context.

## 7. Operator-feedback simulator (research-only)

**Goal.** Given a product mid-build (some steps done, some pending),
predict the most likely *next* failure based on step-by-step patterns
in completed products of the same type.

**What feeds it.** Sequences of step outcomes per product, grouped by
`abas` (product type alias). Sequence model (Markov chain, simple LSTM,
or transformer over step IDs).

**Caveats.** Strictly research / exploration. Per the project brief,
*the AI does not make operational decisions* — this kind of prediction
must remain advisory inside a notebook, never wired into a station
terminal as an instruction.

## 8. Defect-code consolidation hint

**Goal.** Surface defect codes that are *used identically* — same step
context, same station, same product types. Often a sign that two codes
mean the same thing in practice and should be merged in the codebook.

**What feeds it.** For each defect code, the distribution over (step,
station, product type) tuples. Cosine similarity between distributions
identifies near-duplicate codes.

**Caveats.** The defect-code *descriptions* were redacted on export, so
you can't read the codes' meanings — only their behavior. That's fine for
flagging candidates; the human reviewer reads the actual descriptions
back at the source system.

## What's harder because of the redaction

Be realistic about what *isn't* in this dataset:

- **No process telemetry.** Temperatures, pressures, torque values, raw
  PLC payloads — all dropped. Anything requiring physical-process
  modeling won't work here.
- **No customer / order / part identifiers.** `abas`, `orderNumber` and
  product-definition fields are aliased or absent. You can't analyze
  defect rates *per customer* or *per part drawing*.
- **No operator identity.** `createdBy` / `users` were dropped. You
  can't analyze operator skill, training effects, or assign blame.
- **No definitions collection.** The product-type catalog with its
  drawings, recipes, marking criteria isn't shared. Each step instance
  carries enough metadata for analytics, but you can't reverse-engineer
  the active configuration of a product type.

Anything in the redacted set is genuinely off-limits. The list above
intentionally avoids those areas.

## Where to start

If you have one afternoon: build **#6 (trend narrator)**. Lowest effort,
high value, exercises the data + an LLM in the simplest possible way.

If you want to demo something visual: **#3 (defect clustering)** —
embeddings → 2-D projection (UMAP) → coloured scatter plot. The
clusters tend to come out clean enough to look impressive.

If you want to demo something interactive: **#4 (natural-language Q&A)**.
Minimum viable in a few hours with `industflow_starter.queries` as the toolset.
