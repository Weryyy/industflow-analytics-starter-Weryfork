"""FastAPI entrypoint for the Industflow AI layer.

    uv run uvicorn industflow_ai.api.main:app --reload

Endpoints:
    GET  /                    -> redirects to the web UI (/ui/)
    GET  /health             Mongo + Ollama reachability
    POST /ask                natural-language Q&A over production data
    POST /report             generate a shift|trend|anomaly briefing
    GET  /reports            list persisted reports
    GET  /audit              recent audit records
    GET  /anomalies          deterministic scrap-rate anomaly check
    GET  /metrics/*          JSON data for the dashboard charts
The scheduler starts/stops with the app lifespan.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from industflow_starter import queries

from ..agent.agent import ask as agent_ask
from ..audit.log import recent as recent_audit
from ..config import AGENT_MODEL, OLLAMA_BASE_URL
from ..insights.anomaly import scrap_rate_anomalies
from ..mongo import get_db
from ..narrator.report import (
    build_anomaly_report,
    build_shift_report,
    build_trend_report,
    recent_reports,
)
from ..scheduler.jobs import build_scheduler
from ..serialize import jsonable

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class UTF8JSONResponse(JSONResponse):
    """JSON response that advertises charset=utf-8.

    Data contains non-ASCII (e.g. Czech step names). Without the explicit charset
    some clients (PowerShell 5.1's Invoke-RestMethod) decode the body as latin1
    and mangle the characters. The bytes are already UTF-8; this just labels them.
    """
    media_type = "application/json; charset=utf-8"


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = build_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Industflow AI layer", version="0.1.0", lifespan=lifespan,
              default_response_class=UTF8JSONResponse)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, examples=["which line performed worst this week?"])


class ReportRequest(BaseModel):
    type: Literal["shift", "trend", "anomaly"] = "shift"
    line_id: str | None = None


# --------------------------------------------------------------------------- #
# Core endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict:
    out: dict = {"mongo": "down", "ollama": "down", "model": AGENT_MODEL}
    try:
        get_db().command("ping")
        out["mongo"] = "ok"
    except Exception as e:  # noqa: BLE001
        out["mongoError"] = str(e)
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        names = [m["name"] for m in r.json().get("models", [])]
        out["ollama"] = "ok"
        out["modelLoaded"] = AGENT_MODEL in names
    except Exception as e:  # noqa: BLE001
        out["ollamaError"] = str(e)
    return out


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    try:
        return agent_ask(req.question)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/report")
def report(req: ReportRequest) -> dict:
    try:
        if req.type == "shift":
            return build_shift_report(line_id=req.line_id)
        if req.type == "anomaly":
            return build_anomaly_report()
        return build_trend_report()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/reports")
def reports(limit: int = 20, type: str | None = None) -> dict:
    return {"reports": recent_reports(limit=limit, report_type=type)}


@app.get("/audit")
def audit(limit: int = 50) -> dict:
    return {"audit": recent_audit(limit=limit)}


@app.get("/anomalies")
def anomalies() -> dict:
    """Deterministic scrap-rate anomaly check (no LLM involved)."""
    return scrap_rate_anomalies()


# --------------------------------------------------------------------------- #
# Metrics for the dashboard charts (read-only, reuse queries.py)
# --------------------------------------------------------------------------- #
def _line_names() -> dict[str, str]:
    return {str(d["_id"]): d.get("name")
            for d in get_db()["lines"].find({"deleted": False})}


@app.get("/metrics/scrap-trend")
def m_scrap_trend(days: int = 30) -> dict:
    rows = queries.daily_scrap_rate(get_db())[-days:]
    points = [{"day": jsonable(r["day"])[:10], "scrapRate": r["scrapRate"],
               "total": r["total"], "nok": r["nok"]} for r in rows]
    return {"points": points}


@app.get("/metrics/defects")
def m_defects(limit: int = 10) -> dict:
    rows = queries.loss_by_defect(get_db(), limit=limit)
    return {"defects": [{"defectCode": r["defectCode"], "count": r["count"]} for r in rows]}


@app.get("/metrics/worst-fpy")
def m_worst_fpy(min_attempts: int = 200, limit: int = 10) -> dict:
    rows = [r for r in queries.first_pass_yield(get_db())
            if (r.get("total") or 0) >= min_attempts]
    rows.sort(key=lambda r: r.get("fpy", 1.0))
    return {"steps": [{"stepName": r["stepName"], "fpy": r["fpy"], "total": r["total"]}
                      for r in rows[:limit]]}


@app.get("/metrics/shift-output")
def m_shift_output(limit: int = 15) -> dict:
    names = _line_names()
    # Over-fetch then keep only shifts that actually ran (the most recent shifts
    # can be empty future placeholders with created=0); show newest `limit`
    # in chronological order for a left-to-right time feel.
    rows = [r for r in queries.shift_comparison(get_db(), limit=400)
            if (r.get("created") or 0) > 0]
    rows = list(reversed(rows[:limit]))
    out = []
    for r in rows:
        line = names.get(str(r.get("lineId"))) or "line?"
        out.append({
            "label": f"{line} {jsonable(r.get('date'))[:10]} S{r.get('shiftNumber')}",
            "created": r.get("created"),
            "expected": r.get("expectedCreatingOutput"),
            "fulfillment": r.get("creatingFulfillment"),
        })
    return {"shifts": out}


# --------------------------------------------------------------------------- #
# Web UI (served from industflow_ai/web)
# --------------------------------------------------------------------------- #
@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


app.mount("/ui", StaticFiles(directory=WEB_DIR, html=True), name="ui")
