#!/usr/bin/env node
// Fixed flight attitudes must produce an accurate readable horizon at every
// camera angle. HUD tests render to a mock Canvas2D (no GPU/browser required).
import assert from 'node:assert/strict';
import { DEG, UP, qLook, qMul, qAxisAngle } from '../src/sim/math.js';
import { attitudeOf } from '../src/game/attitude.js';
import { Hud } from '../src/game/hud.js';

const approx = (a, b, tol = 0.15) =>
  assert.ok(Math.abs(a - b) < tol, `wanted ${b}, got ${a}`);
const nose = (pitchDeg, headingDeg = 0) => {
  const p = pitchDeg * DEG, hd = headingDeg * DEG;
  return { x: Math.cos(p) * Math.sin(hd), y: Math.sin(p),
    z: -Math.cos(p) * Math.cos(hd) };
};
const orient = (pitchDeg, bankDeg = 0, headingDeg = 0) => {
  const q = qLook(nose(pitchDeg, headingDeg), UP);
  return qMul(q, qAxisAngle({ x: 0, y: 0, z: -1 }, bankDeg * DEG));
};
for (const [p, b, h] of [
  [0, 0, 0], [30, 0, 0], [-30, 0, 0], [0, 45, 0],
  [0, -70, 0], [0, 90, 0], [0, 180, 0],
  [40, 45, 90], [-50, -45, 270], [0, 0, 90], [0, 0, 270],
]) {
  const a = attitudeOf(orient(p, b, h));
  approx(a.pitch, p);
  // ±180 is the same inverted bank and can be returned as either sign.
  if (Math.abs(b) === 180) approx(Math.abs(a.bank), 180);
  else approx(a.bank, b);
  approx(a.heading, h === 0 ? 0 : h);
}

// Fake Canvas2D checks that the square stays clipped, the horizon follows
// true attitude, and the code doesn't depend on the chase camera or renderer.
const calls = [];
const ctx = { textAlign: 'center' };
for (const op of ['save','restore','beginPath','rect','clip','translate',
  'rotate','moveTo','lineTo','stroke','strokeRect','fill','closePath','fillText']) {
  ctx[op] = (...args) => {
    if (args.some((v) => typeof v === 'number' && !Number.isFinite(v)))
      throw new Error(`nonfinite ${op}`);
    calls.push({ op, args });
  };
}
globalThis.window = { devicePixelRatio: 2, innerWidth: 812, innerHeight: 375,
  addEventListener: () => {} };
const canvas = { getContext: () => ctx, style: {} };
const hud = new Hud(canvas);
for (const [p, b, h] of [[0,0,0],[25,40,90],[-30,-70,270],[80,180,0]]) {
  calls.length = 0;
  hud.attitude({ q: orient(p,b,h) }, 375 / 400);
  assert.equal(calls.filter((x) => x.op === 'strokeRect').length, 0,
    'AC-style open corner guides must never draw a full HUD square');
  assert.equal(calls.filter((x) => x.op === 'clip').length, 1,
    'pitch ticks must not spill across speed and altitude boxes');
  assert.ok(calls.some((x) => x.op === 'fillText' &&
    /^\\d{3}$/.test(String(x.args[0]))), 'moving three-digit compass ticks');
  assert.ok(!calls.some((x) => x.op === 'fillText' &&
    /^(HDG|PITCH|BANK) /.test(String(x.args[0]))), 'no large instrument labels');
  const rotation = calls.find((x) => x.op === 'rotate');
  approx(rotation.args[0], -attitudeOf(orient(p,b,h)).bank * DEG, 0.01);
  assert.equal(calls.filter((x) => x.op === 'save').length,
    calls.filter((x) => x.op === 'restore').length, 'restore drawing context');
}

console.log('HUD PASS: AC-style open guides, pitch/roll horizon, compass, inverted flight, clip and no boxed dashboard');
