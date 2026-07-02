"""
Sweat Rate Index computation.

Computes rate of humidity accumualation inside the vapor chamber.
Uses numpy.gradient on the SHT45 humidity readings vs time.

timestamp_ms is converted from ms to s.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import logging
logger = logging.getLogger(__name__)



# Result Type -------------------------------------------------------
@dataclass
class SweatRateResult:
    mean_sri: float | None
    peak_sri: float | None
    sample_count: int



# Functions ---------------------------------------------------------
def compute_sweat_rate_index(samples: list[dict]) -> SweatRateResult:
    """
    Compute mean and peak sweat rate index.

    Args: 
        samples: sample dicts from parser. Contains timestamp_ms and humidity_pct.

    Returns:
        SweatRateResult with mean_sri/peak_sri. Both fields
        are None when fewer than two samples are available, since a rate
        is undefined for 0 or 1 points. sample_count reflects the count
        actually used for computation. If duplicate timestamp rows were
        dropped, it is the post-filter count, not len(samples).
    """
    sample_count = len(samples)
    if sample_count < 2:
        return SweatRateResult(mean_sri=None, peak_sri=None, sample_count=sample_count)
    
    time_s = np.array([s["timestamp_ms"] for s in samples], dtype=float) / 1000.0
    humidity_pct = np.array([s["humidity_pct"] for s in samples], dtype=float)

    dt = np.diff(time_s)
    if np.any(dt == 0):
        dupes = int(np.sum(dt == 0))
        logger.warning("Dropping %d duplicate timestamp sample(s) before SRI computation",dupes)
        
        keep = np.concatenate(([True], dt != 0))
        time_s = time_s[keep]
        humidity_pct = humidity_pct[keep]
        sample_count = len(time_s)
        if sample_count < 2:
            return SweatRateResult(mean_sri=None, peak_sri=None, sample_count=sample_count)
    
    sri = np.gradient(humidity_pct, time_s)

    return SweatRateResult(
        mean_sri=float(np.mean(sri)),
        peak_sri=float(np.max(sri)),
        sample_count=sample_count,
    )