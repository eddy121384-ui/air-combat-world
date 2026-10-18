import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';
import { cpus } from 'node:os';
import { mkdir, writeFile } from 'node:fs/promises';
import { createCloudField } from '../src/cloud/cloud-field.js';

const reports = [];
const near = (a, b, epsilon = 1e-9) => assert.ok(Math.abs(a - b) < epsilon, `${a} != ${b}`);
for (const kind of ['cumulus', 'stratocumulus']) {
  const field = createCloudField({ kind }), same = createCloudField({ kind }), other = createCloudField({ kind, seed: 74 });
  const { base, top, width, depth, wind } = field.params, mid = (base + top) / 2;
  assert.deepEqual(field.lobes, same.lobes);
  assert.notDeepEqual(field.lobes, other.lobes);
  assert.ok(field.sampleDensity(0, mid, 0) > 0.5, 'central traversal crosses substantial density');
  for (const y of [0, base - 1, base, top, top + 1, 10000]) assert.equal(field.sampleDensity(0, y, 0), 0);
  assert.equal(field.sampleDensity(width, mid, 0), 0);
  assert.equal(field.sampleDensity(0, mid, depth), 0);
  const maxDelta = { x: 0, y: 0, z: 0 };
  let different = 0;
  for (let i = 0; i < 5000; i++) {
    const x = (i * 83 % 8000) - 4000, y = base - 300 + i * 17 % (top - base + 600), z = (i * 127 % 6500) - 3250;
    const d = field.sampleDensity(x, y, z);
    assert.ok(Number.isFinite(d) && d >= 0 && d <= 1);
    assert.equal(d, same.sampleDensity(x, y, z));
    if (d !== other.sampleDensity(x, y, z)) different++;
    near(d, field.sampleDensity(x + wind.x * 90, y, z + wind.z * 90, 90));
    for (const axis of ['x', 'y', 'z']) {
      const p = { x, y, z }; p[axis] += 0.5;
      const delta = Math.abs(d - field.sampleDensity(p.x, p.y, p.z));
      maxDelta[axis] = Math.max(maxDelta[axis], delta);
      assert.ok(delta < 0.02, `continuous along ${axis}, 0.5 m step`);
    }
    // Continuous time at a stationary observer, not just a cloud-following path.
    assert.ok(Math.abs(field.sampleDensity(x, y, z, 60) - field.sampleDensity(x, y, z, 60 + 1 / 60)) < 0.02);
  }
  assert.ok(different > 500, 'seed has spatial effect');
  let previous = 0, maxFrameDelta = 0, maximum = 0;
  const outside = depth / 2 + 1100;
  for (let z = outside; z >= -outside; z -= 220 / 60) {
    const d = field.sampleDensity(0, mid, z);
    maximum = Math.max(maximum, d); maxFrameDelta = Math.max(maxFrameDelta, Math.abs(d - previous)); previous = d;
  }
  assert.ok(maximum > 0.5 && maxFrameDelta < 0.08 && previous === 0, '220 m/s entry/exit is smooth at 60 Hz');
  const a = { x: 0, y: mid, z: 2100 }, b = { x: 0, y: mid, z: -2100 };
  const sight = field.integrateSightline(a, b, { step: 20 });
  near(sight.columnDensity, field.integrateSightline(b, a, { step: 20 }).columnDensity, 1e-7);
  const fine = field.integrateSightline(a, b, { step: 10 });
  assert.ok(Math.abs(fine.columnDensity - sight.columnDensity) / fine.columnDensity < 0.01, 'integral convergence');
  assert.ok(sight.transmittance < 0.02, 'cloud blocks long sightline');
  near(field.integrateSightline({ ...a, y: top + 200 }, { ...b, y: top + 200 }).transmittance, 1);
  near(field.integrateSightline(a, a).transmittance, 1);
  // Optical depth and visibility recover continuously along flight, with no threshold fog toggle.
  const T = z => field.integrateSightline({ x: 0, y: mid, z }, { x: 0, y: mid, z: z - 500 }).transmittance;
  assert.ok(T(outside) > 0.99 && T(0) < 0.1 && T(-outside) > 0.99);
  let priorT = T(outside), maxTDelta = 0;
  for (let z = outside; z > -outside; z -= 220 / 60) {
    const t = T(z); maxTDelta = Math.max(maxTDelta, Math.abs(priorT - t)); priorT = t;
  }
  assert.ok(maxTDelta < 0.1, 'no visibility flash at boundary');
  reports.push({ kind, deterministicProbes: 5000, maxDensityDeltaHalfMetre: maxDelta, maxFrameDelta,
    maxTransmittanceDeltaFrame: maxTDelta, sightline: sight });
}
for (const options of [{ top: 2000 }, { density: 2 }, { seed: 1.2 }, { wind: { x: NaN, z: 0 } }, { kind: 'storm' }])
  assert.throws(() => createCloudField(options), RangeError);
assert.equal(createCloudField({ density: 0 }).sampleDensity(0, 3000, 0), 0);
const low = createCloudField({ base: 900, top: 1700, wind: { x: -12, z: 4 } });
assert.ok(low.sampleDensity(0, 1300, 0) > 0.5, 'parameters move actual field, not only display');
assert.throws(() => low.integrateSightline({ x: 0, y: 0, z: 0 }, { x: 0, y: 0, z: 0 }, { step: 0 }), RangeError);

// Separate CPU query benchmark. No browser / GPU / FPS involved. Warmed deterministic inputs.
const field = createCloudField(), count = 100000;
const points = {
  mixed: i => [(i * 83 % 7000) - 3500, 2200 + i * 17 % 1700, (i * 127 % 6000) - 3000],
  interior: i => [(i * 17 % 700) - 350, 2800 + i % 350, (i * 23 % 700) - 350],
};
const cpu = { node: process.version, platform: process.platform, cpu: cpus()[0]?.model, count, units: 'microseconds/query', workloads: {} };
let checksum = 0;
for (const [name, point] of Object.entries(points)) {
  for (let i = 0; i < 10000; i++) checksum += field.sampleDensity(...point(i));
  const rounds = [];
  for (let round = 0; round < 5; round++) {
    const start = performance.now();
    for (let i = 0; i < count; i++) checksum += field.sampleDensity(...point(i));
    rounds.push((performance.now() - start) * 1000 / count);
  }
  cpu.workloads[name] = rounds.sort((a, b) => a - b);
}
const out = new URL('../docs/cloud-engine-b0/', import.meta.url);
await mkdir(out, { recursive: true });
await writeFile(new URL('field-validation.json', out), JSON.stringify({ passed: true, reports, cpu, checksum }, null, 2) + '\n');
console.log(JSON.stringify({ passed: true, reports, cpu }, null, 2));
