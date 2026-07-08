"""
Runs an API for the website.
"""

from __future__ import annotations
from fastapi import FastAPI, HTTPException
import uvicorn
import dataclasses
from ssb_backend.algorithm.rehydration import (
    RehydrationResult,
    compute_rehydration_prescription,
)
from ssb_backend.algorithm.thermal import (
    ThermalResult,
    compute_thermal_recovery,
)
from ssb_backend.algorithm.sweat_rate import (
    SweatRateResult,
    compute_sweat_rate_index,
)
from ssb_backend.algorithm.electrolyte_intensity import (
    GsrElectrolyteResult,
    compute_gsr_electrolyte_adjustment,
)
from ssb_backend.scoring import (
    RecoveryReadinessResult,
    compute_recovery_readiness,
)
from ssb_backend import history
from pathlib import Path
from datetime import datetime
import logging
logger = logging.getLogger(__name__)




# Result ------------------------------------------------------------------------
@dataclasses.dataclass
class SessionResults:
    rehydration: RehydrationResult
    thermal: ThermalResult
    sweat_rate: SweatRateResult
    electrolyte: GsrElectrolyteResult
    readiness: RecoveryReadinessResult
    recovery_plan: str
    timestamp: str




# API ---------------------------------------------------------------------------
app = FastAPI()
_latest_results: SessionResults | None = None
_latest_samples: list[dict] | None = None


@app.get("/results")
def get_results():
    """
    GET /results handler.
    """
    if _latest_results is None:
        raise HTTPException(status_code=404, detail="No sessions recorded")
    return dataclasses.asdict(_latest_results)


@app.get("/results/samples")
def get_result_samples() -> list[dict]:
    """
    GET /results/samples handler.
    
    Raw persample time series from most recent session
    """
    if _latest_samples is None:
        raise HTTPException(status_code=404,detail="No sessions recorded")
    return _latest_samples


@app.get("/history")
def get_history() -> list[dict]:
    """
    GET /history handler.

    Listing of past sessions (oldest to newest) for trend charts
    """
    return history.get_recent_sessions_with_timestamp(db_path=history.DEFAULT_DB_PATH)



def run_pipeline(
        samples: list[dict],
        gsr_baseline: int | None,
        db_path: str | Path = history.DEFAULT_DB_PATH,
        timestamp: str | None = None,
) -> SessionResults:
    """
    Full pipeline orchestrator.

    Args:
        samples: dict {'timestamp_ms', 'skin_temp_c', 'humidity_pct', 
                 'chamber_temp_c', 'gsr_raw'}
        gsr_baseline: None when missing '# gsr_baseline=' header
    """
    global _latest_results
    global _latest_results, _latest_samples

    # resolve timestamp ----------------------------------------------------
    ts = timestamp or datetime.now().isoformat()

    # guard ----------------------------------------------------------------
    if gsr_baseline is None:
        logger.warning("gsr_baseline is None; setting to 0")
        gsr_baseline = 0

    # run pipline ------------------------------------------------------------------
    # Has to be in this order because of degenerate baseline guards
    elec = compute_gsr_electrolyte_adjustment(samples, gsr_baseline,db_path=db_path)
    rehydration = compute_rehydration_prescription(
        samples, gsr_baseline, db_path=db_path, elec=elec
    )
    thermal = compute_thermal_recovery(samples,db_path=db_path)
    sweat_rate = compute_sweat_rate_index(samples)
    readiness = compute_recovery_readiness(
        rehydration_result=rehydration,
        thermal_result=thermal,
        sweat_rate_result=sweat_rate,
        gsr_electrolyte_result=elec,
        db_path=db_path,
        timestamp=ts,
    )

    # plan ----------------------------------------------------------------
    plan = build_recovery_plan(rehydration, thermal, readiness)

    # Assemble and publish ------------------------------------------------
    session_result = SessionResults (
        rehydration=rehydration,
        thermal=thermal,
        sweat_rate=sweat_rate,
        electrolyte=elec,
        readiness=readiness,
        recovery_plan=plan,
        timestamp=ts,
    )
    _latest_results = session_result
    _latest_samples = samples
    return session_result



def build_recovery_plan(
    rehydration: RehydrationResult,
    thermal: ThermalResult,
    readiness: RecoveryReadinessResult,
) -> str:
    clauses: list[str] = []

    if rehydration.status == "insufficient_data":
        clauses.append("insufficient data for a fluid prescription")
    elif rehydration.total_fluid_ml == 0.0:
        clauses.append("no fluid replacement needed")
    else:
        clauses.append(
            f"drink ~{round(rehydration.total_fluid_ml)} ml over "
            f"{len(rehydration.schedule)} × 15-min windows "
            f"(~{round(rehydration.total_sodium_mg)} mg sodium)"
        )

    if rehydration.electrolyte_tier == "low":
        clauses.append("lower relative sodium loss vs. your recent sessions")
    elif rehydration.electrolyte_tier == "high":
        clauses.append("higher relative sodium loss vs. your recent sessions")

    if thermal.recommendation == "active_cooling":
        thermal_clause = "apply active cooling (ice / shade)"
    elif thermal.recommendation == "passive_rest":
        thermal_clause = "passive rest is sufficient"
    else:
        thermal_clause = "no thermal recommendation (insufficient data)"
    if thermal.insufficient_baseline and thermal.recommendation != "insufficient_data":
        thermal_clause += " (baseline still stabilizing)"
    clauses.append(thermal_clause)

    readiness_clause = f"readiness {readiness.score:.0f}/100"
    if readiness.stabilizing:
        readiness_clause += " — stabilizing"
    clauses.append(readiness_clause)

    return " · ".join(clauses)





# Serving -----------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)