# Smart Sweat-Band (SSB) — System Architecture

**Project:** Smart Sweat-Band (SSB)
**MCU:** Seeed Studio XIAO ESP32S3
**Purpose:** Post-exercise recovery analytics — sweat rate, thermal recovery, ionic conductivity

---

## Hardware Layer

### Sensors

| Component | Interface | Role |
|---|---|---|
| MAX30205 | I2C (SDA=D4, SCL=D5) | Skin temperature ±0.1°C — thermal recovery slope |
| SHT45 | I2C (shared bus) | Humidity + ambient temp inside vapor chamber — Sweat Rate Index |
| Grove GSR | ADC (D0/A0) | Skin conductivity via gold cup electrodes — electrolyte/sweat proxy |
| Na⁺ ion-selective electrode (I2C module) | — | **Evaluated and set aside (July 6 audit).** An ISE would have measured sweat sodium concentration directly, but rigid bench-style ISE probes carry too much mounting/mechanical risk to sit reliably against skin on a wearable. Rather than add hardware, sweat-sodium guidance is now derived from the existing on-skin GSR sensor via `electrolyte_intensity.py` (see Algorithm Layer) — a relative, personalized modifier, not a direct concentration measurement. |
| Tactile Button A | GPIO + pull-up | Start / end session |
| Status LED | GPIO + 220Ω resistor | User feedback (3 states) |
| LiPo 3.7V | Power | Battery source |
| TP4056 module | Power management | Safe LiPo charging + voltage regulation |
| Vapor chamber + ePTFE membrane | Physical enclosure | Houses SHT45; isolates sweat humidity from ambient air |

### ADC Note
The ESP32S3 uses a **12-bit ADC (0–4095)**, not the 10-bit (0–1023) found in standard Arduino datasheets. All GSR threshold logic must use 12-bit values. Confirmed resting baseline: ~2450 (offline/no contact: >2300).

### Sensor → Output Mapping

What each sensor reading means — which physiological output it feeds:

| Sensor | Reading | Feeds |
|---|---|---|
| SHT45 (chamber humidity) | ΔRH → mL/min | Sweat rate / sweat volume (`V_rate`) — the canonical volume source for the rehydration mg calculation |
| MAX30205 | Skin temperature | Thermal recovery slope |
| Na⁺ electrode | — | **Set aside (July 6 audit)** — was to supply a measured `C_sweat`; `C_sweat` now stays the `SWEAT_SODIUM_MG_PER_L` population constant, adjusted by the GSR-derived modifier below rather than measured. |
| GSR | Skin conductivity drop | Sweat-onset detection (20%-drop trigger); session-intensity proxy; and a **relative electrolyte-loss intensity modifier** (via `electrolyte_intensity.py`) — explicitly **not** a sodium concentration measurement, just a personalized scaling factor applied to the existing population sodium constant. |

The vapor chamber (SHT45, ΔRH → mL/min) is the real, canonical source of `V_rate`. GSR-drop-as-volume was a **pre-chamber placeholder only** — a rough stand-in adopted because the chamber wasn't built yet. Once the chamber is characterized, GSR retires from the volume calculation to a **trigger/intensity role**: it still drives the 20%-drop sweat-onset trigger (see GSR Calibration) and serves as a session-intensity proxy, but it no longer feeds `V_rate`.

---

## Firmware Layer (ESP32S3 — C++ / Arduino / PlatformIO)

### Session Storage: LittleFS

Sessions are written to the ESP32S3's onboard flash using **LittleFS** (not RAM). This protects data against power loss or crashes mid-session. Each session is stored as a single CSV file.

- File path: `/session.csv`
- Format: `timestamp_ms,skin_temp_c,humidity_pct,chamber_temp_c,gsr_raw` — one row per sample
- **No `na_conc` column:** a 6th `na_conc` column was previously planned to carry raw Na⁺ electrode readings. With the ISE set aside (July 6 audit), that column is no longer planned — the CSV schema stays at the five columns above. The GSR-derived electrolyte modifier needs no new firmware field; it is computed in the backend from the existing `gsr_raw` stream.
- The file is flushed to flash periodically (every 60 seconds) to prevent data loss
- The file is **only deleted after a confirmation byte** is received from the Python backend following a successful USB Serial transfer

