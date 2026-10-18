# SSB Dev Log — July 4, 2026

## Summary

First hardware bench test of the Phase 3 firmware, on the physical XIAO
ESP32S3. Unlike every prior log, there is no pytest suite here — all
verification was `pio device monitor` output from the real board.

Three results:

1. **All three sensors verified** on the shared bus (SHT45 + MAX30205 on
   I2C D4/D5, Grove GSR on A0) via a throwaway `bench_diag` firmware.
2. **The MAX30205 is a clone permanently stuck in extended data format** —
   it reports (true temperature − 64 °C) and ignores the DATA_FORMAT config
   bit. Diagnosed at the bench through a raw-hex + config-register probe
   sequence; corrected in `sensors.cpp` by decomposing the old magic
   `CALIBRATION_OFFSET = 63.8` into an exact 64.0 format correction plus a
   −0.2 calibration placeholder.
3. **The full FSM → transfer → durability path was walked end-to-end**
   without the physical Button A or status LED, using a serial-keystroke
   shim (`s` = button press) and a state tracer, all gated behind
   `#ifdef SSB_DEBUG_SERIAL_BUTTON` so production builds are unaffected.

All of today's work is **currently uncommitted** working-tree changes on
`fix/hardware-testing` — see Git section.

---

## Bench setup & harness

Board over USB; sensors wired; Button A (D1) and LED (D3) not yet present.
`firmware/ssb_firmware/platformio.ini` now has three envs:

- `seeed_xiao_esp32s3` — production, untouched (gained only a
  `build_src_filter` line excluding the diag file).
- `bench_diag` — builds *only* `src/bench_diag.cpp` (Stage 1).
- `bench_fsm` — production sources + `-DSSB_DEBUG_SERIAL_BUTTON` (Stage 2).

`build_src_filter` keeps the two `setup()`/`loop()` pairs mutually
exclusive; `extends` means the bench envs inherit board/libs from
production and stay two lines each.

---

## Stage 1 — sensor bring-up (`bench_diag`)

I2C scan on boot — both expected addresses ACK:

```
I2C scan 0x08-0x77:
  ACK at 0x44
  ACK at 0x48
Scan done: 2 device(s). Expect 0x44 (SHT45) and 0x48 (MAX30205).
```

SHT45 and GSR passed immediately: chamber ≈ 28.9 °C / ~64 %RH stable, GSR
≈ 2450–2470 offline, dropping to ~1273 on electrode pinch and recovering.

### The MAX30205 investigation

The MAX30205 read a rock-stable **−35 °C**. Stable-but-wrong ruled out
loose wiring (that jitters or freezes); a NACK at the wrong address would
have decoded to a constant 0.00 °C, ruling out the 0x48/0x49 strap
question. Decoding the constant: −35.0 ÷ (1/256) = −8960 = `0xDD00` — and
−35 + 64 = 29 °C, matching the co-located SHT45. That pointed at the
MAX30205's *extended data format* (value = true − 64 °C).

Three probes settled it:

1. **Fingertip test (zero code):** the reading drifted upward across
   samples (−34.96 → −34.85 °C) as the chip warmed — conversions are live,
   so the fault is a constant decode offset, not a stale register.
2. **Raw-hex print:** the raw word recovered losslessly from the float
   (`(int16_t)lroundf(temp * 256)`) sat at ≈ `0xDD40` with a live-moving
   low byte.
3. **Config-register readback** (repeated-START read of reg 0x01): the
   register reads back exactly what the driver's `begin()` wrote —
   `0x00`, DATA_FORMAT bit clear — **yet the output stays 64 low**. The
   silicon ignores the format bit; this cannot be fixed by a register
   write.

