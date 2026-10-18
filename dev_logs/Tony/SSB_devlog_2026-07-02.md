# SSB Dev Log — July 2, 2026

## Summary

Built `ssb_backend/history.py`, the SQLite session-history store for Phase 3 —
the module that persists each session's algorithm results as a JSON blob and
enforces a sliding window of the 5 most recent sessions, per the spec in
`SSB_architecture.md`. Also stood up its `pytest` suite
(`test_history.py`, 6 tests). Both were reviewed in chat before being typed in,
across two review cycles that caught two bugs pre-commit. Developed on the
existing `phase3/python-backend` branch (continuing on from PR #4) and pushed;
not yet opened as a PR.

Like `parser.py` and `serial_receiver.py`, none of this needs the physical
device — the store is exercised entirely against `tmp_path` SQLite files, so
everything here was verified locally without hardware.

---

## What was implemented

### `ssb_backend/history.py` (new)

Standard-library only (`sqlite3`, `json`, `datetime`, `pathlib`,
`contextlib.closing`). Every public function takes a `db_path` parameter
rather than relying on a global connection, so it's fully testable against a
temp file — no schema/connection state lives at module level beyond the
`CREATE TABLE` SQL string itself.

- `init_db(db_path=DEFAULT_DB_PATH)` — creates the `sessions` table
  (`id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
  session_json TEXT NOT NULL`) and the parent `data/` directory if missing.
- `save_session(result, db_path=..., timestamp=None)` — serializes `result`
  to JSON and inserts a row. If the table is already at `MAX_SESSIONS` (5),
  evicts the oldest row(s) first — `evict = count - MAX_SESSIONS + 1`, so it
  self-heals even if the table somehow exceeded 5. Delete-then-insert happens
  inside a single transaction. `timestamp` defaults to
  `datetime.now().isoformat()` but is injectable for deterministic testing.
- `get_recent_sessions(limit=MAX_SESSIONS, db_path=...)` — selects
  `ORDER BY id DESC LIMIT ?`, then reverses in Python to return sessions
  **oldest to newest**, ready for direct use by trend/regression code later
  (e.g. `thermal.py`'s baseline calculation).
- `get_session_count(db_path=...)` — returns the current row count.
- Every function runs `CREATE TABLE IF NOT EXISTS` itself (not just
  `init_db`), so any function is safe to call standalone against a brand-new
  `tmp_path` file without a separate setup step.
- Connections use `with closing(sqlite3.connect(db_path)) as conn, conn:` —
  `sqlite3.Connection` as a context manager only commits/rolls back the
  transaction, it does not close the connection, so `contextlib.closing` is
  layered on to guarantee the close. One short-lived connection per call, no
  pooling.

The store is deliberately generic — it has no knowledge of the shape of the
`result` dict passed to `save_session`. That's `scoring.py`'s concern once it
exists; `history.py`'s job is persist, enforce the window, return past
sessions.

### `ssb_backend/tests/test_history.py` (new, 6 tests)

Follows the existing `test_parser.py` / `test_serial_receiver.py` style —
plain functions, no classes, pytest's built-in `tmp_path` fixture for
filesystem isolation (each test gets its own fresh temp dir, so the real
`ssb_backend/data/ssb_history.db` is never touched).

- `test_fresh_db_count_zero` — `get_session_count` on a brand-new `tmp_path`
  DB returns `0` without calling `init_db` first, pinning down the
  per-function `CREATE TABLE IF NOT EXISTS` safety net.
- `test_save_and_retrieve_roundtrip` — a single nested dict
  (`{"score": 87.5, "rehydration": {...}}`) survives the JSON round-trip
  through SQLite exactly.
- `test_ordering_oldest_to_newest` — 3 sessions with distinct injected
  timestamps come back in the right order, isolated from the eviction logic.
- `test_sliding_window_eviction` — saves 7 sessions; asserts count stays at 5
  and the retained sessions are specifically `[2, 3, 4, 5, 6]` (0 and 1
  evicted), not just the count.
- `test_limit_parameter` — with 5 sessions saved, `limit=2` returns only the
  2 most recent, still oldest-to-newest.
- `test_init_db_idempotent` — calling `init_db` twice doesn't raise or
  corrupt the table; the store still works normally afterward.

A `_save_n(db, n, start=0)` helper saves sessions with deterministic,
strictly increasing injected timestamps (`2026-07-02T00:00:00`, `:01`, …) —
the same injection pattern used in `serial_receiver.py`'s `save_csv` tests —
so ordering and eviction assertions are exact and non-flaky.

---

## Bugs found & fixed (pre-commit review)

Two issues were caught across review cycles in chat before either file was
typed into the repo.

### Malformed `IN` subquery in the eviction `DELETE`

The first draft of the eviction query was missing parentheses around the
subquery:

```python
"DELETE FROM sessions WHERE id IN "
"SELECT id FROM sessions ORDER BY id ASC LIMIT ?"
```

`WHERE id IN SELECT ...` isn't valid SQL — SQLite requires
`IN (SELECT ...)`. As written, this would raise
`sqlite3.OperationalError: near "SELECT": syntax error` the moment a 6th
session was saved, i.e. the very first time the sliding window actually had
to evict anything.

**Fix:**
```python
"DELETE FROM sessions WHERE id IN "
"(SELECT id FROM sessions ORDER BY id ASC LIMIT ?)"
```

### `mkdir(parents=True, exist=True)` — wrong keyword

`Path.mkdir` takes `exist_ok`, not `exist`. As originally typed, calling
`init_db()` for the first time would raise
`TypeError: mkdir() got an unexpected keyword argument 'exist'` before the
table was ever created.

**Fix:** `Path(db_path).parent.mkdir(parents=True, exist_ok=True)`.

Both were caught in review before commit — `main` (and this branch) never
carried a broken version of either function.

---

## Build / test verification

```
python -m pytest ssb_backend/tests/test_history.py -v
...... [100%]
6 passed

python -m pytest -q
.......................... [100%]
26 passed
```

Full backend suite is now 26 tests (9 parser + 11 serial + 6 history), all
green. No hardware needed.

---

## Git

Both commits landed on the existing `phase3/python-backend` branch
(continuing on top of the already-merged PR #4 work) and are pushed to
`origin`:

```
f228e99 (HEAD -> phase3/python-backend, origin/phase3/python-backend) test(backend): add test_history.py for history.py
5680700 feat(backend): add history.py for SQLite session history storage
b1fb94f fix: updated ci by adding pyserial
e2c00e3 test(backend): add test for serial_receiver.py
ca052c3 feat(backend): add serial_receiver.py for USB device detection and transfer
```

Kept as two separate commits (feature, then test) per this project's
established convention. **Not yet opened as a PR into `main`** — that's the
immediate next step before moving on to new modules.

---

# Phase 3 Backend — `sweat_rate.py` + requirements.txt centralization (same evening)

## Summary

Built `ssb_backend/algorithm/sweat_rate.py`, the Sweat Rate Index computation
module, and its `pytest` suite (`test_sweat_rate.py`, 4 tests). Also created
`requirements.txt` and updated `.github/workflows/ci.yml` to centralize
backend dependencies, fixing a recurring dependency-drift pattern. All work
was reviewed in chat across multiple plan/critique cycles before being typed in,
following this project's established workflow. No hardware needed — pure
Python/config work, verified locally and in CI.

---

## What was implemented

### `ssb_backend/algorithm/sweat_rate.py` (new, 80 lines)

Standard-library only (`dataclasses`, `logging`); `numpy` for gradient
computation. Public entry point:

```python
def compute_sweat_rate_index(samples: list[dict]) -> SweatRateResult
```

Accepts a parsed sample list from `parser.py` and returns a
`SweatRateResult(mean_sri, peak_sri, sample_count)` dataclass with `mean_sri`
and `peak_sri` optional, encoding degenerate cases (0 or 1 samples) by setting
those fields to `None` while `sample_count` always reflects the actual count used.

**Design decisions:**
- **Timestamp conversion to seconds.** Input `timestamp_ms` is converted to
  seconds via `time_s = np.array([s["timestamp_ms"] for s in samples], dtype=float) / 1000.0`
  so the gradient's units are readable (SRI in `%RH/s` — percent relative
  humidity per second) rather than in per-millisecond increments.
- **Peak SRI as max gradient, not max absolute.** SRI models accumulation
  during exertion (rising humidity). The gradient is computed via
  `numpy.gradient(humidity_pct, time_s)`. A negative gradient reflects
  venting (humidity dropping), not sweat rate — so peak SRI is `max(gradient)`,
  not `max(abs(gradient))`. A negative slope should never be eligible to "win"
  as the peak.
- **Mean SRI unfiltered.** Mean SRI is a plain arithmetic mean over the full
  gradient array, unfiltered, since it's meant to reflect overall session
  trend without smoothing away natural peaks and valleys.
- **Duplicate-consecutive-timestamp defense.** Before computing the gradient,
  any rows with identical consecutive timestamps are deduplicated (keeping the
  first occurrence, dropping the second) via a lightweight scan. A `dt == 0`
  would cause `numpy.gradient`'s finite-difference scheme to produce `inf`/`nan`.
  This is a surgical guard: non-monotonic (out-of-order) timestamps are trusted
  as an upstream contract from `parser.py` and not defensively guarded,
  avoiding over-engineering.
- **`sample_count` reflects post-filter count.** After deduplication,
  `sample_count` is the count actually used for the gradient, not `len(samples)`.
  This is called out explicitly in the docstring so callers can distinguish
  input size from the count used.

### `ssb_backend/tests/test_sweat_rate.py` (new, 4 tests)

- `test_linear_humidity_increase` — evenly-spaced timestamps with perfectly
  linear humidity increase (gradient slope identical at every point by design),
  so every point of `numpy.gradient`'s central/edge finite-difference scheme
  collapses to the exact same value. Safe for `==` assertion without
  `pytest.approx`.
- `test_empty_samples` — 0 samples returns `SweatRateResult(mean_sri=None, peak_sri=None, sample_count=0)`.
- `test_single_sample` — 1 sample returns `SweatRateResult(mean_sri=None, peak_sri=None, sample_count=1)`.
- `test_drop_duplicate_timestamp` — injects a decoy sample at a duplicate
  timestamp with a wildly different humidity value; asserts the result still
  equals the clean linear-series expectation. Proves both that the
  decoy/second-occurrence was dropped and that `sample_count` reflects the
  reduced count (3 instead of 4).

### `requirements.txt` (new, repo root)

Unpinned dependencies:
```
pytest
pyserial
numpy
```

### `.github/workflows/ci.yml` (updated)

Replaced the inline package list with centralized install:
```yaml
pip install -r requirements.txt
```

**Motivation:** The existing pattern (`pip install pytest pyserial`) led to
repeated gaps — July 1 fixed a missing `pyserial`, July 2 fixed a missing
`numpy`. Centralizing into `requirements.txt` prevents future omissions and
makes the dependency list a single source of truth for both local dev and CI.

---

## Bugs found & fixed (pre-commit review)

Five issues were caught in chat review cycles before either file was typed
into the repo.

### `np.Array(...)` — invalid capitalization

**Root cause:** an early draft used `np.Array(...)` instead of
`np.array(...)`. NumPy's public API exports lowercase `array`, not an
`Array` class. This would raise `AttributeError: module 'numpy' has no
attribute 'Array'` at runtime.

**Fix:** corrected to `np.array(...)`.

### `s["humidity"]` — wrong dict key

**Root cause:** an early draft tried to access `s["humidity"]` instead of
`s["humidity_pct"]`, the key that `parser.py` actually produces. This would
raise `KeyError: 'humidity'` on the first real parsed sample.

**Fix:** corrected to `s["humidity_pct"]`.

### Docstring ambiguity about return type

**Root cause:** the docstring initially implied `None` was a possible return
type *alongside* `SweatRateResult`, like `-> SweatRateResult | None`, rather
than describing `SweatRateResult` with `None`-valued fields (the actual design).
This could confuse readers about error handling.

**Fix:** clarified the docstring to explicitly state that the return is always
a `SweatRateResult`, with `mean_sri` and `peak_sri` optional but `sample_count`
always present (0 or more).

### `_sample(0, 40, 0)` — missing decimal point in test helper

**Root cause:** an early test draft called `_sample(0, 40, 0)` instead of
`_sample(0, 40.0)`. The helper was defined as `_sample(timestamp_ms, humidity_pct)`
(2 params). In the buggy call, `40, 0` was meant to be a single float `40.0`,
but the comma caused Python to parse it as two separate positional arguments.
This resulted in 3 args passed to a 2-arg function, raising
`TypeError: _sample() takes 2 positional arguments but 3 were given` at test
collection.

**Fix:** corrected to `_sample(0, 40.0)`.

### Missing `numpy` in CI install step

**Root cause:** `.github/workflows/ci.yml` installed only `pytest pyserial`
without `numpy`, even though `sweat_rate.py` imports it at module load. The
first CI run after adding the module would fail at *test collection* with
`ModuleNotFoundError: No module named 'numpy'` — before any test ever ran.
This is the same failure class as the July 1 missing-`pyserial` gap and the
root motivator for centralizing into `requirements.txt`.

**Fix:** included `numpy` in `requirements.txt` and updated CI to use it.

All five bugs were caught in review before commit — no broken versions ever
reached the repo.

---

## Build verification

```
python -m pytest -q
..............................                                                                                                            [100%]
30 passed in 0.31s
```

Full backend test suite now passes: 30 tests total (9 parser + 11 serial +
6 history + 4 sweat_rate), all green. No hardware needed.

---

## Git

Three commits on `phase3/python-backend`:

1. `feat(backend): add sweat_rate.py for Sweat Rate Index computation`
2. `test(backend): add test_sweat_rate.py for sweat_rate.py`
3. `build: centralize backend dependencies into requirements.txt`

---

## Outstanding / next steps

- **Firmware hardware bench verification** — unchanged from prior logs. Still
  the outstanding device-dependent item; backend work continues to require no
  physical device.

---

# Phase 3 Backend — `thermal.py` (thermal recovery slope)

## Summary

Built `ssb_backend/algorithm/thermal.py`, the thermal recovery slope
computation module, and its `pytest` suite (`test_thermal.py`, 7 tests). The
module fits a linear regression to skin temperature vs. time for the current
session and compares that slope against the athlete's learned baseline,
recommending active cooling when recovery lags. Both files were reviewed in
chat across multiple plan/critique cycles before being typed in — five bugs
were caught pre-commit — and then merged into `main` as PR #7.

Like the rest of Phase 3, none of this needs the physical device — the module
is read-only over history and is exercised entirely against `tmp_path` SQLite
files, so everything here was verified locally without hardware.

---

## What was implemented

### `ssb_backend/algorithm/thermal.py` (new)

Standard-library only (`dataclasses`, `pathlib`, `typing`, `logging`);
`scipy.stats.linregress` for the regression, and `ssb_backend.history` for
baseline lookup. Public entry point:

```python
def compute_thermal_recovery(
    samples: list[dict],
    db_path: str | Path = history.DEFAULT_DB_PATH,
) -> ThermalResult
```

Returns a `ThermalResult` dataclass — `current_slope`, `baseline_slope`
(both `float | None`), `sessions_used`, `recommendation`, and
`insufficient_baseline`, where
`recommendation: Literal["active_cooling", "passive_rest", "insufficient_data"]`.

**Design decisions:**
- **Slope via `linregress`.** `timestamp_ms` is converted to seconds
  (`s["timestamp_ms"] / 1000.0`) and regressed against `skin_temp_c`;
  `current_slope` is `float(linregress(time_s, skin_temp_c).slope)`, in °C/s.
- **Degenerate-input guard.** Fewer than 2 samples can't define a slope, so the
  function short-circuits to `current_slope=None`,
  `recommendation="insufficient_data"`, `insufficient_baseline=True`.
- **Baseline from history, read-only.** The baseline is the mean of past
  `thermal_slope` values pulled from `history.get_recent_sessions()`. The module
  never calls `save_session()` — computing a recommendation is a pure read over
  the session store.
- **Minimum baseline gate.** `MIN_BASELINE_SESSIONS = 3`. With fewer than 3
  valid past slopes, no baseline is computed — the function returns
  `baseline_slope=None`, `insufficient_baseline=True`, and the safe default
  `recommendation="passive_rest"` (logging how many baseline slopes were
  available).
- **Additive-margin comparison, strict `>`.** Once a baseline exists, the
  session triggers `active_cooling` only when
  `current_slope - baseline_slope > THERMAL_ALERT_MARGIN_C_PER_S`
  (`= 0.002`), otherwise `passive_rest`. The boundary is a strict `>`, so a
  difference landing exactly on the margin stays `passive_rest`.
  `THERMAL_ALERT_MARGIN_C_PER_S` is explicitly TODO-flagged as an uncalibrated
  placeholder pending real physiological calibration — the same status as the
  vapor-chamber coefficient in `rehydration.py`.
- **Documented history contract.** A `# CONTRACT:` comment above the
  `get_recent_sessions()` call records that each stored session JSON is assumed
  to carry a top-level `"thermal_slope"` key — a key nothing writes yet.
  Producing it is the future job of whatever assembles the session result dict
  (`scoring.py` / `main.py`) for `history.save_session()`.

### `ssb_backend/tests/test_thermal.py` (new, 7 tests)

Follows the existing plain-function / `tmp_path` style. A `_cooling_samples`
helper builds a perfectly linear skin-temp series with a given slope, and
`_seed_history` saves one past session per supplied slope with deterministic
injected timestamps.

- `test_linear_decrease_no_history` — with no seeded history, a valid cooling
  series returns `sessions_used=0`, `baseline_slope=None`, the safe default
  `passive_rest`, and `insufficient_baseline=True`.
- `test_slower_than_baseline_recommends_active_cooling` — baseline mean
  `-0.003` with a flat (no-cooling) current session trips `active_cooling`.
- `test_at_baseline_recommends_passive_rest` — cooling faster than baseline
  stays `passive_rest` with `insufficient_baseline=False`.
- `test_exact_margin_boundary_stays_passive` — values chosen so `linregress`
  returns `THERMAL_ALERT_MARGIN_C_PER_S` bit-for-bit against a `0.0` baseline;
  locks in the strict `>` (no alert exactly on the margin).
- `test_empty_samples` — 0 samples returns the `insufficient_data` result.
- `test_single_sample` — 1 sample returns the `insufficient_data` result.
- `test_sessions_used_skips_invalid_rows` — seeds three valid slopes plus a
  `None` row and a row with no `thermal_slope` key; asserts `sessions_used == 3`
  and the baseline mean skips the invalid rows.

---

## Bugs found & fixed (pre-commit review)

Five issues were caught across chat review cycles before either file was typed
into the repo.

### Generator passed to `len()`

An early draft built `past_slopes` as a generator expression and then called
`len()` on it to derive `sessions_used`. `len()` can't consume a generator —
this would raise `TypeError: object of type 'generator' has no len()`.

**Fix:** made `past_slopes` a list comprehension so `len(past_slopes)` works.

### `s["thermail_slope"]` — key typo

The baseline extraction misspelled the key as `s["thermail_slope"]` instead of
`s["thermal_slope"]`. Against real stored sessions this would raise `KeyError`
(or silently match nothing), never assembling a baseline.

**Fix:** corrected to `"thermal_slope"`, matching the documented contract.

### `Literal["active cooling", ...]` — space vs. underscore mismatch

The `recommendation` type annotation listed `"active cooling"` (with a space)
while the code actually assigns `"active_cooling"` (with an underscore). The
assigned value wouldn't be a member of the declared `Literal`, so type checkers
would flag every real return.

**Fix:** aligned the `Literal` to the underscore form
`"active_cooling"` (and `"passive_rest"`, `"insufficient_data"`).

### `$d` in a logging format string

The baseline-gate log call used `$d` instead of `%d` in its format string, so
the `sessions_used` / `MIN_BASELINE_SESSIONS` values would not interpolate.

**Fix:** corrected to `%d`.

### Missing `# CONTRACT:` comment

The comment documenting that `"thermal_slope"` is a key nothing writes yet was
absent from the first draft and was added across two follow-up review passes to
make the implicit history contract explicit for future `scoring.py` / `main.py`.

All five were caught in review before commit — no broken version ever reached
the repo.

---

## Build / test verification

```
python -m pytest ssb_backend/tests/test_thermal.py -v
....... [100%]
7 passed
```

The full backend suite is green after this merge (parser + serial_receiver +
history + sweat_rate + thermal). No hardware needed.

`scipy` was added to `requirements.txt` — it was missing and is required for
`linregress`.

---

## Git

Both commits landed on `phase3/python-backend` and merged into `main` as PR #7.
From `git log --oneline` (most recent first):

```
c9f0605 Merge pull request #7 from tonyy-shin:phase3/python-backend
648f1bd test(backend): add test_thermal.py
b1f910a feat(backend): add thermal.py for thermal recovery slope computation
6811a18 fix: update local deps into requirements.txt
49753cb Merge pull request #6 from tonyy-shin:phase3/python-backend
```

---

## Outstanding / next steps

- **`rehydration.py`** — next in dependency order. Like `thermal.py`'s alert
  margin, it needs a TODO-placeholder calibration coefficient for the
  GSR-drop-integral → mL conversion, pending the vapor-chamber ΔRH
  characterization that hasn't been delivered yet.
- **`scoring.py`, `api.py`, `main.py`** — follow after `rehydration.py`;
  `scoring.py`/`main.py` are also the eventual producers of the `"thermal_slope"`
  history key that `thermal.py`'s contract depends on.
- **Firmware hardware bench verification** and the **GSR 20%-drop real-sweat
  stress test** — remain outstanding and hardware-dependent.
- **React/Recharts dashboard** — not started.
- **Phase 2 PCB / enclosure** — remains partner-led.