A 90-minute session at 1Hz produces ~5,400 rows, approximately 130–150KB — well within ESP32S3 LittleFS capacity (~1.5MB usable).

### Sampling Rate

All three sensors are polled at **1Hz (one sample per second)**. SHT45 and MAX30205 do not produce meaningful physiological signal faster than 1Hz. The GSR is also read at 1Hz after the boot calibration phase.

### GSR Calibration (on session start)

Before the session begins, the firmware performs a **dynamic baseline calibration**:

1. Wait for skin contact — GSR ADC value must drop below 2300
2. Collect 100 readings over 5 seconds (50ms spacing)
3. Average the 100 readings to establish `gsr_baseline` for this user and session
4. Active sweating is defined as a **20% drop from `gsr_baseline`**

This replaces all hardcoded GSR thresholds and accounts for potentiometer variation and individual skin differences.

### State Machine

The device operates in three states, controlled by a single physical button.

**Button A** — Start / End session

| Current State | Event | Next State | Notes |
|---|---|---|---|
| Idle | Button A press | Recording | Begin sensor polling, open `/session.csv`, start GSR calibration |
| Recording | Button A press | Transfer Ready | Stop polling, close CSV, LED slow blink |
| Transfer Ready | Plugged into laptop, Python initiates transfer | Transfer Ready | Stream `/session.csv` over USB Serial; on confirmation, delete file and return to Idle |
| Transfer Ready | Confirmation received | Idle | Delete `/session.csv`, LED off |

In **Transfer Ready**, the device simply waits. There is no radio, no advertisement, and no second button — the device stays in this state until it is plugged into a laptop over USB and the Python script initiates the transfer. If it is never plugged in, the session data remains safely on flash.

### LED Feedback

| Pattern | State |
|---|---|
| Off | IDLE |
| Solid | RECORDING |
| Slow blink (500ms) | TRANSFER_READY — waiting for USB connection |

### USB Serial Transfer

Session data is transferred over the ESP32S3's built-in USB connection — there is no wireless link. The transfer is initiated entirely by the laptop, at the moment the device is plugged in (typically the same moment it is docked to charge).

**Transfer sequence:**
1. The session ends (Button A) and the device enters **Transfer Ready**, with `/session.csv` waiting on LittleFS.
2. The user plugs the device into a laptop over USB.
3. The Python script **auto-detects the device on a serial port** and opens the connection.
4. The script **sends a transfer request** over Serial.
5. The ESP32S3 streams the contents of `/session.csv` back over Serial.
6. The Python script receives the CSV and **saves it locally**, then **sends a confirmation** back over Serial.
7. The ESP32S3 deletes `/session.csv` **only after the confirmation is received**, then returns to Idle.

The `/session.csv` file is **never deleted** until the confirmation is received. If the laptop crashes or the cable is unplugged before confirmation, the file remains intact and can be transferred the next time the device is plugged in.

---

## Python Backend Layer

The Python backend runs on a laptop. It handles USB Serial reception, data parsing, algorithm execution, session persistence, and serving results to the web dashboard.

**The backend must be running when the device is plugged in.** It continuously scans available serial ports for an SSB device and auto-connects when one appears, then initiates the transfer.

### File Structure