```
MAX30205 config=0x00  DATA_FORMAT(bit5)=0
MAX30205=-34.75C raw=0xDD40  SHT45=28.88C 64.4%RH  GSR=2471
MAX30205=-34.77C raw=0xDD3C  SHT45=28.91C 64.2%RH  GSR=2459
MAX30205=-34.73C raw=0xDD44  SHT45=28.89C 64.1%RH  GSR=2458
MAX30205=-34.78C raw=0xDD38  SHT45=28.93C 63.9%RH  GSR=2449
MAX30205=-34.80C raw=0xDD34  SHT45=28.94C 63.7%RH  GSR=2456
```

−34.75 + 64 = **29.25 °C** vs. SHT45's 28.9 °C — an exact extended-format
fit. Extended-format-stuck parts are a known trait of counterfeit
MAX30205s; the genuine part powers on in normal format.

---

## The offset fix (`sensors.cpp`, production)

The old `CALIBRATION_OFFSET = 63.8` had been masking this all along — one
magic number silently doing two jobs. Decomposed into:

- `MAX30205_EXT_FORMAT_OFFSET_C = 64.0` — the non-tunable format
  correction, with a comment citing today's bench finding.
- `SKIN_TEMP_CAL_OFFSET_C = -0.2` — the residual physical calibration,
  TODO-flagged as an empirically-estimated placeholder pending calibration
  against a reference thermometer (same placeholder convention as
  `thermal.py` / `rehydration.py`).

Applied sum is unchanged (64.0 − 0.2 = 63.8), so no downstream value —
CSV, thermal algorithm, stored sessions — shifts. The existing `int16_t`
cast in `sensors_read()` was already sign-correct; only the offset
decomposition changed.

---

## Stage 2 — FSM walk (`bench_fsm`)

Four `#ifdef SSB_DEBUG_SERIAL_BUTTON` blocks (each marked
`// BENCH DEBUG — remove before ship`), dead code in production:

1. `main.cpp` `setup()` — `while (!Serial)` so init-phase errors are
   visible over USB CDC.
2. `main.cpp` `loop()` — the shim: when not in TRANSFER_READY (where
   `transfer_update()` owns `'R'`/`'C'` on Serial), drain Serial and set
   the **real** `extern volatile bool button_a_pressed` on `'s'` — the
   identical flag the ISR sets, so the actual transition logic runs, not a
   parallel path. Plus a state tracer printing `STATE X -> Y` in place of
   the LED.
3. `sensors.cpp` `sensors_init()` — the silent SHT45-failure
   `while(1) delay(1)` halt reprints `ERROR: SHT45 not responding` once
   per second in bench builds (production `while(1)` kept in the `#else`).
4. `sensors.cpp` `gsr_calibrate()` — only the skin-contact wait
   (`while (analogRead > 2300)`) is `#ifndef`'d out; the 100 × 50 ms
   baseline averaging still runs, landing at the offline value.

The walk (keystroke echoes `s`/`R`/`C` visible from `--echo`):

```
sSTATE IDLE -> RECORDING
STATE RECORDING -> TRANSFER_READY
R# gsr_baseline=2454
timestamp_ms,skin_temp_c,humidity_pct,chamber_temp_c,gsr_raw
31906,29.22,61.59,29.03,2465
32918,29.26,61.52,29.02,2459
33930,29.25,61.44,29.05,2459
34942,29.23,61.40,29.05,2450
35954,29.22,61.33,29.03,2467
END
CSTATE TRANSFER_READY -> IDLE
```

Everything the capture should show, it shows: `s` → ~5 s calibration
pause → RECORDING; 1 Hz rows; `s` → TRANSFER_READY; `R` → header comment
with the bypassed-calibration baseline (`# gsr_baseline=2454`, the
offline value as designed), correct schema, rows, `END`; `C` → delete →
IDLE. And **`skin_temp_c` ≈ 29.2 °C** — the offset fix confirmed on
hardware (the old build would have logged ~90 °C here).

