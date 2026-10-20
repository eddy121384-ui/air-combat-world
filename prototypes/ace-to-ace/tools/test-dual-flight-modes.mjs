#!/usr/bin/env node
// Dual physics profiles x dual pilot controls. Headless structural/physics gate;
// actual iPhone Safari touch & dogfight feel require real-device acceptance.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createAircraft, stepAircraft, availableG, bankAngle, headingOf, specificEnergy } from '../src/sim/aircraft.js';
import { PlayerController } from '../src/game/input.js';
import { Match } from '../src/sim/world.js';
import { DEG } from '../src/sim/math.js';

const dt = 1 / 60;
const d = v => v / DEG;
function craft(mode, speed = 230) {
  const a = createAircraft('F16V', 'blue', { x: 0, y: 3200, z: 0 },
    { x: 0, y: 0, z: -1 }, speed);
  a.flightFeel = mode;
  a.controls.throttle = .72;
  return a;
}
function step(a, seconds) {
  for (let i = 0; i < Math.round(seconds / dt); i++) stepAircraft(a, dt);
}
function bank(a) {
  a.controls.roll = 1;
  let n = 0;
  while (Math.abs(d(bankAngle(a))) < 90 && n++ < 120) stepAircraft(a, dt);
  assert.ok(n < 120, '90-degree roll must be achievable in either physics profile');
  a.controls.roll = 0;
  step(a, .45);
}
function turn(mode, pull = 1, brake = false) {
  const a = craft(mode);
  bank(a);
  const initialSpeed = a.speed, initialEnergy = specificEnergy(a);
  const start = headingOf(a);
  a.controls.pitch = pull;
  a.controls.brake = brake;
  step(a, 1);
  const heading = Math.abs(d(Math.atan2(Math.sin(headingOf(a)-start),Math.cos(headingOf(a)-start))));
  return { heading, peakG: a.gLoad, speedLoss: initialSpeed-a.speed,
    energyLoss: initialEnergy-specificEnergy(a), speed: a.speed };
}

// Preserve historical A and B for existing regression comparisons.
for (const mode of ['A','B','arcade','tactical']) {
  const match = new Match({ seed: 71429, flightFeel: mode,
    blue: { type: 'F16V' }, red: { type: 'J16' } });
  assert.equal(match.blue.flightFeel, mode);
  assert.equal(match.red.flightFeel, mode, 'AI and player must get the same envelope');
  for (let i = 0; i < 180; i++) match.step();
  assert.ok(Number.isFinite(match.blue.speed) && Number.isFinite(match.red.speed));
}
assert.equal(new Match({ seed: 5, blue: { type: 'F16V' }, red: { type: 'J16' } }).blue.flightFeel,'A',
  'A stays the legacy headless default');

const slowArcade = availableG(craft('arcade',85),85);
const slowTactical = availableG(craft('tactical',85),85);
assert.ok(slowArcade > slowTactical * 1.6,
  'Arcade should be notably more maneuverable at low speed');
assert.ok(availableG(craft('tactical',230),230) <= 9.001);
assert.ok(availableG(craft('arcade',230),230) > 9.5);
const arcade = turn('arcade'), tactical = turn('tactical'), easy = turn('tactical',.55),
  brake = turn('tactical',1,true), arcadeEasy = turn('arcade',.55);
assert.ok(arcade.heading > tactical.heading + 2,
  'Arcade should have greater instantaneous heading authority');
assert.ok(arcade.speedLoss < tactical.speedLoss,
  'Arcade must retain more speed in the same hard turn');
assert.ok(tactical.speedLoss > easy.speedLoss + 4,
  'Tactical full-G maneuver must pay greater energy than moderate pull');
assert.ok(brake.speedLoss > tactical.speedLoss + 2,
  'Airbrake remains independent, costing more speed');
assert.ok(brake.peakG <= tactical.peakG + .01,
  'Airbrake cannot unlock additional G');
assert.ok(arcade.speedLoss > arcadeEasy.speedLoss,
  'Arcade still has meaningful energy tradeoffs');

// No phantom self-leveling in Expert: a released roll axis holds bank.
for (const mode of ['arcade','tactical']) {
  const a = craft(mode);
  bank(a);
  assert.ok(Math.abs(d(bankAngle(a))) > 55, 'neutral roll must not auto-level');
}

// Assisted / Expert have different control interpretation, not different physics.
const stub = () => ({
  axes: () => ({ x: .65, y: 0, yaw: 0 }),
  throttle: () => .72, boost: () => false, brake: () => false,
  gun: () => false, consume: () => false,
});
for (const mode of ['arcade','tactical']) {
  const e = craft(mode), as = craft(mode);
  const expert = new PlayerController(e, stub(), { invert: false, assist: false }).update();
  const assisted = new PlayerController(as, stub(), { invert: false, assist: true }).update();
  assert.equal(expert.roll, .65);
  assert.equal(expert.pitch, 0);
  assert.ok(assisted.pitch > 0, 'Assisted must coordinate bank-and-pull');
  assert.notDeepEqual([expert.roll,expert.pitch],[assisted.roll,assisted.pitch]);
  assert.equal(assisted.boost, false, 'Assisted must not secretly enable AB');
  assert.equal(assisted.throttle, .72);
}

// UI wiring: both selectors are present and carried into match/controller setup.
const html = readFileSync(new URL('../index.html',import.meta.url),'utf8');
const main = readFileSync(new URL('../src/game/main.js',import.meta.url),'utf8');
for (const value of ['arcade','tactical']) assert.ok(html.includes('data-flight-mode="'+value+'"'));
for (const value of ['assisted','expert']) assert.ok(html.includes('data-control-mode="'+value+'"'));
assert.match(main, /assist: controlMode === 'assisted'/);
assert.match(main, /new Match\(\{ seed, flightFeel/);

console.log(JSON.stringify({ slowG: { arcade:slowArcade,tactical:slowTactical },
  fullTurn1s: { arcade,tactical }, moderateTurn1s:{arcade:arcadeEasy,tactical:easy},
  brakeTactical:brake },null,2));
console.log('Dual-mode Arcade/Tactical x Assisted/Expert PASS');
