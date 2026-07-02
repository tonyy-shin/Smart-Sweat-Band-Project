"""Test thermal.py"""

import pytest

from ssb_backend.algorithm.thermal import(
    THERMAL_ALERT_MARGIN_C_PER_S,
    ThermalResult,
    compute_thermal_recovery,
)
from ssb_backend.history import save_session




# helpers ------------------------------------------------------------------
def _sample(timestamp_ms, skin_temp_c):
    return {"timestamp_ms": timestamp_ms, "skin_temp_c": skin_temp_c}

def _seed_history(db, slopes):
    """Save one session per slope"""
    for i, slope in enumerate(slopes):
        save_session(
            {"thermal_slope": slope},
            db_path=db,
            timestamp=f"2026-07-02T00:00:{i:02d}",
        )

def _cooling_samples(sloper_c_per_s, n=4, step_ms=100_000, start_temp=36.0):
    """Perfectly linear skin temp series with given slope"""
    return [
        _sample(i * step_ms, start_temp + sloper_c_per_s * (i * step_ms / 1000.0))
        for i in range(n)
    ]


# tests -----------------------------------------------------------------------
def test_linear_decrease_no_history(tmp_path):
    db = tmp_path / "ssb_history.db"
    samples = _cooling_samples(-0.001)

    result = compute_thermal_recovery(samples, db_path=db)

    assert result.current_slope == pytest.approx(-0.001)
    assert result.baseline_slope is None
    assert result.sessions_used == 0
    assert result.recommendation == "passive_rest"
    assert result.insufficient_baseline is True


def test_slower_than_baseline_recommends_active_cooling(tmp_path):
    db = tmp_path / "ssb_history.db"
    _seed_history(db, [-0.002, -0.003, -0.004])  # mean baseline -0.003
    samples = _cooling_samples(0.0)  # flat temps: no cooling this session

    result = compute_thermal_recovery(samples, db_path=db)

    assert result.baseline_slope == pytest.approx(-0.003)
    assert result.sessions_used == 3
    assert result.recommendation == "active_cooling"
    assert result.insufficient_baseline is False


def test_at_baseline_recommends_passive_rest(tmp_path):
    db = tmp_path / "ssb_history.db"
    _seed_history(db, [-0.002, -0.003, -0.004])  # mean baseline -0.003
    samples = _cooling_samples(-0.0035)  # cooling faster than baseline

    result = compute_thermal_recovery(samples, db_path=db)

    assert result.recommendation == "passive_rest"
    assert result.insufficient_baseline is False


def test_exact_margin_boundary_stays_passive(tmp_path):
    # current - baseline lands exactly on the margin; strict > means no
    # alert. Values chosen so every float op is exact: baseline is 0.0
    # and a two-point rise of exactly the margin over exactly 1 s makes
    # linregress return THERMAL_ALERT_MARGIN_C_PER_S bit-for-bit.
    db = tmp_path / "ssb_history.db"
    _seed_history(db, [0.0, 0.0, 0.0])
    samples = [_sample(0, 0.0), _sample(1000, THERMAL_ALERT_MARGIN_C_PER_S)]

    result = compute_thermal_recovery(samples, db_path=db)

    assert result.current_slope == THERMAL_ALERT_MARGIN_C_PER_S
    assert result.baseline_slope == 0.0
    assert result.recommendation == "passive_rest"


def test_empty_samples(tmp_path):
    db = tmp_path / "ssb_history.db"

    assert compute_thermal_recovery([], db_path=db) == ThermalResult(
        current_slope=None,
        baseline_slope=None,
        sessions_used=0,
        recommendation="insufficient_data",
        insufficient_baseline=True,
    )


def test_single_sample(tmp_path):
    db = tmp_path / "ssb_history.db"

    assert compute_thermal_recovery([_sample(0, 36.0)], db_path=db) == ThermalResult(
        current_slope=None,
        baseline_slope=None,
        sessions_used=0,
        recommendation="insufficient_data",
        insufficient_baseline=True,
    )


def test_sessions_used_skips_invalid_rows(tmp_path):
    db = tmp_path / "ssb_history.db"
    _seed_history(db, [-0.001, -0.002, -0.003, None])
    save_session({"score": 87.5}, db_path=db, timestamp="2026-07-02T00:01:00")

    result = compute_thermal_recovery(_cooling_samples(-0.002), db_path=db)

    assert result.sessions_used == 3
    assert result.baseline_slope == pytest.approx(-0.002)
    assert result.insufficient_baseline is False