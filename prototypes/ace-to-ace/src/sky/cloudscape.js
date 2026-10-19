// Opus Sky — art-directed cloudscape. Pure JS (no three.js), metres, Y up, sea at y=0.
//
// A cloud here is a fractal stack of SPHERES ("puffs"): big turret cores, medium
// billows on their surface, small cauliflower crowns on those. A sphere looks the same
// from every direction, so drawing it on a camera-facing quad is exact — the view
// consistency that B1's painted billboards lacked comes for free. The anime look does
// not come from texture; it comes from the shape grammar here (flat bases, crowns,
// fractal silhouettes) and from value design in the shader (turret/cloud mass normals).
//
// The same puffs answer density queries, so in-cloud fog, vapour streaks, sea shadows
// and any future gameplay occlusion agree with what is drawn.

export const SUN_DIRECTION = normalize3([-0.64, 0.30, -0.69]);
export const PUFF_STRIDE = 16;
// Float layout per puff (matches sky-shaders.js):
//  0-3  centre xyz, radius
//  4-7  turret mass centre xyz, turret aspect (vertical/horizontal radius)
//  8-11 cloud mass centre xyz, cloud aspect
//  12   flat base y, 13 squash (vertical/horizontal radius), 14 reserved, 15 level + seed fraction
// Billows are axis-aligned ellipsoids: radius r horizontally, r*squash vertically.

export const OPUS_LAYOUT = Object.freeze({
  extent: 24000,
  minExposure: 0.09,
  deck: Object.freeze({ base: 820, spacing: 640, minThickness: 200, maxThickness: 470, threshold: 0.555, scale: 6400 }),
  // Hand-placed landmark towers: the composition anchors a flight lab needs.
  towers: Object.freeze([
    Object.freeze({ x: 1200, z: -4200, base: 960, height: 3500, width: 3000, turrets: 4 }),
    Object.freeze({ x: -6200, z: 2600, base: 960, height: 2500, width: 2500, turrets: 3 }),
    Object.freeze({ x: 6800, z: 5200, base: 960, height: 2900, width: 2600, turrets: 3 }),
    Object.freeze({ x: 8200, z: -7400, base: 960, height: 3100, width: 2800, turrets: 4 }),
  ]),
  medium: Object.freeze({ count: 15, base: [1250, 1500], height: [650, 1350], width: [950, 1700], gap: 2400 }),
  small: Object.freeze({ count: 36, base: [1550, 2150], height: [190, 420], width: [260, 620], gap: 900 }),
});

// Billows per parent at level 1/2/3: towers get a fractal crown, the cloud sea stays economical.
const BILLOWS = Object.freeze({ tower: [12, 4, 2], medium: [9, 3, 2], small: [4, 3], deck: [4, 3] });

