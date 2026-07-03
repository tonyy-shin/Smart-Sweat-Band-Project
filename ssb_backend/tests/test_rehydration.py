"""Test for rehydration.py"""

import pytest

from ssb_backend.algorithm.rehydration import(
    FLUID_REPLACEMENT_FACTOR,
    INTAKE_WINDOW_S,
    MAX_INTAKE_PER_WINDOW_ML,
    SCHEDULE_REMAINDER_EPSILON_ML,
    SWEAT_CALIBRATION_ML_PER_COUNT_S,
    SWEAT_SODIUM_MG_PER_L, 
    RehydrationResult,
    compute_rehydration_prescription,
)



# helpers -----------------------------------------------------------------------
def _sample(timestamp_ms, gsr_raw):
    return {"timestamp_ms": timestamp_ms, "gsr_raw": gsr_raw}



# tests -------------------------------------------------------------------------
def test_empty_sample():
    assert compute_rehydration_prescription([], gsr_baseline=2000) == RehydrationResult(
        sweat_volume_ml=None,
        total_fluid_ml=None,
        total_sodium_mg=None,
        schedule=[],
        sample_count=0,
        status="insufficient_data",
    )


def test_single_samples():
    samples = [_sample(0, 1900)]

    assert compute_rehydration_prescription(samples, gsr_baseline=2000) == RehydrationResult(
        sweat_volume_ml=None,
        total_fluid_ml=None,
        total_sodium_mg=None,
        schedule=[],
        sample_count=1,
        status="insufficient_data"
    )


def test_constant_proxy_volume():
    # proxy = baseline - gsr_raw = 2000 - 1500 = 500, held flat for 200 s.
    # trapezoid integral of a flat line = proxy * duration_s = 500 * 200 = 100000.
    # sweat_volume_ml = 100000 * SWEAT_CALIBRATION_ML_PER_COUNT_S = 100.0
    proxy = 500
    duration_s = 200
    samples = [_sample(0, 2000 - proxy), _sample(duration_s * 1000, 2000 - proxy)]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    assert result.sweat_volume_ml == pytest.approx(proxy * duration_s * SWEAT_CALIBRATION_ML_PER_COUNT_S)


def test_fluid_replacement_is_150_percent():
    samples = [_sample(0, 1500), _sample(200_000, 1500)]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    assert result.total_fluid_ml == pytest.approx(result.sweat_volume_ml * FLUID_REPLACEMENT_FACTOR)


def test_sodium_from_sweat_volume():
    samples = [_sample(0, 1500), _sample(200_000, 1500)]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    assert result.total_sodium_mg == pytest.approx((result.sweat_volume_ml / 1000.0) * SWEAT_SODIUM_MG_PER_L)


def test_schedule_caps_at_300ml():
    # proxy = 1000 held for 300 s -> sweat_volume_ml = 1000*300*1e-3 = 300.0
    # total_fluid_ml = 300.0 * 1.5 = 450.0 -> full_windows=1 (300), remainder=150
    proxy = 1000
    duration_s = 300
    samples = [_sample(0, 2000 - proxy), _sample(duration_s * 1000, 2000 - proxy)]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    assert len(result.schedule) == 2
    for window in result.schedule:
        assert window.volume_ml <= MAX_INTAKE_PER_WINDOW_ML


def test_schedule_remainder_window():
    # Target total_fluid_ml = 700 -> sweat_volume_ml = 700/1.5 = 466.666...,
    # a non-terminating decimal, so it can't be hit by any clean integer
    # proxy/duration pair. Instead, derive duration_s directly from the
    # target so total_fluid_ml lands within float precision of 700, then
    # assert the trailing remainder against the *actual* returned
    # total_fluid_ml rather than a hardcoded literal (judgment call, not a
    # bug - see plan notes).
    proxy = 1000
    duration_s = 700 / (proxy * SWEAT_CALIBRATION_ML_PER_COUNT_S * FLUID_REPLACEMENT_FACTOR)
    samples = [_sample(0, 2000 - proxy), _sample(duration_s * 1000, 2000 - proxy)]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    assert result.total_fluid_ml == pytest.approx(700)
    assert len(result.schedule) == 3
    assert result.schedule[0].volume_ml == pytest.approx(MAX_INTAKE_PER_WINDOW_ML)
    assert result.schedule[1].volume_ml == pytest.approx(MAX_INTAKE_PER_WINDOW_ML)
    assert result.schedule[2].volume_ml == pytest.approx(result.total_fluid_ml - 2 * MAX_INTAKE_PER_WINDOW_ML)


