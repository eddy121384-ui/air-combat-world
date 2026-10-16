// Minimal vector / quaternion helpers for the simulation layer.
// The sim deliberately does not depend on three.js so it can run headless in Node
// (AI vs AI batches) and be ported to another engine later.
// Convention (same as three.js cameras): forward = -Z, up = +Y, right = +X.

export const v3 = (x = 0, y = 0, z = 0) => ({ x, y, z });
export const copy = (a) => ({ x: a.x, y: a.y, z: a.z });
export const set = (o, a) => { o.x = a.x; o.y = a.y; o.z = a.z; return o; };
export const add = (a, b) => ({ x: a.x + b.x, y: a.y + b.y, z: a.z + b.z });
export const sub = (a, b) => ({ x: a.x - b.x, y: a.y - b.y, z: a.z - b.z });
export const scale = (a, s) => ({ x: a.x * s, y: a.y * s, z: a.z * s });
export const addScaled = (a, b, s) => ({ x: a.x + b.x * s, y: a.y + b.y * s, z: a.z + b.z * s });
export const addScaledInPlace = (a, b, s) => { a.x += b.x * s; a.y += b.y * s; a.z += b.z * s; return a; };
export const dot = (a, b) => a.x * b.x + a.y * b.y + a.z * b.z;
export const cross = (a, b) => ({ x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x });
export const len = (a) => Math.sqrt(a.x * a.x + a.y * a.y + a.z * a.z);
export const lenSq = (a) => a.x * a.x + a.y * a.y + a.z * a.z;
export const dist = (a, b) => Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2);
export const norm = (a) => { const l = len(a) || 1; return { x: a.x / l, y: a.y / l, z: a.z / l }; };
export const lerp = (a, b, t) => a + (b - a) * t;
export const clamp = (x, lo, hi) => (x < lo ? lo : x > hi ? hi : x);
export const smoothstep = (e0, e1, x) => { const t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); };
export const angleBetween = (a, b) => Math.acos(clamp(dot(a, b) / ((len(a) * len(b)) || 1), -1, 1));
/** Component of a perpendicular to unit vector n. */
export const perp = (a, n) => addScaled(a, n, -dot(a, n));
export const DEG = Math.PI / 180;
export const G = 9.81;
export const UP = Object.freeze({ x: 0, y: 1, z: 0 });

// ---- quaternions {x,y,z,w} ----
export const quat = (x = 0, y = 0, z = 0, w = 1) => ({ x, y, z, w });
export function qMul(a, b) {
  return {
    x: a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
    y: a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
    z: a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
    w: a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
  };
}
export function qAxisAngle(axis, angle) {
  const h = angle / 2, s = Math.sin(h);
  return { x: axis.x * s, y: axis.y * s, z: axis.z * s, w: Math.cos(h) };
}
export function qNormalize(q) {
  const l = Math.hypot(q.x, q.y, q.z, q.w) || 1;
  q.x /= l; q.y /= l; q.z /= l; q.w /= l; return q;
}
/** Rotate vector v by quaternion q. */
export function qRotate(q, v) {
  const { x, y, z, w } = q;
  const ix = w * v.x + y * v.z - z * v.y;
  const iy = w * v.y + z * v.x - x * v.z;
  const iz = w * v.z + x * v.y - y * v.x;
  const iw = -x * v.x - y * v.y - z * v.z;
  return {
    x: ix * w + iw * -x + iy * -z - iz * -y,
    y: iy * w + iw * -y + iz * -x - ix * -z,
    z: iz * w + iw * -z + ix * -y - iy * -x,
  };
}
export const qConj = (q) => ({ x: -q.x, y: -q.y, z: -q.z, w: q.w });
/** Express world vector v in the body frame of q. */
export const toBody = (q, v) => qRotate(qConj(q), v);
export const forwardOf = (q) => qRotate(q, { x: 0, y: 0, z: -1 });
export const upOf = (q) => qRotate(q, { x: 0, y: 1, z: 0 });
export const rightOf = (q) => qRotate(q, { x: 1, y: 0, z: 0 });

/** Orientation looking along `fwd` with approximate `up`. */
export function qLook(fwd, up = UP) {
  const f = norm(fwd);
  let r = cross(f, up);
  if (lenSq(r) < 1e-8) r = cross(f, { x: 0, y: 0, z: 1 });
  r = norm(r);
  const u = cross(r, f);
  // rotation matrix columns: right=r, up=u, back=-f
  const m00 = r.x, m01 = u.x, m02 = -f.x;
  const m10 = r.y, m11 = u.y, m12 = -f.y;
  const m20 = r.z, m21 = u.z, m22 = -f.z;
  const tr = m00 + m11 + m22;
  let q;
  if (tr > 0) {
    const s = 0.5 / Math.sqrt(tr + 1);
    q = { w: 0.25 / s, x: (m21 - m12) * s, y: (m02 - m20) * s, z: (m10 - m01) * s };
  } else if (m00 > m11 && m00 > m22) {
    const s = 2 * Math.sqrt(1 + m00 - m11 - m22);
    q = { w: (m21 - m12) / s, x: 0.25 * s, y: (m01 + m10) / s, z: (m02 + m20) / s };
  } else if (m11 > m22) {
    const s = 2 * Math.sqrt(1 + m11 - m00 - m22);
    q = { w: (m02 - m20) / s, x: (m01 + m10) / s, y: 0.25 * s, z: (m12 + m21) / s };
  } else {
    const s = 2 * Math.sqrt(1 + m22 - m00 - m11);
    q = { w: (m10 - m01) / s, x: (m02 + m20) / s, y: (m12 + m21) / s, z: 0.25 * s };
  }
  return qNormalize(q);
}

/** Closest-approach distance between moving points over one step (segment vs point). */
export function segmentPointDistance(a0, a1, p) {
  const d = sub(a1, a0);
  const l2 = lenSq(d);
  const t = l2 > 0 ? clamp(dot(sub(p, a0), d) / l2, 0, 1) : 0;
  return { dist: dist(addScaled(a0, d, t), p), t };
}

// Deterministic RNG (mulberry32) so AI vs AI batches are reproducible.
export function makeRng(seed = 1) {
  let s = seed >>> 0;
  const rng = () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  rng.range = (a, b) => a + (b - a) * rng();
  rng.sign = () => (rng() < 0.5 ? -1 : 1);
  rng.gauss = () => {
    const u = Math.max(rng(), 1e-9), v = rng();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  };
  return rng;
}
