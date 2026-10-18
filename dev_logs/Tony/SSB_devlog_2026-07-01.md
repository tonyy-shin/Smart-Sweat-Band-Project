# SSB Dev Log — July 1, 2026

## Summary

Built `ssb_backend/serial_receiver.py`, the Phase 3 module that detects the
XIAO ESP32S3 over USB serial, runs the transfer handshake, and durably saves a
received session before confirming it — the direct successor to yesterday's
`parser.py`, which it consumes. Also stood up its `pytest` suite
(`test_serial_receiver.py`, 11 tests) and fixed a CI dependency gap (`pyserial`
was never installed in the workflow). A short bug-fix pass before the first
commit caught a `datetime` import mismatch that would have crashed `save_csv()`,
a header-constant typo, and a couple of naming slips.

Like the parser work, none of this needs the physical device for unit
verification — the serial layer is exercised through a `FakeSerial` stand-in, so
everything here was verified locally and in CI. All of today's work has already
landed on `main` (developed on `phase3/python-backend`, merged via PR #4).

---

## What was implemented

### `ssb_backend/serial_receiver.py` (new, 281 lines)

Standard-library plus `pyserial` and the existing `ssb_backend.parser`. The
module is deliberately split into a pure core (testable without any serial port)
and a thin IO/orchestration shell.

**Detection strategy — active handshake, not port-name guessing.** There is no
attempt to identify the device by VID/PID or port name. Instead `run()`
enumerates every candidate port (`list_candidate_ports()` → all
`comports()`), and `_process_connection()` *actively probes* each one: it sends
the request byte `'R'` and inspects what comes back. A port counts as "detected"
as the SSB device only if it (a) streams to a clean `END`, (b) reports a device
`ERROR`, or (c) its first line passes `_looks_like_ssb()`. Anything else returns
`None` and is treated as unrelated serial junk. This mirrors the firmware's
existing ASCII protocol rather than relying on OS-level enumeration, which is
unreliable across platforms.

- `_looks_like_ssb(line)` — the junk filter: a line qualifies if it starts with
  `#gsr_baseline`, exactly matches `_HEADER_LINE`, or splits into exactly
  `EXPECTED_COLS` (5) comma fields.

**Protocol handling.** `accumulate_stream()` is the pure heart of the receive
path: it consumes decoded lines, strips `\r\n`, and stops on the `END` sentinel
(→ `complete=True`) or an `ERROR`-prefixed line (→ `device_reported_error=True`),
otherwise collecting rows. It returns a `ReceiveResult(csv_text, complete,
device_reported_error)`. Exhausting the stream without an `END` yields
`complete=False` — the signature of a broken/partial transfer.

**Save-then-confirm durability invariant.** This is the core correctness
property. In `_process_connection()`, `'C'` is only ever written *after*
`save_csv()` has returned:

- `save_csv()` writes the CSV, then `f.flush()` + `os.fsync(f.fileno())` before
  returning, so the file is physically on disk before confirmation.
- Only on `recv.complete` does the sequence save → write `CONFIRM_BYTE` → set
  `confirmed=True`. An incomplete stream saves nothing and confirms nothing, so
  the device keeps its copy for a retry on the next connection.
- A device `ERROR` (no session to send) short-circuits to
  `TransferOutcome(detected=True, complete=False, confirmed=False, None, None)`
  — detected, but nothing saved or confirmed.

Files are named `session_<YYYYMMDD_HHMMSS>.csv` under `DATA_DIR`
(`ssb_backend/data/`), with the timestamp injectable for testing.

**Parser integration.** After a successful save, `parse_session_csv()` is run
and `_log_parse_health()` logs the two parser failure fields *distinctly*, per
yesterday's design: `truncated_final_row` is logged at INFO as an expected,
tolerated mid-`RECORDING` power-pull artifact, while `malformed_row_count` is
logged at WARNING as possible real corruption. Critically, parse health is
diagnostic only — a truncated final row does **not** withhold `'C'` (the
transfer itself completed cleanly), which is asserted directly in the tests.

**Daemon loop with cooldown re-probing.** `run()` is an infinite scan loop
(`POLL_INTERVAL_S = 2.0s`):

- Once a port answers as the SSB device, it is remembered in `ssb_port` and
  re-polled every cycle (it's placed first in the candidate list).
- A port that *doesn't* answer is put on a cooldown of
  `REPROBE_COOLDOWN_CYCLES = 15` cycles before it's probed again, so unrelated
  ports (Bluetooth modems, other dev boards) aren't hammered with `'R'` bytes
  every 2 seconds.
- Cooldown bookkeeping is self-cleaning: entries for unplugged ports are dropped,
  counters decrement each cycle, and the remembered `ssb_port` is cleared if it
  disappears from the port list.
- The whole cycle body is wrapped in a `try/except` that logs via
  `logger.exception` and keeps looping — a single bad port read can't kill the
  daemon.
- On a saved transfer, `_run_algorithm_pipeline(outcome)` is called — currently a
  TODO stub that just logs the sample count, pending the `algorithm/` module.

### Testing — `ssb_backend/tests/test_serial_receiver.py` (11 tests)

The suite is built around a `FakeSerial` stand-in that records every `write()`
(so byte *ordering* can be asserted) and scripts `readline()` from pre-seeded
lines — no real port required. Coverage:

- **`accumulate_stream`** — well-formed complete stream, no-`END`/incomplete,
  device `ERROR` line, and CRLF stripping.
- **`_looks_like_ssb`** — true for header / `#gsr_baseline` / a real 5-col row;
  false for `"hello world"` and a 3-col `"1,2,3"`.
- **`save_csv`** — default-timestamp round-trip into a `tmp_path`, asserting the
  file exists, content matches byte-for-byte, and the `session_*.csv` naming.
- **`_process_connection` orchestration** — the durability invariant is pinned
  down explicitly: `test_complete_saves_before_confirm` monkeypatches `save_csv`
  with a spy that snapshots `ser.writes` *at save time* and asserts `'R'` is
  present but `'C'` is **not yet** written, then confirms `'C'` appears
  afterward. Plus: no-`END` never confirms, a truncated final row still confirms
  (with `truncated_final_row=True`, `malformed_row_count==0`), and a device
  `ERROR` saves/confirms nothing while still reporting `detected=True`.

---

## Bugs found & fixed

Three issues were caught in the pre-commit review pass, in the same style as
yesterday's parser bugs. None reached `main` in broken form — the committed
module is the corrected version.

### `datetime` import mismatch broke `save_csv()`

`save_csv()` builds its default filename with
`datetime.now().strftime("%Y%m%d_%H%M%S")`.

**Root cause**: the import and the call site disagreed on which name was bound.
The call uses `datetime.now(...)` (i.e. the *class*), but the import line bound
the *module* instead (`import datetime`). Under that pairing,
`datetime.now(...)` resolves to the module's attribute chain incorrectly and
`save_csv()` raises at runtime — meaning every real, complete transfer would
crash at the exact moment it tried to persist the session, right before the
`'C'` confirmation. Because the failure is in the default-timestamp path, tests
that inject a timestamp or monkeypatch `save_csv` wouldn't have surfaced it.

**Fix**: bind the class directly so the call site matches —

```python
from datetime import datetime
...
ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
```

### `_HEADER_LINE` column typo

**Root cause**: the header constant used for the exact-match arm of
`_looks_like_ssb()` (and re-exported for the tests) had a misspelled column
name, so it would not have matched the firmware's real 5-column header
(`timestamp_ms,skin_temp_c,humidity_pct,chamber_temp_c,gsr_raw`). A mismatched
header constant silently weakens detection — the header line would fall through
to the 5-field count check instead of matching exactly, and any test asserting
against the canonical header string would fail.

**Fix**: corrected the constant to the exact firmware header, including
`humidity_pct`. This is the same class of bug as yesterday's `skin_temps_c`
parser typo — a hand-typed column constant drifting from the real schema.

### Naming / cosmetic corrections

Minor identifier and comment cleanups made in the same pass — aligning helper
and constant names with their actual roles so the module reads consistently.
Cosmetic only; no behavioral change. (A few surface quirks remain in comments,
e.g. `BAND_RATE`/`basline`/`truncated_final_rw` in log strings — harmless typos,
flagged not fixed.)

---

## Build / test verification

Ran the new suite and the full backend suite locally in this environment:

```
python -m pytest ssb_backend/tests/test_serial_receiver.py -q
...........                                                              [100%]
11 passed in 0.05s

python -m pytest -q
....................                                                     [100%]
20 passed in 0.04s
```

11 serial-receiver tests pass; the full backend suite is now 20 tests (9 parser
+ 11 serial), all green. No hardware needed — the `FakeSerial` stand-in exercises
the entire orchestration path.

**CI dependency fix.** The GitHub Actions workflow installed only `pytest`, but
`serial_receiver.py` imports `serial` (pyserial) at module load. The first CI
run after adding the module would have failed at *collection* with
`ModuleNotFoundError: No module named 'serial'` — before any test even ran.
Fixed in `.github/workflows/ci.yml`:

```yaml
pip install pytest pyserial
```

CI on Python 3.12 / `ubuntu-latest` remains the standing verification method for
backend changes.

---

## Git

All of today's work is already committed and merged to `main`, developed on the
`phase3/python-backend` branch per the branch convention adopted yesterday:

1. `ca052c3` — `feat(backend): add serial_receiver.py for USB device detection and transfer`
2. `e2c00e3` — `test(backend): add test for serial_receiver.py`
3. `b1fb94f` — `fix: updated ci by adding pyserial`
4. `4bb5d9e` — merge of PR #4 (`phase3/python-backend` → `main`)

The three bug fixes above were applied to the working tree before commit `ca052c3`,
so `main` never carried the broken versions.

---

## Outstanding / next steps (Phase 3 backend)

The receiver's `_run_algorithm_pipeline()` is a logging TODO — it's the seam
where the rest of Phase 3 plugs in. Per the file structure in
`SSB_architecture.md`, none of the following exist yet:

- **`algorithm/` modules** — the actual signal processing over parsed samples
  (the receiver already hands them a `ParseResult`).
- **`scoring.py`** — turn processed samples into whatever the sweat/exertion
  score is defined to be.
- **`history.py`** — persistence/aggregation of past sessions (the receiver
  currently only drops raw `session_*.csv` files into `ssb_backend/data/`).
- **`api.py`** — surface for the frontend/consumer to read scores and history.
- **`main.py`** — the backend entry point that wires the receiver daemon to the
  algorithm → scoring → history → api chain, replacing the current
  `if __name__ == "__main__": run()` bootstrap in `serial_receiver.py`.

**Hardware item (unchanged):** the firmware bench walkthrough from the June 30
log is still the outstanding device-dependent task; backend work continues to
need no hardware for unit verification.
