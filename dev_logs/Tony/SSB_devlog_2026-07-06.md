# SSB Dev Log — July 6, 2026

## Summary

Designed and implemented `ssb_backend/algorithm/electrolyte_intensity.py` —
the GSR-derived electrolyte-loss intensity module that replaces the
abandoned Na⁺ ISE hardware path (see July 5 audit). Also wrote its `pytest`
suite (`test_electrolyte_intensity.py`, 9 tests). This module went through a
full design-spec-first process: the logic was written out as a documentation
spec before any code existed, reviewed and revised, then implemented and
debugged across several passes before being finalized. Both files were typed
in, committed as two separate commits per convention, pushed, and merged
into `main` today.

Like the rest of Phase 3 backend work, none of this needs the physical
device — the module is read-only over history and is fully exercised via
`tmp_path` SQLite files.

---

## Part 1 — Design spec

Before writing any code, the module's logic was fully specified as prose:
function signature, dataclass fields, step-by-step logic for all 6 steps,
edge cases, and non-goals. Writing the spec out in full first — rather than
jumping straight to code — surfaced two design issues early:

### Revisions made during spec review

- **Constant naming drift.** The first draft used `MODIFIER_MIN`/
  `MODIFIER_MAX` instead of the architecture-doc's established
  `GSR_MODIFIER_MIN_CLAMP`/`GSR_MODIFIER_MAX_CLAMP` naming. Renamed for
  consistency, along with the tier thresholds
  (`GSR_TIER_LOW_THRESHOLD`/`GSR_TIER_HIGH_THRESHOLD`).
- **Insufficient-baseline tier defaulting to `"typical"`.** The first draft
  mirrored `thermal.py`'s pattern exactly: when fewer than
  `MIN_BASELINE_SESSIONS` (3) history sessions exist, default to a "safe"
  label — in `thermal.py`'s case, `passive_rest`; in the first draft here,
  `tier="typical"`. This reproduced the **exact gap** the July 5 audit
  called out in `thermal.py` — a baseline-insufficient result silently
  presenting as a normal one, catchable only if every downstream consumer
  remembers to check the `insufficient_baseline` boolean. Per the project's
  own "emit and label, never withhold" principle (also from the July 5
  log), the fix was to keep `modifier=1.0` as the safe numeric default but
  change the label itself to `tier="insufficient_data"` — so the tier is
  never allowed to lie about calibration state, independent of whether a
  caller checks the flag.

### Approved design (final shape)

Public entry point:
```python
def compute_gsr_electrolyte_adjustment(
    samples: list[dict],
    gsr_baseline: int,
    db_path: str | Path = history.DEFAULT_DB_PATH,
) -> GsrElectrolyteResult
```

`GsrElectrolyteResult` fields: `current_intensity`, `baseline_intensity`,
`modifier`, `tier` (`Literal["insufficient_data", "low", "typical", "high"]`),
`sessions_used`, `insufficient_baseline`.

Six-step logic, mirroring `thermal.py`'s structure but standard-library only
(no `scipy` — just `min`/mean arithmetic):

1. **Degenerate-input guard** — 0 samples *or* `gsr_baseline <= 0` (the
   latter a design addition beyond the original ask, preventing a
   divide-by-zero) short-circuits to `insufficient_data`. Unlike
   `thermal.py`'s 2-sample minimum, 1 sample is enough here — a peak drop
   only needs a `min()`.
2. **Current-session intensity** — relative peak drop:
   `(gsr_baseline - min(gsr_raw)) / gsr_baseline`, floored at `0.0` so a
   session dryer than baseline reads as zero intensity, never negative.
