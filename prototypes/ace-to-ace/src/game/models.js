// Procedural low-poly aircraft. Each airframe is ONE BufferGeometry with vertex colours
// (one draw call) plus an inverted-hull outline mesh. Nose points to -Z, up is +Y.
// Silhouettes aim for "instantly recognisable", not engineering accuracy.
import * as THREE from 'three';

class Builder {
  constructor() { this.pos = []; this.col = []; }
  tri(a, b, c, color) {
    this.pos.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
    for (let i = 0; i < 3; i++) this.col.push(color.r, color.g, color.b);
  }
  quad(a, b, c, d, color) { this.tri(a, b, c, color); this.tri(a, c, d, color); }
  /** Two-sided mirrored helper: builds a part and its mirror across X=0. */
  mirror(fn) { fn(1); fn(-1); }

  /** Loft through cross-sections {z, cy, w, h, cx?, sq?}; colorFn(i, j) picks face colours. */
  loft(sections, n, colorFn, { capStart = true, capEnd = true } = {}) {
    const rings = sections.map((s) => {
      const pts = [];
      for (let j = 0; j < n; j++) {
        const th = (j / n) * Math.PI * 2 + Math.PI / n;
        let c = Math.cos(th), sn = Math.sin(th);
        const e = s.sq ?? 1; // superellipse exponent (<1 = boxier)
        c = Math.sign(c) * Math.abs(c) ** e; sn = Math.sign(sn) * Math.abs(sn) ** e;
        pts.push([(s.cx ?? 0) + (c * s.w) / 2, s.cy + (sn * s.h) / 2, s.z]);
      }
      return pts;
    });
    for (let i = 0; i < rings.length - 1; i++) {
      const A = rings[i], B = rings[i + 1];
      for (let j = 0; j < n; j++) {
        const k = (j + 1) % n;
        const col = colorFn(i, j, n);
        // ring order goes counter-clockwise looking down -Z; faces point outwards
        this.quad(A[j], A[k], B[k], B[j], col);
      }
    }
    const capCol = colorFn(-1, 0, n);
    if (capStart) { const R = rings[0], c = center(R); for (let j = 0; j < n; j++) this.tri(c, R[(j + 1) % n], R[j], capCol); }
    if (capEnd) { const R = rings[rings.length - 1], c = center(R); for (let j = 0; j < n; j++) this.tri(c, R[j], R[(j + 1) % n], colorFn(-2, 0, n)); }
  }

  /** Flat slab from a planform polygon [[x,z],...] at height y with thickness t (wings, stabs). */
  slab(poly, y, t, color, edgeColor = color, dihedral = 0) {
    const top = poly.map(([x, z]) => [x, y + t / 2 + Math.abs(x) * dihedral, z]);
    const bot = poly.map(([x, z]) => [x, y - t / 2 + Math.abs(x) * dihedral, z]);
    // planforms with LERX are concave: ear-clip, then orient every triangle explicitly
    for (const [a, b, c] of triangulate(poly)) {
      const ny = normalY(top[a], top[b], top[c]);
      if (ny > 0) { this.tri(top[a], top[b], top[c], color); this.tri(bot[a], bot[c], bot[b], shade(color, 0.8)); }
      else { this.tri(top[a], top[c], top[b], color); this.tri(bot[a], bot[b], bot[c], shade(color, 0.8)); }
    }
    const ccw = signedArea(poly) > 0; // in (x,z): >0 means the outline runs clockwise seen from +Y
    for (let i = 0; i < poly.length; i++) {
      const k = (i + 1) % poly.length;
      if (ccw) this.quad(top[i], top[k], bot[k], bot[i], edgeColor);
      else this.quad(top[k], top[i], bot[i], bot[k], edgeColor);
    }
  }

