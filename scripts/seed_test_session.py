"""
One-off dev script: seed a synthetic session through run_pipeline, then serve
the real GET /results on port 8000 so the dashboard can fetch it.

Run from anywhere:
    python scripts/seed_test_session.py
"""

import math
import random
import sys
from pathlib import Path

# make `import ssb_backend` work when run as a plain script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

from ssb_backend import history
from ssb_backend.api import app, run_pipeline

GSR_BASELINE = 3000  # plausible resting ADC counts
N_SAMPLES = 90       # 90 s at 1 Hz — comfortably past every >=2-sample threshold


def make_samples() -> list[dict]:
    random.seed(42)  # deterministic run-to-run
    samples = []
    for i in range(N_SAMPLES):
        frac = i / (N_SAMPLES - 1)  # 0.0 → 1.0 across the session

        skin_temp = 37.8 - 1.2 * frac + random.uniform(-0.05, 0.05)   # cooling
        humidity = 55.0 + 30.0 * frac + random.uniform(-0.5, 0.5)     # sweat accumulating
        chamber_temp = 30.0 + 2.0 * frac + random.uniform(-0.1, 0.1)

        # GSR: hump-shaped dip — near baseline at start/end, ~30% below
        # baseline mid-session (sweat onset)
        dip = math.sin(math.pi * frac) ** 2
        gsr = GSR_BASELINE - 900 * dip + random.randint(-25, 25)

        samples.append({
            "timestamp_ms": i * 1000,
            "skin_temp_c": round(skin_temp, 2),
            "humidity_pct": round(humidity, 2),
            "chamber_temp_c": round(chamber_temp, 2),
            "gsr_raw": int(gsr),
        })
    return samples


def main() -> None:
    history.init_db()
    result = run_pipeline(make_samples(), GSR_BASELINE, db_path=history.DEFAULT_DB_PATH)
    print("Pipeline OK.")
    print("  recovery_plan:", result.recovery_plan)
    print("  readiness score:", result.readiness.score)
    print("Session saved to real DB:", history.DEFAULT_DB_PATH)
    print("Serving seeded results at http://127.0.0.1:8000/results — Ctrl+C to stop")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
