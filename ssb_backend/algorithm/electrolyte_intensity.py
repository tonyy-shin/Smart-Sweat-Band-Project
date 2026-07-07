"""

"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from ssb_backend import history
import logging
logger = logging.getLogger(__name__)




# Constants -------------------------------------------------------------------
MIN_BASELINE_SESSIONS = 3
GSR_MODIFIER_MIN_CLAMP = 0.5
GSR_MODIFIER_MAX_CLAMP = 2.0
GSR_TIER_LOW_THRESHOLD = 0.8
GSR_TIER_HIGH_THRESHOLD = 1.2




# Result ----------------------------------------------------------------------
@dataclass
class GsrElectrolyteResult:
    current_intensity: float | None
    baseline_intensity: float | None
    modifier: float | None
    tier: Literal["insufficient_data", "low", "typical", "high"]
    sessions_used: int
    insufficient_baseline: bool




# Helpers ---------------------------------------------------------------------
def insufficient_data_result(samples, gsr_baseline) -> GsrElectrolyteResult | None:
    if not samples or gsr_baseline <= 0:
        if gsr_baseline <= 0:
            logger.warning(
                "Non-positive gsr_baseline %d; cannot compute intensity",
                gsr_baseline,
            )
        return GsrElectrolyteResult(
            current_intensity=None,
            baseline_intensity=None,
            modifier=1.0,
            tier="insufficient_data",
            sessions_used=0,
            insufficient_baseline=True,
        )
    return None


def min_baseline_sessions_not_acheived(sessions_used, current_intensity):
    if sessions_used < MIN_BASELINE_SESSIONS:
        logger.info(
            "Only %d baseline intensity value(s) (< %d); neutral modifier, "
            "tier insufficient_data",
            sessions_used, MIN_BASELINE_SESSIONS,
        )
        return GsrElectrolyteResult(
            current_intensity=current_intensity,
            baseline_intensity=None,
            modifier=1.0,
            tier="insufficient_data",
            sessions_used=sessions_used,
            insufficient_baseline=True
        )
    return None



def get_past_intensities(db_path):
    past_sessions = history.get_recent_sessions(db_path=db_path)
    # CONTRACT: assume each stored session JSON has a top-level
    # "gsr_drop_intensity" key: set by whatever assembles the session
    # result dict for history.save_session()
    past_intensities = [
        s["gsr_drop_intensity"]
        for s in past_sessions
        if s.get("gsr_drop_intensity") is not None
    ]
    return past_intensities



def get_modifier(baseline_intensity, current_intensity):
    modifier = 0
    if baseline_intensity == 0:
        logger.warning("Baseline intensity is 0; intensity ratio undefined")
        modifier = GSR_MODIFIER_MAX_CLAMP if current_intensity > 0 else 1.0
    else:
        modifier = current_intensity / baseline_intensity
    modifier = max(GSR_MODIFIER_MIN_CLAMP, min(GSR_MODIFIER_MAX_CLAMP, modifier))
    return modifier


def get_tier(modifier: float) -> str:
    tier = ""
    if modifier < GSR_TIER_LOW_THRESHOLD:
        tier = "low"
    elif modifier > GSR_TIER_HIGH_THRESHOLD:
        tier = "high"
    else:
        tier = "typical"
    return tier





# Function -------------------------------------------------------------------
def compute_gsr_electrolyte_adjustment(
    samples: list[dict],
    gsr_baseline: int,
    db_path=history.DEFAULT_DB_PATH
    ) -> GsrElectrolyteResult:
    """
    Compare this session's GSR peak drop intensity against baseline.

    Returns:
        GsrElectrolyteResult: current_intensity and modifier are None with
                              tier "insufficient_data" when there are no
                              samples or gsr_baseline <= 0.
                              baseline_intensity is None with modifier=1.0,
                              tier "insufficient_data", and
                              insufficient_baseline=True until
                              MIN_BASELINE_SESSIONS valid.
    """
    guard = insufficient_data_result(samples=samples, gsr_baseline=gsr_baseline)
    if guard is not None:
        return guard
    
    min_raw = min(s["gsr_raw"] for s in samples)
    current_intensity = max(0.0, (gsr_baseline - min_raw) / gsr_baseline)

    past_intensities = get_past_intensities(db_path=db_path)
    sessions_used = len(past_intensities)

    guard = min_baseline_sessions_not_acheived(
        sessions_used=sessions_used,
        current_intensity=current_intensity
        )
    if guard is not None:
        return guard
    
    baseline_intensity = sum(past_intensities) / sessions_used
    modifier = get_modifier(
        baseline_intensity=baseline_intensity,
        current_intensity=current_intensity
    )

    tier = get_tier(modifier=modifier) 

    return GsrElectrolyteResult(
        current_intensity=current_intensity,
        baseline_intensity=baseline_intensity,
        modifier=modifier,
        tier=tier,
        sessions_used=sessions_used,
        insufficient_baseline=False,
    )