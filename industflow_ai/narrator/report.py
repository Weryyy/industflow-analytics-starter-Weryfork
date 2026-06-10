"""Generate shift / trend briefings from aggregated production data.

Per AI_IDEAS.md (#1, #6) the model receives ONLY aggregated numbers — never raw
documents — and its output is advisory ("worth checking"), never prescriptive.
Reports are persisted to `ai.reports` and logged to `ai.audit`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from industflow_starter import queries
from ..audit.log import record
from ..config import (
    AGENT_MODEL,
    REPORT_LANG,
    REPORTS_COLLECTION,
    SHIFT_BASELINE_DAYS,
    TREND_BASELINE_DAYS,
)
from ..agent.llm import get_chat_model
from ..insights.anomaly import scrap_rate_anomalies
from ..mongo import get_db
from ..serialize import jsonable

_LANG_NAME = {"es": "Spanish", "en": "English"}

_SYSTEM = (
    "You are a production-intelligence analyst for a manufacturing line. "
    "Write a concise (2-3 paragraph) briefing from the aggregated "
    "JSON metrics provided. Rules: use ONLY the numbers given; do not invent "
    "values; quote concrete figures; keep the tone advisory ('worth checking', "
    "'may warrant review'), never prescriptive or alarmist; the AI does not make "
    "operational decisions. Write in {lang}."
)


def _baseline_scrap(db) -> dict[str, Any]:
    """Average scrap rate over the recent baseline window."""
    series = queries.daily_scrap_rate(db)
    recent = [r["scrapRate"] for r in series[-SHIFT_BASELINE_DAYS:]
              if r.get("scrapRate") is not None]
    return {
        "windowDays": SHIFT_BASELINE_DAYS,
        "avgScrapRate": round(mean(recent), 4) if recent else None,
        "dailySeries": jsonable(series[-SHIFT_BASELINE_DAYS:]),
    }


def _narrate(context: dict, *, report_type: str, scope: dict) -> dict:
    """Run the LLM over context, persist, audit, and return the report doc."""
    llm = get_chat_model()
    lang = _LANG_NAME.get(REPORT_LANG, "English")
    messages = [
        SystemMessage(_SYSTEM.format(lang=lang)),
        HumanMessage(
            f"Report type: {report_type}\n"
            f"Aggregated metrics (JSON):\n{jsonable(context)}\n\n"
            "Write the briefing now."
        ),
    ]
    text = llm.invoke(messages).content

    doc = {
        "ts": datetime.now(timezone.utc),
        "type": report_type,
        "scope": jsonable(scope),
        "lang": REPORT_LANG,
        "model": AGENT_MODEL,
        "context": jsonable(context),
        "text": text,
    }
    res = get_db()[REPORTS_COLLECTION].insert_one(doc)
    doc["_id"] = res.inserted_id
    record("report", input={"type": report_type, "scope": scope},
           result_summary={"reportId": str(res.inserted_id), "chars": len(text)})
    return jsonable(doc)


def _line_names(db) -> dict[str, str]:
    """Map line id (str) -> alias name (e.g. line_1) so briefings read naturally."""
    return {str(d["_id"]): d.get("name") for d in db["lines"].find({"deleted": False})}


def build_shift_report(line_id: str | None = None) -> dict:
    """Briefing for the most recent shift(s), optionally scoped to one line."""
    from bson import ObjectId
    db = get_db()
    oid = ObjectId(line_id) if line_id else None
    shifts = queries.shift_comparison(db, line_id=oid, limit=3)
    names = _line_names(db)
    shifts = [{**jsonable(s), "line": names.get(str(s.get("lineId")))} for s in shifts]
    context = {
        "recentShifts": shifts,
        "topDefects": queries.loss_by_defect(db, limit=5),
        "downtimeByReason": queries.downtime_by_reason(db),
        "scrapBaseline": _baseline_scrap(db),
    }
    return _narrate(context, report_type="shift", scope={"lineId": line_id})


def build_trend_report(top_n: int = 10, min_volume: int = 100) -> dict:
    """Trend briefing: recent KPIs vs the rolling baseline.

    Real data has ~1500 distinct steps, so we never feed the full step lists to
    the model. We surface the most informative slices: the worst-FPY steps and
    the highest-volume steps (both filtered to a meaningful sample size).
    """
    db = get_db()
    series = queries.daily_scrap_rate(db)

    fpy = [r for r in queries.first_pass_yield(db) if (r.get("total") or 0) >= min_volume]
    worst_fpy = sorted(fpy, key=lambda r: r.get("fpy", 1.0))[:top_n]

    cycle = [r for r in queries.step_cycle_time(db) if (r.get("n") or 0) >= min_volume]
    busiest_steps = sorted(cycle, key=lambda r: r.get("n", 0), reverse=True)[:top_n]

    context = {
        "outcomes": queries.outcomes(db),
        "scrapTrend": jsonable(series[-TREND_BASELINE_DAYS:]),
        "worstFirstPassYield": worst_fpy,
        "busiestStepsCycleTime": busiest_steps,
        "topDefects": queries.loss_by_defect(db, limit=10),
        "baselineDays": TREND_BASELINE_DAYS,
    }
    return _narrate(context, report_type="trend", scope={"windowDays": TREND_BASELINE_DAYS})


def build_anomaly_report(detection: dict | None = None) -> dict:
    """Briefing over the statistical scrap-rate anomaly check.

    The detection itself is deterministic (insights.anomaly); the LLM only
    narrates the findings — or states that nothing unusual was flagged.
    """
    db = get_db()
    if detection is None:
        detection = scrap_rate_anomalies(db)
    series = queries.daily_scrap_rate(db)
    context = {
        "anomalyDetection": detection,
        "recentScrapTrend": jsonable(series[-14:]),
    }
    return _narrate(context, report_type="anomaly",
                    scope={"zThreshold": detection.get("zThreshold"),
                           "findings": len(detection.get("findings", []))})


def recent_reports(limit: int = 20, report_type: str | None = None) -> list[dict]:
    """List persisted reports (newest first), optionally filtered by type."""
    q = {"type": report_type} if report_type else {}
    cur = get_db()[REPORTS_COLLECTION].find(q).sort("ts", -1).limit(limit)
    return [jsonable(d) for d in cur]