  /** Vertical fin from a side profile [[z,y],...] at x with thickness t, optional cant (rad). */
  fin(profile, x, t, color, cant = 0) {
    const pts = (side) => profile.map(([z, y]) => [x + side * t / 2 + Math.sin(cant) * y, Math.cos(cant) * y, z]);
    const L = pts(-1), R = pts(1);
    for (const [a, b, c] of triangulate(profile)) {
      const nx = normalX(R[a], R[b], R[c]);
      if (nx > 0) { this.tri(R[a], R[b], R[c], color); this.tri(L[a], L[c], L[b], shade(color, 0.85)); }
      else { this.tri(R[a], R[c], R[b], color); this.tri(L[a], L[b], L[c], shade(color, 0.85)); }
    }
    const flip = signedArea(profile) < 0;
    for (let i = 0; i < profile.length; i++) {
      const k = (i + 1) % profile.length;
      if (flip) this.quad(L[i], L[k], R[k], R[i], color); else this.quad(L[k], L[i], R[i], R[k], color);
    }
  }

  build() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.col, 3));
    g.computeVertexNormals(); // non-indexed => flat (faceted) normals
    addSmoothNormals(g);
    g.computeBoundingSphere();
    return g;
  }
}

const center = (ring) => {
  const c = [0, 0, 0];
  for (const p of ring) { c[0] += p[0]; c[1] += p[1]; c[2] += p[2]; }
  return c.map((v) => v / ring.length);
};
const C = (hex) => new THREE.Color(hex);
const signedArea = (poly) => { let a = 0; for (let i = 0; i < poly.length; i++) { const [x1, z1] = poly[i], [x2, z2] = poly[(i + 1) % poly.length]; a += x1 * z2 - x2 * z1; } return a; };
const triangulate = (poly) => THREE.ShapeUtils.triangulateShape(poly.map(([u, v]) => new THREE.Vector2(u, v)), []);
const normalY = (a, b, c) => (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]);
const normalX = (a, b, c) => (b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]);
const shade = (c, k) => new THREE.Color(c.r * k, c.g * k, c.b * k);

/** Averaged normals per shared position, used to extrude a gap-free outline hull. */
function addSmoothNormals(g) {
  const p = g.attributes.position.array, n = g.attributes.normal.array;
  const map = new Map();
  const key = (i) => `${Math.round(p[i] * 100)},${Math.round(p[i + 1] * 100)},${Math.round(p[i + 2] * 100)}`;
  for (let i = 0; i < p.length; i += 3) {
    const k = key(i);
    const acc = map.get(k) || [0, 0, 0];
    acc[0] += n[i]; acc[1] += n[i + 1]; acc[2] += n[i + 2];
    map.set(k, acc);
  }
  const out = new Float32Array(p.length);
  for (let i = 0; i < p.length; i += 3) {
    const a = map.get(key(i));
    const l = Math.hypot(a[0], a[1], a[2]) || 1;
    out[i] = a[0] / l; out[i + 1] = a[1] / l; out[i + 2] = a[2] / l;
  }
  g.setAttribute('smoothNormal', new THREE.BufferAttribute(out, 3));
}

