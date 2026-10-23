#!/usr/bin/env node
// Spring-centred virtual stick. Releasing the finger returns the stick COMMAND
// to neutral; the aircraft keeps its attitude (Expert) or the Assisted flight
// control rolls it out. Power controls are independent of the stick.
// Headless: real Input event handlers on a fake DOM + the shared flight model.
import assert from 'node:assert/strict';
import { Input, PlayerController } from '../src/game/input.js';
import { createAircraft, stepAircraft, bankAngle } from '../src/sim/aircraft.js';
import { DEG } from '../src/sim/math.js';

function element(name) {
  const events = new Map(), classes = new Set();
  return {
    dataset: { btn: name }, style: {}, textContent: '',
    classList: {
      add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c),
      toggle: (c, yes) => { if (yes ?? !classes.has(c)) classes.add(c); else classes.delete(c); },
    },
    addEventListener: (type, fn) => events.set(type, fn),
    setAttribute() {}, getBoundingClientRect: () => ({ top: 100, height: 112 }), setPointerCapture() {},
    fire: (type, opts = {}) => events.get(type)({ preventDefault() {}, ...opts }),
  };
}
const el = Object.fromEntries(['zone', 'base', 'knob', 'track', 'handle', 'fill', 'value', 'boost', 'brake', 'gun', 'msl', 'flare', 'look'].map((n) => [n, element(n)]));
const lookup = {
  '#stickZone': el.zone, '#stickBase': el.base, '#stickKnob': el.knob, '#throttleTrack': el.track,
  '#throttleHandle': el.handle, '#throttleFill': el.fill, '#throttleValue': el.value,
  '[data-btn="boost"]': el.boost, '[data-btn="brake"]': el.brake,
};
const root = {
  querySelector: (s) => lookup[s] ?? null,
  querySelectorAll: (s) => s === '[data-btn]' ? [el.boost, el.brake, el.gun, el.msl, el.flare, el.look]
    : s === '[data-btn].down' ? [el.brake, el.gun].filter((b) => b.classList.contains('down')) : [],
};
const T = (id, x, y) => ({ identifier: id, clientX: x, clientY: y });
const touch = (type, changed, down) => el.zone.fire(type, { changedTouches: changed, touches: down });

const savedWindow = globalThis.window;
const winEvents = new Map();
globalThis.window = { addEventListener: (type, fn) => winEvents.set(type, fn) };
try {
  const inp = new Input(root);
  const R = 62, shape = (v) => { const a = Math.max(0, Math.abs(v) - 0.06) / 0.94; return Math.sign(v) * (0.35 * a + 0.65 * a * a); };

  // 1. drag, release -> command and knob back to neutral
  touch('touchstart', [T(1, 100, 200)], [T(1, 100, 200)]);
  touch('touchmove', [T(1, 140, 200)], [T(1, 140, 200)]);
  assert.ok(Math.abs(inp.stick.x - shape(40 / R)) < 1e-12, 'dead zone + expo curve unchanged');
  touch('touchend', [T(1, 140, 200)], []);
  assert.deepEqual([inp.stick.x, inp.stick.y], [0, 0], 'released stick returns to neutral');
  assert.equal(el.knob.style.transform, 'translate(0px, 0px)', 'knob springs back to centre');
  assert.equal(el.base.classList.contains('on'), false);

  // 2. the next touch starts at neutral, wherever it lands
  touch('touchstart', [T(2, 300, 250)], [T(2, 300, 250)]);
  assert.deepEqual([inp.stick.x, inp.stick.y], [0, 0], 'new touch does not inherit the old offset');
  touch('touchmove', [T(2, 320, 250)], [T(2, 320, 250)]);
  assert.ok(Math.abs(inp.stick.x - shape(20 / R)) < 1e-12, 'new drag is measured from the new anchor');

  // 3. multi-touch: a second finger in the zone is ignored and its release does not centre the stick
  touch('touchstart', [T(3, 120, 120)], [T(2, 320, 250), T(3, 120, 120)]);
  touch('touchmove', [T(3, 10, 10)], [T(2, 320, 250), T(3, 10, 10)]);
  assert.ok(Math.abs(inp.stick.x - shape(20 / R)) < 1e-12, 'second finger does not steer');
  touch('touchend', [T(3, 10, 10)], [T(2, 320, 250)]);
  assert.ok(inp.stick.x > 0, 'releasing the other finger keeps the stick finger in control');
  // a lost end event for the stick finger is caught by the next end/cancel in the zone
  touch('touchstart', [T(4, 50, 50)], [T(2, 320, 250), T(4, 50, 50)]);
  touch('touchend', [T(4, 50, 50)], []);
  assert.deepEqual([inp.stick.x, inp.stick.y], [0, 0], 'no ghost stick when its touch is gone');

  // 4. touchcancel (system gesture / incoming call) centres too
  touch('touchstart', [T(5, 100, 100)], [T(5, 100, 100)]);
  touch('touchmove', [T(5, 100, 150)], [T(5, 100, 150)]);
  assert.ok(inp.stick.y < 0);
  touch('touchcancel', [T(5, 100, 150)], []);
  assert.deepEqual([inp.stick.x, inp.stick.y], [0, 0], 'touchcancel centres the stick');

  // 5. power controls are independent of stick release
  el.track.fire('pointerdown', { pointerId: 9, clientY: 156 });
  el.track.fire('pointerup', { pointerId: 9 });
  const thr = inp.throttle();
  el.boost.fire('touchstart');
  touch('touchstart', [T(6, 100, 100)], [T(6, 100, 100)]);
  touch('touchmove', [T(6, 150, 100)], [T(6, 150, 100)]);
  el.brake.fire('touchstart');
  touch('touchend', [T(6, 150, 100)], []);
  assert.deepEqual([inp.throttle(), inp.boost(), inp.brake()], [thr, true, true],
    'stick release leaves throttle, AB toggle and a held BRK alone');
  el.brake.fire('touchend');
  assert.equal(inp.brake(), false, 'BRK is still momentary');

  // 6. app switch / focus loss: no ghost input, latched settings survive
  touch('touchstart', [T(7, 100, 100)], [T(7, 100, 100)]);
  touch('touchmove', [T(7, 150, 100)], [T(7, 150, 100)]);
  el.brake.fire('touchstart'); el.gun.fire('touchstart');
  winEvents.get('blur')();
  assert.deepEqual([inp.stick.x, inp.stick.y, inp.brake(), inp.gun()], [0, 0, false, false], 'blur releases stick, BRK and GUN');
  assert.deepEqual([inp.throttle(), inp.boost()], [thr, true], 'blur keeps throttle and AB');
  touch('touchmove', [T(7, 190, 100)], [T(7, 190, 100)]);
  assert.equal(inp.stick.x, 0, 'a stale finger after blur does not steer');
  touch('touchstart', [T(8, 100, 100)], [T(8, 100, 100)]);
  touch('touchmove', [T(8, 130, 100)], [T(8, 130, 100)]);
  assert.ok(inp.stick.x > 0, 'a fresh touch after blur works');
  winEvents.get('pagehide')();
  assert.equal(inp.stick.x, 0, 'pagehide releases the stick');
} finally {
  if (savedWindow === undefined) delete globalThis.window; else globalThis.window = savedWindow;
}

