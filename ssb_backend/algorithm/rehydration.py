"""
Rehydration prescription that estimates fluid and sodium replacement needs.

Uses the GSR drop from baseline as a proxy for sweat volume. 
The sweat volume is converted into fluid volume and sodium mass.
"""


from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import Literal
from ssb_backend import history
from ssb_backend.algorithm.electrolyte_intensity import (
    GsrElectrolyteResult,
    compute_gsr_electrolyte_adjustment,
)
import logging
logger = logging.getLogger(__name__)


# Config Constants -------------------------------------------------------------
# TODO - pending real vapor chamber calibration
# neutral starting guess to 1e-3 so it lands around mid-range
SWEAT_CALIBRATION_ML_PER_COUNT_S = 1e-3
# TODO: 1000 mg/L is a placeholder average pending per athlete sweat sodium
# calibration - same status as the vapor chamber coefficient above
SWEAT_SODIUM_MG_PER_L = 1000

FLUID_REPLACEMENT_FACTOR = 1.5 # American College of Sports Medicine 150% RULE
INTAKE_WINDOW_S = 900 #15 minute pacing window
MAX_INTAKE_PER_WINDOW_ML = 300 # threshold for excessive hydration
SCHEDULE_REMAINDER_EPSILON_ML = 1e-6



# Result Type -------------------------------------------------------------------
@dataclass 
class IntakeWindow:
    window_index: int
    start_s: float
    volume_ml: float
    sodium_mg: float

@dataclass
class RehydrationResult:
    sweat_volume_ml: float | None # raw estimated sweat loss
    total_fluid_ml: float | None # 1.5x replacement target
    total_sodium_mg: float | None # (sweat_volume_ml / 1000) x SWEAT_SODIUM_MG_PER_L
    schedule: list[IntakeWindow]
    sample_count: int
    status: Literal["ok", "insufficient_data"]
    electrolyte_tier: Literal["insufficient_data", "low", "typical", "high"]
    calibration_state: dict[str, str]




# helpers ------------------------------------------------------------------------
def validate_gsr(gsr_baseline: int):
    if gsr_baseline < 500 or gsr_baseline > 2300:
        logger.warning(
            "gsr_baseline %d outside plausible range [500, 2300]; "
            "baseline may have been set without proper skin contact",
            gsr_baseline,
        )


def insufficient_data_result(sample_count: int) -> RehydrationResult | None:
    if sample_count < 2:
        return RehydrationResult(
            sweat_volume_ml=None,
            total_fluid_ml=None,
            total_sodium_mg=None,
            schedule=[],
            sample_count=sample_count,
            status="insufficient_data",
            electrolyte_tier="insufficient_data",
            calibration_state={"volume": "provisional", "sodium": "provisional"}
        )
    return None


def dedupe_timestamps(
        time_s: np.ndarray,
        gsr_raw: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
    dt = np.diff(time_s)
    if np.any(dt == 0):
        dupes = int(np.sum(dt == 0))
        logger.warning("Dropping %d duplicate timestamp sample(s) before rehydration computation", dupes)

        keep = np.concatenate(([True], dt != 0))
        time_s = time_s[keep]
        gsr_raw = gsr_raw[keep]
    return time_s, gsr_raw


def compute_volume_and_sodium(
        gsr_raw: np.ndarray,
        time_s: np.ndarray,
        gsr_baseline: int,
        modifier: float,
    ) -> tuple[float, float, float]:
    proxy = [max(gsr_baseline - gsr, 0) for gsr in gsr_raw]
    integral = float(np.trapezoid(proxy, time_s)) # integrate proxy series over time_s using trapzoid rule
    sweat_volume_ml = float(integral * SWEAT_CALIBRATION_ML_PER_COUNT_S)
    total_fluid_ml = sweat_volume_ml * FLUID_REPLACEMENT_FACTOR
    
    total_sodium_mg = (sweat_volume_ml / 1000.0) * SWEAT_SODIUM_MG_PER_L * modifier
    return sweat_volume_ml, total_fluid_ml, total_sodium_mg


def build_intake_schedule(total_fluid_ml: float, total_sodium_mg: float) -> list[IntakeWindow]:
    full_windows = int(total_fluid_ml // MAX_INTAKE_PER_WINDOW_ML)
    remainder = total_fluid_ml - full_windows * MAX_INTAKE_PER_WINDOW_ML

    schedule = []
    for i in range(full_windows):
        schedule.append(IntakeWindow(
            window_index=i,
            start_s=i*INTAKE_WINDOW_S,
            volume_ml=MAX_INTAKE_PER_WINDOW_ML,
            sodium_mg=total_sodium_mg*(MAX_INTAKE_PER_WINDOW_ML/total_fluid_ml),
        ))
    if remainder > SCHEDULE_REMAINDER_EPSILON_ML:
        schedule.append(IntakeWindow(
            window_index=full_windows,
            start_s=full_windows*INTAKE_WINDOW_S,
            volume_ml=remainder,
            sodium_mg=total_sodium_mg*(remainder/total_fluid_ml),
        ))
    return schedule


# Function ------------------------------------------------------------------------
def compute_rehydration_prescription(
        samples: list[dict],
        gsr_baseline: int,
        db_path=history.DEFAULT_DB_PATH,
        elec: GsrElectrolyteResult | None = None,
    ) -> RehydrationResult:
    """
    Rehydration prescription entry point.

    Args:
        samples: dict contains 'timestamp_ms' and 'gsr_raw'
        gsr_baseline: goes in for proxy ('gsr_baseline' - 'gsr_raw')

    Returns:
        RehydrationResult: 'status="insufficient_data"' with 'None' numerics
                            and empty 'schedule' when '< 2' usable samples
    """
    sample_count = len(samples)
    guard = insufficient_data_result(sample_count)
    if guard is not None:
        return guard

    time_s = np.array([s["timestamp_ms"] for s in samples], dtype=float) / 1000.0
    gsr_raw = np.array([s["gsr_raw"] for s in samples], dtype=float)
    validate_gsr(gsr_baseline=gsr_baseline)

    time_s, gsr_raw = dedupe_timestamps(time_s, gsr_raw)
    sample_count = len(time_s)
    guard = insufficient_data_result(sample_count)
    if guard is not None:
        return guard
    
    # get modifier and sodium_state
    if elec is None:
        elec = compute_gsr_electrolyte_adjustment(samples, gsr_baseline, db_path)
    modifier = elec.modifier
    sodium_state = "provisional" if elec.insufficient_baseline else "gsr_adjusted"

    # get result values
    sweat_volume_ml, total_fluid_ml, total_sodium_mg = compute_volume_and_sodium(
        gsr_raw, time_s, gsr_baseline, modifier
    )

    # build schedule
    if total_fluid_ml <= 0.0:
        return RehydrationResult(
            sweat_volume_ml=0.0,
            total_fluid_ml=0.0,
            total_sodium_mg=0.0,
            schedule=[],
            sample_count=sample_count,
            status="ok",
            electrolyte_tier=elec.tier,
            calibration_state={"volume": "provisional", "sodium": sodium_state}
        )

    schedule = build_intake_schedule(total_fluid_ml, total_sodium_mg)

    # result
    return RehydrationResult(
        sweat_volume_ml=sweat_volume_ml,
        total_fluid_ml=total_fluid_ml,
        total_sodium_mg=total_sodium_mg,
        schedule=schedule,
        sample_count=sample_count,
        status="ok",
        electrolyte_tier=elec.tier,
        calibration_state={"volume": "provisional", "sodium": sodium_state}
    )
