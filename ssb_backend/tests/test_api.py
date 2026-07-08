"""
Test for api.py

Test written by Claude Code and reviewed by coder.  
"""

import sqlite3
import pytest
from fastapi.testclient import TestClient
from ssb_backend import api, history
from ssb_backend.algorithm.rehydration import (
    SWEAT_SODIUM_MG_PER_L,
    IntakeWindow,
    RehydrationResult,
)
from ssb_backend.algorithm.thermal import ThermalResult
from ssb_backend.algorithm.sweat_rate import SweatRateResult
from ssb_backend.algorithm.electrolyte_intensity import GsrElectrolyteResult
from ssb_backend.scoring import RecoveryReadinessResult

client = TestClient(api.app)


# fixtures ---------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_latest():
    """The endpoint reads module state in-process; never let it leak."""
    api._latest_results = None
    api._latest_samples = None
    yield
    api._latest_results = None
    api._latest_samples = None


# sample factory ----------------------------------------------------------------
def _session_samples(gsr_values=(1500, 1000)):
    """Parser-shape dicts (all five keys), 100 s apart, cooling skin temp."""
    return [
        {
            "timestamp_ms": i * 100_000,
            "skin_temp_c": 36.0 - 0.1 * i,
            "humidity_pct": 55.0,
            "chamber_temp_c": 30.0,
            "gsr_raw": g,
        }
        for i, g in enumerate(gsr_values)
    ]


def _seed_sessions(db, n, intensity=0.25):
    """Seed n prior rows carrying both CONTRACT keys."""
    for i in range(n):
        history.save_session(
            {"thermal_slope": -0.001, "gsr_drop_intensity": intensity},
            db_path=db,
            timestamp=f"2026-07-07T00:00:{i:02d}",
        )


# plan-input factories ------------------------------------------------------------
# build_recovery_plan is pure; only the fields it reads matter, the rest is
# filler so the dataclasses construct.
def _rehydration(total_fluid_ml=450.0, total_sodium_mg=150.0, n_windows=2,
                 status="ok", tier="typical"):
    if status == "insufficient_data":
        return RehydrationResult(
            sweat_volume_ml=None,
            total_fluid_ml=None,
            total_sodium_mg=None,
            schedule=[],
            sample_count=1,
            status=status,
            electrolyte_tier=tier,
            calibration_state={"volume": "provisional", "sodium": "provisional"},
        )
    return RehydrationResult(
        sweat_volume_ml=total_fluid_ml / 1.5,
        total_fluid_ml=total_fluid_ml,
        total_sodium_mg=total_sodium_mg,
        schedule=[
            IntakeWindow(
                window_index=i,
                start_s=i * 900.0,
                volume_ml=total_fluid_ml / n_windows,
                sodium_mg=total_sodium_mg / n_windows,
            )
            for i in range(n_windows)
        ],
        sample_count=2,
        status=status,
        electrolyte_tier=tier,
        calibration_state={"volume": "provisional", "sodium": "gsr_adjusted"},
    )


def _thermal(recommendation="active_cooling", insufficient_baseline=False):
    return ThermalResult(
        current_slope=-0.003,
        baseline_slope=None if insufficient_baseline else -0.001,
        sessions_used=0 if insufficient_baseline else 3,
        recommendation=recommendation,
        insufficient_baseline=insufficient_baseline,
    )


def _readiness(score=72.4, stabilizing=False):
    return RecoveryReadinessResult(
        score=score,
        rehydration_score=50.0,
        thermal_score=50.0,
        sri_score=50.0,
        prior_session_count=0 if stabilizing else 5,
        stabilizing=stabilizing,
    )


# endpoint / pipeline tests --------------------------------------------------------
def test_get_results_before_any_session_returns_404():
    resp = client.get("/results")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "No sessions recorded"


def test_run_pipeline_returns_all_sections(tmp_path):
    db = tmp_path / "ssb_history.db"
    ts = "2026-07-07T10:00:00"

    result = api.run_pipeline(
        _session_samples(), gsr_baseline=2000, db_path=db, timestamp=ts
    )

    assert isinstance(result, api.SessionResults)
    assert isinstance(result.rehydration, RehydrationResult)
    assert isinstance(result.thermal, ThermalResult)
    assert isinstance(result.sweat_rate, SweatRateResult)
    assert isinstance(result.electrolyte, GsrElectrolyteResult)
    assert isinstance(result.readiness, RecoveryReadinessResult)
    assert isinstance(result.recovery_plan, str)
    assert result.timestamp == ts
    # Empty history -> passive_rest with insufficient_baseline=True, so the
    # thermal clause must carry the stabilizing marker.
    assert "(baseline still stabilizing)" in result.recovery_plan


