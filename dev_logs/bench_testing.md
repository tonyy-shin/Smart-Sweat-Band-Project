# Bench Testing — no Button A, no LED

Bench-test walkthrough for the Smart Sweat-Band firmware (XIAO ESP32S3) using the
debug harness on the `fix/hardware-testing` branch. All commands run from
`firmware/ssb_firmware/`.

## Purpose & branch model

This branch (`fix/hardware-testing`) permanently holds the bench harness: the
`bench_diag` / `bench_fsm` PlatformIO envs, `src/bench_diag.cpp`, and the
`#ifdef SSB_DEBUG_SERIAL_BUTTON` blocks in `main.cpp` / `sensors.cpp`. It is
**never merged into `main`** — rebase it onto `main` to keep it current.
Production changes discovered at the bench (e.g. the MAX30205 extended-format
offset fix in `sensors.cpp`) are merged to `main` independently.

## What the harness provides

| Env | Builds | Purpose |
|---|---|---|
| `seeed_xiao_esp32s3` | production sources only | Untouched production build — `SSB_DEBUG_SERIAL_BUTTON` is never defined here |
| `bench_diag` | `bench_diag.cpp` only | Stage 1 sensor bring-up: I2C scan, raw MAX30205 / SHT45 / GSR reads at 1 Hz |
| `bench_fsm` | production sources + `-DSSB_DEBUG_SERIAL_BUTTON` | Stage 2 FSM walk: `s` keystroke substitutes for Button A; `STATE X -> Y` tracer substitutes for the LED; loud once-per-second SHT45 init-error loop; GSR contact-wait bypass (baseline lands at the offline value) |

## Stage 1 — sensor bring-up

```
pio run -e bench_diag -t upload
pio device monitor --echo
```

Pass criteria:
- [ ] I2C scan shows ACK at **0x44** (SHT45) and **0x48** (MAX30205)
- [ ] MAX30205 ≈ ambient °C (raw, no offset applied in this diagnostic)
- [ ] SHT45 shows plausible room temp / RH
- [ ] GSR ≈ **2450** offline; pinching both electrodes drops it visibly and it recovers

## Stage 2 — FSM walk

```
pio run -e bench_fsm -t upload
pio device monitor --echo
```

Send protocol bytes as **bare keystrokes** (no Enter needed; see gotchas):

1. Boot → expect `IDLE`. (Stale `/session.csv` boots into `TRANSFER_READY`
   instead — send `R` then `C` to clear.)
2. `s` → ~5 s calibration pause → `STATE IDLE -> RECORDING`
3. Record ≥ 5 s (rows written at 1 Hz)
4. `s` → `STATE RECORDING -> TRANSFER_READY`
5. `R` → CSV rows stream out, terminated by `END`
6. `C` → session deleted → `STATE TRANSFER_READY -> IDLE`
7. Repeat once to confirm the FSM re-arms

Confirm-timeout durability check (run once per session):

8. Record a fresh session, send `R`, let CSV + `END` stream out
9. **Withhold `C` for >10 s** (the confirm timeout), then send `R` again
10. Verify the **same rows re-stream** — not `ERROR: no session`. The session
    survives the timeout; deletion happens **only** on `C`. Then `R` + `C` to clear.

## Monitor gotchas (read before debugging "silence")

- **Port hopping:** the board re-enumerates on every reset/flash and can move
  between `/dev/ttyACM0` and `/dev/ttyACM1`. If the monitor is silent, check
  `ls /dev/ttyACM*` before suspecting the firmware.
- **No local echo by default:** use `pio device monitor --echo` or your
  keystrokes are invisible.
- **Ctrl+T is miniterm's menu key** and swallows the next character. Never
  chain `s`/`R`/`C` after Ctrl+T — send them as bare keystrokes.
- **Benign boot error:** `[E] ...vfs_api.cpp... /littlefs/session.csv does not
  exist` at boot is the recovery guard probing an empty flash. It is **not** a
  failure.

## Expected values

| Value | Expected | Red flag |
|---|---|---|
| `skin_temp_c` | ≈ 26–29 °C at bench (extended-format offset applied) | **~90 °C ⇒ the MAX30205 offset fix is missing from the build** |
| `chamber_temp_c` | ≈ skin temp | — |
| `gsr_raw` | ≈ 2450 offline | — |
| GSR baseline | in the CSV header comment (`# gsr_baseline=...`) | — |

CSV schema: `timestamp_ms,skin_temp_c,humidity_pct,chamber_temp_c,gsr_raw`

## Removing the harness (if ever retired)

- [ ] Delete `src/bench_diag.cpp`
- [ ] In `platformio.ini`: delete the `[env:bench_diag]` and `[env:bench_fsm]`
      blocks and the production env's `build_src_filter` line
- [ ] `grep -rn SSB_DEBUG src/` → remove the four `#ifdef` blocks
      (main.cpp setup + loop, sensors.cpp init + calibrate)
