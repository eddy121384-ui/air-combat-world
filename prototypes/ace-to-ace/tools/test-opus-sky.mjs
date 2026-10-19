// Node checks for the Opus Sky cloudscape and lab routes (no browser).
//   node tools/test-opus-sky.mjs
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createCloudscape, PUFF_STRIDE, SUN_DIRECTION } from '../src/sky/cloudscape.js';
import { buildRoutes } from './sky-routes.js';

const t0 = performance.now();
const a = createCloudscape({ seed: 1801 });
const buildMs = performance.now() - t0;
const b = createCloudscape({ seed: 1801 });
const hash = s => createHash('sha256').update(Buffer.from(s.data.buffer)).digest('hex');

// Deterministic, seed-sensitive, finite.
assert.equal(hash(a), hash(b), 'same seed → identical puffs');
assert.notEqual(hash(a), hash(createCloudscape({ seed: 1802 })), 'different seed → different puffs');
assert.ok(a.data.every(Number.isFinite), 'all packed values finite');
assert.equal(a.data.length, a.count * PUFF_STRIDE);

// Budget and shape grammar.
assert.ok(a.count > 8000 && a.count < 26000, `puff budget ${a.count}`);
const kinds = a.clouds.reduce((m, c) => (m[c.kind] = (m[c.kind] ?? 0) + 1, m), {});
assert.equal(kinds.tower, 4); assert.ok(kinds.medium >= 10 && kinds.small >= 20 && kinds.deck >= 200, JSON.stringify(kinds));
for (let i = 0; i < a.count; i++) {
  const o = i * PUFF_STRIDE, y = a.data[o + 1], r = a.data[o + 3], base = a.data[o + 12], sq = a.data[o + 13], level = Math.floor(a.data[o + 15]);
  assert.ok(r > 0 && sq > 0.2 && sq <= 1, `puff ${i} radius/squash`);
  assert.ok(level >= 0 && level <= 3);
  assert.ok(y + r * sq > base, `puff ${i} has visible volume above its flat base`);
}

// The density field agrees with the geometry: inside a core → 1, open air → 0, below base → 0.
const o0 = 0;
assert.equal(a.density(a.data[o0], a.data[o0 + 1], a.data[o0 + 2]), 1);
assert.equal(a.density(0, 9000, 0), 0, 'nothing at 9 km');
const deck = a.clouds.find(c => c.kind === 'deck');
assert.equal(a.density(deck.x, deck.base - 120, deck.z), 0, 'flat cloud-sea base: clear air underneath');
const g = a.gradient(a.data[o0] + a.data[o0 + 3] * 1.05, a.data[o0 + 1], a.data[o0 + 2]);
assert.ok(Math.abs(Math.hypot(...g) - 1) < 1e-6, 'gradient is a unit vector');

// Hero sun corridor: the hero tower's lit face is not in another cloud's cast shadow.
const hero = a.clouds[0];
let blocked = 0;
for (let k = 0; k < 24; k++) {
  const along = 1200 + k * 500, y = hero.base + 900 + (k % 4) * 300;
  const x = hero.x + SUN_DIRECTION[0] / Math.hypot(SUN_DIRECTION[0], SUN_DIRECTION[2]) * along;
  const z = hero.z + SUN_DIRECTION[2] / Math.hypot(SUN_DIRECTION[0], SUN_DIRECTION[2]) * along;
  if (a.density(x, y + along * SUN_DIRECTION[1] / Math.hypot(SUN_DIRECTION[0], SUN_DIRECTION[2]), z) > 0.5) blocked++;
}
assert.ok(blocked <= 2, `hero sun corridor mostly clear (${blocked}/24 samples in cloud)`);

// Shadow raster: deterministic and partially covering.
const sa = a.shadowRaster(128), sb = b.shadowRaster(128);
assert.deepEqual(sa.data, sb.data);
const cover = sa.data.reduce((s, v) => s + v, 0) / (255 * sa.data.length);
assert.ok(cover > 0.15 && cover < 0.85, `sea shadow coverage ${cover.toFixed(2)}`);

// Lift moves everything by exactly the offset.
const lifted = createCloudscape({ seed: 1801, lift: 900 });
assert.equal(lifted.count, a.count);
assert.ok(Math.abs(lifted.data[1] - a.data[1] - 900) < 1e-3 && Math.abs(lifted.data[12] - a.data[12] - 900) < 1e-3);

// Routes: finite, continuous, and they really cross cloud where they claim to.
const routes = buildRoutes(a);
for (const [name, r] of Object.entries(routes)) {
  let prev = null, maxStep = 0;
  for (let i = 0; i <= 200; i++) {
    const s = r.shot(r.duration * i / 200);
    for (const v of [...s.camera, ...s.target, ...s.up, ...s.plane.position]) assert.ok(Number.isFinite(v), `${name} finite`);
    if (prev) maxStep = Math.max(maxStep, Math.hypot(...s.camera.map((v, k) => v - prev[k])));
    prev = s.camera;
  }
  const limit = name === 'orbit180' ? 5000 * Math.PI / 200 * 1.2 : 255 * r.duration / 200 * 1.6;
  assert.ok(maxStep < limit, `${name} camera continuous (max step ${maxStep.toFixed(1)} m)`);
}
const insideAt = (name, f) => { const s = routes[name].shot(routes[name].duration * f); return a.density(...s.camera); };
assert.ok(insideAt('traverse', 0.5) > 0.3 && insideAt('traverse', 0) === 0 && insideAt('traverse', 1) === 0, 'traverse goes in and out');
const deckRun = Array.from({ length: 101 }, (_, i) => insideAt('deck', i / 100));
assert.ok(deckRun.filter(d => d > 0.3).length >= 4 && deckRun[0] === 0 && deckRun[100] === 0, 'deck route crosses the cloud sea');

console.log(JSON.stringify({ passed: true, puffs: a.count, levels: a.levels, buried: a.stats.buried, kinds, buildMs: +buildMs.toFixed(0), seaShadowCover: +cover.toFixed(3) }));
