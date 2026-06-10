# Industflow AI layer (`industflow_ai`)

An AI intelligence layer on top of the `industflow_starter` data layer, built per
`AI_to_digitalization_system.pdf`. It turns the production data slice into:

- **Natural-language Q&A** over production data (LangChain agent + Ollama).
- **Automatic shift/trend report narrator** (plain-language briefings).
- **Continuous analysis** via a scheduler.
- **Auditability**: every answer and report is logged.

Everything runs **locally** — Ollama for inference, MongoDB in Docker. No cloud,
no per-token cost, full data privacy (the project brief's "local-first" goal).

## Architecture

```
FastAPI (industflow_ai/api)        REST: /ask /report /reports /audit /health
  ├── agent/      LangChain create_agent + ChatOllama; tools wrap queries.py
  │               + mongo_aggregate (sandboxed read-only escape hatch)
  ├── narrator/   aggregations -> LLM -> advisory briefing (shift | trend)
  ├── safety/     pipeline allow-list, forced $limit, timeout (read-only)
  ├── audit/      ai.audit — every generation/query recorded
  ├── scheduler/  APScheduler — shift reports (14/22/06) + nightly trend
  ├── config.py   all settings, env-overridable
  └── mongo.py    pooled DB handle (wraps industflow_starter.db)

industflow_starter/   reused unchanged (db, queries, importer)
tools/gen_synthetic.py   synthetic data generator (until the real drop arrives)
docker-compose.yml       mongo:7
```

## Prerequisites

- **Docker Desktop** running (for MongoDB).
- **Ollama ≥ 0.24** running with the models pulled:
  `qwen3:14b-q4_K_M` (agent) and `bge-m3:latest` (embeddings, future use).
  > GPU note: RTX 50-series (Blackwell) needs Ollama ≥ 0.24 — older builds fall
  > back to CPU (~4 tok/s vs ~87 tok/s on a 5080). Check with `ollama ps`:
  > `size_vram` must be non-zero.
- **uv** for Python deps.

## Setup

```bash
# 1. Mongo
docker compose up -d

# 2. deps (includes the AI extras)
uv sync --extra ai

# 3. data — synthetic for now (swap in the real drop later, same flow)
uv run python tools/gen_synthetic.py
uv run mip import
uv run mip summary           # sanity check

# 4. run the API (starts the scheduler too)
uv run uvicorn industflow_ai.api.main:app --reload
# web UI at http://localhost:8000/  (Swagger at /docs)
```

## Web UI

A single-page chat UI is served at **`/`** (→ `/ui/`), built into
`industflow_ai/web/` (vanilla JS, no build step; Chart.js vendored locally under
`web/vendor/`, no external CDN). Features:

- **Chat** — ask in natural language; answers show which tools the agent used.
- **Report buttons** — generate a shift or trend briefing inline.
- **Charts toggle** — a checkbox opens a KPI panel with four charts: daily scrap
  rate, top defect codes, worst first-pass-yield steps, and output by shift
  (created vs expected). Data comes from the `/metrics/*` endpoints.

Configuration is via env vars (see `.env.example`): model, Mongo URI, report
language (`REPORT_LANG=en|es`), sandbox limits, baseline windows.

## Endpoints

| Method | Path       | What |
|--------|------------|------|
| GET    | `/`        | web UI (redirects to `/ui/`) |
| GET    | `/health`  | Mongo + Ollama reachability, model loaded? |
| POST   | `/ask`     | `{ "question": "..." }` → agent answer + tools used |
| POST   | `/report`  | `{ "type": "shift"\|"trend", "line_id"?: "..." }` → briefing |
| GET    | `/reports` | persisted reports (newest first) |
| GET    | `/audit`   | recent audit records |
| GET    | `/metrics/scrap-trend` | daily scrap rate series (chart) |
| GET    | `/metrics/defects` | top defect codes (chart) |
| GET    | `/metrics/worst-fpy` | worst first-pass-yield steps (chart) |
| GET    | `/metrics/shift-output` | recent shift output vs expected (chart) |

```bash
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question":"which step has the lowest first pass yield?"}'

curl -s localhost:8000/report -H 'content-type: application/json' \
  -d '{"type":"shift"}'
```

## Safety model

- The agent only ever **reads**. Predefined tools are fixed aggregations from
  `industflow_starter/queries.py`.
- The `mongo_aggregate` escape hatch passes every pipeline through
  `safety/sandbox.py`: collection allow-list, stage allow-list (applied
  recursively into `$facet` and `$lookup` sub-pipelines), `$lookup` restricted
  to the same collection allow-list (a join cannot escape into e.g. `ai.audit`),
  recursive rejection of write/exec stages (`$out`, `$merge`, `$function`,
  `$where`, …), an always-enforced `$limit`, and a query timeout.
- Per the brief, the AI **interprets and summarizes** — it does not make
  operational decisions; report wording is advisory.

## Models

`qwen3:14b-q4_K_M` (~10 GB) fits fully on a 16 GB GPU and has native tool-calling.
Swap via `AGENT_MODEL`. `deepseek-r1` is a reasoner (weaker at tool-calling) and
is not recommended for the agent. Embeddings (`bge-m3`) are reserved for a later
phase (e.g. defect-sequence clustering, AI_IDEAS.md #3).

## Roadmap (phased)

- ✅ Phase 1 — tool layer + LLM + sandbox
- ✅ Phase 2 — narrator + audit + scheduler
- ✅ Phase 3 — Q&A agent + FastAPI
- ⬜ Later — embeddings/clustering, real data drop, auth, web chat UI
