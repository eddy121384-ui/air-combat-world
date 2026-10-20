# Ace to Ace — Dual Flight Modes, 2026-10-20

This spike extends Draft PR #47 on a separate branch `feat/ace-dual-flight-modes`.
Unreal, aircraft art, weapon logic, HUD rendering and match rules are unchanged.
The legacy `?feel=A` and `?feel=B` simulation aliases remain for automated
comparisons; the player-facing options are two **flight physics** profiles and
two **independent pilot control** modes.

## In-game selection

- `?mode=arcade&control=expert&seed=71429`: AC-inspired fast, forgiving flight;
  direct roll/pitch. Default if omitted.
- `?mode=arcade&control=assisted&seed=71429`: same flight performance with
  bank-and-pull coordinated by the pilot assistance layer.
- `?mode=tactical&control=expert&seed=71429`: RB-inspired speed-limited
  flight-envelope approximation, direct roll/pitch.
- `?mode=tactical&control=assisted&seed=71429`: same tactical flight model,
  with the assisted bank/turn controller.

Arcade widens the available-lift envelope below corner speed, uses slightly
faster roll/G response, retains more speed during sustained high-G maneuvering,
and has stronger acceleration. Tactical restricts G at low speed by a squared
speed ratio, caps positive G at an approximate 9G game benchmark, and uses
greater induced drag. Both use lift-vector bank-to-turn, real speed/position,
gravity, shared AI/player constraints, AB and independent speedbrake. Neither
is a DCS-level F-16 nor validated J-16 simulation: no explicit AoA/stall CFD,
stores or high-fidelity flight-control laws.

Input choice does not change plane physics. Expert: x=roll, y=pitch, no
auto-level. Assisted: x commands heading-turn through roll+pull, neutral x
autolevels; manual pitch and yaw remain. Assisted never secretly turns on AB;
throttle, AB and BRK stay player-controlled. The existing iPhone virtual stick
and throttle remain **latched on release** by design.

## Checks and release gate

Run `node tools/test-dual-flight-modes.mjs`, existing regression suite,
and `node tools/aivai.mjs --n 3 --feel arcade` / `--feel tactical`.
The deterministic probe measures same-seed turns, available low-speed G,
turn energy losses, brake independence, both-side flight profiles, assisted
vs expert controller outputs and title UI wiring.

Real-device acceptance: landscape iPhone Safari; for each of the four combinations,
check rolling, stopping precisely, tracking target, high-G turns, stalled/low-speed
handling, AB recovery, aim assistance and full 1v1 victory/defeat conditions.
Measure learning effort and fun; do not infer user preference from headless results.
Keep this in Draft until visually and physically verified.

## Independent preview (Vercel READY, iPhone Safari NOT device-tested)

Deployment: `dpl_GLc2Yn9CtGhjefYcH7Mwobc3NkSY`, source commit
`9b55f21f359464eeeedcb86ef0248ef769bfe444` (runtime identical to
the later test-only assertion-fix commit).

- [Arcade × Expert](https://skyfront-ace-to-kao5v9bld-eddy121384-1385s-projects.vercel.app/?mode=arcade&control=expert&seed=71429)
- [Arcade × Assisted](https://skyfront-ace-to-kao5v9bld-eddy121384-1385s-projects.vercel.app/?mode=arcade&control=assisted&seed=71429)
- [Tactical × Expert](https://skyfront-ace-to-kao5v9bld-eddy121384-1385s-projects.vercel.app/?mode=tactical&control=expert&seed=71429)
- [Tactical × Assisted](https://skyfront-ace-to-kao5v9bld-eddy121384-1385s-projects.vercel.app/?mode=tactical&control=assisted&seed=71429)

Vercel API confirms READY and inspected deployed source tree includes the
root index.html, aircraft physics, AI, HUD/input/render JS, two vendored Three.js
scripts, and original sky/cloud paintings. An independent outside HTTP success
check was not available through the browsing environment. Real iPhone Safari
touch/play acceptance remains OPEN.

## Deterministic headless measurements

At 60Hz, F-16V, same bank-to-90 setup, 1 second at full aft stick:

| Measurement | Arcade | Tactical |
|---|---:|---:|
| heading gain | 24.74 deg | 21.52 deg |
| end load factor | 10.5 G | 9.0 G |
| airspeed loss | 5.52 m/s | 15.97 m/s |
| available G at 85 m/s | 5.70 G | 1.90 G |
| airspeed loss at 55% pull | 0.25 m/s | 4.43 m/s |

These numbers are algorithmic arcade experiments, not real aircraft
performance data. We still need human comparisons to decide whether either
mode actually feels enjoyable.
