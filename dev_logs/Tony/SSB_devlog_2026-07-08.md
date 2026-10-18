# SSB Dev Log — July 8, 2026

## Summary

Two major pieces today. First, `ssb_backend/main.py` — the process entry point
that closes out the backend dependency chain: it runs `serial_receiver.run()` in
a daemon thread and `uvicorn` (serving `api.app`) in the main thread, replaces
`serial_receiver.py`'s algorithm-pipeline stub with a real call into
`api.run_pipeline`, and resolves the long-deferred double-compute tradeoff
flagged since `scoring.py`'s build. Second, the SSB web dashboard — built from
scratch in `ssb-dashboard/` (Vite + React + Recharts), implementing all six
planned panels as pure props-in/UI-out components. Also added
`scripts/seed_test_session.py`, a hardware-free pipeline-seeding dev utility used
to exercise dashboard states across calibration stages. Everything below is
committed, pushed, and merged to `main`.

---

## What was implemented

### Backend — `main.py` and the double-compute resolution

`ssb_backend/main.py` is now the real process entry point — no longer the
placeholder the file-structure section described:

- **Concurrency model.** Runs `serial_receiver.run()` in a daemon thread and
  `uvicorn` (serving `api.app`) in the main thread. The two share state only
  through `api._latest_results` — a module-level `SessionResults | None`
  variable. This is a single-writer atomic reference assignment, so no lock is
  needed: Python's GIL makes the reference swap safe.
- **Real pipeline call.** `serial_receiver.py`'s `_run_algorithm_pipeline`
  (previously a stub that only logged sample counts) now calls into
  `api.run_pipeline`. It is guarded against `outcome.parse_result is None` /
  empty samples, and wrapped in a local `try/except` so an algorithm bug doesn't
  masquerade as a transfer failure in the logs — by that point the transfer
  itself has already succeeded (CSV saved, `'C'` confirmed).
- **Double-compute resolution.** `compute_gsr_electrolyte_adjustment` was
  running twice per pipeline — once in `rehydration.py`, once in `api.py`'s
  `run_pipeline` for scoring's 4th parameter (the tradeoff flagged since the
  July 7 logs and deliberately deferred to `main.py`). Fixed by adding an
  optional `elec: GsrElectrolyteResult | None = None` parameter to
  `compute_rehydration_prescription`: `api.run_pipeline` now computes `elec` once
  and passes it through, instead of letting `rehydration.py` recompute it. This
  eliminates the redundant SQLite read and the hidden same-DB-snapshot invariant
  (the two computations previously had to be reading the same history snapshot to
  agree).
- **Test change.** `test_api.py`'s old double-compute consistency test — which
  only proved that two *independent* computations happened to agree — was
  replaced with `test_rehydration_uses_injected_electrolyte_result`, asserting
  structural equality (the injected result is the one actually used) instead of
  numeric coincidence.
- **Pre-implementation verification.** Two source-code facts were confirmed
  before typing: `api._latest_results` is a module-level `SessionResults | None`
  variable, and `TransferOutcome`'s fields are `(detected, complete, confirmed,
  saved_path, parse_result)` in that order.

Full test suite passed after the changes. Committed, pushed, merged to `main`.

### Frontend — SSB dashboard (`ssb-dashboard/`)

Built from scratch. The project lives inside a OneDrive-synced path with Korean
characters and spaces — a known friction point from prior firmware sync issues —
so the dev environment (Node/npm, none present initially) was set up via `nvm`
first.

- **Scaffold.** `ssb-dashboard/` on Vite + React (JavaScript) + Recharts.
- **`src/hooks/useResults.js`.** Fetches `GET /api/results` once on mount through
  a Vite dev-server proxy to `localhost:8000` — avoiding CORS without touching
  the backend. Exposes a `status` of `loading | no-session | error | ready`.
- **`src/theme.js`.** Shared color/typography tokens — a saline /
  hydration-teal / heat-orange / kelp-green / sodium-amber domain palette,
  grounded in the sweat/thermal/hydration subject rather than a generic dashboard
  look. Typography: Barlow Condensed for titles, Barlow for body, IBM Plex Mono
  for all numbers.
- **`src/panels/shared.jsx`.** Reusable primitives — `Panel` / `StatTile` /
  `Badge` / `Stabilizing` / `Ticks`. `Ticks` became the dashboard's signature
  element: a calibration-progress indicator reused in three places (score-panel
  session count, thermal baseline count, and history's empty state).
- **Six panels.** `ScorePanel`, `RehydrationPanel`, `ThermalPanel`,
  `SweatRatePanel`, `RecoveryPlanPanel`, `SessionHistoryPanel` — all pure
  props-in/UI-out components, wired into `App.jsx` via a CSS
  `grid-template-areas` hero layout (score panel visually largest), with
  responsive breakpoints at 1100px and 640px.
- **RIT credit.** A small color/text credit — masthead accent plus a "Built at
  RIT" footer, no logo or mascot reproduction (trademark-conscious). The RIT
  orange was deliberately kept distinguishable from the existing thermal-domain
  accent orange so the two don't collide semantically.

### Dev tooling — `scripts/seed_test_session.py`

A one-off dev script (repo-root `scripts/`) that seeds a synthetic 90-sample
session through `run_pipeline` and self-serves the real FastAPI app on `:8000`.
It is deterministic via `random.seed(42)`: skin temp cooling 37.8 → 36.6 °C,
humidity rising 55 → 85%, GSR dipping ~30% mid-session to simulate sweat onset.
It self-serves the app because a *separate* script process calling `run_pipeline`
can't populate the `api._latest_results` living in a *separately-running*
`main.py` process's memory — this was diagnosed explicitly before the workaround
was built. Used repeatedly to test dashboard states across calibration stages
(e.g. watching the "stabilizing" badge disappear once `prior_session_count`
crossed `SCORE_CALIBRATED_SESSIONS = 5`). It writes to the real `ssb_history.db`,
so **it must be deleted before real device data collection begins.**

---

## Bugs found & fixed

1. **Vite-template CSS constraining the layout.** The scaffold's default
   `#root { width: 1126px }` (hardcoded) plus `text-align: center` inheriting
   into every panel was pinning the whole layout to a narrow centered column.
   Fixed with a minimal CSS reset.
