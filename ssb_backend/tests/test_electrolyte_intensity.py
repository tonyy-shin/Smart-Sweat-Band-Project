"""Test electrolyte_intensity.py"""

import pytest

from ssb_backend.algorithm.electrolyte_intensity import (
    GSR_MODIFIER_MAX_CLAMP,
    GSR_MODIFIER_MIN_CLAMP,
    GsrElectrolyteResult,
    compute_gsr_electrolyte_adjustment,
)
from ssb_backend.history import save_session




# helpers ------------------------------------------------------------------
def _samples(*gsr_raws):
    return [{"gsr_raw": raw} for raw in gsr_raws]

def _seed_history(db, intensities):
    """Save one session per drop intensity"""
    for i, intensity in enumerate(intensities):
        save_session(
            {"gsr_drop_intensity": intensity},
            db_path=db,
            timestamp=f"2026-07-06T00:00:{i:02d}",
        )




# tests ------------------------------------------------------------------------------------
def test_empty_samples(tmp_path):
    db = tmp_path / "ssb_history.db"

    assert compute_gsr_electrolyte_adjustment([], 2000, db_path=db) == GsrElectrolyteResult(
        current_intensity=None,
        baseline_intensity=None,
        modifier=1.0,
        tier="insufficient_data",
        sessions_used=0,
        insufficient_baseline=True,
    )


def test_non_positive_gsr_baseline(tmp_path):
    db = tmp_path / "ssb_history.db"

    for bad_baseline in (0, -100):
        result = compute_gsr_electrolyte_adjustment(
            _samples(1500), bad_baseline, db_path=db
        )
        assert result.current_intensity is None
        assert result.modifier == 1.0
        assert result.tier == "insufficient_data"


def test_no_history_neutral_modifier(tmp_path):
    db = tmp_path / "ssb_history.db"

    result = compute_gsr_electrolyte_adjustment(_samples(1500), 2000, db_path=db)

    assert result.current_intensity == pytest.approx(0.25)
    assert result.baseline_intensity is None
    assert result.modifier == 1.0
    assert result.tier == "insufficient_data"
    assert result.sessions_used == 0
    assert result.insufficient_baseline is True


def test_negative_drop_clamps_to_zero(tmp_path):
    db = tmp_path / "ssb_history.db"

    result = compute_gsr_electrolyte_adjustment(_samples(2200), 2000, db_path=db)

    assert result.current_intensity == 0.0
    assert result.modifier == 1.0
    assert result.insufficient_baseline is True


def test_modifier_clamped_to_min(tmp_path):
    db = tmp_path / "ssb_history.db"
    _seed_history(db, [0.2, 0.25, 0.3])

    result = compute_gsr_electrolyte_adjustment(_samples(1800), 2000, db_path=db)

    assert result.modifier == GSR_MODIFIER_MIN_CLAMP  # raw ratio 0.4
    assert result.tier == "low"


def test_modifier_clamped_to_max(tmp_path):
    db = tmp_path / "ssb_history.db"
    _seed_history(db, [0.2, 0.25, 0.3])

    result = compute_gsr_electrolyte_adjustment(_samples(0), 2000, db_path=db)

    assert result.current_intensity == 1.0
    assert result.modifier == GSR_MODIFIER_MAX_CLAMP  # raw ratio 4.0
    assert result.tier == "high"


def test_tier_boundaries_are_typical(tmp_path):
    # Dividing by baseline 0.25 (a power of two) is exact in floats, so
    # these modifiers equal the thresholds bit-for-bit; strict </> means
    # both boundaries classify as typical.
    db = tmp_path / "ssb_history.db"
    _seed_history(db, [0.2, 0.25, 0.3])

    at_low = compute_gsr_electrolyte_adjustment(_samples(1600), 2000, db_path=db)
    at_high = compute_gsr_electrolyte_adjustment(_samples(1400), 2000, db_path=db)

    assert at_low.modifier == 0.8
    assert at_low.tier == "typical"
    assert at_high.modifier == 1.2
    assert at_high.tier == "typical"


def test_zero_baseline_intensity(tmp_path):
    db = tmp_path / "ssb_history.db"
    _seed_history(db, [0.0, 0.0, 0.0])

    sweaty = compute_gsr_electrolyte_adjustment(_samples(1500), 2000, db_path=db)
    dry = compute_gsr_electrolyte_adjustment(_samples(2000), 2000, db_path=db)

    assert sweaty.modifier == GSR_MODIFIER_MAX_CLAMP
    assert sweaty.tier == "high"
    assert dry.modifier == 1.0
    assert dry.tier == "typical"


def test_sessions_used_skips_invalid_rows(tmp_path):
    db = tmp_path / "ssb_history.db"
    _seed_history(db, [0.2, 0.25, 0.3, None])
    save_session({"score": 87.5}, db_path=db, timestamp="2026-07-06T00:01:00")

    result = compute_gsr_electrolyte_adjustment(_samples(1500), 2000, db_path=db)

    assert result.sessions_used == 3
    assert result.baseline_intensity == pytest.approx(0.25)
    assert result.insufficient_baseline is False