3. **Baseline intensity from history** — pulled from
   `history.get_recent_sessions()`, filtering out sessions missing a
   `gsr_drop_intensity` value. A `# CONTRACT:` comment (matching
   `thermal.py`'s `thermal_slope` contract) documents that nothing writes
   this key yet — it's a forward dependency on `scoring.py`/`main.py`.
4. **Minimum baseline gate** — `MIN_BASELINE_SESSIONS = 3`; below that,
   return `modifier=1.0`, `tier="insufficient_data"` (the corrected
   behavior from the spec revision above).
5. **Clamped modifier** — `current / baseline`, clamped to
   `[GSR_MODIFIER_MIN_CLAMP, GSR_MODIFIER_MAX_CLAMP]` (`0.5`–`2.0`,
   TODO-flagged placeholders). A documented edge case: if
   `baseline_intensity == 0` (all past sessions had zero drop), the ratio
   is undefined — resolved to `GSR_MODIFIER_MAX_CLAMP` if the current
   session shows any drop, else neutral `1.0`.
6. **Tier classification** — on the *clamped* modifier, so tier and
   modifier never disagree: `< GSR_TIER_LOW_THRESHOLD` (`0.8`) → `"low"`;
   `> GSR_TIER_HIGH_THRESHOLD` (`1.2`) → `"high"`; otherwise `"typical"`
   (both boundaries inclusive to `"typical"`, i.e. strict `<`/`>`).

---

## Part 2 — Implementation & debugging

With the design finalized, the module was implemented and put through
several rounds of review before being considered correct. A first pass at
the code carried **8 distinct bugs**, caught in review before any of it was
typed into the repo:

1. **Tuple-comma typo** — `GSR_TIER_LOW_THRESHOLD = 0.8,` (trailing comma)
   silently made the constant a 1-tuple instead of a float, which would
   raise `TypeError` on every tier comparison.
2. **`get_modifier()` missing `return`** — the function computed and
   clamped `modifier` locally but never returned it, so every real call
   received `modifier=None`.
3. **Undefined-variable reference** — `min_baseline_sessions_not_acheived()`
   referenced `current_intensity`, a name never passed into or defined in
   that function's scope; would raise `NameError` on the very common
   less-than-3-history-sessions path.
4. **History key typo/mismatch** — the list comprehension extracted
   `"gsr_drop_intensities"` (plural) while the filter checked
   `"grs_drop_intensities"` (transposed letters, also plural) — neither
   matched the agreed contract key `"gsr_drop_intensity"` (singular).
5. **Missing `gsr_baseline <= 0` guard** — the spec's divide-by-zero
   protection was absent; a separate helper existed instead but only
   logged a plausibility warning without an early return.
6. **Wrong degenerate-sample threshold** — guarded on `sample_count < 2`
   (copied from `thermal.py`) instead of the spec's explicit `== 0`, a
   deliberate divergence since one sample suffices for a peak drop here.
7. **Stale log message** — `"defaulting to passive_rest"`, copy-pasted from
   `thermal.py`, described a concept (`passive_rest`) that doesn't exist in
   this module.
8. **Missing `# CONTRACT:` comment** — the required forward-dependency
   documentation on the history-key assumption was absent entirely.

A follow-up correction pass fixed 5 of the 8 cleanly but left 3 unresolved:
the history key was still plural (internally consistent this time, but
still not matching the real contract key), the log message wording was
only half-corrected, and `get_tier`'s type hint still read `str` instead of
`float`. A second correction pass resolved the key rename and the
`# CONTRACT:` comment addition together, along with the log wording and the
type hint — except the `# CONTRACT:` comment itself turned out to still be
missing even after the key rename landed. A final, targeted pass added the
one-line comment and confirmed it was worded correctly.

**Net result:** all 8 original bugs, tracked individually across the
correction passes, are now confirmed fixed. No broken version of this
module ever reached the repo — everything was caught in review before
typing.

---

## Part 3 — Test suite review

`ssb_backend/tests/test_electrolyte_intensity.py` (9 tests) was reviewed by
hand-tracing each test against the corrected implementation:

- `test_empty_samples` / `test_non_positive_gsr_baseline` — both exercise
  the Step 1 degenerate-input guard.
- `test_no_history_neutral_modifier` — confirms `current_intensity` is
  still computed and returned (`0.25`) even when the baseline gate fires,
  proving the "emit and label" behavior holds at the code level, not just
  in the design.
- `test_negative_drop_clamps_to_zero` — confirms the `max(0.0, ...)` floor.
- `test_modifier_clamped_to_min` / `test_modifier_clamped_to_max` — hand-
  verified raw ratios (`0.4` and `4.0` against a seeded baseline of `0.25`)
  both clamp correctly to the configured bounds.
- `test_tier_boundaries_are_typical` — exploits `0.25` being an exact power
  of two so the resulting ratios land bit-for-bit on `0.8`/`1.2`, proving
  the strict `<`/`>` boundary logic (both edges classify `"typical"`)
  without needing `pytest.approx` tolerance.
- `test_zero_baseline_intensity` — exercises both branches of the
  degenerate zero-baseline edge case (current intensity `>0` vs. `==0`).
- `test_sessions_used_skips_invalid_rows` — seeds a mix of valid, explicit
  `None`, and key-missing history rows; confirms `sessions_used` correctly
  counts only the 3 valid ones and the baseline mean is computed
  accordingly.

No bugs found in the test suite. Approved as-is.

---

## Git

Both files were typed in, committed as two separate commits per this
project's established convention (feature, then test), pushed, and merged
into `main`:

1. `feat(backend): add electrolyte_intensity.py for GSR-derived electrolyte intensity modifier`
2. `test(backend): add test_electrolyte_intensity.py for electrolyte_intensity.py`

---

## Outstanding / next steps

- **Module docstring is minimal.** The approved code carries an empty
  top-level docstring; worth filling in with the peak-drop concept
  description before/shortly after committing, for consistency with every
  other module in `algorithm/`.
- **Not yet wired into `rehydration.py`.** Per the architecture doc, this
  module is a standalone helper — `rehydration.py` does not yet consume its
  modifier or tier. Wiring it in (adding the per-quantity `calibration_state`
  transition from `provisional` to `gsr_adjusted`) is a separate follow-up
  task.
- **`scoring.py`** remains the next module in dependency order after the
  wiring task above — and the eventual producer of both `thermal_slope`
  and `gsr_drop_intensity`, the two history keys currently read via
  `# CONTRACT:` comments from an empty well.
- **Firmware hardware bench verification** and the **GSR 20%-drop
  real-sweat stress test** — unchanged, still outstanding and
  hardware-blocked.
- **React/Recharts dashboard** — not started.
- **Vapor chamber ΔRH → mL/min characterization** — partner-led, still
  gates the volume half of `rehydration.py`.
