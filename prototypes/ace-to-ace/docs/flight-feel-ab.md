# Ace to Ace — Expert Flight Feel A/B (isolated spike)

Baseline: `claude/vibrant-dirac-kmsuin` at `0db84b5953eaffd75c3256ad0579f3c098dd0147`.
This study does not change the Unreal project, aircraft visuals, clouds, weapon rules, or HUD.

## Test at identical conditions

Open **A** using `?feel=A&seed=71429` and **B** using `?feel=B&seed=71429` on the same preview host.
Both force **MANUAL Expert** (x = roll, y = pitch), keep the original latched iPhone stick,
72% throttle slider, independent AB toggle and momentary BRK. Same seeded start,
skill and PilotAI logic. Rematch reuses seed by design. Use landscape Safari.

A is the original `stepAircraft` integration, renamed internally to
`stepLegacyAircraft` without retuning. Without a feel flag, headless tools and
`Match` default to A, preserving old regressions. B runs a separate, identically
shared player-and-AI physics integration. Neither mode adds automatic leveling or
yaw-to-turn; both turn through physical banked lift, bounded G, gravity, drag and
finite velocity-vector response. The HUD W and FPM still read the actual nose and
displacement vectors.

## B v2 hypothesis — realistic principles, arcade responsiveness

The B-mode flight controls retain responsive Expert roll, rapid roll stop and
load-factor response, bank-to-turn, and the actual lagging velocity vector.
Neither mode auto-levels. Full aft stick now requests all **available** G
without any BRK modifier. The B envelope uses a **nominal 9G ceiling** for
both simulated aircraft and a speed-squared lift limit below corner speed.
The F-16 9G value is an approximate clean-airframe baseline. **The J-16
9G in B is a deliberate game benchmark, not a verified real-world spec**.

Induced drag scales with the square of the current G load: an aggressive turn
buys nose position and costs substantial airspeed. Moderate pull preserves
energy. BRK adds parasite drag only; no G unlock, timer or cooldown remains.
Throttle and AB stay independent and BRK never changes either. Faster throttle
spool and a modest parasite drag discount retain the Arcade Expert flavor,
while the previous arbitrary +10% thrust buff is removed.

This is an arcade point-mass approximation, **not** a certified F-16 flight
model. Actual envelope and sustained-turn behavior depend on altitude,
weight, external stores, angle of attack, engine conditions, etc.
B may still overshoot with the existing release-to-hold virtual stick;
evaluate on real iPhone Safari before calling the feel accepted.

## Measurements and acceptance

Run `node tools/test-flight-feel-ab.mjs` for measured 90° bank time, stopped-bank
error, 90° and 180° turn time, peak angular rate/G, full vs moderate pull and brake-on/off speed
loss, low-speed lift limits, and AB recovery. The test prints JSON rather
than fabricating expected numbers. Existing test suite and headless AI tests
must also run. The benchmark runs no real iOS browser, so ***iPhone feel,
target acquisition and 1v1 aiming remain human acceptance items***.

iPhone play-check sequence: A and B, same seed and difficulty; 90° roll-stop;
bank-and-pull 90°/180°; repeat normal turns; compare BRK on/off at the same pull; extend
and regain speed and altitude; recover from low-speed turns; fight full 1v1
using missiles and guns. Rate directness, overshoot, target dwell time,
post-turn responsiveness, and fun separately from numeric metrics. Keep this
Draft until real-device review; avoid declaring B the winner from CI alone.

## B v2 web preview (device acceptance pending)

Vercel static preview (separate from the production alias):

- [A — Legacy Expert](https://skyfront-ace-to-boqge2bak-eddy121384-1385s-projects.vercel.app/?feel=A&seed=71429)
- [B — Arcade Expert](https://skyfront-ace-to-boqge2bak-eddy121384-1385s-projects.vercel.app/?feel=B&seed=71429)

B v2 commit `777267a11` was deployed independently via Vercel API and reports READY. Deployment source tree was inspected: index, simulation and AI modules, HUD/input/render code, vendored Three.js and original sky/cloud textures are all present at expected paths. The external web fetcher could not establish a live HTTP success code; **iPhone Safari hardware playthrough and clickable URL response are not verified**. Do not confuse deployment state with real-device validation.

### Headless comparison (60 Hz, same seed and initial state)

| Maneuver | A original | B v2 |
|---|---:|---:|
| 90-degree roll command | 0.467 s | 0.417 s |
| bank settling error after 0.45 s | 16.89 deg | 8.23 deg |
| 1 s full-pull peak G | 10 G (legacy game value) | 9 G |
| 1 s full-pull airspeed loss | 18.91 m/s | 15.97 m/s |
| B moderate (55% pull) 1 s loss | — | 4.43 m/s |
| B BRK + full pull 1 s loss | — | 24.10 m/s (no extra G) |
| 90-degree heading turn | 3.78 s | 4.22 s |
| 180-degree heading turn | 8.13 s | 8.85 s |
| B lift-available at 85 m/s | — | ~1.90 G |

Numeric tests are not a guarantee of better dogfighting feel; target tracking, iPhone touch and fun must be evaluated by a player.
