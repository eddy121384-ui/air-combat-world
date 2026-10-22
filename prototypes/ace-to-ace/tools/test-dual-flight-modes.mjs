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
  assert.ok(Math.abs(expert.pitch) < 1e-9, 'neutral expert pitch may be signed zero');
  assert.ok(assisted.pitch > 0, 'Assisted must coordinate bank-and-pull');
  assert.notDeepEqual([expert.roll,expert.pitch],[assisted.roll,assisted.pitch]);
  assert.equal(assisted.boost, false, 'Assisted must not secretly enable AB');
  assert.equal(assisted.throttle, .72);
}

// UI selection is now reachable from both the title and the in-fight PAUSE menu.
const html = readFileSync(new URL('../index.html',import.meta.url),'utf8');
const main = readFileSync(new URL('../src/game/main.js',import.meta.url),'utf8');
for (const flight of ['arcade','tactical']) {
  for (const ctrl of ['assisted','expert']) {
    assert.ok(html.includes('data-flight-choice="'+flight+':'+ctrl+'"'),
      'all four direct-choice preset buttons must exist');
  }
}
for (const id of ['flightSettings', 'btnTitleSettings', 'btnPauseSettings',
  'btnSettingsCancel', 'btnSettingsApply', 'currentFlightPreset']) {
  assert.ok(html.includes('id="'+id+'"'), 'settings UI missing '+id);
}
assert.ok(main.includes("assist: controlMode === 'assisted'"));
assert.ok(main.includes('new Match({ seed, flightFeel'));
assert.ok(/if \(changed\)[^\n]*start\(kind\)/.test(main),
  'physics change must restart same sortie, not switch in flight');
assert.ok(/if \(changed\)[^\n]*startLesson\(lessonId\)/.test(main),
  'in an Academy lesson the same lesson restarts with the new model');
assert.ok(main.includes('settings.flightMode = draftFlight'), 'flight selection must persist');
assert.ok(main.includes('settings.controlMode = draftControl'), 'control selection must persist');
assert.ok(main.includes("params.get('autostart') === '1'"), 'mode=arcade must not auto-start');
assert.ok(main.includes("mode === 'title' && !settingsVisible()"),
  'title Enter must not bypass open settings');
console.log(JSON.stringify({ slowG: { arcade:slowArcade,tactical:slowTactical },
  fullTurn1s: { arcade,tactical }, moderateTurn1s:{arcade:arcadeEasy,tactical:easy},
  brakeTactical:brake },null,2));
console.log('Dual-mode Arcade/Tactical x Assisted/Expert PASS');