/** lift raises the whole cloudscape (metres), e.g. to sit the cloud band around the game's combat altitudes. */
export function createCloudscape({ seed = 1801, layout = OPUS_LAYOUT, sun = SUN_DIRECTION, lift = 0 } = {}) {
  if (!Number.isInteger(seed)) throw new RangeError('seed must be an integer');
  if (!Number.isFinite(lift)) throw new RangeError('lift must be finite');
  // Layout and shapes use separate streams: reshaping one cloud never reshuffles the composition.
  const layoutRng = mulberry32(seed);
  let rng = layoutRng;
  const half = layout.extent / 2;
  const puffs = [];        // working objects, packed at the end
  const clouds = [];       // {kind, x, z, base, top, rh, rv}
  const sunDir = normalize3(sun);
  const stats = { buried: 0 };

  // ---- towers (hand placed) then medium/small cumulus (seeded Poisson-ish placement)
  const occupied = [];
  for (const t of layout.towers) {
    addCumulus({ ...t, kind: 'tower' });
    occupied.push({ x: t.x, z: t.z, r: t.width * 0.75 });
  }
  // Keep the hero tower's sunlit face clear: no cumulus in the 14 km toward the low sun.
  const hero = layout.towers[0], sunH = normalize3([sunDir[0], 0, sunDir[2]]);
  const inSunCorridor = (x, z, width) => {
    const dx = x - hero.x, dz = z - hero.z, along = dx * sunH[0] + dz * sunH[2];
    const lateral = Math.abs(dx * sunH[2] - dz * sunH[0]);
    if (along > 0 && along < 14000 && lateral < hero.width * 0.7 + width * 0.6) return true;
    // Composition valley: the hero's three-quarter-lit face stays open toward the viewer.
    const va = rotY(sunH, 65), vx = -(dx * va[0] + dz * va[2]), vl = Math.abs(dx * va[2] - dz * va[0]);
    return vx > 0 && vx < 7500 && vl < 900 + width * 0.6;
  };
  const place = (spec, kind) => {
    let made = 0;
    for (let tries = 0; made < spec.count && tries < spec.count * 60; tries++) {
      const x = (layoutRng() * 2 - 1) * half * 0.86, z = (layoutRng() * 2 - 1) * half * 0.86;
      const width = lerp(spec.width[0], spec.width[1], layoutRng());
      if (occupied.some(o => Math.hypot(o.x - x, o.z - z) < o.r + width * 0.5 + spec.gap * 0.5)) continue;
      if (inSunCorridor(x, z, width)) continue;
      const base = lerp(spec.base[0], spec.base[1], layoutRng());
      const height = lerp(spec.height[0], spec.height[1], layoutRng());
      addCumulus({ x, z, base, height, width, turrets: kind === 'small' ? 1 : 1 + Math.floor(layoutRng() * 2.6), kind });
      occupied.push({ x, z, r: width * 0.6 });
      made++;
    }
  };
  place(layout.medium, 'medium');
  place(layout.small, 'small');

  // ---- cloud sea: dome clusters on a jittered grid where a low-frequency coverage field allows
  const deck = layout.deck;
  const cells = Math.floor(layout.extent / deck.spacing);
  const noiseSeed = seed * 7 + 3;
  for (let iz = 0; iz < cells; iz++) for (let ix = 0; ix < cells; ix++) {
    const x = -half + (ix + 0.5 + (layoutRng() - 0.5) * 0.7) * deck.spacing;
    const z = -half + (iz + 0.5 + (layoutRng() - 0.5) * 0.7) * deck.spacing;
    const cover = fbm2(x / deck.scale, z / deck.scale, noiseSeed);
    const jitter = layoutRng();
    if (cover < deck.threshold) continue;
    const k = smooth01((cover - deck.threshold) / 0.22);
    const thickness = lerp(deck.minThickness, deck.maxThickness, k) * (0.82 + jitter * 0.3);
    addDome(x, z, deck.base, thickness);
  }

  if (lift) {
    for (const p of puffs) { p.y += lift; p.base += lift; }
    for (const t of new Set(puffs.map(p => p.turret))) t.y += lift;
    for (const c of clouds) { c.base += lift; c.top += lift; c.cy += lift; }
  }
  cullContained();
  const grid = buildGrid();
  const packed = pack();

  function addCumulus({ x, z, base, height, width, turrets, kind }) {
    const ci = clouds.length;
    rng = mulberry32((Math.imul(seed, 9973) + Math.imul(ci + 1, 7919)) >>> 0);
    const rh = width * 0.5, rv = height * 0.5;
    const cloud = { kind, x, z, base, top: base + height, rh, rv, cy: base + rv };
    clouds.push(cloud);
    const lean = [0.10 + rng() * 0.08, -0.04 + rng() * 0.08]; // gentle downwind shear
    for (let k = 0; k < turrets; k++) {
      const main = k === 0;
      const a = rng() * Math.PI * 2, off = main ? rh * 0.12 * rng() : rh * (0.30 + rng() * 0.32);
      const tx = x + Math.cos(a) * off, tz = z + Math.sin(a) * off;
      const th = height * (main ? 1 : 0.42 + rng() * 0.38);
      const rb = rh * (main ? 0.62 : 0.40 + rng() * 0.16) * (turrets > 2 ? 0.86 : 1);
      // Turret mass centre and aspect drive the painted value blocks for its puffs.
      const turret = { x: tx + lean[0] * th * 0.5, y: base + th * 0.48, z: tz + lean[1] * th * 0.5, aspect: Math.max(0.8, th / (rb * 2)) };
      // Broad flattened skirt at the condensation level: cumulus are wide at the base.
      if (main && kind !== 'small') {
        const nSkirt = 3 + Math.floor(rng() * 3);
        for (let q = 0; q < nSkirt; q++) {
          const a2 = (q + rng() * 0.6) / nSkirt * Math.PI * 2, rs = rb * (0.62 + rng() * 0.2);
          const sk = addPuff(tx + Math.cos(a2) * rb * 0.72, base + rs * 0.22, tz + Math.sin(a2) * rb * 0.72, rs, 0, ci, turret, base, 0.58 + rng() * 0.12);
          billow(sk, 1, ci, turret, base, kind);
        }
      }
      // A smooth column of overlapping heads, narrowing upward; small lateral wander.
      let y = base + rb * 0.24;
      for (let guard = 0; guard < 20; guard++) {
        const f = clamp01((y - base) / th);
        const r = rb * (1 - 0.46 * f) * (0.92 + rng() * 0.14);
        if (y + r * 0.55 > base + th && guard > 0) break;
        const jx = (rng() - 0.5) * r * 0.3, jz = (rng() - 0.5) * r * 0.3;
        const p = addPuff(tx + lean[0] * (y - base) + jx, y, tz + lean[1] * (y - base) + jz, r, 0, ci, turret, base, kind === 'small' ? 0.72 : 0.86 + rng() * 0.14);
        billow(p, 1, ci, turret, base, kind);
        if (kind !== 'small' && rng() < 0.3) {
          // Shoulder head bulging off the column.
          const a2 = rng() * Math.PI * 2, rs = r * (0.55 + rng() * 0.2);
          const q = addPuff(p.x + Math.cos(a2) * r * 0.7, y + r * (rng() - 0.3) * 0.5, p.z + Math.sin(a2) * r * 0.7, rs, 0, ci, turret, base, 0.86 + rng() * 0.14);
          billow(q, 1, ci, turret, base, kind);
        }
        y += r * (0.50 + rng() * 0.12);
      }
    }
  }

  function addDome(x, z, base, thickness) {
    // A stratocumulus raft: a wide, low ellipsoid cap on the shared flat base, billowed on top.
    const ci = clouds.length;
    rng = mulberry32((Math.imul(seed, 9973) + Math.imul(ci + 1, 7919)) >>> 0);
    const a = thickness * (2.0 + rng() * 0.6), b = thickness * 1.05;
    const cloud = { kind: 'deck', x, z, base, top: base + thickness, rh: a, rv: thickness * 0.55, cy: base + thickness * 0.35 };
    clouds.push(cloud);
    // Mass centre sits under the raft so its normals fan upward and out, like a cloud-sea roof.
    const turret = { x, y: base - thickness * 0.8, z, aspect: 0.55 };
    const p = addPuff(x, base + thickness - b, z, a, 0, ci, turret, base, b / a);
    billow(p, 1, ci, turret, base, 'deck');
  }

  // Recursive surface billows: medium on cores, small on medium, crown on the tallest.
  function billow(parent, level, ci, turret, base, kind) {
    const maxLevel = BILLOWS[kind].length;
    if (level > maxLevel) return;
    const deck = kind === 'deck';
    const ratio = level === 1 ? (deck ? 0.36 : 0.38) : level === 2 ? 0.44 : 0.46;
    const want = BILLOWS[kind][level - 1];
    const count = Math.round(want * (0.75 + rng() * 0.5));
    // Evenly spread candidate directions (randomly rotated Fibonacci set): billows tile the
    // parent's exposed surface instead of clumping and leaving bald patches.
    const minY = deck ? 0.25 : level === 1 ? -0.40 : level === 2 ? -0.45 : 0.10;
    const out = normalize3([parent.x - turret.x, (parent.y - turret.y) / turret.aspect, parent.z - turret.z]);
    const minOut = level === 1 ? -0.15 : 0.0;
    const cands = fibonacciDirs(count * 4).map(d => rotate3(d, parentSpin(parent)))
      .filter(d => d[1] >= minY && dot3(d, out) >= minOut);
    for (let i = cands.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [cands[i], cands[j]] = [cands[j], cands[i]]; }
    for (let i = 0; i < Math.min(count, cands.length); i++) {
      const dir = cands[i];
      const shrink = 1 - 0.35 * Math.max(0, -dir[1]);
      const pr = deck && level === 1 ? parent.r * 0.62 : parent.r;   // raft billows scale with its height, not width
      const r = pr * ratio * (0.72 + rng() * 0.5) * shrink;
      // Point on the parent's ellipsoid surface along dir; always protrude, or the billow is
      // invisible and only costs fill.
      const surf = [dir[0] * parent.r, dir[1] * parent.r * parent.squash, dir[2] * parent.r];
      const k = 0.66 + rng() * 0.14 + 0.5 * r / Math.hypot(surf[0], surf[1], surf[2]);
      const cx = parent.x + surf[0] * k, cy = parent.y + surf[1] * k, cz = parent.z + surf[2] * k;
      if (cy - base < -r * 0.2) continue; // nothing hangs below the condensation level
      const squash = deck ? (level === 1 ? 0.62 : 0.78) + rng() * 0.14 : 0.82 + rng() * 0.16;
      const child = addPuff(cx, cy, cz, r, level, ci, turret, base, squash);
      billow(child, level + 1, ci, turret, base, kind);
    }
  }

  function addPuff(x, y, z, r, level, ci, turret, base, squash = 1) {
    const p = { x, y, z, r, level, ci, turret, base, squash, seed: rng() };
    puffs.push(p);
    return p;
  }

  function cullContained() {
    let kept = puffs.slice();
    // Drop billows whose surface is (almost) entirely buried in neighbours. They are invisible,
    // but an impostor still rasterises and shades its whole quad (no early-z with frag depth).
    const exposed = exposure(kept, 40, 300);
    stats.buried = kept.filter((p, i) => exposed[i] < layout.minExposure).length;
    kept = kept.filter((p, i) => exposed[i] >= layout.minExposure);
    puffs.length = 0; puffs.push(...kept);
  }

  function buildGrid() {
    const cell = 500, n = Math.ceil(layout.extent / cell) + 4, origin = -half - cell * 2;
    const lists = Array.from({ length: n * n }, () => []);
    puffs.forEach((p, i) => {
      const reach = p.r * 1.25;
      const x0 = Math.max(0, Math.floor((p.x - reach - origin) / cell)), x1 = Math.min(n - 1, Math.floor((p.x + reach - origin) / cell));
      const z0 = Math.max(0, Math.floor((p.z - reach - origin) / cell)), z1 = Math.min(n - 1, Math.floor((p.z + reach - origin) / cell));
      for (let z = z0; z <= z1; z++) for (let x = x0; x <= x1; x++) lists[z * n + x].push(i);
    });
    return { cell, n, origin, lists: lists.map(l => Int32Array.from(l)) };
  }

  /**
   * Density 0..1 at a world point (wind offset already removed by the caller).
   * Rises from 0 at 1.22 r to 1 at 0.80 r of any puff; flat-cut below the shared base.
   */
  function density(x, y, z, exclude = -1) {
    const gx = Math.floor((x - grid.origin) / grid.cell), gz = Math.floor((z - grid.origin) / grid.cell);
    if (gx < 0 || gz < 0 || gx >= grid.n || gz >= grid.n) return 0;
    let best = 0;
    for (const i of grid.lists[gz * grid.n + gx]) {
      if (i === exclude) continue;
      const p = puffs[i];
      const dy = (y - p.y) / p.squash;
      const q = Math.sqrt((x - p.x) ** 2 + dy * dy + (z - p.z) ** 2) / p.r;
      if (q >= 1.22) continue;
      const v = smooth01((1.22 - q) / 0.42) * smooth01((y - p.base + 25) / 70);
      if (v > best) best = v;
    }
    return best;
  }

  function pack() {
    const data = new Float32Array(puffs.length * PUFF_STRIDE);
    const levels = [0, 0, 0, 0];
    puffs.forEach((p, i) => {
      const c = clouds[p.ci], o = i * PUFF_STRIDE;
      data.set([p.x, p.y, p.z, p.r,
        p.turret.x, p.turret.y, p.turret.z, p.turret.aspect,
        c.x, c.cy, c.z, Math.max(0.35, c.rv / c.rh),
        p.base, p.squash, 0, p.level + Math.min(0.999, p.seed)], o);
      levels[p.level]++;
    });
    return { data, levels };
  }

  /**
   * Top-down sea shadow footprint, size×size over the layout extent. Each puff's sphere is
   * projected along the sun onto y=0 (an ellipse stretched by 1/sun.y). Returns Uint8 coverage.
   */
  function shadowRaster(size = 256) {
    const out = new Float32Array(size * size);
    const texel = layout.extent / size;
    const hx = sunDir[0] / sunDir[1], hz = sunDir[2] / sunDir[1];
    const along = normalize3([sunDir[0], 0, sunDir[2]]);
    const cot = Math.hypot(sunDir[0], sunDir[2]) / Math.max(0.15, sunDir[1]);
    for (const p of puffs) {
      if (p.level > 1) continue;
      const cx = p.x - hx * p.y, cz = p.z - hz * p.y;  // where the centre's shadow lands
      const ra = Math.hypot(p.r, p.r * p.squash * cot), rb = p.r;
      const reach = ra * 1.2;
      const x0 = Math.max(0, Math.floor((cx - reach + half) / texel)), x1 = Math.min(size - 1, Math.ceil((cx + reach + half) / texel));
      const z0 = Math.max(0, Math.floor((cz - reach + half) / texel)), z1 = Math.min(size - 1, Math.ceil((cz + reach + half) / texel));
      for (let z = z0; z <= z1; z++) for (let x = x0; x <= x1; x++) {
        const wx = -half + (x + 0.5) * texel - cx, wz = -half + (z + 0.5) * texel - cz;
        const u = (wx * along[0] + wz * along[2]) / ra, v = (-wx * along[2] + wz * along[0]) / rb;
        const q = Math.sqrt(u * u + v * v);
        if (q < 1.15) { const k = z * size + x; out[k] = Math.max(out[k], smooth01((1.15 - q) / 0.4)); }
      }
    }
    const bytes = new Uint8Array(size * size);
    for (let i = 0; i < out.length; i++) bytes[i] = Math.round(out[i] * 255);
    return { size, extent: layout.extent, data: bytes };
  }

  /** True when the grid cell around a point holds any puff (cheap gate for per-frame work). */
  function near(x, z) {
    const gx = Math.floor((x - grid.origin) / grid.cell), gz = Math.floor((z - grid.origin) / grid.cell);
    return gx >= 0 && gz >= 0 && gx < grid.n && gz < grid.n && grid.lists[gz * grid.n + gx].length > 0;
  }

  /** Outward direction from the nearest cloud mass, for directional in-cloud fog. */
  function gradient(x, y, z, h = 18) {
    const gx = density(x + h, y, z) - density(x - h, y, z);
    const gy = density(x, y + h, z) - density(x, y - h, z);
    const gz = density(x, y, z + h) - density(x, y, z - h);
    const l = Math.hypot(gx, gy, gz);
    return l > 1e-6 ? [-gx / l, -gy / l, -gz / l] : [0, 1, 0];
  }

  return Object.freeze({
    seed, layout, sun: sunDir, count: puffs.length, stats, clouds: Object.freeze(clouds.map(c => Object.freeze({ ...c }))),
    data: packed.data, levels: packed.levels, density, gradient, near, shadowRaster,
    bounds: { min: [-half, 0, -half], max: [half, Math.max(...clouds.map(c => c.top)), half] },
  });
}

