"""Tests for sweat_rate.py"""

from ssb_backend.algorithm.sweat_rate import compute_sweat_rate_index, SweatRateResult



# Samples -----------------------------------------------------------------------------
def _sample(timestamp_ms, humidity_pct):
    return {"timestamp_ms": timestamp_ms, "humidity_pct": humidity_pct}



# tests --------------------------------------------------------------------------------
def test_linear_humidity_increase():
    samples = [
        _sample(0, 40.0),
        _sample(1000, 42.0),
        _sample(2000, 44.0),
        _sample(3000, 46.0),
    ]
    result = compute_sweat_rate_index(samples=samples)

    assert result == SweatRateResult(mean_sri=2.0, peak_sri=2.0, sample_count=4)


def test_empty_samples():
    assert compute_sweat_rate_index([]) == SweatRateResult(
        mean_sri=None,
        peak_sri=None,
        sample_count=0,
    )


def test_single_sample():
    samples = [_sample(0, 40.0)]

    assert compute_sweat_rate_index(samples) == SweatRateResult(
        mean_sri=None,
        peak_sri=None,
        sample_count=1,
    )


def test_drop_duplicate_timestamp():
    samples = [
        _sample(0, 40.0),
        _sample(1000, 42.0),
        _sample(1000, 99.0),  # duplicate timestamp (should be dropped)
        _sample(2000, 44.0),
    ]
    result = compute_sweat_rate_index(samples)

    assert result == SweatRateResult(
        mean_sri=2.0,
        peak_sri=2.0,
        sample_count=3,
    )