def test_schedule_exact_multiple_no_trailing_window():
    # proxy = 1000 held for 400 s -> sweat_volume_ml = 1000*400*1e-3 = 400.0
    # total_fluid_ml = 400.0 * 1.5 = 600.0 -> exactly 2 full windows, remainder = 0
    proxy = 1000
    duration_s = 400
    samples = [_sample(0, 2000 - proxy), _sample(duration_s * 1000, 2000 - proxy)]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    assert result.total_fluid_ml == pytest.approx(600)
    assert len(result.schedule) == 2
    assert result.schedule[0].volume_ml == pytest.approx(MAX_INTAKE_PER_WINDOW_ML)
    assert result.schedule[1].volume_ml == pytest.approx(MAX_INTAKE_PER_WINDOW_ML)


def test_sub_window_single_partial():
    # proxy = 1000 held for 100 s -> sweat_volume_ml = 1000*100*1e-3 = 100.0
    # total_fluid_ml = 100.0 * 1.5 = 150.0 -> below MAX_INTAKE_PER_WINDOW_ML,
    # so exactly one partial window
    proxy = 1000
    duration_s = 100
    samples = [_sample(0, 2000 - proxy), _sample(duration_s * 1000, 2000 - proxy)]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    assert len(result.schedule) == 1
    assert result.schedule[0].volume_ml == pytest.approx(150)


def test_window_start_times():
    # Reuses the exact-600mL/2-window setup: i*INTAKE_WINDOW_S with integer
    # i and INTAKE_WINDOW_S is exact (no float approx needed for start_s).
    proxy = 1000
    duration_s = 400
    samples = [_sample(0, 2000 - proxy), _sample(duration_s * 1000, 2000 - proxy)]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    for i, window in enumerate(result.schedule):
        assert window.start_s == i * INTAKE_WINDOW_S


def test_sodium_allocated_proportionally():
    # Reuses the 700mL/3-window (300, 300, remainder) setup so the
    # proportionality check spans windows of different sizes, not just
    # equal ones.
    proxy = 1000
    duration_s = 700 / (proxy * SWEAT_CALIBRATION_ML_PER_COUNT_S * FLUID_REPLACEMENT_FACTOR)
    samples = [_sample(0, 2000 - proxy), _sample(duration_s * 1000, 2000 - proxy)]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    assert sum(w.sodium_mg for w in result.schedule) == pytest.approx(result.total_sodium_mg)

    expected_ratio = result.total_sodium_mg / result.total_fluid_ml
    for window in result.schedule:
        assert window.sodium_mg / window.volume_ml == pytest.approx(expected_ratio)


def test_schedule_volumes_sum_to_total():
    proxy = 1000
    duration_s = 300
    samples = [_sample(0, 2000 - proxy), _sample(duration_s * 1000, 2000 - proxy)]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    assert sum(w.volume_ml for w in result.schedule) == pytest.approx(result.total_fluid_ml)


def test_duplicate_timestamps_dropped():
    samples = [
        _sample(0, 1900),
        _sample(1000, 1900),
        _sample(1000, 1900),  # duplicate timestamp (should be dropped)
        _sample(2000, 1900),
    ]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    assert result.sample_count == 3


def test_zero_duration_returns_insufficient_data():
    # All three timestamps identical -> dt==0 dedup drops two of three rows,
    # collapsing to a single sample -> falls through the existing <2 guard
    # (not a separate zero-duration branch).
    samples = [_sample(500, 1900), _sample(500, 1850), _sample(500, 1800)]

    assert compute_rehydration_prescription(samples, gsr_baseline=2000) == RehydrationResult(
        sweat_volume_ml=None,
        total_fluid_ml=None,
        total_sodium_mg=None,
        schedule=[],
        sample_count=1,
        status="insufficient_data",
    )


def test_zero_fluid_ok_empty_schedule():
    # >=2 distinct timestamps, but gsr_raw >= gsr_baseline at every point ->
    # proxy clamps to 0 everywhere -> integral is 0.
    samples = [_sample(0, 2000), _sample(1000, 2100)]

    assert compute_rehydration_prescription(samples, gsr_baseline=2000) == RehydrationResult(
        sweat_volume_ml=0.0,
        total_fluid_ml=0.0,
        total_sodium_mg=0.0,
        schedule=[],
        sample_count=2,
        status="ok",
    )


def test_negative_proxy_clamped():
    # Middle sample spikes above baseline (gsr_raw=2500 > baseline=2000),
    # which would make proxy = 2000-2500 = -500 if unclamped. With the
    # max(..., 0) clamp, proxy at that point is 0, giving trapezoid
    # [100, 0, 100] over t=[0,100,200]s -> integral = 0.5*100*100 + 0.5*100*100
    # = 10000 -> sweat_volume_ml = 10000*1e-3 = 10.0.
    # Without the clamp, proxy would be [100,-500,100], integral = -40000,
    # sweat_volume_ml = -40.0 - a physically nonsensical negative volume.
    samples = [_sample(0, 1900), _sample(100_000, 2500), _sample(200_000, 1900)]

    result = compute_rehydration_prescription(samples, gsr_baseline=2000)

    assert result.sweat_volume_ml == pytest.approx(10.0)
    assert result.sweat_volume_ml >= 0