**Confirm-timeout durability check** also passed: after `R` + `END`,
withholding `C` for >10 s (the `CONFIRM_TIMEOUT_MS` window) and sending
`R` again re-streamed the identical rows — the session survives the
timeout; deletion happens only on `C`. The save-then-confirm invariant
holds.

---

## Debugging notes / gotchas (the real time-sinks)

- **OneDrive / unsaved-buffer mismatch** — twice, edits reported as saved
  were not on disk (old code compiled and flashed, changes silently
  absent). Resolution habit: after saving, grep the file for the new
  symbol before building. This repo living inside OneDrive makes disk
  state untrustworthy until verified.
- **USB-CDC port hopping** — the board re-enumerates on every
  reset/flash and moves between `/dev/ttyACM0` and `/dev/ttyACM1`. Check
  `ls /dev/ttyACM*` before suspecting the firmware when the monitor is
  silent.
- **miniterm** — use `pio device monitor --echo` or keystrokes are
  invisible; and Ctrl+T is the menu key, which *swallows the next
  character* — protocol bytes (`s`/`R`/`C`) must be bare keystrokes,
  never chained after Ctrl+T.
- **Benign boot error** — `[E] ...vfs_api.cpp... /littlefs/session.csv
  does not exist` at boot is the recovery guard probing an empty flash
  (the `storage_session_exists()` check in `setup()`), not a failure.

---

## Artifacts

- `dev_logs/bench_testing.md` — reusable bench walkthrough (both stages,
  gotchas, expected values, harness-removal checklist). **Caveat found
  while writing this log:** `dev_logs/` is git-ignored (`.gitignore:42`),
  so this doc currently won't ride any branch — open item below.
- The bench harness itself (`bench_diag.cpp`, the two envs, the four
  `#ifdef` blocks) — lives on `fix/hardware-testing` permanently; never
  merged to `main`, rebased onto it as production evolves.

---

## Git

Today's work landed as **two deliberate commits on `fix/hardware-testing`**,
pushed and up to date with `origin/fix/hardware-testing`; working tree clean:

```
d76589a test(firmware): add bench harness (bench_diag/bench_fsm envs, serial-shim FSM driver)
de77b70 fix(firmware): decompose MAX30205 offset into extended-format + calibration constants
e5d531b fix: no extra configs. deleted extra config file
```

- `de77b70` — the production offset fix, isolated to `sensors.cpp`
  (8 insertions, 2 deletions).
- `d76589a` — the bench harness: `platformio.ini` envs, new
  `bench_diag.cpp`, and the `#ifdef` blocks in `main.cpp` / `sensors.cpp`
  (4 files, 108 insertions).

The split (and the ordering — offset fix *underneath* the harness commit)
is deliberate: `de77b70` touches only production code and can be
cherry-picked to `main` on its own, while the harness commit stays on this
branch forever. `main` is untouched at `e5d531b` (local and `origin/main`
both).

---

## Outstanding / next steps

- **Get the offset fix onto `main`** — committed on the branch
  (`de77b70`) but not yet on `main`; cherry-pick when ready. The harness
  commit (`d76589a`) is done and stays on `fix/hardware-testing`
  (unmerged; rebase onto `main` to keep current).
- **Decide `bench_testing.md`'s home** — it's in the git-ignored
  `dev_logs/`; if it should version with the harness, move it to
  `firmware/ssb_firmware/`.
- **Real skin-temp calibration** — replace the `SKIN_TEMP_CAL_OFFSET_C =
  -0.2` placeholder against a reference thermometer.
- **Backend resumes at `rehydration.py`** — two open test bugs from the
  prior session: a missing dataclass field raising `TypeError`, and a
  vacuous epsilon assertion that never exercises the exact-multiple
  windowing edge.
- **Physical Button A + LED** — on arrival, either retire the harness via
  the removal checklist in `bench_testing.md` or keep the branch for
  future bench work.
- **GSR 20 %-drop real-sweat stress test** — still outstanding; today's
  bench was dry-skin only.