// ---------------------------------------------------------------- F-16V
export function buildF16(palette = {}) {
  const P = {
    body: C(palette.body ?? 0xaebbc8), top: C(palette.top ?? 0x8d9bab), dark: C(0x3a4452),
    radome: C(0x8b96a2), canopy: C(0x2a3b5c), glint: C(0xbfe3ff), accent: C(palette.accent ?? 0x2f7ae5),
    nozzle: C(0x4a4f57), intake: C(0x1c2128), missile: C(0xe8ecef),
  };
  const b = new Builder();
  const body = (i, j, n) => (i === -1 ? P.radome : i === -2 ? P.nozzle : i <= 1 ? P.radome : j >= n / 2 ? P.body : P.top);
  // fuselage (nose at -Z)
  b.loft([
    { z: -8.2, cy: 0.05, w: 0.08, h: 0.08 },
    { z: -7.0, cy: 0.1, w: 0.62, h: 0.62 },
    { z: -5.6, cy: 0.16, w: 0.98, h: 1.02 },
    { z: -4.4, cy: 0.24, w: 1.12, h: 1.3 },
    { z: -2.4, cy: 0.3, w: 1.22, h: 1.5 },
    { z: -0.6, cy: 0.24, w: 1.42, h: 1.42 },
    { z: 2.0, cy: 0.2, w: 1.42, h: 1.32 },
    { z: 4.8, cy: 0.22, w: 1.26, h: 1.18 },
    { z: 6.7, cy: 0.22, w: 1.08, h: 1.02 },
    { z: 7.3, cy: 0.22, w: 1.0, h: 0.98 },
  ], 10, body, { capStart: false });
  // engine nozzle
  b.loft([
    { z: 7.3, cy: 0.22, w: 1.0, h: 0.98 },
    { z: 8.1, cy: 0.22, w: 0.82, h: 0.8 },
  ], 10, () => P.nozzle, { capStart: false });
  // chin intake (the F-16 signature)
  b.loft([
    { z: -3.6, cy: -0.72, w: 1.0, h: 0.62, sq: 0.6 },
    { z: -2.4, cy: -0.66, w: 1.02, h: 0.66, sq: 0.6 },
    { z: 0.8, cy: -0.5, w: 1.04, h: 0.6, sq: 0.6 },
    { z: 2.4, cy: -0.25, w: 0.9, h: 0.4, sq: 0.6 },
  ], 8, (i) => (i === -1 ? P.intake : P.body), { capEnd: false });
  // bubble canopy
  b.loft([
    { z: -5.0, cy: 0.62, w: 0.1, h: 0.1 },
    { z: -4.5, cy: 0.88, w: 0.62, h: 0.56 },
    { z: -3.3, cy: 1.04, w: 0.74, h: 0.72 },
    { z: -2.0, cy: 0.92, w: 0.6, h: 0.5 },
    { z: -1.2, cy: 0.76, w: 0.22, h: 0.2 },
  ], 8, (i, j) => (j === 2 && i === 1 ? P.glint : P.canopy));
  // dorsal spine
  b.slab([[0.32, -1.2], [0.32, 5.6], [-0.32, 5.6], [-0.32, -1.2]], 0.92, 0.22, P.top);
  // wings with LERX, cropped delta
  b.mirror((s) => {
    b.slab([[s * 0.5, -4.6], [s * 0.72, -1.6], [s * 4.75, 2.2], [s * 4.75, 3.15], [s * 0.7, 3.5]], 0.0, 0.16, P.top, P.body);
    b.slab([[s * 4.6, 1.6], [s * 4.95, 1.6], [s * 4.95, 3.3], [s * 4.6, 3.3]], 0.0, 0.18, P.accent);
    // horizontal stabilizer
    b.slab([[s * 0.7, 5.3], [s * 3.15, 6.95], [s * 3.15, 7.65], [s * 0.7, 7.5]], 0.12, 0.12, P.top, P.body, -0.06);
    // ventral fin
    b.fin([[5.0, -0.25], [6.2, -0.25], [6.3, -0.95], [5.7, -0.95]], s * 0.45, 0.06, P.body, s * -0.4);
    // wingtip missile
    b.loft([
      { z: 0.0, cy: 0.0, w: 0.02, h: 0.02, cx: s * 5.05 },
      { z: 0.6, cy: 0.0, w: 0.2, h: 0.2, cx: s * 5.05 },
      { z: 3.4, cy: 0.0, w: 0.2, h: 0.2, cx: s * 5.05 },
    ], 6, () => P.missile);
  });
  // vertical tail
  b.fin([[3.6, 0.8], [7.4, 0.8], [7.6, 1.0], [7.2, 4.9], [6.0, 4.9]], 0, 0.14, P.top);
  b.fin([[6.15, 4.15], [7.3, 4.15], [7.25, 4.9], [6.0, 4.9]], 0, 0.17, P.accent);
  return b.build();
}

