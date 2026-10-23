#!/usr/bin/env node
// Mobile power strip: latched throttle, independent AB & BRK, and two-finger control.
import assert from 'node:assert/strict';
import { Input, PlayerController } from '../src/game/input.js';
import { createAircraft, stepAircraft, bankAngle, pitchAngle } from '../src/sim/aircraft.js';
import { DEG } from '../src/sim/math.js';

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
      events.get(type)({ type, preventDefault() { prevented = true; }, ...opts });
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
const originalDocument = globalThis.document;
try {
  globalThis.window = element('window');
  globalThis.document = element('document');
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
  el.boost.fire('touchend');
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

  // Every release centres the command/knob; retouch establishes a fresh anchor.
  const t = { identifier: 10, clientX: 120, clientY: 120 };
  el.zone.fire('touchstart', { changedTouches: [t] });
  el.zone.fire('touchmove', { changedTouches: [{ ...t, clientX: 158 }] });
  const heldRoll = input.axes().x;
  assert.ok(heldRoll > 0.05, 'touch drag must command roll');
  el.zone.fire('touchend', { changedTouches: [t] });
  assert.equal(input.axes().x, 0, 'release must centre roll command');
  assert.equal(el.knob.style.transform, 'translate(0px, 0px)');
  el.zone.fire('touchstart', { changedTouches: [{ ...t, identifier: 11, clientX: 180 }] });
  assert.deepEqual(input.stick, { x: 0, y: 0 }, 'retouch starts neutral');
  el.zone.fire('touchmove', { changedTouches: [{ ...t, identifier: 11, clientX: 220 }] });
  assert.ok(input.axes().x > 0);
  el.zone.fire('touchcancel', { changedTouches: [{ ...t, identifier: 11 }] });
  assert.deepEqual(input.stick, { x: 0, y: 0 });
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

  // An unrelated finger ending must not release the stick or another BRK owner.
  const finger = (id, x = 120, y = 120) => ({ identifier: id, clientX: x, clientY: y });
  const touch = (node, type, ...points) => node.fire(type, { changedTouches: points });
  touch(el.zone, 'touchstart', finger(21));
  touch(el.zone, 'touchmove', finger(21, 160));
  touch(el.zone, 'touchend', finger(22));
  assert.ok(input.axes().x > 0, 'other finger cannot release stick');
  touch(el.brake, 'touchstart', finger(22));
  touch(el.brake, 'touchstart', finger(23));
  touch(el.brake, 'touchend', finger(22));
  assert.equal(input.brake(), true, 'second finger still holds BRK');
  touch(el.brake, 'touchcancel', finger(23));
  assert.equal(input.brake(), false);
  input.setThrottle(0.43);
  touch(el.boost, 'touchstart', finger(24)); touch(el.boost, 'touchend', finger(24));
  touch(el.brake, 'touchstart', finger(25));
  touch(el.gun, 'touchstart', finger(26));
  input.keys.add('ArrowLeft'); input.pressed.add('msl');
  window.fire('blur');
  assert.deepEqual(input.axes(), { x: 0, y: 0, yaw: 0 });
  assert.equal(input.brake(), false); assert.equal(input.gun(), false);
  assert.equal(input.consume('msl'), false);
  assert.equal(input.throttle(), 0.43); assert.equal(input.boost(), true);
  touch(el.zone, 'touchmove', finger(21, 180));
  assert.equal(input.axes().x, 0, 'stale touch cannot resurrect input after blur');
  for (const event of ['pagehide', 'visibilitychange']) {
    touch(el.zone, 'touchstart', finger(30)); touch(el.zone, 'touchmove', finger(30, 160));
    document.hidden = true;
    (event === 'pagehide' ? window : document).fire(event);
    assert.equal(input.axes().x, 0, event);
    assert.equal(input.boost(), true, 'latching AB survives transient cleanup');
  }

  for (const flight of ['arcade', 'tactical']) for (const assist of [false, true]) {
    input.releaseHeld(); input.resetPower();
    const ac = createAircraft('F16V', 'blue', { x: 0, y: 3500, z: 0 }, { x: 0, y: 0, z: -1 }, 230);
    ac.flightFeel = flight;
    const controller = new PlayerController(ac, input, { assist, invert: false });
    const step = () => { Object.assign(ac.controls, controller.update()); stepAircraft(ac, 1/60); };
    touch(el.zone, 'touchstart', finger(40)); touch(el.zone, 'touchmove', finger(40, 182));
    let steps = 0;
    while (Math.abs(bankAngle(ac)/DEG) < 58 && steps++ < 120) step();
    const releaseBank = bankAngle(ac)/DEG, releaseRate = Math.abs(ac.rollRateCur);
    assert.ok(releaseBank >= 58 && releaseBank < 67, 'actually roll to approximately 60 degrees');
    touch(el.zone, 'touchend', finger(40));
    const pitch0 = pitchAngle(ac)/DEG;
    for (let i=0; i<90; i++) step();
    assert.deepEqual(input.stick, { x: 0, y: 0 });
    if (assist) assert.ok(Math.abs(bankAngle(ac)/DEG) < 15, `${flight}: assisted rolls out`);
    else {
      assert.equal(ac.controls.roll, 0); assert.equal(Math.abs(ac.controls.pitch), 0);
      assert.ok(Math.abs(ac.rollRateCur) < releaseRate*0.05, `${flight}: roll rate converges`);
      assert.ok(Math.abs(bankAngle(ac)/DEG-releaseBank) < 10, `${flight}: expert retains bank`);
      assert.ok(Math.abs(pitchAngle(ac)/DEG-pitch0) > 0.2, 'neutral pitch does not lock current attitude');
    }
    assert.equal(ac.controls.boost, false); assert.equal(ac.controls.throttle, 0.72);
  }
} finally {
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
  if (originalDocument === undefined) delete globalThis.document;
  else globalThis.document = originalDocument;
}
console.log('Touch lifecycle + four-mode ~60° release dynamics + independent power PASS');
