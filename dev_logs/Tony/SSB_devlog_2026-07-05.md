# SSB Dev Log — July 5, 2026

## Summary

No code today — a **logic/feasibility audit** of the Phase 3 backend, followed by
a **hardware planning decision**: committing in principle to a Na⁺ ion-selective
electrode (I2C) so the rehydration mg sodium output can become a real measurement
instead of a hardcoded population constant. The architecture doc was updated to
record the decision and its open items; this log captures the reasoning.

Nothing was built or committed. The electrode is **decided but not purchased** —
interface (I2C) is settled; exact part, output unit, and price are still to be
sourced. All backend/firmware changes that follow from this decision are deferred
until the part is in hand.

---

## Part 1 — Backend logic audit (read-only)

Ran a two-axis read-only audit of the backend: (A) algorithmic/mathematical
correctness, (B) cross-module contracts, invariants, and units. Physics/physiology
feasibility was handled separately (Part 2). Key results:

### Confirmed / refined findings

- **Mean SRI is a boundary functional, not a session-shape measure** (`sweat_rate.py`).
  The pre-flag guessed it reduces to `(last − first) / duration`; the real closed
  form (accounting for `numpy.gradient`'s `edge_order=1` one-sided endpoint
  stencils, which don't cancel on summation) is, for uniform spacing `h`:

  ```
  mean_sri = [3(y[n-1] − y[0]) + (y[1] − y[n-2])] / (2·n·h)
  ```

  So mean SRI depends only on the four boundary samples and is blind to the entire
  interior — verified numerically (perturbing an interior sample by +999 left the
  mean unchanged). Under non-uniform timestamps it additionally picks up a term
  proportional to local spacing *asymmetry* — i.e. clock jitter, not physiology.
  Verdict: degenerate/redundant with peak SRI, worth reconsidering whether it earns
  a slot in scoring. **Latent** (nothing consumes SRI until `scoring.py` exists).

- **`thermal_slope` has no producer** (`thermal.py` reads it; nothing writes it).
  `_run_algorithm_pipeline()` is still a stub; `scoring.py`/`main.py` don't exist,
  and `history.save_session()` stores an unschema'd dict. Consequence: baseline is
  permanently empty → `sessions_used = 0 < 3` → recommendation silently pinned to
  `passive_rest`, with no error. This is the load-bearing gap and it fails quietly.
  Its fix *is* the integration work — `scoring.py`/`main.py` is the missing producer.
  **Latent** (activator: `scoring.py`/`main.py`).

- **Intake window 250 mL (doc) vs 300 mL (code).** Code is self-consistent
  (1.2 L/hr × 15 min = 300); the doc's 250 was the outlier. Fixed in the doc today.

- **`_looks_like_ssb` space-drift** (`serial_receiver.py`). The junk-filter tests
  `startswith("#gsr_baseline")` but firmware emits `# gsr_baseline=` (with a space,
  confirmed by the July 4 bench capture `R# gsr_baseline=2454`). That detection arm
  is dead. Bounded impact — a normal complete transfer is still recognized via the
  `END`/`ERROR` paths — but a genuinely partial transfer could be misfiled as junk.
  The parser's own `^#\s*gsr_baseline` regex tolerates the space, so parsing is
  unaffected. Same constant-vs-schema drift class the devlogs keep catching.
  **Live** (only defect in code that runs today), low severity.

- **Both July-4 rehydration test bugs confirmed resolved on `main`** — the missing
  dataclass field and the vacuous epsilon assertion are both fixed; full suite green.

### Clean results (worth recording)

- Units are dimensionally consistent across every module boundary (every consumer
  converts `timestamp_ms → /1000 → s`; the rehydration integral is counts·seconds
  and the coefficient is mL per count·second → mL). The suspected ms/s 1000×
  inflation is **refuted**.
- CSV schema, `END` sentinel, truncated-final-row handling, and the 5-session
  eviction invariant (`MIN_BASELINE_SESSIONS = 3 ≤ MAX_SESSIONS = 5`) are all coherent.

### Framing takeaway

The entire algorithm layer is **unwired** — `_run_algorithm_pipeline()` is a stub,
so every Axis-A finding computes into a void until `scoring.py`/`api.py`/`main.py`
land. That stub is the single seam that gates all of them. Implication for
sequencing: the integration layer should be built **once**, against a model already
validated on physical grounds — not wired up first and reworked later.

---

## Part 2 — Feasibility axis (physics/physiology)

Three measurement models stress-tested against the sensing physics:

- **Thermal — feasible.** Skin temp over time is a sound measurement; the only issue
  is modeling exponential cooling with a straight-line `linregress` slope, which is
  window-length-dependent and confounds cross-session baseline comparison. Fix is a
  better curve model (a decaying-exponential time-constant τ is duration-independent),
  not a redesign. Green-light.

- **Sweat Rate Index — feasibility-*unconfirmed*, deferred by hardware.** SRI is only
  meaningful below chamber saturation: as RH → ~100%, ΔRH flattens to zero even as
  sweating continues, so the heaviest sweating could produce the *flattest* curve.
  Can't be tested — the vapor chamber isn't built and the rig is on a breadboard, so
  a real sweat session isn't possible. Decision: build SRI with **saturation
  awareness** (detect the near-saturation regime, flag SRI unreliable rather than
  reporting a flat curve as "low sweat"), so it fails loudly when the chamber does
  arrive. Deferred, not blocked.

- **Rehydration sodium (mg) — the driving decision.** GSR measures sudomotor activity
  and *total* ionic conductivity; it cannot isolate sodium, so it cannot yield a real
  mg-of-sodium figure on its own, and `SWEAT_SODIUM_MG_PER_L` is a population guess.
  Product requirement stands: athletes want a concrete mg number ("drink more water"
  is uselessly vague; experienced athletes already know the water story — the sodium
  figure is the value-add). Since a real mg number requires measuring sodium
  concentration directly, this led to the electrode decision below.

---

## Part 3 — Hardware decision: Na⁺ ion-selective electrode (I2C)

**Decision: add a Na⁺ ion-selective electrode on the existing I2C bus** to measure
sweat sodium concentration directly, converting `SWEAT_SODIUM_MG_PER_L` from a
hardcoded population constant into a measured, per-athlete, per-session value.

**Why an electrode at all.** The mg number is `concentration × volume`, summed over
the session. GSR gives neither — it's a "how wet/active is the skin" proxy that can't
separate sodium from potassium/chloride/other ions. A Na⁺ ISE has a membrane that
responds to sodium only, reporting the exact missing `C_sweat`. Analogy: a pool strip
that reads only chlorine, or a glucose meter that reads only blood sugar.

**Why I2C over a bare analog probe.** A raw ISE signal is tiny, high-impedance, and
logarithmic (Nernst). Reading it analog into the ESP32S3 means fighting ADC input
loading, building a high-impedance buffer amp, and hand-rolling the two-point
calibration + log conversion — a full analog-electrochemistry sub-project, the kind
that yields "stable but wrong" readings (cf. the MAX30205 clone episode). A packaged
I2C carrier (Atlas Scientific EZO-class is the reference) puts the buffer, ADC, and
calibration on-board; firmware just adds a third address to the SDA/SCL bus already
shared by SHT45 + MAX30205. This matches the project's standing instinct — don't
spend bench time on solved problems (shared I2C bus, LittleFS, USB Serial over BLE).
It also costs the scarce free analog pin nothing (A0 is already GSR).

**Honest tradeoffs recorded.** Packaged I2C carrier is pricier (~$40–60 order of
magnitude, comfortable against the $1,000 endowment but real); the two-solution
calibration ritual before each session is inherent to ISE chemistry and unavoidable
either way; and you trade raw-millivolt visibility for a finished number. Because the
electrode reads sweat directly (not the vapor chamber), it's one of the few upgrades
prototypable on the current breadboard.

**The key limitation, kept explicit.** The electrode upgrades only the *sodium* half
of the mg equation. *Volume* still depends on the un-built vapor chamber. So after
integration the state is: **sodium measured, volume still proxied.** This is why the
rehydration output should track calibration state **per-quantity** (sodium vs volume),
not with a single provisional/calibrated flag — otherwise the dashboard would either
over- or under-claim. The mg number is always emitted at full strength; the flag is
honest metadata beside it.

---

## Part 4 — Design clarifications (today)

Two design points the architecture doc left implicit or contradictory, resolved and recorded
today. No code.

### Per-user calibration phase — "emit and label, never withhold"

The calibration notions scattered across the modules (thermal's `MIN_BASELINE_SESSIONS = 3`,
the 5-session sliding window, rehydration's per-quantity calibration state, the planned SRI
saturation flag) are one coherent per-user phase: over a user's first several sessions the
volume coefficient, thermal baseline, sodium, and SRI all stabilize toward their per-user
values ("sessions 1–N, outputs stabilizing").

**Decision:** from session 1 the system emits full-strength output numbers and labels them
*stabilizing* — never withholding, fuzzing, or suppressing an output while calibration is thin.
**Why emit-and-label over withhold:** (1) consistency with `thermal.py`'s existing soft-fallback,
which returns `passive_rest` rather than withholding when baseline data is sparse — the same
instinct, made system-wide; (2) withholding starves the user of data exactly when they're most
curious (the first few sessions), whereas an honest "stabilizing" label sets expectations
without hiding the number. The calibration state is a **forward contract** the not-yet-built
scoring/API/dashboard layers must read and surface.

### Sensor → output mapping / volume-source reconciliation

The doc named two competing volume sources — the rehydration section called GSR-drop the
sweat-volume proxy, while the chamber framing called vapor-chamber ΔRH → mL/min the source — and
never reconciled them. Clarified: **vapor-chamber ΔRH → mL/min is the canonical `V_rate`** that
feeds the rehydration mg calculation. **GSR-drop-as-volume was a pre-chamber placeholder only**,
adopted because the chamber wasn't built; once the chamber is characterized GSR retires from the
volume calculation to a **trigger/intensity role** (it still drives the 20%-drop sweat-onset
trigger; it no longer feeds `V_rate`). Added an explicit "what each sensor reading means" mapping
so a future builder sees exactly one volume source.

---

## Part 5 — Hardware sourcing (today)

Three candidate parts triaged for the sensor plan. Priority stated explicitly so none is
over-weighted.

### Na⁺ ion-selective electrode (I2C) — HIGH priority, the real unlock

Still to source, and the part everything downstream waits on: it is the only path to a measured
(not population-guess) mg sodium number. Interface is decided — an I2C packaged carrier (Atlas
Scientific EZO-class as the reference example). Still open: exact module, output unit (mmol/L vs
mg/L — determines whether a ×23 mg/mmol conversion is needed), and price against the $1,000
budget. This is the next purchase that matters.

### Gold cup electrodes — LOW priority, optional GSR signal-quality upgrade (not a sodium fix)

Clarifying a common confusion: gold cup electrodes are a **contact-material upgrade to the
existing Grove GSR sensor** — they still measure total skin conductance (GSR); they do **not**
measure sodium. They would give a cleaner GSR signal on sweaty skin in motion (corrosion/
polarization resistance, stable contact), but GSR signal quality is not a current bottleneck.
Sourcing finding: lab-grade gold cups (e.g. BIOPAC EL160) have a connector mismatch with the
Grove GSR module (Touchproof/DIN vs Grove leads), are sold singly at research prices, and need
conductive paste — so if pursued, a hobbyist gold-cup set with Grove-compatible or solderable
leads is the better buy. Optional, deferrable.

### Adafruit 3961 conductive nylon fabric tape (already purchased) — not usable for either role

Recording this so it isn't mistakenly pressed into service later: it is a **conductive trace
material** (metallic nylon + conductive glue), not an electrode and not gold. As a GSR skin
contact on sweaty skin it would likely corrode/drift and perform worse than the existing Velcro
finger straps. It fills neither the gold-electrode nor the Na⁺-ISE role. Fine as a general
wearables-bin material; not part of the SSB sensor plan.

---

## Architecture doc changes (today)

- Added the Na⁺ ISE to the hardware sensor table (flagged planned/not-purchased).
- Rewrote the rehydration algorithm section to document the two-half calibration
  state and the per-quantity flag requirement.
- Updated the "Three Core Outputs" sodium derivation line.
- Noted the planned 6th CSV column (`na_conc`), with the schema-update dependency
  (parser + receiver header + `EXPECTED_COLS`).
- Added two "Key Constraints & Decisions" entries: the electrode decision (with the
  I2C-over-analog rationale and open items) and the calibration-transparency principle.
- Fixed the intake-window inconsistency (250 → 300 mL).
- Added a **Per-User Calibration Phase** section unifying the scattered calibration notions into
  one "sessions 1–N, outputs stabilizing" model, with the system-wide emit-and-label rule and the
  forward contract for scoring/API/dashboard.
- Added a **Sensor → Output Mapping** subsection and reconciled the rehydration algorithm wording
  to name a single canonical volume source (chamber ΔRH), with GSR demoted to its trigger/intensity
  role post-chamber.
- Reframed volume from "forever provisional" to calibrated-per-user once the chamber is characterized.

---

## Outstanding / next steps

**Blocked on purchasing:**
- **HIGH — the next purchase that matters:** source the Na⁺ ISE I2C module — confirm exact part,
  **output unit (mmol/L vs mg/L)**, and price. The output unit determines whether a molar-mass
  conversion (×23 mg/mmol) is needed and whether it lives in firmware or backend.
- **Optional / deferrable:** gold cup electrodes — a GSR contact-material upgrade for a cleaner
  signal on sweaty skin, *not* a sodium fix and not a current bottleneck. If pursued, buy a
  hobbyist set with Grove-compatible/solderable leads (lab-grade cups like BIOPAC EL160 mismatch
  the Grove connector, sell singly at research prices, and need conductive paste).

**Queued once the part is chosen (two prompts, in sequence):**
1. Firmware — add the electrode I2C read + the 6th `na_conc` CSV column (firmware stays
   a dumb sensor logger; all mg math stays in the backend).
2. Backend — thread real `C_sweat` into `rehydration.py`, add the per-quantity
   `calibration_state`, and flip sodium to `calibrated` when the electrode value is present.

**Independent of the electrode (can proceed anytime):**
- SRI saturation-awareness flag (`sweat_rate.py`) — plan already drafted.
- The two trivial audit sweep-ups: `_looks_like_ssb` space-drift (`serial_receiver.py`)
  and the already-fixed doc window value.
- The integration layer (`scoring.py` → `api.py` → `main.py`), which is also the
  `thermal_slope` producer — build once, against the validated model. It must build against the
  per-user calibration-state contract — reading and surfacing each output's stabilizing/calibrated
  state (emit-and-label, never withhold).

**Still hardware-blocked (unchanged):**
- Vapor chamber ΔRH → mL/min characterization (partner-led) — gates the volume half.
- GSR 20%-drop real-sweat stress test — needs a non-breadboard rig and a sweat session.