```
ssb_backend/
├── main.py              # Entry point (implemented): serial listener (daemon thread) + uvicorn/FastAPI (main thread)
├── serial_receiver.py   # Serial port detection, transfer request, CSV reception, confirmation send
├── parser.py            # Received CSV bytes → list of sample dicts
├── algorithm/
│   ├── rehydration.py            # Rehydration prescription (fluid volume + sodium)
│   ├── electrolyte_intensity.py  # GSR-derived relative electrolyte-loss modifier + tier label
│   ├── thermal.py                # Thermal recovery slope regression
│   └── sweat_rate.py             # Sweat Rate Index from humidity accumulation
├── scoring.py           # Composite Recovery Readiness Score (0–100)
├── history.py           # SQLite session store for cross-session learning
└── api.py               # FastAPI routes — serves results to web dashboard
```

> **`main.py` — implemented (July 8), not a placeholder.** It runs
> `serial_receiver.run()` in a daemon thread and `uvicorn` (serving `api.app`)
> in the main thread, sharing state only through the module-level
> `api._latest_results` (single-writer atomic reference assignment — safe under
> the GIL, no lock needed). `serial_receiver.py`'s former pipeline stub now calls
> `api.run_pipeline` for real, guarded so an algorithm error can't masquerade as
> a transfer failure once the CSV is already saved and confirmed.

### Dev Tooling

- **`scripts/seed_test_session.py`** (repo root) — a hardware-free dev utility.
  It seeds a synthetic, deterministic 90-sample session (`random.seed(42)`: skin
  temp 37.8 → 36.6 °C, humidity 55 → 85%, GSR dipping ~30% mid-session for sweat
  onset) through `run_pipeline`, and self-serves the real FastAPI app on `:8000`
  so the dashboard can be exercised across calibration stages without the
  physical device. It writes to the real `ssb_history.db`, so it must be deleted
  before real device data collection begins.

### Libraries

| Library | Role |
|---|---|
| `pyserial` | Cross-platform USB Serial port detection and I/O (macOS, Windows, Linux) |
| `numpy` | Numerical integration (trapz), gradient computation |
| `scipy.stats` | Linear regression for thermal slope |
| `FastAPI` + `uvicorn` | Async API server, serves results at `localhost:8000` |
| `sqlite3` | Session history persistence (built-in Python, no extra dependencies) |

### Serial Receiver (`serial_receiver.py`)

Scans available serial ports, detects the SSB device, and opens the connection. Sends a transfer request, receives the streamed `/session.csv` contents, and saves the CSV locally. On a complete, successful read, it sends a confirmation back to the device (which then deletes its copy) and triggers the algorithm pipeline.

### Parser (`parser.py`)

Decodes the received CSV bytes into a list of sample dictionaries, each containing: `timestamp_ms`, `skin_temp_c`, `humidity_pct`, `chamber_temp_c`, `gsr_raw`. Passes the list and the session's `gsr_baseline` value downstream to the algorithm layer.

### Algorithm Layer (`algorithm/`)

Three independent functions run in parallel on the parsed sample list (thermal, sweat rate, and the volume half of rehydration). A fourth module, `electrolyte_intensity.py`, is a helper that feeds the sodium half of rehydration rather than a standalone output:

**Rehydration Prescription** (`rehydration.py`)
Estimates fluid and sodium replacement needs. Sweat volume (`V_rate`) comes from the vapor chamber's ΔRH → mL/min reading, integrated over session time with `numpy.trapz` — the single, canonical volume source. (GSR-drop-as-volume was a pre-chamber placeholder used before the chamber existed; once the chamber is characterized, GSR retires from the volume calculation to its trigger/intensity role — see Sensor → Output Mapping.) The sweat volume is converted to fluid volume (ACSM 150% replacement rule) and sodium mass. Intake is scheduled in 300ml windows (15-min windows at ~1.2L/hr gastric emptying).

The mg sodium output depends on **two** measured quantities, `m_Na = ∫(C_sweat · V_rate)dt`, and each has its own calibration state:

