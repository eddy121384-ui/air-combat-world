#!/usr/bin/env node
// Airbrake and throttle are independent commands, without changing controls layout.
import assert from 'node:assert/strict';
import { createAircraft, stepAircraft } from '../src/sim/aircraft.js';
import { Input, PlayerController } from '../src/game/input.js';

const position = { x: 0, y: 2500, z: 0 };
const forward = { x: 0, y: 0, z: -1 };
function aircraft(speed = 220) {
  return createAircraft('F16V', 'blue', position, forward, speed);
}
function run(commands) {
  const ac = aircraft();
  ac.controls = { ...ac.controls, ...commands };
  for (let i = 0; i < 60; i++) stepAircraft(ac, 1 / 60);
  return ac;
}
function near(actual, expected, label) {
  assert.ok(Math.abs(actual - expected) < 1e-10, `${label}: ${actual} != ${expected}`);
}

// At identical throttle / AB settings, extending the brake changes drag only.
for (const power of [{ throttle: 0.72, boost: false }, { throttle: 0.72, boost: true }]) {
  const clean = run({ ...power, brake: false });
  const braking = run({ ...power, brake: true });
  near(braking.thrustCur, clean.thrustCur, 'military power must not change');
  near(braking.abCur, clean.abCur, 'afterburner power must not change');
  assert.ok(braking.speed < clean.speed - 0.5, 'airbrake must cost speed at equal power');
}
const brakingAtPower = run({ throttle: 0.72, boost: false, brake: true });
const brakingIdle = run({ throttle: 0, boost: false, brake: true });
assert.ok(brakingAtPower.speed > brakingIdle.speed, 'brake must not forcibly idle the engine');
const burnerBrake = run({ throttle: 0.72, boost: true, brake: true });
assert.ok(burnerBrake.abCur > 0.5, 'AB and BRK can operate together');

// PlayerController passes through both explicit buttons without changing the stick logic.
function playerInput(boost, brake) {
  return { axes: () => ({ x: 0, y: 0, yaw: 0 }), throttle: () => 0.72, boost: () => boost,
    brake: () => brake, gun: () => false, consume: () => false };
}
const player = new PlayerController(aircraft(), playerInput(true, true), { invert: true, assist: false });
const controls = player.update();
assert.equal(controls.boost, true);
assert.equal(controls.brake, true);
near(controls.throttle, 0.72, 'player throttle unchanged');

// Retain the original safety choice: low-speed ASSIST must not automatically
// switch on AB while the player holds BRK.
const assisted = new PlayerController(aircraft(60), playerInput(false, true), { invert: true, assist: true });
assert.equal(assisted.update().boost, false, 'no auto-AB against held brake');

// Touch AB remains latched while BRK is held/released; no added controls or modes.
function element(name) {
  const events = new Map(), classes = new Set();
  return {
    dataset: { btn: name }, style: {},
    classList: {
      add: (n) => classes.add(n),
      remove: (n) => classes.delete(n),
      contains: (n) => classes.has(n),
      toggle: (n, value) => { if (value ?? !classes.has(n)) classes.add(n); else classes.delete(n); },
    },
    addEventListener: (type, fn) => events.set(type, fn),
    fire: (type) => events.get(type)({ preventDefault() {} }),
  };
}
const zone = element('zone'), base = element('base'), knob = element('knob');
const boostButton = element('boost'), brakeButton = element('brake');
const elements = { '#stickZone': zone, '#stickBase': base, '#stickKnob': knob,
  '[data-btn="boost"]': boostButton };
const root = {
  querySelector: (sel) => elements[sel],
  querySelectorAll: () => [boostButton, brakeButton],
};
const savedWindow = globalThis.window;
try {
  globalThis.window = { addEventListener() {} };
  const input = new Input(root);
  boostButton.fire('touchstart');
  boostButton.fire('touchend'); // a tap ends before the next tap starts
  assert.equal(input.boost(), true);
  brakeButton.fire('touchstart');
  assert.equal(input.brake(), true);
  assert.equal(input.boost(), true, 'BRK must not cancel toggled AB');
  assert.equal(boostButton.classList.contains('lit'), true);
  brakeButton.fire('touchend');
  assert.equal(input.brake(), false);
  assert.equal(input.boost(), true, 'releasing BRK must retain AB state');
  boostButton.fire('touchstart');
  assert.equal(input.boost(), false, 'AB still toggles off with second tap');
} finally {
  if (savedWindow === undefined) delete globalThis.window;
  else globalThis.window = savedWindow;
}
console.log('Airbrake/throttle physics and AB/BRK controls PASS');
