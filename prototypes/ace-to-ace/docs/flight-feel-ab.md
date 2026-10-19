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

## Design hypotheses to evaluate on device

B: quicker onset and roll stop, ~8% greater roll-rate envelope; normal-pull cap
is 78% of aircraft max G, less induced drag and faster throttle spool; low-speed
lift falls off more gently; AB response has moderately stronger authority.
At **BRK + deep pull (>72%) above 110 m/s**, B may briefly use full airframe G
for up to 1.25 s with a 1.4 s cooldown and must release the input to rearm.
BRK's original independent parasite drag remains and high G increases induced
drag too. Max load factor and flight-path angular cap still apply.

B may be *too* responsive with the existing **release-to-hold virtual stick**:
any small remaining x input keeps rolling after the finger leaves the glass,
while an exact neutral command stops the aircraft without leveling it. Do not
auto-center the stick or change input gestures in this spike. Play 90° roll +
stop and near-lock fine-aim on real iPhone Safari to measure accidental overshoot,
thumb fatigue and ability to find neutral.

## Measurements and acceptance

Run `node tools/test-flight-feel-ab.mjs` for measured 90° bank time, stopped-bank
error, 90° and 180° turn time, peak angular rate/G, normal and BRK turn speed
loss, low-speed heading response, and AB recovery. The test prints JSON rather
than fabricating expected numbers. Existing test suite and headless AI tests
must also run. The benchmark runs no real iOS browser, so ***iPhone feel,
target acquisition and 1v1 aiming remain human acceptance items***.

iPhone play-check sequence: A and B, same seed and difficulty; 90° roll-stop;
bank-and-pull 90°/180°; repeat normal turns; engage BRK + deep pull; extend
and regain speed and altitude; recover from low-speed turns; fight full 1v1
using missiles and guns. Rate directness, overshoot, target dwell time,
post-turn responsiveness, and fun separately from numeric metrics. Keep this
Draft until real-device review; avoid declaring B the winner from CI alone.

## Independently verified remote preview

Vercel static preview (separate from the production alias):

- [A — Legacy Expert](https://skyfront-ace-to-f9dqaci6z-eddy121384-1385s-projects.vercel.app/?feel=A&seed=71429)
- [B — Arcade Expert](https://skyfront-ace-to-f9dqaci6z-eddy121384-1385s-projects.vercel.app/?feel=B&seed=71429)

Vercel READY plus explicit GET 200 checks for each entry point, simulation modules, render/HUD/input JS, CSS, vendored Three.js, and sky/cloud images. Actual iPhone Safari hardware playthrough remains unverified; no claim of player-validated feel.
