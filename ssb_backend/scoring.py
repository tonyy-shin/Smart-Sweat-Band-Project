"""
Composite recovery readiness score for the SSB backend.

Combine the three independent alogrithm outputs 
(RehydrationResult,ThermalResult, SweatRateResult) into a single 0-100 range 
recovery readiness score.
It is the first module that writes directly to history.
"""

from __future__ import annotations
from dataclasses import dataclass
from ssb_backend import history
from ssb_backend.algorithm.rehydration import(
    RehydrationResult,
    compute_rehydration_prescription,
)
from ssb_backend.algorithm.thermal import(
    ThermalResult,
    compute_thermal_recovery,
)
from ssb_backend.algorithm.sweat_rate import (
    SweatRateResult,
    compute_sweat_rate_index
)
from ssb_backend.algorithm.electrolyte_intensity import (
    GsrElectrolyteResult,
    compute_gsr_electrolyte_adjustment
)
import logging
logger = logging.getLogger(__name__)




# Constants --------------------------------------------------------------------
# TODO: all four are uncalibrated placeholders pending physiological validation
# same status as THERMAL_ALERT_MARGIN_C_PER_S / vapor chamber.
REHYDRATION_FULL_DEFICIT_ML = 1500.0 # fluid volume that maps to 0 readiness
THERMAL_SCORE_GAIN = 5000.0 # readiness points per (C/s) below baseline
SRI_FULL_STRESS = 0.1 # mean SRI that maps to 0 readiness
NEUTRAL_SUBSCORE = 50.0 # midpoint

SCORE_WEIGHT_REHYDRATION = 0.50
SCORE_WEIGHT_THERMAL = 0.30
SCORE_WEIGHT_SRI = 0.20
SCORE_CALIBRATED_SESSIONS = 5




# Result -----------------------------------------------------------------------
@dataclass
class RecoveryReadinessResult:
    score: float
    rehydration_score: float
    thermal_score: float
    sri_score: float
    prior_session_count: int
    stabilizing: bool




# Helpers ----------------------------------------------------------------------
def validate_gsr(gsr_baseline: int):
    if gsr_baseline < 500 or gsr_baseline > 2300:
        logger.warning(
            "gsr_baseline %d outside plausible range [500, 2300]; "
            "baseline may have been set without proper skin contact",
            gsr_baseline,
        )


def _rehydration_subscore(rehydration_result: RehydrationResult) -> float:
    """
    Maps fluid deficit to 0-100.
    """
    total_fluid_ml = rehydration_result.total_fluid_ml

    # total_fluid_ml is None covers case of 'status == "insufficient_data"
    # total_fluid_ml == 0.0 is correct and maps to score = 100
    if total_fluid_ml is None:
        return NEUTRAL_SUBSCORE
    return 100 * (1 - min(total_fluid_ml / REHYDRATION_FULL_DEFICIT_ML, 1))
    

def _thermal_subscore(thermal_result: ThermalResult) -> float:
    """
    Maps slope vs baseline to 0-100.
    """
    baseline_slope = thermal_result.baseline_slope
    current_slope = thermal_result.current_slope

    # baseline_slop is None or current_slope is None covers both cases of
    # 'recommendation' == "insufficient_data" and 'insufficient baseline' is True 
    if baseline_slope is None or current_slope is None:
        return NEUTRAL_SUBSCORE
    return max(0.0, min(100.0, NEUTRAL_SUBSCORE + THERMAL_SCORE_GAIN * (baseline_slope - current_slope)))

def _sri_subscore(sweat_rate_result: SweatRateResult) -> float:
    """
    Maps SRI to 0-100.
    """
    mean_sri = sweat_rate_result.mean_sri

    if mean_sri is None:
        return NEUTRAL_SUBSCORE
    
    return max(0.0, min(100.0, 100 * (1 - min(mean_sri / SRI_FULL_STRESS, 1))))




# Function -----------------------------------------------------------------------
def compute_recovery_readiness(
        rehydration_result: RehydrationResult,
        thermal_result: ThermalResult,
        sweat_rate_result: SweatRateResult,
        gsr_electrolyte_result: GsrElectrolyteResult,
        db_path=history.DEFAULT_DB_PATH,
        timestamp=None,
) -> RecoveryReadinessResult:
    """
    entry point to compute recovery readiness score.
    """
    # get variables for scoring ------------------------------------
    rehydration_score = _rehydration_subscore(rehydration_result)
    thermal_score = _thermal_subscore(thermal_result)
    sri_score = _sri_subscore(sweat_rate_result)

    # get variables for RecoveryReadinessResult --------------------
    score = (SCORE_WEIGHT_REHYDRATION * rehydration_score) \
    + (SCORE_WEIGHT_THERMAL * thermal_score) \
    + (SCORE_WEIGHT_SRI * sri_score)
    score = max(0.0, min(score, 100.0))
    prior_session_count = history.get_session_count(db_path)
    stabilizing = prior_session_count < SCORE_CALIBRATED_SESSIONS

    # get variables for history.save_session() record --------------
    thermal_slope = thermal_result.current_slope
    gsr_drop_intensity = gsr_electrolyte_result.current_intensity
    mean_sri = sweat_rate_result.mean_sri
    peak_sri = sweat_rate_result.peak_sri

    # create record -----------------------------------------------
    record = {
        "score": score,
        "thermal_slope": thermal_slope,
        "gsr_drop_intensity": gsr_drop_intensity,
        "mean_sri": mean_sri,
        "peak_sri": peak_sri,
    }

    # call history.save_session() to write to history -------------
    history.save_session(record, db_path, timestamp=timestamp)

    # return result -----------------------------------------------
    return RecoveryReadinessResult(
        score=score,
        rehydration_score=rehydration_score,
        thermal_score=thermal_score,
        sri_score=sri_score,
        prior_session_count=prior_session_count,
        stabilizing=stabilizing,
    )