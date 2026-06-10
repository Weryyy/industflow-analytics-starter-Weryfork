"""Unit tests for the deterministic scrap-rate anomaly detector (pure)."""
from datetime import datetime, timedelta

from industflow_ai.insights.anomaly import detect


def _series(days: int, rate: float = 0.05, total: int = 100, wobble: float = 0.002):
    base = datetime(2026, 5, 1)
    return [{"day": base + timedelta(days=i),
             "scrapRate": rate + wobble * (i % 3),
             "total": total,
             "nok": int(total * rate)} for i in range(days)]


def test_flags_spike_above_threshold():
    series = _series(30)
    series.append({"day": datetime(2026, 6, 1), "scrapRate": 0.25,
                   "total": 100, "nok": 25})
    out = detect(series, z_threshold=2.0)
    assert len(out["findings"]) == 1
    f = out["findings"][0]
    assert f["scrapRate"] == 0.25
    assert f["zScore"] >= 2.0
    assert out["baseline"]["days"] > 0


def test_quiet_series_yields_no_findings():
    out = detect(_series(30))
    assert out["findings"] == []
    assert "insufficientData" not in out


def test_insufficient_history_is_reported_not_flagged():
    out = detect(_series(4))
    assert out["insufficientData"] is True
    assert out["findings"] == []


def test_low_volume_days_are_ignored():
    series = _series(30)
    # Huge rate but only 2 products completed: noise, not an anomaly.
    series.append({"day": datetime(2026, 6, 1), "scrapRate": 0.5,
                   "total": 2, "nok": 1})
    assert detect(series, min_total=20)["findings"] == []


def test_zero_variance_baseline_does_not_divide_by_zero():
    series = _series(30, wobble=0.0)
    series.append({"day": datetime(2026, 6, 1), "scrapRate": 0.30,
                   "total": 100, "nok": 30})
    out = detect(series)
    assert out["findings"] == []  # sigma == 0 -> no z-score, no crash


def test_days_missing_rate_are_skipped():
    series = _series(30)
    series.append({"day": datetime(2026, 6, 1), "scrapRate": None, "total": 0})
    out = detect(series)
    assert out["findings"] == []
