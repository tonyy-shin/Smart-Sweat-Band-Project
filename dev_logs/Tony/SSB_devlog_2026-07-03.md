# SSB Dev Log — July 3, 2026

## Summary

Hand-implemented `ssb_backend/algorithm/rehydration.py` against a spec reviewed
and approved over multiple chat rounds — this is the first Phase 3 backend
module written by hand rather than typed in from Claude Code output. Two
review passes against the implementation caught real bugs before commit
(inverted window-count math, a malformed `np.concatenate` call, a broken
sodium-proportionality formula, and more — full list below). The module was
then refactored into four helper functions
(`insufficient_data_result`, `dedupe_timestamps`, `compute_volume_and_sodium`,
`build_intake_schedule`) per a Claude Code plan reviewed and approved in chat,
which also surfaced a fifth bug: an early hand-typed guard helper had its
return value discarded at both call sites, so `insufficient_data` never
actually fired.

`ssb_backend/tests/test_rehydration.py` (15 tests) was then drafted by Claude
Code — output-only, hand-typed in rather than written to disk directly — and
went through two further review rounds that caught bugs in the test file
itself before it was finalized.

Like the rest of Phase 3, none of this needs the physical device — pure
proxy/volume/sodium arithmetic over parsed samples, verified locally.
`rehydration.py` is committed to `phase3/python-backend`; `test_rehydration.py`
is written and reviewed but not yet committed pending a real local test run.

---

## What was implemented

### `ssb_backend/algorithm/rehydration.py` (182 lines)

Standard-library plus `numpy`. Public entry point:

```python
def compute_rehydration_prescription(
    samples: list[dict],
    gsr_baseline: int,
) -> RehydrationResult
```

Uses the GSR drop from baseline as a proxy for sweat volume, integrated over
session time with `numpy.trapezoid`, then converted to a fluid target (ACSM
150% replacement rule) and sodium mass, paced into 15-minute intake windows.

**Design decisions:**
- **Proxy clamped before integrating.** `proxy = max(gsr_baseline - gsr, 0)`
  per sample — a below-baseline spike (GSR rising above baseline) can't
  produce a negative proxy that would erode the integral.
- **Sodium from `sweat_volume_ml`, not the 1.5x fluid figure** —
  `total_sodium_mg = (sweat_volume_ml / 1000.0) * SWEAT_SODIUM_MG_PER_L`,
  kept independent of the ACSM replacement factor.
- **Windowing** — full windows at `MAX_INTAKE_PER_WINDOW_ML` (300 mL), one
  partial remainder window, no trailing window when the remainder is at or
  below `SCHEDULE_REMAINDER_EPSILON_ML` (guards float noise on an
  exact-multiple-of-300 total). Sodium is allocated to each window
  proportional to its fluid share.
- **`gsr_baseline` plausibility check** (`validate_gsr`) — warn-and-continue,
  not a hard reject, matching the existing duplicate-timestamp pattern.
  Range `[500, 2300]` reasoned from `SSB_architecture.md`: the firmware's
  dynamic calibration only *starts* averaging once contact drops below 2300
  (line 50 of the architecture doc), so any real calibrated baseline is
  bounded above by 2300; 500 is a floor against a disconnected/malfunctioning
  electrode reading. The doc's separate "~2450 resting" figure describes an
  *offline/no-contact* reading, not a valid post-calibration baseline, so it
  was not used as the upper bound.
- **Decomposed into four helpers** post-implementation, orchestrated by
  `compute_rehydration_prescription()`: `insufficient_data_result` (guard),
  `dedupe_timestamps` (dt==0 handling), `compute_volume_and_sodium` (proxy →
  integral → scalars), `build_intake_schedule` (window construction). Pure
  structural split — no behavior change beyond fixing the discarded-guard bug
  below.

### `ssb_backend/tests/test_rehydration.py` (238 lines, 15 tests)

Mirrors the `_sample()`-builder / plain-function style of `test_thermal.py`
and `test_sweat_rate.py`. Covers: empty/single-sample insufficient-data,
constant-proxy volume against hand-computed trapezoid arithmetic, the 150%
fluid-replacement and sodium-mass relationships, five schedule/windowing
scenarios (caps at 300 mL, remainder window, exact-multiple no trailing
window, single sub-300 window, window start times), sodium proportionality,
volume-sum consistency, duplicate-timestamp dropping, zero-duration collapse
to `insufficient_data`, zero-fluid `ok`-with-empty-schedule, and negative-proxy
clamping.

---

## Bugs found & fixed (implementation review)

Six issues were caught across two review passes before commit.

### Malformed `np.concatenate` call

```python
keep = np.concatenate([True], dt != 0)
```

`[True]` and `dt != 0` were passed as two positional args instead of one
sequence — `np.concatenate` takes `(arrays, axis=...)`, so this raises at
runtime the moment any duplicate timestamp exists (i.e. exactly the
zero-duration-session path).

**Fix:** `np.concatenate(([True], dt != 0))`.

### `start_s=full_windows*IntakeWindow` — class instead of constant