def test_run_pipeline_writes_exactly_one_history_row(tmp_path):
    db = tmp_path / "ssb_history.db"

    api.run_pipeline(_session_samples(), gsr_baseline=2000, db_path=db)

    assert history.get_session_count(db_path=db) == 1


def test_run_pipeline_reads_precede_history_write(tmp_path):
    db = tmp_path / "ssb_history.db"
    _seed_sessions(db, 3)

    result = api.run_pipeline(_session_samples(), gsr_baseline=2000, db_path=db)

    # Each reader saw only the 3 seeded rows, not this session's own write...
    assert result.thermal.sessions_used == 3
    assert result.electrolyte.sessions_used == 3
    assert result.readiness.prior_session_count == 3
    # ...which landed afterwards.
    assert history.get_session_count(db_path=db) == 4


def test_rehydration_uses_injected_electrolyte_result(tmp_path):
    db = tmp_path / "ssb_history.db"
    # baseline intensity 0.25 vs current 0.5 -> modifier clamps to 2.0,
    # tier "high", so a wrong/default elec could not pass unnoticed.
    _seed_sessions(db, 3, intensity=0.25)

    result = api.run_pipeline(_session_samples(), gsr_baseline=2000, db_path=db)

    assert result.electrolyte.tier == "high"
    # run_pipeline computes elec once and injects it into rehydration,
    # so tier and modifier agree by construction.
    assert result.rehydration.electrolyte_tier == result.electrolyte.tier
    assert result.rehydration.total_sodium_mg == (
        (result.rehydration.sweat_volume_ml / 1000.0)
        * SWEAT_SODIUM_MG_PER_L
        * result.electrolyte.modifier
    )


def test_get_results_serializes_latest_session(tmp_path):
    db = tmp_path / "ssb_history.db"
    ts = "2026-07-07T10:00:00"
    result = api.run_pipeline(
        _session_samples(), gsr_baseline=2000, db_path=db, timestamp=ts
    )

    resp = client.get("/results")

    assert resp.status_code == 200
    body = resp.json()
    assert body["timestamp"] == ts
    assert body["recovery_plan"] == result.recovery_plan
    assert body["rehydration"]["total_fluid_ml"] == result.rehydration.total_fluid_ml
    assert body["readiness"]["score"] == result.readiness.score
    # asdict() recursed into the IntakeWindow list.
    assert isinstance(body["rehydration"]["schedule"][0], dict)


def test_get_results_reflects_most_recent_session(tmp_path):
    db = tmp_path / "ssb_history.db"
    api.run_pipeline(
        _session_samples(), gsr_baseline=2000, db_path=db,
        timestamp="2026-07-07T10:00:00",
    )
    api.run_pipeline(
        _session_samples(), gsr_baseline=2000, db_path=db,
        timestamp="2026-07-07T11:00:00",
    )

    body = client.get("/results").json()

    assert body["timestamp"] == "2026-07-07T11:00:00"
    # The second run read the first run's row before writing its own.
    assert body["readiness"]["prior_session_count"] == 1


def test_get_results_samples_before_any_session_returns_404():
    resp = client.get("/results/samples")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "No sessions recorded"


def test_get_results_samples_returns_processed_samples(tmp_path):
    db = tmp_path / "ssb_history.db"
    samples = _session_samples()
    api.run_pipeline(samples, gsr_baseline=2000, db_path=db)

    resp = client.get("/results/samples")

    assert resp.status_code == 200
    # Flat list of parser-shape dicts, identical to what run_pipeline consumed.
    assert resp.json() == samples



def test_insufficient_samples_emit_and_label(tmp_path):
    db = tmp_path / "ssb_history.db"

    result = api.run_pipeline(
        _session_samples(gsr_values=(1500,)), gsr_baseline=2000, db_path=db
    )

    assert result.rehydration.status == "insufficient_data"
    assert result.thermal.recommendation == "insufficient_data"
    assert isinstance(result.readiness.score, float)
    assert "insufficient data for a fluid prescription" in result.recovery_plan
    assert "no thermal recommendation (insufficient data)" in result.recovery_plan
    assert "(baseline still stabilizing)" not in result.recovery_plan
    # A degenerate session is still recorded.
    assert history.get_session_count(db_path=db) == 1


def test_none_gsr_baseline_treated_as_degenerate(tmp_path):
    db = tmp_path / "ssb_history.db"

    result = api.run_pipeline(_session_samples(), gsr_baseline=None, db_path=db)

    # baseline coerced to 0: electrolyte guard fires, sweat proxy is all zeros.
    assert result.electrolyte.tier == "insufficient_data"
    assert result.rehydration.status == "ok"
    assert result.rehydration.total_fluid_ml == 0.0
    assert "no fluid replacement needed" in result.recovery_plan
    assert "sodium loss vs." not in result.recovery_plan


