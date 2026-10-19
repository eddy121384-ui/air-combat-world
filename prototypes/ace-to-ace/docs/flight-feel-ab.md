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

## Independently verified remote preview

Vercel static preview (separate from the production alias):

- [A — Legacy Expert](https://skyfront-ace-to-f9dqaci6z-eddy121384-1385s-projects.vercel.app/?feel=A&seed=71429)
- [B — Arcade Expert](https://skyfront-ace-to-f9dqaci6z-eddy121384-1385s-projects.vercel.app/?feel=B&seed=71429)

The links above point to the previous B v1 until the B v2 commit is redeployed and checked. Do not evaluate new physics using an old preview. Actual iPhone Safari hardware playthrough remains unverified.
