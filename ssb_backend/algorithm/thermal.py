"""
Thermal Recovery Slope Computation

Fits a linear regression to skin temperature vs time.
The slope is compared against the athlete's learned baseline slope.
Recovering slower than baseline triggers cooling recommendations.
"""



from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from scipy.stats import linregress
from ssb_backend import history
import logging
logger = logging.getLogger(__name__)



# Config Constants ------------------------------------------------------------
MIN_BASELINE_SESSIONS = 3

# TODO: 0.002 C/s is a placeholder pedning real physiological
# calibration - same status as the vapor chamber coefficient in rehydration.py
THERMAL_ALERT_MARGIN_C_PER_S = 0.002



# Result Type -----------------------------------------------------------------
@dataclass
class ThermalResult:
    current_slope: float | None
    baseline_slope: float | None
    sessions_used: int
    recommendation: Literal["active_cooling", "passive_rest", "insufficient_data"]
    insufficient_baseline: bool




# Function ----------------------------------------------------------------------
def compute_thermal_recovery(
        samples: list[dict],
        db_path: str | Path = history.DEFAULT_DB_PATH,
    ) -> ThermalResult:
    """
    Compare this session's skin temp slope against baseline
    
    Returns:
        ThermalResult: current_slope is None with recommendation,
                       "insufficient_data" when fewer than two samples exist.
                       baseline_slope is None with insufficient_baseline=True
                       and safe default "passive_rest" until MIN_BASELINE_SESSIONS 
                       valid.
    """
    if len(samples) < 2:
        return ThermalResult(
            current_slope=None,
            baseline_slope=None, 
            sessions_used=0,
            recommendation="insufficient_data",
            insufficient_baseline=True,
        )
    
    time_s = []
    skin_temp_c = []
    for s in samples:
        time_s.append(s["timestamp_ms"] / 1000.0)
        skin_temp_c.append(s["skin_temp_c"])
    current_slope = float(linregress(time_s, skin_temp_c).slope)

    past_sessions = history.get_recent_sessions(db_path=db_path)
    # CONTRACT: assume each stored session JSON has a top-level "thermal_slope"
    # Key: set by whatever assembles the session result dict for
    # history.save_session()
    past_slopes = [
        s["thermal_slope"]
        for s in past_sessions
        if s.get("thermal_slope") is not None
    ]
    sessions_used = len(past_slopes)

    if sessions_used < MIN_BASELINE_SESSIONS:
        logger.info(
            "Only %d baseline slope(s) (< %d); defaulting to passive_rest",
            sessions_used,MIN_BASELINE_SESSIONS,
        )
        return ThermalResult(
            current_slope=current_slope,
            baseline_slope=None,
            sessions_used=sessions_used,
            recommendation="passive_rest",
            insufficient_baseline=True,
        )
    
    baseline_slope = sum(past_slopes) / sessions_used
    if current_slope - baseline_slope > THERMAL_ALERT_MARGIN_C_PER_S:
        recommendation = "active_cooling"
    else:
        recommendation = "passive_rest"
    return ThermalResult(
        current_slope=current_slope,
        baseline_slope=baseline_slope,
        sessions_used=sessions_used,
        recommendation=recommendation,
        insufficient_baseline=False,
    )