// ---------------------------------------------------------------- helpers
export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hash2(x, y, seed) {
  let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(seed, 2147483647);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
function vnoise2(x, y, seed) {
  const ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy;
  const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
  const a = hash2(ix, iy, seed), b = hash2(ix + 1, iy, seed), c = hash2(ix, iy + 1, seed), d = hash2(ix + 1, iy + 1, seed);
  return lerp(lerp(a, b, u), lerp(c, d, u), v);
}
function fbm2(x, y, seed) {
  return vnoise2(x, y, seed) * 0.55 + vnoise2(x * 2.07 + 5.1, y * 2.07 - 3.3, seed + 1) * 0.30 + vnoise2(x * 4.3 - 1.7, y * 4.3 + 9.2, seed + 2) * 0.15;
}
/** Fraction of each ellipsoid's surface (above its flat base) not inside any other one. */
function exposure(list, samples, cell) {
  const m = list.length, X = new Float32Array(m), Y = new Float32Array(m), Z = new Float32Array(m), R = new Float32Array(m), S = new Float32Array(m);
  let minX = Infinity, minZ = Infinity, maxX = -Infinity, maxZ = -Infinity;
  list.forEach((p, i) => { X[i] = p.x; Y[i] = p.y; Z[i] = p.z; R[i] = p.r; S[i] = p.squash;
    minX = Math.min(minX, p.x - p.r); maxX = Math.max(maxX, p.x + p.r); minZ = Math.min(minZ, p.z - p.r); maxZ = Math.max(maxZ, p.z + p.r); });
  const nx = Math.ceil((maxX - minX) / cell) + 1, nz = Math.ceil((maxZ - minZ) / cell) + 1;
  const cx = v => Math.max(0, Math.min(nx - 1, Math.floor((v - minX) / cell))), cz = v => Math.max(0, Math.min(nz - 1, Math.floor((v - minZ) / cell)));
  // Compressed cell lists, largest ellipsoids first so containment is found early.
  const order = Array.from({ length: m }, (_, i) => i).sort((a, b) => R[b] - R[a]);
  const counts = new Int32Array(nx * nz + 1);
  for (const i of order) for (let z = cz(Z[i] - R[i]); z <= cz(Z[i] + R[i]); z++) for (let x = cx(X[i] - R[i]); x <= cx(X[i] + R[i]); x++) counts[z * nx + x + 1]++;
  for (let k = 1; k <= nx * nz; k++) counts[k] += counts[k - 1];
  const fill = counts.slice(0, nx * nz), items = new Int32Array(counts[nx * nz]);
  for (const i of order) for (let z = cz(Z[i] - R[i]); z <= cz(Z[i] + R[i]); z++) for (let x = cx(X[i] - R[i]); x <= cx(X[i] + R[i]); x++) items[fill[z * nx + x]++] = i;
  const dirs = fibonacciDirs(samples), out = new Float32Array(m);
  for (let i = 0; i < m; i++) {
    let open = 0, total = 0;
    for (const d of dirs) {
      const x = X[i] + d[0] * R[i] * 1.01, y = Y[i] + d[1] * R[i] * S[i] * 1.01, z = Z[i] + d[2] * R[i] * 1.01;
      if (y < list[i].base) continue;
      total++;
      const c = cz(z) * nx + cx(x);
      let inside = false;
      for (let k = counts[c]; k < counts[c + 1]; k++) {
        const j = items[k]; if (j === i) continue;
        const dx = x - X[j], dy = (y - Y[j]) / S[j], dz = z - Z[j];
        if (dx * dx + dy * dy + dz * dz < R[j] * R[j]) { inside = true; break; }
      }
      if (!inside) open++;
    }
    out[i] = total ? open / total : 1;
  }
  return out;
}
function parentSpin(p) { return [p.seed * 6.283, p.seed * 17.1 % 6.283, p.seed * 41.7 % 6.283]; }
function rotate3(v, [a, b, c]) {
  let [x, y, z] = v;
  [x, z] = [x * Math.cos(a) - z * Math.sin(a), x * Math.sin(a) + z * Math.cos(a)];
  [y, z] = [y * Math.cos(b) - z * Math.sin(b), y * Math.sin(b) + z * Math.cos(b)];
  [x, y] = [x * Math.cos(c) - y * Math.sin(c), x * Math.sin(c) + y * Math.cos(c)];
  return [x, y, z];
}
function fibonacciDirs(n) {
  const out = [], g = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) { const y = 1 - (i + 0.5) * 2 / n, r = Math.sqrt(1 - y * y); out.push([Math.cos(g * i) * r, y, Math.sin(g * i) * r]); }
  return out;
}
function randomDir(rng) {
  const y = rng() * 2 - 1, a = rng() * Math.PI * 2, s = Math.sqrt(1 - y * y);
  return [Math.cos(a) * s, y, Math.sin(a) * s];
}
function rotY(v, deg) { const a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a); return [v[0] * c - v[2] * s, 0, v[0] * s + v[2] * c]; }
function normalize3(v) { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; }
function dot3(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
function lerp(a, b, t) { return a + (b - a) * t; }
function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
function smooth01(x) { x = clamp01(x); return x * x * (3 - 2 * x); }