// ---------------------------------------------------------------- J-16 (Flanker family)
export function buildJ16(palette = {}) {
  const P = {
    body: C(palette.body ?? 0x6f7f90), top: C(palette.top ?? 0x56636f), under: C(0x8d9aa7), dark: C(0x2c333c),
    radome: C(0x9aa4ad), canopy: C(0x253553), glint: C(0xbfe3ff), accent: C(palette.accent ?? 0xd8463c),
    nozzle: C(0x44484f), intake: C(0x161a20), missile: C(0xe6e9ec),
  };
  const b = new Builder();
  // long drooping nose + centre fuselage
  b.loft([
    { z: -11.6, cy: -0.25, w: 0.1, h: 0.1 },
    { z: -10.3, cy: -0.15, w: 0.75, h: 0.72 },
    { z: -8.4, cy: 0.02, w: 1.1, h: 1.05 },
    { z: -6.4, cy: 0.2, w: 1.3, h: 1.35 },
    { z: -4.0, cy: 0.25, w: 1.5, h: 1.45 },
    { z: -1.0, cy: 0.18, w: 2.0, h: 1.2, sq: 0.8 },
    { z: 3.0, cy: 0.1, w: 2.0, h: 1.0, sq: 0.8 },
    { z: 8.0, cy: 0.05, w: 1.2, h: 0.7, sq: 0.8 },
    { z: 11.8, cy: 0.0, w: 0.5, h: 0.4 },
  ], 10, (i, j, n) => (i === -1 ? P.radome : i <= 1 ? P.radome : j >= n / 2 ? P.under : P.top));
  // flat "pancake" lifting body between the nacelles
  b.slab([[2.9, -2.0], [2.9, 8.5], [-2.9, 8.5], [-2.9, -2.0], [0, -5.2]], 0.05, 0.35, P.top, P.body);
  // canopy + IRST ball
  b.loft([
    { z: -7.2, cy: 0.62, w: 0.1, h: 0.1 },
    { z: -6.6, cy: 0.9, w: 0.7, h: 0.58 },
    { z: -5.2, cy: 1.08, w: 0.82, h: 0.74 },
    { z: -3.8, cy: 0.98, w: 0.7, h: 0.6 },
    { z: -2.6, cy: 0.8, w: 0.3, h: 0.24 },
  ], 8, (i, j) => (j === 2 && i === 1 ? P.glint : P.canopy));
  b.loft([
    { z: -7.75, cy: 0.62, w: 0.05, h: 0.05 },
    { z: -7.55, cy: 0.62, w: 0.3, h: 0.3 },
    { z: -7.25, cy: 0.62, w: 0.22, h: 0.22 },
  ], 6, () => P.glint);
  b.mirror((s) => {
    const x = s * 1.55;
    // engine nacelle with box intake underneath
    b.loft([
      { z: -2.4, cy: -0.75, w: 1.25, h: 1.05, cx: x, sq: 0.55 },
      { z: 0.5, cy: -0.6, w: 1.35, h: 1.2, cx: x, sq: 0.6 },
      { z: 6.0, cy: -0.35, w: 1.35, h: 1.15, cx: x },
      { z: 9.0, cy: -0.3, w: 1.15, h: 1.05, cx: x },
    ], 8, (i) => (i === -1 ? P.intake : P.body), { capEnd: false });
    b.loft([
      { z: 9.0, cy: -0.3, w: 1.15, h: 1.05, cx: x },
      { z: 10.4, cy: -0.3, w: 0.95, h: 0.9, cx: x },
    ], 8, () => P.nozzle, { capStart: false });
    // big swept wing with ogival LERX
    b.slab([[s * 1.2, -6.4], [s * 2.2, -2.2], [s * 7.4, 4.9], [s * 7.4, 6.0], [s * 2.6, 6.6], [s * 2.4, 7.2], [s * 2.0, 2.0], [s * 1.6, -2.0]], 0.0, 0.2, P.top, P.body);
    b.slab([[s * 7.2, 3.6], [s * 7.65, 3.6], [s * 7.65, 6.2], [s * 7.2, 6.2]], 0.0, 0.22, P.accent);
    // horizontal stabilizer
    b.slab([[s * 2.6, 7.6], [s * 5.4, 9.6], [s * 5.4, 10.5], [s * 2.6, 10.3]], -0.2, 0.14, P.top, P.body);
    // twin canted vertical tails on the nacelles
    b.fin([[5.0, 0.35], [8.9, 0.35], [9.2, 0.6], [8.6, 4.6], [7.2, 4.6]], s * 2.05, 0.16, P.top, s * 0.08);
    b.fin([[7.25, 3.8], [8.75, 3.8], [8.6, 4.6], [7.2, 4.6]], s * 2.05, 0.19, P.accent, s * 0.08);
    // ventral fin
    b.fin([[6.0, -0.9], [7.6, -0.9], [7.7, -1.55], [6.9, -1.55]], s * 1.55, 0.08, P.body);
    // underwing missile
    b.loft([
      { z: 0.6, cy: -0.45, w: 0.02, h: 0.02, cx: s * 4.6 },
      { z: 1.2, cy: -0.45, w: 0.24, h: 0.24, cx: s * 4.6 },
      { z: 4.4, cy: -0.45, w: 0.24, h: 0.24, cx: s * 4.6 },
    ], 6, () => P.missile);
  });
  return b.build();
}