# build_recovery_plan tests ---------------------------------------------------------
def test_build_recovery_plan_full_prescription():
    plan = api.build_recovery_plan(_rehydration(), _thermal(), _readiness())

    assert plan == (
        "drink ~450 ml over 2 × 15-min windows (~150 mg sodium)"
        " · apply active cooling (ice / shade)"
        " · readiness 72/100"
    )


def test_build_recovery_plan_insufficient_data():
    plan = api.build_recovery_plan(
        _rehydration(status="insufficient_data", tier="insufficient_data"),
        _thermal(recommendation="insufficient_data", insufficient_baseline=True),
        _readiness(score=50.0, stabilizing=True),
    )

    assert plan == (
        "insufficient data for a fluid prescription"
        " · no thermal recommendation (insufficient data)"
        " · readiness 50/100 — stabilizing"
    )
    # Flag is True but recommendation is insufficient_data -> marker suppressed.
    assert "(baseline still stabilizing)" not in plan


def test_build_recovery_plan_tier_clause_only_when_atypical():
    low = api.build_recovery_plan(_rehydration(tier="low"), _thermal(), _readiness())
    high = api.build_recovery_plan(_rehydration(tier="high"), _thermal(), _readiness())
    typical = api.build_recovery_plan(_rehydration(tier="typical"), _thermal(), _readiness())
    no_data = api.build_recovery_plan(
        _rehydration(tier="insufficient_data"), _thermal(), _readiness()
    )

    assert "lower relative sodium loss vs. your recent sessions" in low
    assert "higher relative sodium loss vs. your recent sessions" in high
    assert "sodium loss vs." not in typical
    assert "sodium loss vs." not in no_data


def test_build_recovery_plan_thermal_baseline_stabilizing():
    on = api.build_recovery_plan(
        _rehydration(),
        _thermal(recommendation="passive_rest", insufficient_baseline=True),
        _readiness(),
    )
    off = api.build_recovery_plan(
        _rehydration(),
        _thermal(recommendation="passive_rest", insufficient_baseline=False),
        _readiness(),
    )
    # Flag-based, not string-based: the marker attaches to active_cooling too.
    cooling_on = api.build_recovery_plan(
        _rehydration(),
        _thermal(recommendation="active_cooling", insufficient_baseline=True),
        _readiness(),
    )

    assert "passive rest is sufficient (baseline still stabilizing)" in on
    assert "passive rest is sufficient" in off
    assert "(baseline still stabilizing)" not in off
    assert "apply active cooling (ice / shade) (baseline still stabilizing)" in cooling_on


def test_timestamp_passthrough_to_history(tmp_path):
    db = tmp_path / "ssb_history.db"
    ts = "2026-07-07T12:34:56"

    api.run_pipeline(_session_samples(), gsr_baseline=2000, db_path=db, timestamp=ts)

    with sqlite3.connect(db) as conn:
        stored = conn.execute("SELECT timestamp FROM sessions").fetchall()
    assert stored == [(ts,)]


def test_get_history_returns_empty_list_when_no_sessions(monkeypatch, tmp_path):
    db = tmp_path / "ssb_history.db"
    monkeypatch.setattr(history, "DEFAULT_DB_PATH", db)

    resp = client.get("/history")

    assert resp.status_code == 200
    assert resp.json() == []


def test_get_history_returns_single_session(monkeypatch, tmp_path):
    db = tmp_path / "ssb_history.db"
    monkeypatch.setattr(history, "DEFAULT_DB_PATH", db)
    ts = "2026-07-08T09:00:00"
    result = api.run_pipeline(
        _session_samples(), gsr_baseline=2000, db_path=db, timestamp=ts
    )

    resp = client.get("/history")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["timestamp"] == ts
    assert body[0]["score"] == result.readiness.score


def test_get_history_sliding_window_of_five(monkeypatch, tmp_path):
    db = tmp_path / "ssb_history.db"
    monkeypatch.setattr(history, "DEFAULT_DB_PATH", db)
    for i in range(7):
        history.save_session(
            {"score": i, "thermal_slope": 0.0, "gsr_drop_intensity": 0.0,
             "mean_sri": None, "peak_sri": None},
            db_path=db,
            timestamp=f"2026-07-0{i+1}T00:00:00",
        )

    resp = client.get("/history")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 5
    assert [entry["score"] for entry in body] == [2, 3, 4, 5, 6]
    assert body[0]["timestamp"] == "2026-07-03T00:00:00"
    assert body[-1]["timestamp"] == "2026-07-07T00:00:00"

