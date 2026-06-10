"""Statistical anomaly detection over the daily scrap-rate series.

Per the brief ("detects patterns, anomalies, and bottlenecks") the detection
itself is deterministic — a z-score against a rolling baseline — so a flag
never depends on LLM judgement. The LLM only narrates findings afterwards
(see narrator.report.build_anomaly_report).

`detect` is pure (takes the series, returns findings) so it is unit-testable
without a database; `scrap_rate_anomalies` wraps it with the live query.
"""
from __future__ import annotations

from statistics import mean, pstdev
from typing import Any

from industflow_starter import queries

from ..config import (
    ANOMALY_MIN_TOTAL,
    ANOMALY_RECENT_DAYS,
    ANOMALY_Z_THRESHOLD,
    TREND_BASELINE_DAYS,
)
from ..mongo import get_db
from ..serialize import jsonable

# Below this many baseline days a z-score is statistically meaningless.
_MIN_BASELINE_DAYS = 5


def detect(series: list[dict], *, baseline_days: int = TREND_BASELINE_DAYS,
           recent_days: int = ANOMALY_RECENT_DAYS,
           z_threshold: float = ANOMALY_Z_THRESHOLD,
           min_total: int = ANOMALY_MIN_TOTAL) -> dict[str, Any]:
    """Flag recent days whose scrap rate sits >= z_threshold sigmas above the
    rolling baseline. `series` is `queries.daily_scrap_rate` output (oldest
    first). Days with fewer than `min_total` completed products are ignored
    on both sides (a 1-of-2 scrap day is noise, not an anomaly).
    """
    usable = [r for r in series
              if r.get("scrapRate") is not None and (r.get("total") or 0) >= min_total]
    recent = usable[-recent_days:]
    baseline = usable[-(baseline_days + recent_days):-recent_days] if recent else []

    out: dict[str, Any] = {
        "metric": "dailyScrapRate",
        "baselineDays": baseline_days,
        "recentDays": recent_days,
        "zThreshold": z_threshold,
        "minTotal": min_total,
        "baseline": None,
        "findings": [],
    }
    if len(baseline) < _MIN_BASELINE_DAYS:
        out["insufficientData"] = True
        return out

    rates = [r["scrapRate"] for r in baseline]
    mu, sigma = mean(rates), pstdev(rates)
    out["baseline"] = {"days": len(baseline), "avgScrapRate": round(mu, 4),
                       "stdDev": round(sigma, 5)}
    if sigma == 0:
        return out

    for r in recent:
        z = (r["scrapRate"] - mu) / sigma
        if z >= z_threshold:
            out["findings"].append({
                "day": jsonable(r.get("day")),
                "scrapRate": round(r["scrapRate"], 4),
                "total": r.get("total"),
                "nok": r.get("nok"),
                "zScore": round(z, 2),
                "baselineAvg": round(mu, 4),
            })
    return out


def scrap_rate_anomalies(db=None, **kwargs) -> dict[str, Any]:
    """Run `detect` over the live daily scrap-rate series."""
    return detect(queries.daily_scrap_rate(db if db is not None else get_db()),
                  **kwargs)