- **Sodium concentration (`C_sweat`) — personalized, not measured.** `SWEAT_SODIUM_MG_PER_L` remains a population constant; there is no on-band sodium measurement (the Na⁺ ISE was set aside — see Hardware Layer). Instead, `electrolyte_intensity.py` scales that constant by a GSR-derived relative modifier, moving sodium from `provisional` to the intermediate `gsr_adjusted` state. This does **not** make sodium `calibrated`: it is a personalized *relative* adjustment (this athlete vs. their own recent sessions), not an absolute per-athlete concentration. Individual sweat sodium varies 3–4× person to person, so this narrows — but does not close — the gap to a true measurement.
- **Sweat volume (`V_rate`) — moving to calibrated-per-user.** `V_rate` comes from the vapor chamber's ΔRH → mL/min characterization — the canonical volume source. It is `provisional` only until that characterization lands (being characterized soon), at which point volume flips to `calibrated` per-user. (Unlike sodium, volume has a real per-user *measurement* path, so it reaches full `calibrated`.)

> **Important:** Because the mg number is only as trustworthy as its weakest half, `rehydration.py` should carry a **per-quantity `calibration_state`** (sodium vs volume tracked independently) rather than a single flag — so the dashboard can honestly show e.g. "sodium GSR-adjusted, volume proxied" rather than over- or under-claiming. Sodium's ladder is `provisional → gsr_adjusted` (there is no route to `calibrated` for sodium now that the ISE is set aside); volume's ladder is `provisional → calibrated` via the vapor chamber. The mg number is always emitted at full strength; the flag is metadata alongside it, not a hedge that reduces it.
>
> **Two placeholder coefficients remain TODO-flagged:** the GSR-drop-integral → mL conversion (pending vapor chamber ΔRH characterization) and `SWEAT_SODIUM_MG_PER_L` (a population constant — no longer pending a hardware measurement; it is now scaled per-user by the GSR-derived modifier in `electrolyte_intensity.py`).

**GSR-Derived Electrolyte Intensity** (`electrolyte_intensity.py`)
Produces a *relative* electrolyte-loss signal from the existing GSR stream — the replacement for the abandoned Na⁺ ISE path. It takes this session's GSR-drop magnitude (the same drop that drives sweat-onset detection) and compares it against the athlete's own historical average GSR-drop, pulled from `history.py`. From that ratio it emits two things:

- **(a) A clamped numeric modifier** applied to `SWEAT_SODIUM_MG_PER_L` in the rehydration mg calculation. It is clamped to a bounded range so an anomalous session (poor skin contact, a spike) cannot swing the sodium figure wildly. A session at the user's own average leaves the constant unchanged (modifier ≈ 1.0).
- **(b) A qualitative tier label** — `low` / `typical` / `high` — surfaced next to the rehydration prescription, e.g. *"higher relative sodium loss vs. your recent sessions."* The label is framed explicitly as relative-to-self, never as an absolute concentration.

This is deliberately **not** a sodium measurement and does **not** flip sodium to `calibrated`. It moves sodium's per-quantity `calibration_state` from `provisional` to the new intermediate value **`gsr_adjusted`** (sitting between `provisional` and `calibrated`): the population constant is now personalized by a relative factor, but no absolute per-athlete sodium concentration is ever measured. Because it relies on the on-skin GSR contact, **skin-contact impedance variability is a real and acknowledged limitation** — the modifier is a best-effort relative signal, not a resolved measurement (see Key Constraints & Decisions).

> **Now wired in.** `rehydration.py`'s `compute_rehydration_prescription()` consumes this module's `modifier` and `tier`: the modifier scales `SWEAT_SODIUM_MG_PER_L` in the mg calculation, and the tier is surfaced as the `electrolyte_tier` field on the result. Sodium's per-quantity `calibration_state` transitions from `provisional` to `gsr_adjusted` when `insufficient_baseline` is `False`, and stays `provisional` otherwise — the mg number is never withheld, always emitted and labeled. As part of the wiring, Step 1's degenerate-input guard (0 samples or `gsr_baseline <= 0`) now returns `modifier=1.0` instead of `None`, simplifying the neutral-default contract `rehydration.py` consumes.

