// Renderer-independent CloudField B0. Metres, Y up, seconds; density is dimensionless.
// Kinematic geometry, NOT a weather or liquid-water-content simulation.
const clamp = x => Math.max(0, Math.min(1, x));
const smooth = x => { x = clamp(x); return x * x * (3 - 2 * x); };
const fade = x => x * x * x * (x * (x * 6 - 15) + 10);
const mix = (a, b, t) => a + (b - a) * t;
function hash(x, y, z, seed) {
  let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(z, 2147483647) ^ seed;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
function noise(x, y, z, seed) {
  const ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z);
  const u = fade(x - ix), v = fade(y - iy), w = fade(z - iz);
  const row = (dy, dz) => mix(hash(ix, iy + dy, iz + dz, seed), hash(ix + 1, iy + dy, iz + dz, seed), u);
  return mix(mix(row(0, 0), row(1, 0), v), mix(row(0, 1), row(1, 1), v), w);
}

export const CLOUD_PRESETS = Object.freeze({
  cumulus: Object.freeze({ base: 2450, top: 3650, width: 6000, depth: 5000, cellSize: 1700, density: 0.9 }),
  // Deliberately raised to intersect the game's combat band; not a typical Sc altitude.
  stratocumulus: Object.freeze({ base: 2650, top: 3350, width: 6000, depth: 5000, cellSize: 2300, density: 0.82 }),
});

/** Construct once; change parameters by making a new field. No Three.js dependency. */
export function createCloudField(options = {}) {
  const kind = options.kind ?? 'cumulus';
  if (!CLOUD_PRESETS[kind]) throw new RangeError('kind must be cumulus or stratocumulus');
  const p = { ...CLOUD_PRESETS[kind], seed: 73, wind: { x: 8, z: 3 }, ...options, kind };
  for (const key of ['base', 'top', 'width', 'depth', 'cellSize', 'density', 'seed']) {
    if (!Number.isFinite(p[key])) throw new RangeError(`${key} must be finite`);
  }
  if (p.top <= p.base || p.width <= 0 || p.depth <= 0 || p.cellSize <= 0 || p.density < 0 || p.density > 1)
    throw new RangeError('invalid cloud dimensions/density');
  if (!Number.isInteger(p.seed) || !Number.isFinite(p.wind?.x) || !Number.isFinite(p.wind?.z))
    throw new RangeError('seed must be an integer; wind x/z must be finite');
  p.wind = Object.freeze({ x: p.wind.x, z: p.wind.z });
  Object.freeze(p);
  const height = p.top - p.base, lobes = [];
  // Nine bounded clusters. The middle cluster is a reproducible traversal target.
  for (let iz = -1; iz <= 1; iz++) for (let ix = -1; ix <= 1; ix++) {
    const rnd = n => hash(ix, n, iz, p.seed);
    const cx = ix * p.width * 0.31 + (ix || iz ? (rnd(1) - 0.5) * 360 : 0);
    const cz = iz * p.depth * 0.30 + (ix || iz ? (rnd(2) - 0.5) * 360 : 0);
    const radius = p.cellSize * (0.46 + rnd(3) * 0.12);
    for (let j = 0; j < 3; j++) {
      const angle = j * Math.PI * 2 / 3 + rnd(4) * 2;
      lobes.push(Object.freeze({
        x: cx + Math.cos(angle) * radius * 0.25,
        y: p.base + height * (0.40 + rnd(5 + j) * 0.12),
        z: cz + Math.sin(angle) * radius * 0.25,
        rx: radius * (j ? 0.72 : 1), ry: height * (0.45 + rnd(8 + j) * 0.15),
        rz: radius * (kind === 'stratocumulus' ? 1.12 : 0.82),
      }));
    }
  }
  Object.freeze(lobes);
  const bounds = Object.freeze({ min: Object.freeze({ x: -p.width / 2, y: p.base, z: -p.depth / 2 }),
    max: Object.freeze({ x: p.width / 2, y: p.top, z: p.depth / 2 }) });

  function sampleDensity(x, y, z, time = 0) {
    x -= p.wind.x * time; z -= p.wind.z * time;
    const edgeX = (p.width / 2 - Math.abs(x)) / 180;
    const edgeZ = (p.depth / 2 - Math.abs(z)) / 180;
    if (y <= p.base || y >= p.top || edgeX <= 0 || edgeZ <= 0) return 0;
    let empty = 1;
    for (const l of lobes) {
      const dx = (x - l.x) / l.rx, dy = (y - l.y) / l.ry, dz = (z - l.z) / l.rz;
      const q = dx * dx + dy * dy + dz * dz;
      if (q < 1) empty *= 1 - smooth((1 - Math.sqrt(q)) / 0.40);
    }
    if (empty === 1) return 0;
    // Continuous erosion, never binary occupancy or per-frame random changes.
    const detail = 0.70 + 0.22 * noise(x / 260, y / 220, z / 260, p.seed)
      + 0.08 * noise(x / 85, y / 85, z / 85, p.seed + 1);
    return clamp((1 - empty) * p.density * detail * smooth((y - p.base) / 85)
      * smooth((p.top - y) / 130) * smooth(edgeX) * smooth(edgeZ));
  }

  /** Midpoint integral. T = exp(-extinction * integral(rho ds)); diagnostic only. */
  function integrateSightline(a, b, { time = 0, step = 25, extinction = 0.012 } = {}) {
    if (!(step > 0) || !Number.isFinite(step) || extinction < 0 || !Number.isFinite(extinction))
      throw new RangeError('invalid sightline step/extinction');
    const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
    const distance = Math.hypot(dx, dy, dz), samples = Math.max(1, Math.ceil(distance / step));
    let columnDensity = 0;
    for (let i = 0; i < samples; i++) {
      const t = (i + 0.5) / samples;
      columnDensity += sampleDensity(a.x + dx * t, a.y + dy * t, a.z + dz * t, time);
    }
    columnDensity *= distance / samples;
    const opticalDepth = columnDensity * extinction;
    return { distance, samples, columnDensity, opticalDepth, transmittance: Math.exp(-opticalDepth) };
  }
  return Object.freeze({ params: p, bounds, lobes, sampleDensity, integrateSightline });
}