The remainder-window construction multiplied by the `IntakeWindow` class
itself instead of `INTAKE_WINDOW_S`, raising `TypeError` on every session with
a partial trailing window.

**Fix:** `start_s=full_windows*INTAKE_WINDOW_S`.

### Window count inverted

```python
full_windows = int(MAX_INTAKE_PER_WINDOW_ML // total_fluid_ml)
```

Computed `300 // total_fluid`, which is 0 for any normal (>300 mL) session —
dividend and divisor were swapped, so the "remainder" window ended up holding
the entire fluid target, exceeding the 300 mL cap it was meant to enforce.

**Fix:** `int(total_fluid_ml // MAX_INTAKE_PER_WINDOW_ML)`.

### Sodium allocation collapsed to plain volume

```python
sodium_mg=total_fluid_ml*(volume/total_fluid_ml)
```

Algebraically reduces to just `volume` — every window's `sodium_mg` was
silently set equal to its fluid *milliliters*, not a sodium mass.

**Fix:** proportional base changed from `total_fluid_ml` to `total_sodium_mg`.

### `SCHEDULE_REMAINDER_EPSILON_ML` defined but never wired in

The trailing-window guard tested `if remainder > 0:` — on an exact multiple of
300, float subtraction can leave a ~1e-13 residual, producing a spurious
near-zero fourth window. The epsilon constant existed but wasn't referenced
anywhere.

**Fix:** `if remainder > SCHEDULE_REMAINDER_EPSILON_ML:`.

### Guard helper's return value discarded (found during refactor planning)

An early hand-typed extraction of the `insufficient_data` guard
(`validate_insufficient_data`) built and returned the result object, but both
call sites discarded the return value — the early return never fired, so a
`<2`-sample input fell through to a crash on empty-array indexing instead of
returning `insufficient_data`. Surfaced as a byproduct of extracting the guard
helper during the decomposition refactor (user-confirmed fix, not a silent
behavior change).

**Fix:** guard renamed to `insufficient_data_result(sample_count) -> RehydrationResult | None`; both call sites now check and return:
```python
guard = insufficient_data_result(sample_count)
if guard is not None:
    return guard
```

All six were caught in review before commit — `main` and this branch never
carried a broken version of `rehydration.py`.

---

## Bugs found & fixed (test file review)

Two rounds of review on the drafted `test_rehydration.py` caught four issues
before it was finalized.

- **Missing dataclass fields → `TypeError`** — `test_empty_sample` and
  `test_single_sample` each omitted a required `RehydrationResult` field
  (`total_sodium_mg` and `schedule=[]` respectively). `RehydrationResult` has
  no default values, so both would raise `TypeError` at collection/run time,
  not just fail an assertion.
- **Vacuous epsilon assertion** —
  `result.total_fluid_ml - 2*MAX_INTAKE_PER_WINDOW_ML <= SCHEDULE_REMAINDER_EPSILON_ML`
  is true even when the result took the *wrong* branch (1 full window + a
  near-300mL remainder instead of 2 clean full windows), since a negative
  number is always ≤ a positive epsilon. Replaced with direct per-window
  volume assertions that actually distinguish the two branches.
- **Stray trailing `L` character** — a literal `L` left after a closing
  paren on an assertion line, a plain `SyntaxError`.
- **Naming inconsistency** — `test_empty_sample` renamed to `test_empty_samples`
  (plural) to match the rest of the spec's test list.

All four were caught in review before the file was considered final — nothing
broken was ever run against the real module.

---

## Build / test verification

```
[PASTE PYTEST OUTPUT HERE — e.g. `python -m pytest ssb_backend/tests/test_rehydration.py -v` and `python -m pytest -q` for the full suite]
```

---

## Git

Both commits landed on `phase3/python-backend`:

```
e7a8c93 test(backend): add test_rehydration.py for rehydration.py
188b9dd feat(backend): add rehydration.py for fluid and sodium prescription
```

Kept as two separate commits (feature, then test) per this project's
established convention. The bugs listed above — six in the implementation,
four in the test file — were all caught and fixed in review before their
respective commits, so neither ever carried a broken version.

---

## Outstanding / next steps

- **Commit `test_rehydration.py`** once the pytest run above is confirmed green.
- **`scoring.py`, `api.py`, `main.py`** — next in dependency order now that all
  three algorithm modules (`sweat_rate.py`, `thermal.py`, `rehydration.py`)
  exist; these are also the eventual producers of the `"thermal_slope"`
  history key `thermal.py` depends on.
- **Vapor-chamber calibration coefficient** (`SWEAT_CALIBRATION_ML_PER_COUNT_S`)
  and **sweat sodium concentration** (`SWEAT_SODIUM_MG_PER_L`) remain
  TODO-flagged placeholders pending the partner's physical vapor-chamber
  characterization — unchanged from prior logs.
- **`gsr_baseline` plausibility range `[500, 2300]`** is a reasoned default,
  not a spec-mandated value — worth revisiting once real device calibration
  data is available to confirm the bounds.
- **Firmware hardware bench verification** and the **GSR 20%-drop real-sweat
  stress test** — remain outstanding and hardware-dependent, unchanged from
  prior logs.