**Thermal Recovery Slope** (`thermal.py`)
Fits a linear regression (`scipy.stats.linregress`) to the skin temperature readings over time. The slope (°C/s) is compared against the athlete's learned baseline slope stored in SQLite. A slope significantly above baseline (poor cooling) triggers an active cooling recommendation; otherwise passive rest is recommended.

**Sweat Rate Index** (`sweat_rate.py`)
Computes the rate of humidity accumulation inside the vapor chamber using `numpy.gradient` on the SHT45 humidity readings over time. Returns mean SRI and peak SRI for the session.

### Scoring (`scoring.py`)

Combines the three algorithm outputs into a single **Recovery Readiness Score (0–100)**. Weightings are adjustable; initial suggested split is 50% rehydration, 30% thermal, 20% SRI. Score improves as the learning loop accumulates baseline data over sessions 1–5.

### Session History (`history.py`)

Persists each session result as a JSON blob in SQLite (`ssb_history.db`). Used by the algorithm layer on subsequent sessions to retrieve the athlete's learned thermal baseline and refine the readiness score.

The database maintains a **sliding window of the 5 most recent sessions**. On sessions 1–5, results are simply appended. Starting from session 6, the oldest session is deleted before the newest is inserted — the table always holds exactly 5 rows. This ensures baselines always reflect the athlete's current physiology rather than drifting toward stale early-session data.

The learning loop activates meaningfully once 3 sessions are present, and reaches full baseline accuracy at 5.

### API (`api.py`)

FastAPI server running at `localhost:8000`. Exposes a single primary endpoint:

- `GET /results` — returns the most recent session's rehydration prescription, thermal recommendation, SRI values, readiness score, and plain-language recovery plan

The dashboard polls this endpoint after the transfer completes.

Two further endpoints are **not yet built** but are prerequisites for completing
the dashboard's chart panels:

- `GET /results/samples` (hypothetical) — the raw per-sample list
  (`skin_temp_c`, `humidity_pct`, `gsr_raw`, timestamps) the Thermal and Sweat
  Rate panels need for their time-series charts; without it those two panels show
  summary stats only.
- `GET /history` (hypothetical) — a listing of past sessions for the Session
  History panel (currently a stub). The data already lives in `ssb_history.db`;
  this is an endpoint over existing data, not a schema change.

---

## Web Dashboard Layer (React + Recharts)

Built (July 8) in `ssb-dashboard/` — a Vite + React (JavaScript) + Recharts
single-page app served locally. It fetches from `localhost:8000/results` (through
a Vite dev-server proxy that avoids CORS without any backend change) and renders
the recovery analysis. All six panels below are implemented as pure
props-in/UI-out components, backed by a shared `theme.js` (domain palette /
typography tokens) and `panels/shared.jsx` (`Panel` / `StatTile` / `Badge` /
`Stabilizing` / `Ticks` primitives).

### Dashboard Panels

| Panel | Content |
|---|---|
| Recovery Readiness Score | Large 0–100 gauge, color-coded (red → green) |
| Rehydration Prescription | Total fluid (ml) + sodium (mg), paced intake schedule in 15-min windows |
| Thermal Recovery | Skin temp time-series chart (Recharts LineChart), slope value, cooling recommendation |
| Sweat Rate Index | SRI curve over session duration, peak SRI |
| Recovery Plan | Plain-language summary: e.g. "Drink 450ml over 2 hours · apply cooling · rest 6hrs" |
| Session History | Trend charts across past sessions (readiness score, SRI, thermal slope) |

**Status (July 8).** All six panels are built. Two carry known gaps — both
blocked on backend endpoints rather than on frontend work:

- **Thermal Recovery** and **Sweat Rate Index** currently render **summary stats
  only**, not time-series charts. `GET /results` doesn't return raw per-sample
  data, so the planned Recharts curves (skin-temp series, SRI series) can't be
  drawn yet. Adding them needs a new endpoint (e.g. a hypothetical
  `GET /results/samples`) returning the raw sample list.
