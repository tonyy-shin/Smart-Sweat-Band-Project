"""Test scoring.py"""

import sqlite3

import pytest

from ssb_backend import history
from ssb_backend.scoring import (
    NEUTRAL_SUBSCORE,
    RecoveryReadinessResult,
    compute_recovery_readiness,
)
from ssb_backend.algorithm.rehydration import RehydrationResult
from ssb_backend.algorithm.thermal import ThermalResult, compute_thermal_recovery
from ssb_backend.algorithm.sweat_rate import SweatRateResult
from ssb_backend.algorithm.electrolyte_intensity import (
    GsrElectrolyteResult,
    compute_gsr_electrolyte_adjustment,
)

# result-dataclass factories --------------------------------------------------
# Only the field each subscore actually reads matters; the rest is filler so
# the dataclass constructs. Defaults are chosen so a bare call lands every
# subscore strictly inside (0, 100)
# no clamp fires unless a test asks for it.
def _rehydration(total_fluid_ml=300.0, status="ok"):
    # _rehydration_subscore reads only total_fluid_ml (None -> neutral fallback).
    return RehydrationResult(
        sweat_volume_ml=None if total_fluid_ml is None else total_fluid_ml / 1.5,
        total_fluid_ml=total_fluid_ml,
        total_sodium_mg=None if total_fluid_ml is None else 100.0,
        schedule=[],
        sample_count=2,
        status=status,
        electrolyte_tier="typical",
        calibration_state={"volume": "provisional", "sodium": "gsr_adjusted"},
    )

def _thermal(current_slope=-0.003, baseline_slope=-0.001):
    # _thermal_subscore reads current_slope/baseline_slope (either None -> neutral).
    return ThermalResult(
        current_slope=current_slope,
        baseline_slope=baseline_slope,
        sessions_used=3,
        recommendation="passive_rest",
        insufficient_baseline=False,
    )

def _sweat(mean_sri=0.04, peak_sri=0.08):
    # _sri_subscore reads only mean_sri (None -> neutral fallback).
    return SweatRateResult(mean_sri=mean_sri, peak_sri=peak_sri, sample_count=2)

def _gsr(current_intensity=0.25):
    # scoring reads only current_intensity (-> the gsr_drop_intensity history key).
    return GsrElectrolyteResult(
        current_intensity=current_intensity,
        baseline_intensity=0.25,
        modifier=1.0,
        tier="typical",
        sessions_used=3,
        insufficient_baseline=False,
    )

# sample lists for the two history readers in the round-trip test -------------
def _skin_samples():
    return [
        {"timestamp_ms": 0, "skin_temp_c": 36.0},
        {"timestamp_ms": 100_000, "skin_temp_c": 35.5},
    ]

def _gsr_samples():
    return [
        {"timestamp_ms": 0, "gsr_raw": 1500},
        {"timestamp_ms": 1000, "gsr_raw": 1500},
    ]

def _seed_sessions(db, n):
    """Seed n prior rows carrying both CONTRACT keys."""
    for i in range(n):
        history.save_session(
            {"thermal_slope": -0.001, "gsr_drop_intensity": 0.25},
            db_path=db,
            timestamp=f"2026-07-07T00:00:{i:02d}",
        )

# tests -----------------------------------------------------------------------
def test_composite_is_weighted_sum_of_subscores(tmp_path):
    db = tmp_path / "ssb_history.db"
    # rehydration: 100*(1 - 300/1500) = 80
    # thermal:     50 + 5000*(-0.001 - -0.003) = 50 + 10 = 60
    # sri:         100*(1 - 0.04/0.1) = 60
    # composite:   0.5*80 + 0.3*60 + 0.2*60 = 70
    result = compute_recovery_readiness(
        _rehydration(), _thermal(), _sweat(), _gsr(), db_path=db
    )

    assert isinstance(result, RecoveryReadinessResult)
    assert result.rehydration_score == pytest.approx(80.0)
    assert result.thermal_score == pytest.approx(60.0)
    assert result.sri_score == pytest.approx(60.0)
    assert result.score == pytest.approx(70.0)

def test_score_always_emitted_when_all_insufficient(tmp_path):
    db = tmp_path / "ssb_history.db"
    # Every subsignal in its insufficient/None state -> each helper falls back
    # to NEUTRAL_SUBSCORE; the composite is a real float, never None.
    result = compute_recovery_readiness(
        _rehydration(total_fluid_ml=None, status="insufficient_data"),
        _thermal(current_slope=None, baseline_slope=None),
        _sweat(mean_sri=None, peak_sri=None),
        _gsr(current_intensity=None),
        db_path=db,
    )

    assert isinstance(result.score, float)
    assert result.score == pytest.approx(NEUTRAL_SUBSCORE)
    assert result.stabilizing is True

