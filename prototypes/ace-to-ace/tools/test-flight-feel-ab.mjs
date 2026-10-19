#!/usr/bin/env node
// Deterministic headless A/B flight-feel probe. Interpret numbers together with
// iPhone human-play feedback; this is NOT a substitute for touch-device QA.
import assert from 'node:assert/strict';
import { createAircraft, stepAircraft, bankAngle, headingOf, availableG } from '../src/sim/aircraft.js';
import { forwardOf, angleBetween, DEG } from '../src/sim/math.js';
import { Match } from '../src/sim/world.js';

const dt = 1 / 60, deg = n => n / DEG;
function craft(feel, speed = 230) {
  const ac = createAircraft('F16V', 'blue', { x: 0, y: 3200, z: 0 }, { x: 0, y: 0, z: -1 }, speed);
  ac.flightFeel = feel;
  ac.controls.throttle = 0.72;
  return ac;
}
function step(ac, seconds) {
  for (let i = 0; i < Math.round(seconds / dt); i++) stepAircraft(ac, dt);
}
function deltaHeading(start, end) {
  return Math.abs(deg(Math.atan2(Math.sin(end - start), Math.cos(end - start))));
}
function bank90(ac) {
  ac.controls.roll = 1;
  let frames = 0;
  while (Math.abs(deg(bankAngle(ac))) < 90 && frames < 120) { stepAircraft(ac, dt); frames++; }
  assert.ok(frames < 120, 'must be able to roll 90 degrees');
  const elapsed = frames * dt;
  ac.controls.roll = 0;
  step(ac, 0.45);
  const settleError = Math.abs(deg(Math.atan2(
    Math.sin(bankAngle(ac) - Math.PI / 2), Math.cos(bankAngle(ac) - Math.PI / 2))));
  assert.ok(settleError < 28, 'roll stop must stay reasonably precise, not spring-level or spin');
  return { elapsed, settleError };
}
function turning(feel, brake = false, duration = 1.0, pull = 1) {
  const ac = craft(feel);
  const bank = bank90(ac);
  const startHeading = headingOf(ac), initialSpeed = ac.speed;
  ac.controls.pitch = pull;
  ac.controls.brake = brake;
  let peakG = 0, maxTurnRate = 0, previous = headingOf(ac);
  for (let i = 0; i < Math.round(duration / dt); i++) {
    stepAircraft(ac, dt);
    peakG = Math.max(peakG, ac.gLoad);
    maxTurnRate = Math.max(maxTurnRate, deltaHeading(previous, headingOf(ac)) / dt);
    previous = headingOf(ac);
  }
  return { bank, headingDeg: deltaHeading(startHeading, headingOf(ac)),
    maxTurnRateDegPerSec: maxTurnRate, peakG, lostMps: initialSpeed - ac.speed,
    endSpeed: ac.speed, heightChangeM: ac.pos.y - 3200 };
}
function turnMilestone(feel, goal) {
  const ac = craft(feel);
  bank90(ac);
  ac.controls.pitch = 0.85;
  const initial = headingOf(ac);
  for (let i = 0; i < 30 / dt; i++) {
    stepAircraft(ac, dt);
    if (deltaHeading(initial, headingOf(ac))  >= goal - 1) return { seconds: (i + 1) * dt, speed: ac.speed };
  }
  return null;
}
function recover(feel, startSpeed = 90) {
  const ac = craft(feel, startSpeed);
  ac.controls.boost = true;
  const startHeight = ac.pos.y;
  let tToCorner = null;
  for (let i = 0; i < 18 / dt; i++) {
    stepAircraft(ac, dt);
    if (tToCorner === null && ac.speed >= ac.type.cornerSpeed) tToCorner = (i + 1) * dt;
  }
  return { speed: ac.speed, secondsToCorner: tToCorner, altDeltaM: ac.pos.y - startHeight };
}
function lowSpeed(feel) {
  const ac = craft(feel, 85);
  bank90(ac);
  const h0 = headingOf(ac);
  ac.controls.pitch = 0.85; ac.controls.boost = true;
  step(ac, 4);
  return { headingDeg: deltaHeading(h0, headingOf(ac)), speed: ac.speed, gAvailable: availableG(ac, 85) };
}

// A cannot change behavior just because the experiment exists.
{
  const legacy = craft('A'), defaultLegacy = craft(undefined);
  legacy.controls.pitch = defaultLegacy.controls.pitch = 0.8;
  legacy.controls.roll = defaultLegacy.controls.roll = 0.45;
  legacy.controls.brake = defaultLegacy.controls.brake = true;
  for (let i = 0; i < 300; i++) { stepAircraft(legacy, dt); stepAircraft(defaultLegacy, dt); }
  assert.deepEqual({ pos: legacy.pos, q: legacy.q, speed: legacy.speed, g: legacy.gLoad },
    { pos: defaultLegacy.pos, q: defaultLegacy.q, speed: defaultLegacy.speed, g: defaultLegacy.gLoad },
    'Legacy must be identical to the original/default path');
}