- **Session History** is a **stub** pending a session-listing endpoint (e.g.
  `GET /history`). `history.py` already persists past sessions in SQLite, so this
  is an endpoint away — not a data-model change.

---

## Three Core Outputs

### 1. Rehydration Prescription
- Exact fluid volume in ml + sodium in mg
- Paced in 15-minute intake windows (gastric emptying rate ~1.2L/hr, ~300ml/window)
- Derived from: sweat volume (vapor-chamber ΔRH, provisional until the chamber is characterized) × sweat sodium concentration (population constant `SWEAT_SODIUM_MG_PER_L`, personalized by the GSR-derived relative modifier from `electrolyte_intensity.py`) → sodium mass balance
- Each half carries its own calibration state; sodium moves `provisional → gsr_adjusted` via the GSR modifier (the Na⁺ ISE that would have made it `calibrated` was set aside), volume becomes `calibrated` when the vapor chamber is characterized

### 2. Thermal Regulation Recommendation
- Active cooling (ice vest, shade) vs. passive rest
- Derived from: MAX30205 skin temp slope vs. athlete's personal learned baseline

### 3. Recovery Readiness Score (0–100)
- Composite of rehydration deficit, thermal recovery rate, and SRI
- Improves in accuracy as the sliding window of 5 sessions fills — meaningful after session 3, fully calibrated at session 5, and stays current from session 6 onward by replacing the oldest data
- Displayed as primary output on dashboard

---

## Per-User Calibration Phase

Every SSB output stabilizes per-user over a user's first several sessions rather than being correct from a cold start. The calibration notions currently scattered across the modules are one coherent phase:

- **Thermal** learns the athlete's baseline slope — meaningful once `MIN_BASELINE_SESSIONS = 3` sessions are present, fully accurate at 5 (the 5-session sliding window in `history.py`).
- **Volume** (`V_rate`) becomes calibrated-per-user as the vapor chamber's ΔRH → mL/min characterization lands (being characterized soon).
- **Sodium** (`C_sweat`) is personalized *relative-to-self* by the GSR-derived modifier (`electrolyte_intensity.py`), moving from `provisional` to `gsr_adjusted` as the user's own GSR-drop history accumulates. It never reaches `calibrated` — the Na⁺ ISE that would have supplied an absolute measurement was set aside.
- **SRI** gains its planned saturation-awareness flag so it reports honestly near chamber saturation.

Read together, these are a single **"sessions 1–N, outputs stabilizing"** model: during the early sessions the coefficients, baselines, and per-quantity calibration states are still settling toward their per-user values.

**System-wide rule — emit and label, never withhold.** From session 1 the system emits full-strength output numbers and labels them *stabilizing*. It never withholds, fuzzes, or suppresses an output while calibration is thin. This mirrors `thermal.py`'s existing soft-fallback (it returns `passive_rest` rather than withholding when baseline data is sparse) and the rehydration rule that the mg number is always emitted at full strength with the calibration flag as metadata beside it. "Emit and label" is the convention for every module during the calibration phase.

**Forward contract.** The calibration state (per-quantity for rehydration, session-count for thermal/scoring, saturation flag for SRI) is a contract the not-yet-built scoring, API, and dashboard layers must read and surface — so the user sees "stabilizing" honestly rather than a withheld or silently-degraded value.

---

## End-to-End Data Flow

