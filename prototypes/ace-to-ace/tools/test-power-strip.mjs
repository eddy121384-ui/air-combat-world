#!/usr/bin/env node
// Mobile power strip: latched throttle, independent AB & BRK, and two-finger control.
import assert from 'node:assert/strict';
import { Input, PlayerController } from '../src/game/input.js';
import { createAircraft } from '../src/sim/aircraft.js';

function element(name) {
  const events = new Map(), classes = new Set(), attributes = new Map();
  return {
    dataset: { btn: name }, style: {}, textContent: '',
    classList: {
      add: (c) => classes.add(c), remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
      toggle: (c, yes) => { if (yes ?? !classes.has(c)) classes.add(c); else classes.delete(c); },
    },
    addEventListener: (type, fn) => events.set(type, fn),
    setAttribute: (name, value) => attributes.set(name, value),
    getAttribute: (name) => attributes.get(name),
    getBoundingClientRect: () => ({ top: 100, height: 112 }),
    setPointerCapture() {},
    fire: (type, opts = {}) => {
      assert.ok(events.has(type), `missing ${type} on ${name}`);
      let prevented = false;
      events.get(type)({ preventDefault() { prevented = true; }, ...opts });
      return prevented;
    },
  };
}
const el = Object.fromEntries(['zone','base','knob','track','handle','fill','value','boost','brake','gun','msl','flare','look'].map(n=>[n,element(n)]));
const lookup = {
  '#stickZone': el.zone, '#stickBase': el.base, '#stickKnob': el.knob,
  '#throttleTrack': el.track, '#throttleHandle': el.handle,
  '#throttleFill': el.fill, '#throttleValue': el.value,
  '[data-btn="boost"]': el.boost, '[data-btn="brake"]': el.brake,
};
const root = {
  querySelector: (selector) => lookup[selector] ?? null,
  querySelectorAll: (selector) => selector === '[data-btn]' ? [el.boost, el.brake, el.gun, el.msl, el.flare, el.look] : [],
};
const originalWindow = globalThis.window;
try {
  globalThis.window = { addEventListener() {} };
  const input = new Input(root);
  assert.equal(input.throttle(), 0.72);
  assert.equal(el.value.textContent, '72%');

  // Absolute track: top=100, thumb-centre travel starts at 109 and ends at 203.
  el.track.fire('pointerdown', { pointerId: 2, clientY: 109 });
  assert.equal(input.throttle(), 1);
  el.track.fire('pointermove', { pointerId: 2, clientY: 156 });
  assert.equal(input.throttle(), 0.5);
  el.track.fire('pointermove', { pointerId: 99, clientY: 109 }); // ignore another finger
  assert.equal(input.throttle(), 0.5);
  el.track.fire('pointerup', { pointerId: 2 });
  el.track.fire('pointermove', { pointerId: 2, clientY: 109 });
  assert.equal(input.throttle(), 0.5, 'finger release keeps chosen throttle');

  // AB tap and BRK hold are independent and preserve throttle.
  el.boost.fire('touchstart');
  assert.equal(input.boost(), true);
  assert.equal(el.boost.getAttribute('aria-pressed'), 'true');
  el.brake.fire('touchstart');
  assert.equal(input.brake(), true);
  assert.equal(input.boost(), true);
  assert.equal(input.throttle(), 0.5);
  el.brake.fire('touchend');
  assert.equal(input.brake(), false);
  assert.equal(input.boost(), true);
  el.boost.fire('touchstart');
  assert.equal(input.boost(), false);

  // Keyboard precision, pointer cancel, and drag clamping.
  el.track.fire('keydown', { code: 'Home' });
  assert.equal(input.throttle(), 0);
  el.track.fire('keydown', { code: 'ArrowUp' });
  assert.equal(input.throttle(), 0.05);
  el.track.fire('keydown', { code: 'End' });
  assert.equal(input.throttle(), 1);
  el.track.fire('pointerdown', { pointerId: 3, clientY: 999 });
  assert.equal(input.throttle(), 0);
  el.track.fire('pointercancel', { pointerId: 3 });

  // Expert joystick: lifting a finger keeps the selected deflection; new
  // touch resumes from it. Do not convert this to auto-center in A or B.
  const t = { identifier: 10, clientX: 120, clientY: 120 };
  el.zone.fire('touchstart', { changedTouches: [t] });
  el.zone.fire('touchmove', { changedTouches: [{ ...t, clientX: 158 }] });
  const heldRoll = input.axes().x;
  assert.ok(heldRoll > 0.05, 'touch drag must command roll');
  el.zone.fire('touchend', { changedTouches: [t] });
  assert.equal(input.axes().x, heldRoll, 'release must preserve roll bias');
  input.resetStick();
  assert.equal(input.axes().x, 0, 'fresh sortie may explicitly neutralize the stick');

  // Controls consumed by the real player controller, not just UI decoration.
  input.setThrottle(0.35);
  const ac = createAircraft('F16V', 'blue', {x:0,y:2500,z:0}, {x:0,y:0,z:-1}, 250);
  const c = new PlayerController(ac, input, { assist:false, invert:false }).update();
  assert.equal(c.throttle, 0.35);
  assert.equal(c.boost, false);
  input.resetPower();
  assert.equal(input.throttle(), 0.72);
  assert.equal(input.boost(), false);
  assert.equal(input.brake(), false);
  assert.equal(el.value.textContent, '72%');
  assert.equal(el.boost.getAttribute('aria-pressed'), 'false');
} finally {
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
}
console.log('Mobile power strip: slider, AB, BRK, keyboard, reset PASS');
