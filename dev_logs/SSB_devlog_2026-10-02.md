# SSB Dev Log — October 2, 2026

## Summary

Today I wired in the physical button (D1) and status LED (D3) and ran the
whole system end to end for the first time: button -> record -> transfer ->
backend -> dashboard. It works.

Before flashing, I found and fixed two firmware bugs that only show up with a
real button. I also found that the GSR isn't reading properly. I'm leaving that
for next time.

---

## Firmware fixes

**1. Phantom button presses.** The button can "bounce" when released and
register as a second press. Because GSR calibration blocks for about 5 seconds,
a bounce during that window would end the session right after it started.
Fixed by clearing the button flag right before entering RECORDING and while in
TRANSFER_READY.

**2. Stale transfer requests.** The backend keeps sending `'R'` to the board.
While the board isn't in TRANSFER_READY, those bytes pile up. When a session
ended, the board would react to an old `'R'` and the transfer could get cut
off, losing the start of the CSV. Fixed by clearing the serial buffer in
`transfer_reset()`.

I also added `-DARDUINO_USB_CDC_ON_BOOT=1` to `platformio.ini` to be safe.

Build: RAM 6.0%, Flash 9.8%, no warnings.

One thing to note: fix #2 only covers short sessions. If the board is plugged
in with the backend running for a long recording, the problem could come back.
This doesn't matter for real use, since the band runs on battery. Fixing it
properly needs a change on the backend side later.

---

## Bench testing

- **Upload issue:** the board didn't show up as `/dev/ttyACM0` at first. It
  worked after replugging.
- **Backed up the fake test data** (`ssb_history.db` ->
  `ssb_history_synthetic_backup.db`) so it doesn't mess up real baselines.
- **Recovery guard works:** I unplugged USB in the middle of a recording. On
  replug, the board went straight to blinking, and the backend pulled the
  session (118 samples, nothing lost).
- **Button troubleshooting:** this took a while. What I found:
  - The D3 wire was loose. The board was recording, but the LED stayed off.
  - Touching the D1 wire while powered counts as a button press.
  - The button was the wrong way around. Tapping the D1 wire straight to GND
    worked, which showed the button was the problem. Rotating the button 90
    degrees fixed it. The 4 legs are connected in pairs inside the button, so
    in the wrong orientation the wires were on legs that are always connected
    (or never switched).

After that, everything worked on the first press.

---

## GSR problem (not fixed yet)

The GSR reads about 25–40 when it should read about 2450 with nothing touching
it. The other sensors are fine (SHT45: 20.6 °C / 64.5 %RH, MAX30205: about
22.8 °C room temp).

Possible causes:
1. The module isn't getting power (wiring or loose connector)
2. The adjustment screw got turned
3. The electrode pads are touching each other
4. The signal wire isn't actually on A0
5. The module is broken

Because the GSR reads so low, the board skips the "waiting for skin" step, so
the dots never show up.

---

## Dashboard

The session showed up on all six panels, but the numbers aren't meaningful
yet:
- The MAX30205 was sitting in room air, not on skin (about 21.7 °C).
- Rehydration showed 0 ml because the GSR isn't working.
- History was full of my test runs, so the score treated them as a real
  baseline.
- The Thermal Slope axis labels in Session History are cut off.

---

## Lessons

- Unplug USB before touching any wires.
- Run the backend from the repo root, not `firmware/`.
- Check `git branch --show-current` before flashing. I flashed the wrong
  branch once.
- Create the branch *before* committing. My fix ended up directly on `main`.
- Close the serial monitor before starting the backend.
- Clear test sessions before recording real data.

---

## Git

- `a771edd` fix(firmware): clear stale button presses and serial input across state transitions (`main`)

---

## Next steps

- Fix the GSR (use `bench_diag` to watch the live reading)
- Clear test history
- Record a real session with sensors on skin after exercise
- Backend-side fix for the stale `'R'` issue
- Fix the cut-off chart labels
- Still pending: GSR sweat stress test, vapor chamber calibration, Stage 2
  wearable build