```
[Athlete wears SSB]
       │
       ▼
[Button A] → Idle → Recording
       │  GSR calibration on skin contact (100-sample baseline, 5s window)
       │  Sensors polled at 1Hz
       │  Rows written to /session.csv on LittleFS
       │  CSV flushed to flash every 60 seconds
       │
[Button A] → Recording → Transfer Ready (LED slow blink)
       │
[Plug device into laptop via USB]
       │
       ▼
[Python backend auto-detects device on serial port via pyserial]
       │  Sends transfer request over Serial
       │  ESP32S3 streams /session.csv over Serial
       │  Python saves CSV locally
       │  Python sends confirmation → ESP32S3 deletes /session.csv → Idle
       │
       ▼
[parser.py decodes samples]
       │
┌──────┼──────┐
▼      ▼      ▼
[rehydration] [thermal] [sweat_rate]
└──────┼──────┘
       ▼
[scoring.py → Readiness Score]
       │
┌──────┴──────┐
▼             ▼
[SQLite history]  [FastAPI /results]
(learning loop)          │
                         ▼
               [React dashboard renders]
               "Drink 450ml · cool 10min · rest 6hrs"
```

---

## Technology Stack

| Layer | Technology | Language |
|---|---|---|
| Hardware | XIAO ESP32S3, SHT45, MAX30205, Grove GSR | — |
| Firmware | PlatformIO + Arduino framework, LittleFS | C++ |
| USB Serial transfer | pyserial (cross-platform serial client) | Python |
| Algorithm | numpy, scipy | Python |
| API server | FastAPI + uvicorn | Python |
| Session store | sqlite3 | Python |
| Dashboard | React + Recharts | JavaScript |

---

## Key Constraints & Decisions

- **LittleFS over RAM:** Session data survives power loss. File deleted only after the transfer confirmation is received.
- **1Hz sampling:** Sufficient for physiological signals; keeps file sizes manageable (~150KB/90min).
- **USB Serial transfer:** Transfer is initiated by the Python script detecting the device on a serial port when it is plugged into the laptop. `/session.csv` is deleted only after the script sends back a confirmation, so an interrupted transfer never loses data — the file simply transfers on the next plug-in.
- **Dynamic GSR calibration:** Personal baseline collected on each boot — no hardcoded thresholds.
- **12-bit ADC:** All GSR logic uses 0–4095 range. Do not use Arduino datasheet thresholds (10-bit).
- **5-session sliding window:** SQLite history keeps only the 5 most recent sessions. From session 6 onward, the oldest is dropped before the newest is saved — baselines always reflect current physiology.
- **Vapor chamber coefficient:** Rehydration math requires physical calibration of ΔRH → mL/min conversion before outputs are clinically meaningful. Flag as TODO until partner's vapor chamber characterization is complete.
- **Na⁺ ion-selective electrode — evaluated and rejected (July 6 audit):** An ISE on the existing I2C bus was the plan for a genuine (not population-average) mg sodium figure, since GSR measures total ionic conductivity and cannot isolate sodium. It was **decided against**: rigid bench-style ISE probes carry too much mounting/mechanical risk to hold reliably against skin on a wearable, and the per-session two-point calibration ritual is inherent to ISE chemistry and unavoidable. **Decided instead:** derive sodium *guidance* from the existing on-skin GSR sensor via `electrolyte_intensity.py` — a relative, personalized modifier on `SWEAT_SODIUM_MG_PER_L` (this athlete vs. their own recent sessions), plus a low/typical/high tier label. This uses hardware already on the band. **Acknowledged tradeoff — not resolved:** skin-contact impedance varies with electrode placement, pressure, and skin moisture, so the GSR signal (and thus the modifier) carries real session-to-session variability. This limitation is accepted, not fixed — it is the cost of avoiding added hardware. The modifier is deliberately *relative* and clamped precisely because the underlying signal is noisy; it never claims to be an absolute concentration.
- **Calibration transparency:** The rehydration mg output tracks sodium and volume calibration state independently. The mg number is always shown at full strength; a per-quantity flag communicates which halves are measured vs proxied, so the dashboard never presents a population guess as a personalized clinical value. The flag has three values: `provisional` (bare population constant / uncharacterized proxy), `gsr_adjusted` (sodium personalized by the GSR-derived relative modifier — better than population, but still not an absolute measurement), and `calibrated` (a true per-user measurement). Sodium tops out at `gsr_adjusted`; volume reaches `calibrated` once the vapor chamber is characterized.