2. **Full-viewport-height fill made it worse.** A follow-up attempt to force
   full-viewport-height fill via `fr` grid rows created a worse problem —
   thin-content panels stretched into large internal dead zones. Three further
   passes tried to fill the stretched space with more visuals; ultimately
   reverted to content-sized (`auto`) rows as the better fit for a quick-glance
   personal tool that doesn't need to justify every pixel of a monitor. Some
   panels (Rehydration, Sweat Rate Index, and especially Recovery Readiness's
   lower half) still carry acknowledged, accepted whitespace as a result —
   treated as a minor cosmetic tradeoff, not a defect worth further passes right
   now.
3. **Terminal mistake — stray root-level `package.json` / `node_modules`.**
   Pasting multiple `npm` commands at once cancelled an interactive prompt and
   caused subsequent commands to run in the wrong directory, leaking a
   `package.json` and `node_modules` into the repo root. Both were cleaned up.

---

## Build/test verification

- Full backend `pytest` suite passed after the `main.py` / double-compute
  changes, including the new `test_rehydration_uses_injected_electrolyte_result`
  that replaced the old double-compute consistency test.
- Dashboard verified by running `seed_test_session.py` against it and stepping
  through calibration stages — confirmed the "stabilizing" badge clears once
  `prior_session_count` crosses `SCORE_CALIBRATED_SESSIONS = 5`, and that the
  `loading | no-session | error | ready` states each render correctly.

---

## Git

- **Backend** — `main.py` + the double-compute fix: committed in dependency
  order, pushed, and merged to `main`.
- **Frontend** — squashed into a single commit,
  `feat(frontend): build recovery dashboard with six panels`. It was **not**
  split further because the files were edited across multiple design passes with
  no clean commit seams between them, and no intermediate state was independently
  tested — a finer split would have committed states that were never verified.
- **Dev tooling** — `chore(backend): add scripts/seed_test_session.py`.
- **Housekeeping** — added `ssb_backend/data/` to `.gitignore` (previously
  untracked but unprotected against future accidental commits); removed the stray
  root `package.json` / `node_modules` from the terminal mistake above.

All of the above is committed, pushed, and merged to `main`.

---

## Outstanding / next steps

- **Raw-samples endpoint for time-series charts.** `ThermalPanel` and
  `SweatRatePanel` currently show summary stats only — `GET /results` doesn't
  return raw per-sample data, so the planned Recharts time-series (skin-temp
  curve, SRI curve) can't be drawn yet. A new backend endpoint (e.g.
  `GET /results/samples`) is needed before those two panels are fully built out.
- **Session-history-listing endpoint.** `SessionHistoryPanel` is a stub pending a
  `GET /history` (or similar) endpoint listing past sessions. `history.py`
  already stores this data in SQLite, so it's an endpoint away — not a
  data-model change.
- **Real device hardware bench verification** and the **GSR 20%-drop real-sweat
  stress test** — still pending, hardware-blocked.
- **Vapor chamber ΔRH → mL/min characterization** — partner-led, still pending;
  still gates the volume half of `rehydration.py`.
- **Phase 2 PCB / enclosure** — partner-led, still pending.