def test_writes_contract_keys_to_history(tmp_path):
    db = tmp_path / "ssb_history.db"
    compute_recovery_readiness(
        _rehydration(),
        _thermal(current_slope=-0.0025),
        _sweat(),
        _gsr(current_intensity=0.42),
        db_path=db,
    )

    sessions = history.get_recent_sessions(db_path=db)
    assert len(sessions) == 1
    row = sessions[0]
    # Exact CONTRACT key strings + correct field sourcing.
    assert row["thermal_slope"] == pytest.approx(-0.0025)
    assert row["gsr_drop_intensity"] == pytest.approx(0.42)
    assert "score" in row

def test_history_round_trip_feeds_thermal_and_electrolyte_readers(tmp_path):
    db = tmp_path / "ssb_history.db"
    # Write 3 real sessions, then prove the two readers actually consume the
    # keys scoring wrote non-empty baselines (sessions_used == 3).
    for i in range(3):
        compute_recovery_readiness(
            _rehydration(),
            _thermal(current_slope=-0.002),
            _sweat(),
            _gsr(current_intensity=0.25),
            db_path=db,
            timestamp=f"2026-07-07T00:00:{i:02d}",
        )

    thermal_res = compute_thermal_recovery(_skin_samples(), db_path=db)
    gsr_res = compute_gsr_electrolyte_adjustment(
        _gsr_samples(), gsr_baseline=2000, db_path=db
    )

    assert thermal_res.sessions_used == 3
    assert gsr_res.sessions_used == 3

def test_none_thermal_slope_still_writes_and_scores(tmp_path):
    db = tmp_path / "ssb_history.db"
    result = compute_recovery_readiness(
        _rehydration(),
        _thermal(current_slope=None, baseline_slope=None),
        _sweat(),
        _gsr(),
        db_path=db,
    )

    # Thermal falls back to neutral, the score is still a real float, and a
    # None thermal_slope is written without error.
    assert result.thermal_score == pytest.approx(NEUTRAL_SUBSCORE)
    assert isinstance(result.score, float)
    assert history.get_recent_sessions(db_path=db)[0]["thermal_slope"] is None

def test_stabilizing_true_below_five_sessions(tmp_path):
    db = tmp_path / "ssb_history.db"
    _seed_sessions(db, 4)

    result = compute_recovery_readiness(
        _rehydration(), _thermal(), _sweat(), _gsr(), db_path=db
    )

    assert result.prior_session_count == 4
    assert result.stabilizing is True

def test_stabilizing_false_at_five_sessions(tmp_path):
    db = tmp_path / "ssb_history.db"
    _seed_sessions(db, 5)

    result = compute_recovery_readiness(
        _rehydration(), _thermal(), _sweat(), _gsr(), db_path=db
    )

    # prior_session_count is read before the write, so the 5 prior rows show
    # even though save_session will then evict the oldest.
    assert result.prior_session_count == 5
    assert result.stabilizing is False

def test_high_readiness_when_low_deficit_fast_cooling_low_sri(tmp_path):
    db = tmp_path / "ssb_history.db"
    # low deficit (90), fast cooling vs baseline (70), low sweat rate (90).
    result = compute_recovery_readiness(
        _rehydration(total_fluid_ml=150.0),
        _thermal(current_slope=-0.005, baseline_slope=-0.001),
        _sweat(mean_sri=0.01),
        _gsr(),
        db_path=db,
    )

    assert result.score > 75.0

def test_low_readiness_when_high_deficit_poor_cooling_high_sri(tmp_path):
    db = tmp_path / "ssb_history.db"
    # deficit past the reference (0), warming vs baseline (clamps 0), high SRI (0).
    result = compute_recovery_readiness(
        _rehydration(total_fluid_ml=3000.0),
        _thermal(current_slope=0.01, baseline_slope=-0.001),
        _sweat(mean_sri=0.3),
        _gsr(),
        db_path=db,
    )

    assert result.score < 25.0

def test_score_clamped_to_0_100(tmp_path):
    db = tmp_path / "ssb_history.db"
    # Extreme-high: every sub-score saturates at 100 -> composite 100.
    high = compute_recovery_readiness(
        _rehydration(total_fluid_ml=0.0),
        _thermal(current_slope=-1.0, baseline_slope=0.0),
        _sweat(mean_sri=0.0),
        _gsr(),
        db_path=db,
    )
    # Extreme-low: every sub-score bottoms at 0 -> composite 0.
    low = compute_recovery_readiness(
        _rehydration(total_fluid_ml=100_000.0),
        _thermal(current_slope=1.0, baseline_slope=0.0),
        _sweat(mean_sri=100.0),
        _gsr(),
        db_path=db,
    )

    assert high.score == pytest.approx(100.0)
    assert low.score == pytest.approx(0.0)

def test_db_path_isolation_and_timestamp_passthrough(tmp_path):
    db = tmp_path / "ssb_history.db"
    ts = "2026-07-07T12:34:56"

    compute_recovery_readiness(
        _rehydration(), _thermal(), _sweat(), _gsr(), db_path=db, timestamp=ts
    )

    # Exactly one row in the isolated DB, written with the passed timestamp.
    assert history.get_session_count(db_path=db) == 1
    with sqlite3.connect(db) as conn:
        stored = conn.execute("SELECT timestamp FROM sessions").fetchall()
    assert stored == [(ts,)]