const OUTLINE_VS = /* glsl */`
  attribute vec3 smoothNormal;
  uniform float thickness;
  uniform vec2 resolution;
  void main() {
    vec4 clip = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    vec3 nView = normalize(normalMatrix * smoothNormal);
    vec2 dir = normalize((projectionMatrix * vec4(nView, 0.0)).xy + 1e-6);
    clip.xy += dir * thickness * clip.w * 2.0 / resolution;
    gl_Position = clip;
  }`;
const OUTLINE_FS = /* glsl */`
  uniform vec3 color;
  void main() { gl_FragColor = vec4(color, 1.0); }`;

let gradientMap = null;
export function toonGradient() {
  if (gradientMap) return gradientMap;
  // 3-band anime shading ramp
  const data = new Uint8Array([90, 90, 90, 255, 175, 175, 175, 255, 255, 255, 255, 255]);
  gradientMap = new THREE.DataTexture(data, 3, 1, THREE.RGBAFormat);
  gradientMap.minFilter = gradientMap.magFilter = THREE.NearestFilter;
  gradientMap.generateMipmaps = false;
  gradientMap.needsUpdate = true;
  return gradientMap;
}

export function outlineMaterial(color = 0x18202b, thickness = 1.6) {
  return new THREE.ShaderMaterial({
    uniforms: { color: { value: new THREE.Color(color) }, thickness: { value: thickness }, resolution: { value: new THREE.Vector2(1280, 720) } },
    vertexShader: OUTLINE_VS, fragmentShader: OUTLINE_FS, side: THREE.BackSide,
  });
}

/** Aircraft group: toon body + outline hull. `scale` enlarges for readability. */
export function makeAircraftMesh(typeId, outline, scale = 1.35) {
  const geo = typeId === 'J16' ? buildJ16() : buildF16();
  const mat = new THREE.MeshToonMaterial({ vertexColors: true, gradientMap: toonGradient() });
  const body = new THREE.Mesh(geo, mat);
  const hull = new THREE.Mesh(geo, outline);
  const g = new THREE.Group();
  g.add(body, hull);
  g.scale.setScalar(scale);
  g.userData.length = typeId === 'J16' ? 23.4 * scale : 16.3 * scale;
  g.userData.nozzles = typeId === 'J16'
    ? [new THREE.Vector3(-1.55, -0.3, 10.5).multiplyScalar(scale), new THREE.Vector3(1.55, -0.3, 10.5).multiplyScalar(scale)]
    : [new THREE.Vector3(0, 0.22, 8.2).multiplyScalar(scale)];
  g.userData.wingtips = typeId === 'J16'
    ? [new THREE.Vector3(-7.5, 0, 5.8).multiplyScalar(scale), new THREE.Vector3(7.5, 0, 5.8).multiplyScalar(scale)]
    : [new THREE.Vector3(-5.05, 0, 3.4).multiplyScalar(scale), new THREE.Vector3(5.05, 0, 3.4).multiplyScalar(scale)];
  return g;
}