// Flight dynamics: roll to ~60 deg with ~55% stick, release, watch 2 s.
const dt = 1 / 60, rows = [];
for (const flight of ['arcade', 'tactical']) {
  for (const control of ['expert', 'assisted']) {
    const a = createAircraft('F16V', 'blue', { x: 0, y: 3200, z: 0 }, { x: 0, y: 0, z: -1 }, 230);
    a.flightFeel = flight; a.controls.throttle = 0.72;
    const stick = { x: 0, y: 0 };
    const inp = { axes: () => ({ ...stick, yaw: 0 }), throttle: () => 0.72, boost: () => false, brake: () => false, gun: () => false, consume: () => false };
    const pc = new PlayerController(a, inp, { invert: false, assist: control === 'assisted' });
    const fly = (sec) => { for (let i = 0; i < Math.round(sec / dt); i++) { Object.assign(a.controls, pc.update()); stepAircraft(a, dt); } };
    stick.x = 0.55;
    let n = 0;
    while (bankAngle(a) / DEG < 60 && n++ < 600) fly(dt);
    assert.ok(n < 600, `${flight}:${control}: reaches 60 deg bank`);
    const b0 = bankAngle(a) / DEG;
    stick.x = 0; // finger lifted: neutral command
    fly(0.5);
    const rate05 = Math.abs(a.rollRateCur) / DEG, b05 = bankAngle(a) / DEG;
    fly(1.5);
    const b2 = bankAngle(a) / DEG, c = pc.update();
    rows.push({ mode: `${flight}:${control}`, bankAtRelease: +b0.toFixed(1), bank05: +b05.toFixed(1), rollRate05: +rate05.toFixed(1), bank2s: +b2.toFixed(1) });
    if (control === 'expert') {
      assert.equal(c.roll, 0, 'Expert: neutral stick commands no roll');
      assert.ok(Math.abs(c.pitch) < 1e-9, 'Expert: neutral stick is a neutral pitch command');
      assert.ok(rate05 < 10, `${flight}: Expert roll rate settles after release (${rate05.toFixed(1)} deg/s)`);
      assert.ok(Math.abs(b05 - b0) < 15 && Math.abs(b2 - b0) < 20, `${flight}: Expert keeps the bank (${b0.toFixed(0)} -> ${b2.toFixed(0)})`);
    } else {
      assert.ok(Math.abs(b2) < 12, `${flight}: Assisted rolls wings level after release (${b2.toFixed(0)} deg)`);
    }
  }
}
console.table(rows);
console.log('Stick recenter PASS: release centres the command and knob; Expert keeps bank, Assisted rolls out; power and focus loss handled');
