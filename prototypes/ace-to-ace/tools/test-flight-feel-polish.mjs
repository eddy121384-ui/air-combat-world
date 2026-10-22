#!/usr/bin/env node
// Guard rails for the Oct 2026 flight-feel polish (docs/flight-feel-polish.md).
// Each assertion encodes a design property, not a tuned number: if a future
// change breaks one, decide deliberately whether the property should change.
import assert from 'node:assert/strict';
import {
  createAircraft, stepAircraft, availableG, instantTurnRate, bestTurn, bankAngle, MAX_SPEED,
} from '../src/sim/aircraft.js';
import { pullUpWarning } from '../src/sim/warnings.js';
import { PlayerController } from '../src/game/input.js';
import { CircleBot } from '../src/ai/bots.js';
import { DEG } from '../src/sim/math.js';

const dt = 1 / 60, deg = (r) => r / DEG;
function craft(feel, speed = 230, type = 'F16V') {
  const ac = createAircraft(type, 'blue', { x: 0, y: 3200, z: 0 }, { x: 0, y: 0, z: -1 }, speed);
  ac.flightFeel = feel; ac.controls.throttle = 1;
  return ac;
}
const run = (ac, s) => { for (let i = 0; i < Math.round(s / dt); i++) stepAircraft(ac, dt); };

for (const feel of ['arcade', 'tactical']) {
  // 1. Top speed is set by drag, not by the MAX_SPEED clamp (energy no longer vanishes).
  const ab = craft(feel, 300); ab.controls.boost = true; run(ab, 60);
  assert.ok(ab.speed < MAX_SPEED - 30, `${feel}: AB top speed must be drag-limited (${ab.speed.toFixed(0)})`);
  // 2. MIL power can still recover speed in level flight.
  const mil = craft(feel, 150); run(mil, 45);
  assert.ok(mil.speed > 250, `${feel}: MIL must accelerate 150 -> 250 m/s within 45 s`);
  // 3. Turn-rate peak sits at corner speed, not at the minimum-speed clamp.
  const ref = craft(feel), best = bestTurn(ref);
  assert.ok(best.lo > 100, `${feel}: best-turn band must not start at the stall clamp (${best.lo})`);
  assert.ok(instantTurnRate(ref, 60) < best.rate * 0.8, `${feel}: crawling must not out-turn corner speed`);
  // ...while slowing still tightens the radius (brake-turn stays meaningful).
  const radius = (v) => v / instantTurnRate(ref, v);
  assert.ok(radius(110) < radius(best.hi), `${feel}: slower than corner gives a tighter radius`);
  // 4. Expert roll stop: releasing the stick does not drift on past the target.
  const r = craft(feel); r.controls.roll = 1;
  while (deg(bankAngle(r)) < 90) stepAircraft(r, dt);
  r.controls.roll = 0; let peak = 0;
  for (let i = 0; i < 60; i++) { stepAircraft(r, dt); peak = Math.max(peak, deg(bankAngle(r))); }
  assert.ok(peak - 90 < 6, `${feel}: roll overshoot after release must stay under 6 deg (${(peak - 90).toFixed(1)})`);
}

// 5. Arcade is still the forgiving profile at low speed; Tactical remains lift-limited.
assert.ok(availableG(craft('arcade', 85), 85) > 2 * availableG(craft('tactical', 85), 85));

// 6. Tactical energy: a full-G corner pull with AB bleeds clearly; a moderate MIL
//    5G turn is close to sustainable. Hard and moderate pulls must feel different.
{
  const hard = craft('tactical', 185); hard.controls.boost = true;
  hard.nCur = 9; hard.controls.pitch = 1; // level G bookkeeping only; drag uses nCur
  const v0 = hard.speed; stepAircraft(hard, dt);
  const bleedHard = (v0 - hard.speed) / dt;
  const easy = craft('tactical', 230); easy.nCur = 5; easy.controls.throttle = 1;
  easy.controls.pitch = 0.45;
  const e0 = easy.speed; stepAircraft(easy, dt);
  const bleedEasy = (e0 - easy.speed) / dt;
  assert.ok(bleedHard > 5, `tactical 9G at corner with AB must bleed > 5 m/s^2 (${bleedHard.toFixed(1)})`);
  assert.ok(Math.abs(bleedEasy) < 3.5, `tactical 5G MIL turn should be near-sustainable (${bleedEasy.toFixed(1)})`);
}