// Expert x-axis is pure roll: no auto-level, no invisible yaw-turn assist.
{
  const ac = craft('B');
  const h0 = headingOf(ac);
  const roll = bank90(ac);
  assert.ok(roll.elapsed < 1, 'roll command should respond promptly');
  assert.ok(deltaHeading(h0, headingOf(ac)) < 15, 'roll alone must not become a horizontal turn');
  assert.ok(Math.abs(deg(bankAngle(ac))) > 55, 'neutral roll must NOT level the wings');
  const noPitch = deltaHeading(headingOf(ac), (step(ac, 0.4), headingOf(ac)));
  assert.ok(noPitch < 12, 'banked zero-pitch should not secretly command a coordinated turn');
}

// A full pull requests available G directly, while airbrake ONLY adds drag.
const normalA = turning('A'), normalB = turning('B');
const brakeB = turning('B', true), moderateB = turning('B', false, 1, 0.55);
assert.ok(normalB.peakG > 8.8 && normalB.peakG <= 9.001,
  'B F-16 full pull should reach nominal 9G without any BRK modifier');
assert.ok(brakeB.peakG <= normalB.peakG + 0.001,
  'BRK must never unlock more G');
assert.ok(brakeB.lostMps > normalB.lostMps + 1,
  'BRK must cost additional speed, independently of the G command');
assert.ok(normalB.lostMps > moderateB.lostMps + 4,
  'hard 9G pull must pay more speed than moderate 5G pull');
assert.ok(normalB.headingDeg > moderateB.headingDeg + 2,
  'high-G pull must yield more heading response than moderate pull');
assert.ok(availableG(craft('B', 85), 85) < 3,
  'low speed cannot provide almost 9G of lift');
assert.ok(availableG(craft('B', 230), 230) <= 9,
  'F-16 B-mode must respect its nominal 9G envelope');
{
  const ac = craft('B');
  bank90(ac);
  ac.controls.pitch = 1; ac.controls.brake = true;
  step(ac, 2.3);
  assert.ok(ac.gLoad <= 9.001, 'sustained BRK and pitch cannot exceed airframe G');
  assert.equal(ac.highGCooldown, undefined, 'no arbitrary High-G unlock/cooldown');
  assert.equal(ac.controls.throttle, 0.72, 'BRK must not overwrite throttle');
  assert.equal(ac.controls.boost, false, 'BRK must not enable AB');
  ac.controls.pitch = 0; ac.controls.brake = false; ac.controls.boost = true;
  step(ac, 2);
  assert.ok(ac.abCur > 0, 'AB remains separate from brake');
  assert.ok(Number.isFinite(ac.speed) && ac.speed >= 45, 'physics must stay finite');
}

// Same seed/spawn/difficulty and flight performance shared by AI and player.
for (const feel of ['A', 'B']) {
  const m = new Match({ seed: 71429, flightFeel: feel,
    blue: { type: 'F16V' }, red: { type: 'J16' } });
  const repeated = new Match({ seed: 71429, flightFeel: feel,
    blue: { type: 'F16V' }, red: { type: 'J16' } });
  assert.deepEqual(m.blue.pos, repeated.blue.pos);
  assert.deepEqual(m.red.pos, repeated.red.pos);
  assert.equal(m.blue.flightFeel, feel);
  assert.equal(m.red.flightFeel, feel);
  for (let i = 0; i < 120; i++) m.step();
  assert.ok(Number.isFinite(m.blue.speed) && Number.isFinite(m.red.speed));
}

// Fixed-slope, unloaded energy exchange: gravity, not a scripted speed boost,
// must slow the climb and accelerate the dive. Test both flight integrations.
function slopeExchange(feel, angleDeg) {
  const a = angleDeg * DEG;
  const ac = createAircraft('F16V', 'blue', { x: 0, y: 3400, z: 0 },
    { x: 0, y: Math.sin(a), z: -Math.cos(a) }, 230);
  ac.flightFeel = feel;
  ac.controls.throttle = 0.72;
  step(ac, 3);
  return { heightDeltaM: ac.pos.y - 3400, speedDeltaMps: ac.speed - 230 };
}
const slopes = {};
for (const feel of ['A', 'B']) {
  const climb = slopeExchange(feel, 18), dive = slopeExchange(feel, -18);
  assert.ok(climb.heightDeltaM > 100, feel + ' climb must actually gain altitude');
  assert.ok(dive.heightDeltaM < -100, feel + ' dive must actually lose altitude');
  assert.ok(dive.speedDeltaMps > climb.speedDeltaMps + 12,
    feel + ' descending must retain more speed than climbing');
  slopes[feel] = { climb, dive };
}

const data = {
  climbDive: slopes,
  roll90: { A: normalA.bank, B: normalB.bank },
  normalTurn1s: { A: normalA, B: normalB },
  brakeTurn1s: brakeB,
  moderateTurn1s: moderateB,
  turn90: { A: turnMilestone('A', 90), B: turnMilestone('B', 90) },
  turn180: { A: turnMilestone('A', 180), B: turnMilestone('B', 180) },
  recoveryFrom85: { A: recover('A', 85), B: recover('B', 85) },
  lowSpeed: { A: lowSpeed('A'), B: lowSpeed('B') },
};
console.log(JSON.stringify(data, null, 2));
assert.ok(data.turn90.B && data.turn180.B, 'B must support continuous 90/180-degree expert turns');
assert.ok(data.lowSpeed.B.headingDeg > 5, 'B low-speed pull must retain steering authority');
assert.ok(data.recoveryFrom85.B.speed > 85, 'B AB must recover speed');
console.log('Expert Flight Feel A/B physics PASS');
