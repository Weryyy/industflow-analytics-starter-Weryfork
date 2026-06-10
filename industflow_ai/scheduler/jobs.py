"""Background scheduler for the 'continuous analysis' part of the brief.

Generates a shift briefing shortly after each shift boundary (06:00 / 14:00 /
22:00) and a trend briefing nightly. Each run persists a report and an audit
record. Built on APScheduler's BackgroundScheduler so it lives inside the
FastAPI process (started/stopped via the app lifespan).
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..audit.log import record
from ..insights.anomaly import scrap_rate_anomalies
from ..narrator.report import (
    build_anomaly_report,
    build_shift_report,
    build_trend_report,
)

log = logging.getLogger("industflow_ai.scheduler")

# Shifts: 1->06-14, 2->14-22, 3->22-06. Run each report ~15 min after the
# shift ends so the data has settled.
_SHIFT_REPORT_HOURS = [14, 22, 6]


def _run_shift_report() -> None:
    try:
        doc = build_shift_report()
        log.info("shift report generated: %s", doc.get("_id"))
    except Exception:  # noqa: BLE001 - scheduler must not die on one failure
        log.exception("shift report failed")


def _run_trend_report() -> None:
    try:
        doc = build_trend_report()
        log.info("trend report generated: %s", doc.get("_id"))
    except Exception:  # noqa: BLE001
        log.exception("trend report failed")


def _run_anomaly_check() -> None:
    """Daily statistical check; a report is only narrated when something fires."""
    try:
        detection = scrap_rate_anomalies()
        if detection.get("findings"):
            doc = build_anomaly_report(detection)
            log.info("anomaly report generated: %s", doc.get("_id"))
        else:
            record("anomaly_check", result_summary={"findings": 0,
                   "insufficientData": detection.get("insufficientData", False)})
            log.info("anomaly check: nothing flagged")
    except Exception:  # noqa: BLE001
        log.exception("anomaly check failed")


def build_scheduler() -> BackgroundScheduler:
    """Configure (but do not start) the scheduler."""
    sched = BackgroundScheduler(timezone="Europe/Madrid")
    for hour in _SHIFT_REPORT_HOURS:
        sched.add_job(
            _run_shift_report,
            CronTrigger(hour=hour, minute=15),
            id=f"shift_report_{hour}",
            replace_existing=True,
        )
    sched.add_job(
        _run_trend_report,
        CronTrigger(hour=2, minute=0),
        id="trend_report_nightly",
        replace_existing=True,
    )
    sched.add_job(
        _run_anomaly_check,
        CronTrigger(hour=6, minute=30),
        id="anomaly_check_daily",
        replace_existing=True,
    )
    return sched