// 7. Assisted: stick is proportional to turn rate, so a light touch is a gentle bank.
//    Full stick is unchanged and can never exceed the airframe's available G.
function assistedRun(feel, x, seconds = 3) {
  const ac = craft(feel); ac.controls.throttle = 0.72;
  const inp = { axes: () => ({ x, y: 0, yaw: 0 }), throttle: () => 0.72, boost: () => false,
    brake: () => false, gun: () => false, consume: () => false };
  const pc = new PlayerController(ac, inp, { assist: true, invert: false });
  let peakBank = 0, over = 0, boost = false;
  for (let i = 0; i < Math.round(seconds / dt); i++) {
    const c = pc.update(); boost ||= c.boost;
    Object.assign(ac.controls, c); stepAircraft(ac, dt);
    peakBank = Math.max(peakBank, Math.abs(deg(bankAngle(ac))));
    over = Math.max(over, ac.gLoad - availableG(ac));
  }
  return { peakBank, over, boost };
}
for (const feel of ['arcade', 'tactical']) {
  const light = assistedRun(feel, 0.15), full = assistedRun(feel, 1);
  assert.ok(light.peakBank < 56, `${feel}: 15% assisted stick must not snap to a steep bank (${light.peakBank.toFixed(0)})`);
  assert.ok(full.peakBank > 75, `${feel}: full assisted stick still commands a hard level turn`);
  assert.ok(full.over < 0.01 && light.over < 0.01, `${feel}: Assisted cannot exceed available G`);
  assert.equal(full.boost, false, `${feel}: Assisted never lights the afterburner`);
}
// Fine-aim rudder fades out continuously (no jump at the old |x| = 0.3 edge).
{
  const ac = craft('arcade');
  const yawAt = (x) => new PlayerController(ac, { axes: () => ({ x, y: 0, yaw: 0 }), throttle: () => 0.72,
    boost: () => false, brake: () => false, gun: () => false, consume: () => false }, { assist: true }).update().yaw;
  for (let x = 0.2; x < 0.4; x += 0.01) assert.ok(Math.abs(yawAt(x + 0.01) - yawAt(x)) < 0.12, 'assisted rudder must fade smoothly');
}

// 8. AI rudder is fine-tracking only: a sustained max-G level turn must stay level.
for (const feel of ['arcade', 'tactical']) {
  const ac = craft(feel); const bot = new CircleBot(ac);
  const y0 = ac.pos.y;
  for (let i = 0; i < 25 * 60; i++) { Object.assign(ac.controls, bot.update(dt)); stepAircraft(ac, dt); }
  assert.ok(Math.abs(ac.pos.y - y0) < 300, `${feel}: AI level turn must not sink into the sea (${(ac.pos.y - y0).toFixed(0)} m)`);
}

// 9. PULL UP is energy-aware: a fast dive warns early, gentle low flight does not nag.
{
  const dive = createAircraft('F16V', 'blue', { x: 0, y: 800, z: 0 },
    { x: 0, y: -Math.sin(35 * DEG), z: -Math.cos(35 * DEG) }, 380);
  dive.flightFeel = 'tactical';
  assert.equal(pullUpWarning(dive), true, '380 m/s 35-degree dive at 800 m must warn (old rule: silent above 600 m)');
  dive.pos.y = 1500;
  assert.equal(pullUpWarning(dive), false, 'the same dive with 1500 m of room needs no warning');
  const cruise = createAircraft('F16V', 'blue', { x: 0, y: 450, z: 0 }, { x: 0, y: 0, z: -1 }, 230);
  cruise.flightFeel = 'arcade';
  assert.equal(pullUpWarning(cruise), false, 'level flight at 450 m must not warn');
}

console.log('Flight-feel polish guard rails PASS');
