# Industflow — analytics starter

A small Python package that imports an **Industflow** data slice into your
local MongoDB and runs the headline queries you'd want to start with. The
CLI command is `mip` (short for *manufacturing-intelligence package*).

## About Industflow

**Industflow** is a manufacturing-intelligence platform built by
**Industware s.r.o.** It connects the production floor — lines, stations,
operators, tools — and captures what's actually happening, piece by piece:

- **Production tracking.** Each product gets a serial number and is followed
  through every stage of its build (forming → assembly → testing → packing).
  Multiple stations can contribute to one product across one or more groups.
- **Step-level execution.** Steps are configured per product type by
  quality and process operators. Each step instance records timing, the
  station that ran it, OK/NOK status, captured measurements (electrical
  resistance, leak/tightness, thickness, vision checks), and a full retry
  history.
- **Shift management.** Three shifts per day per line, with automatic
  expected-vs-actual output reconciliation and downtime classification
  (planned vs unplanned, machine pause vs operator break, coded reasons).
- **Quality & traceability.** Defects are coded against a controlled
  codebook; products can be flagged as suspect for follow-up; first-piece
  and tester samples get extra checkpoints. A defect-history audit log
  preserves changes over time.

This repository is the receiver-side companion to a redacted data export
shared by an Industflow customer.

Built with [`uv`](https://github.com/astral-sh/uv). No virtualenv to manage,
no `pip install`, no global Python pollution.

## Prerequisites

- **MongoDB** running locally (or anywhere reachable). Default URI is
  `mongodb://localhost:27017/mip`. Override with `--uri` or `$MONGO_URI`.
- **uv** — install once: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- The data drop — a bundle from the sender containing `data/*.jsonl`,
  `schema.json`, `SCHEMA.md`, `RECEIVER.md`, and `MANIFEST.json`. Place
  the `.jsonl` files into `data/` (see [`data/README.md`](data/README.md)).

## Quickstart

```bash
# 1. fetch dependencies into a local virtualenv (uv handles it)
uv sync

# 2. import the data and create indexes
uv run mip import

# 3. one-page snapshot of what landed
uv run mip summary
```

That's it. From here, run any of the example scripts.

> **No local MongoDB?** A `docker-compose.yml` is included — `docker compose up -d`
> starts MongoDB 7 on `localhost:27017`. **No data drop yet?**
> `uv run python tools/gen_synthetic.py` generates a schema-conformant synthetic
> slice you can import and explore until the real `.jsonl` files arrive.

## AI layer

On top of this data layer there's an **AI intelligence layer** (`industflow_ai`)
that turns the data slice into a production-intelligence assistant — all running
**locally** (Ollama + LangChain + FastAPI), no cloud, no per-token cost:

- **Natural-language Q&A** — ask questions in plain language; the agent calls
  read-only tools (the aggregations in `queries.py`) plus a sandboxed
  `mongo_aggregate` escape hatch, and answers with concrete figures.
- **Automatic report narrator** — shift and trend briefings in plain language.
- **Continuous analysis** — a scheduler generates reports after each shift and
  nightly.
- **Auditable** — every answer and report is logged to `ai.audit`.
- **Web UI** — a single-page chat with a KPI charts panel, served at `/`.

```bash
uv sync --extra ai                                  # AI dependencies
uv run uvicorn industflow_ai.api.main:app           # API + scheduler + UI
# → web UI at http://localhost:8000/  (Swagger at /docs)
```

Needs Docker (MongoDB) and [Ollama](https://ollama.com) ≥ 0.24 with the
`qwen3:14b-q4_K_M` model. Full setup, endpoints, and safety model in
**[AI_LAYER.md](AI_LAYER.md)**.

## Example queries

Every script in `examples/` is independently runnable and prints a table.

```bash
uv run examples/01_outcomes.py            # scrap vs good vs in-flight
uv run examples/02_daily_scrap_rate.py    # day-by-day NOK %
uv run examples/03_loss_by_defect.py      # top defect codes
uv run examples/04_shift_comparison.py    # recent shifts
uv run examples/05_first_pass_yield.py    # FPY per step
uv run examples/06_step_cycle_time.py     # mean / p50 step duration
uv run examples/07_downtime_by_reason.py  # downtime minutes by reason
```

The example scripts are also self-contained — each one carries its own
PEP 723 dependency block, so this works too:

```bash
./examples/01_outcomes.py
```

## Customizing

`industflow_starter/queries.py` holds every aggregation. Each function takes a `db`
handle and returns a list of dicts. Easy to copy into a Jupyter notebook,
feed into pandas, or repurpose for a Grafana / Metabase dashboard.

```python
from industflow_starter.db import get_db
from industflow_starter.queries import daily_scrap_rate

rows = daily_scrap_rate(get_db())
# do whatever: pandas, plotly, csv...
```

## Re-importing

`mip import` is idempotent — it drops each target collection before
reloading. Run it again whenever the sender ships a fresh data drop.

## What's in the data

Four docs, depending on what you're after — the first two are in this repo,
the second two ship with the data drop:

- **[ABOUT_DATA.md](ABOUT_DATA.md)** — cookbook-style: model, collections,
  9 "try this" snippets, joining patterns, gotchas. Start here.
- **[AI_IDEAS.md](AI_IDEAS.md)** — eight concrete projects you can build
  with this data + an LLM (shift narrator, anomaly flagging, defect
  clustering, NL Q&A over operations, trend summarizer…), each with what
  feeds it, an implementation sketch, and honest caveats.
- **`SCHEMA.md`** (in the data drop) — every collection's fields with type,
  presence frequency, and a description where one was extractable. Open
  this when you want to know what a particular field means.
- **`RECEIVER.md`** (in the data drop) — full domain orientation, joining
  patterns, indexes, caveats list. The sender's reference document.

Both `SCHEMA.md` and `schema.json` are rendered from the same source —
`schema.json` is the machine-readable version (use it from code), `SCHEMA.md`
is the same content laid out for humans.

## Troubleshooting

- **`MONGO_URI must include a database name`** — your URI is missing `/dbname`
  at the end. Default uses `mip` after the host.
- **`bson.errors.InvalidBSON: ...`** — the JSONL files were probably modified
  in a way that broke Extended JSON. Re-fetch from the sender.
- **`$median` not recognized** — needs MongoDB 7.0+. Drop the `p50Sec` line
  in `industflow_starter/queries.py::step_cycle_time` if you're on older Mongo.
- **AI layer is slow (Ollama on CPU)** — `curl localhost:11434/api/ps` and check
  `size_vram` is non-zero. New NVIDIA GPUs (RTX 50-series / Blackwell) need
  Ollama ≥ 0.24; older builds silently fall back to CPU. If the CUDA backend
  goes missing after an auto-update, reinstall Ollama to restore it.
- **Garbled non-ASCII in a client (e.g. Czech step names)** — the API serves
  UTF-8; PowerShell 5.1 mis-decodes unless the console is UTF-8
  (`[Console]::OutputEncoding = [Text.Encoding]::UTF8`). Browsers render it fine.
