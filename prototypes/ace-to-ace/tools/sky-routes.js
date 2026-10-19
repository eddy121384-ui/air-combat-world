// Deterministic flight routes for the Opus Sky Lab. Each route is a function of time only,
// so a capture at frame k is identical no matter how fast the machine renders.
// Positions are world metres; clouds are found from the cloudscape, not hard-coded twice.

const UP = [0, 1, 0];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const len = a => Math.hypot(a[0], a[1], a[2]);
const norm = a => { const l = len(a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

/** Centripetal-free uniform Catmull-Rom through timed keys [{t, p:[x,y,z]}]. */
function spline(keys) {
  return t => {
    let i = 0;
    while (i < keys.length - 2 && t > keys[i + 1].t) i++;
    const k1 = keys[i], k2 = keys[i + 1];
    const k0 = keys[Math.max(0, i - 1)], k3 = keys[Math.min(keys.length - 1, i + 2)];
    const u = Math.max(0, Math.min(1, (t - k1.t) / (k2.t - k1.t)));
    const out = [0, 0, 0];
    for (let c = 0; c < 3; c++) {
      const p0 = k0.p[c], p1 = k1.p[c], p2 = k2.p[c], p3 = k3.p[c];
      const m1 = (p2 - p0) / ((k2.t - k0.t) || 1) * (k2.t - k1.t), m2 = (p3 - p1) / ((k3.t - k1.t) || 1) * (k2.t - k1.t);
      const u2 = u * u, u3 = u2 * u;
      out[c] = (2 * u3 - 3 * u2 + 1) * p1 + (u3 - 2 * u2 + u) * m1 + (-2 * u3 + 3 * u2) * p2 + (u3 - u2) * m2;
    }
    return out;
  };
}

/** Aircraft pose from a position function: forward from velocity, bank from lateral accel. */
function flight(pos, { bankGain = 1 } = {}) {
  return t => {
    const h = 1 / 30;
    const a = pos(t - h), b = pos(t), c = pos(t + h);
    const vel = mul(sub(c, a), 1 / (2 * h));
    const acc = mul(add(sub(c, mul(b, 2)), a), 1 / (h * h));
    const fwd = norm(vel);
    // Coordinated turn: lift vector = gravity compensation + centripetal demand.
    const lift = add([0, 9.81, 0], acc);
    lift[1] = Math.max(lift[1], 3.5); // no inverted pushovers in the lab paths
    let up = norm(sub(lift, mul(fwd, dot(lift, fwd))));
    const level = norm(sub(UP, mul(fwd, dot(UP, fwd))));
    up = norm(add(mul(level, 1 - bankGain), mul(up, bankGain)));
    return { position: b, forward: fwd, up, velocity: vel };
  };
}

/** Game-like chase camera (src/game/render.js framing). */
function chase(pose, { back = 38, rise = 9, side = 0, look = 70, lag = 0.06 } = {}) {
  return t => {
    const p = pose(t), q = pose(t - lag);
    const right = norm(cross(q.forward, q.up));
    const cam = add(add(add(q.position, mul(q.forward, -back)), mul(q.up, rise)), mul(right, side));
    const target = add(add(p.position, mul(p.forward, look)), mul(p.up, 3));
    return { camera: cam, target, up: q.up, plane: p, velocity: p.velocity };
  };
}

export function buildRoutes(scape) {
  const V = 255;
  const hero = scape.clouds.findIndex(c => c.kind === 'tower');
  const H = scape.clouds[hero];
  const routes = {};

  // Directions are chosen against the sun, like a layout artist would: the sun sits ~65°
  // to the left of the approach so the tower shows a lit face, a terminator and a shade side.
  const sunH = norm([scape.sun[0], 0, scape.sun[2]]);
  const rot = (v, deg) => { const a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a); return [v[0] * c - v[2] * s, 0, v[0] * s + v[2] * c]; };
  const heroAt = y => scape.clouds[hero] && cloudReach(scape, hero, y);

  // 1. Approach: straight at the hero tower from ~4.8 km to ~0.6 km off its billows.
  {
    const y = H.base + (H.top - H.base) * 0.34, dir = rot(sunH, 65), reach = heroAt(y)(mul(dir, -1));
    const end = add([H.x, y, H.z], mul(dir, -(reach + 600))), start = add(end, mul(dir, -4200));
    const T = 4200 / V, side = norm(cross(dir, UP));
    const pos = t => add(add(start, mul(dir, V * t)), add(mul(side, 60 * Math.sin(t / T * Math.PI)), [0, 70 * t / T, 0]));
    routes.approach = { label: '飛近 Approach', duration: T, shot: chase(flight(pos)) };
  }

  // 2. Side pass: skim the sunlit flank ~140 m off the outermost billows, banked toward it.
  {
    const y = H.base + (H.top - H.base) * 0.30, out = sunH, reach = heroAt(y)(out);
    const along = rot(sunH, 90), mid = add([H.x, y, H.z], mul(out, reach + 140));
    const L = 4600, T = L / V, start = add(mid, mul(along, -L / 2));
    const pos = t => add(add(start, mul(along, V * t)), add(mul(out, 45 * Math.sin(t / T * Math.PI * 2)), [0, 30 * t / T, 0]));
    const pose = flight(pos);
    routes.sidepass = { label: '側掠 Side pass', duration: T, shot: chase(t => {
      const p = pose(t); const toCloud = norm(sub([H.x, p.position[1], H.z], p.position));
      // Visual bank toward the wall (the path is nearly straight, so physics alone barely rolls).
      const right = norm(cross(p.forward, p.up)), roll = 0.40 * Math.sign(dot(right, toCloud));
      return { ...p, up: norm(add(mul(p.up, Math.cos(roll)), mul(right, Math.sin(roll)))) };
    }, { side: 14, back: 40, rise: 7 }) };
  }

  // 3. 180° orbit from the sunlit side round to the backlit side, camera always on the tower.
  {
    const R = 5000, y = H.base + (H.top - H.base) * 0.40, T = 16;
    const a0 = Math.atan2(sunH[0], sunH[2]) - Math.PI * 0.15;
    const ring = (a, r, dy) => [H.x + Math.sin(a) * r, y + dy, H.z + Math.cos(a) * r];
    const planeAt = tt => ring(a0 + Math.PI * tt / T + 0.05, R - 250, 260);
    const pose = flight(planeAt);
    routes.orbit180 = { label: '180° 繞行 Orbit', duration: T, shot: t => {
      const a = a0 + Math.PI * Math.max(0, Math.min(1, t / T));
      return { camera: ring(a, R, 330), target: [H.x, y + 120, H.z], up: UP, plane: pose(t), velocity: pose(t).velocity };
    } };
  }

  // 4. Traverse: punch straight through the biggest medium cumulus, exit facing the hero tower.
  {
    const mids = scape.clouds.map((c, i) => ({ c, i })).filter(e => e.c.kind === 'medium').sort((a, b) => b.c.rh - a.c.rh);
    const M = mids[0].c, y = M.base + (M.top - M.base) * 0.32;
    const dir = norm([H.x - M.x, 0, H.z - M.z]);
    const span = M.rh + 1500, T = span * 2 / V;
    const p0 = add([M.x, y, M.z], mul(dir, -span)), p1 = add([M.x, y, M.z], mul(dir, span));
    const pos = t => add(p0, mul(sub(p1, p0), t / T));
    routes.traverse = { label: '穿入穿出 Traverse', duration: T, shot: chase(flight(pos)) };
  }

  // 5. Cloud-sea dive and climb: descend through the deck, run beneath it, climb back out.
  {
    const deckBase = scape.layout.deck.base, best = findDeckRun(scape, deckBase);
    const { origin, dir } = best;
    const at = (s, y) => [origin[0] + dir[0] * s, y, origin[2] + dir[2] * s];
    const keys = [[-1, 1750], [0, 1750], [3, 1720], [6.5, 1180], [9, 520], [12, 380], [15, 430], [18, 1050], [20.5, 1580], [23, 1760], [24, 1770]];
    const pos = spline(keys.map(([t, y]) => ({ t, p: at(t * V, y) })));
    routes.deck = { label: '雲海穿層 Cloud sea', duration: 23, shot: chase(flight(pos)) };
  }
  return routes;
}

/** Horizontal distance from a cloud's centre to its outermost billow surface along dir at altitude y. */
function cloudReach(scape, ci, y) {
  const c = scape.clouds[ci];
  return dir => {
    let best = 0;
    for (let i = 0; i < scape.count; i++) {
      const o = i * 16;
      if (Math.abs(scape.data[o + 8] - c.x) > 1e-3 || Math.abs(scape.data[o + 10] - c.z) > 1e-3) continue;
      const r = scape.data[o + 3], dy = Math.abs(scape.data[o + 1] - y);
      if (dy >= r) continue;
      const rr = Math.sqrt(r * r - dy * dy), along = (scape.data[o] - c.x) * dir[0] + (scape.data[o + 2] - c.z) * dir[2];
      const lateral = Math.hypot(scape.data[o] - c.x - along * dir[0], scape.data[o + 2] - c.z - along * dir[2]);
      if (lateral < rr) best = Math.max(best, along + Math.sqrt(rr * rr - lateral * lateral));
    }
    return best;
  };
}

function findDeckRun(scape, base) {
  // Pick a straight line whose descent (~7.5 s) and climb (~17.5 s) both cross thick deck.
  let best = null;
  for (let a = 0; a < 24; a++) for (let oz = -4; oz <= 4; oz++) for (let ox = -4; ox <= 4; ox++) {
    const ang = a / 24 * Math.PI * 2, dir = [Math.cos(ang), 0, Math.sin(ang)];
    const origin = [ox * 1500, 0, oz * 1500];
    const sample = s => scape.density(origin[0] + dir[0] * s * 255, base + 220, origin[2] + dir[2] * s * 255);
    const under = s => scape.density(origin[0] + dir[0] * s * 255, base - 300, origin[2] + dir[2] * s * 255);
    const score = sample(7.5) + sample(17.4) + sample(7.0) + sample(18.0) - 2 * (under(12) > 0 ? 1 : 0)
      - (Math.abs(origin[0] + dir[0] * 3000) > 9000 || Math.abs(origin[2] + dir[2] * 3000) > 9000 ? 4 : 0);
    if (!best || score > best.score) best = { score, origin, dir };
  }
  return best;
}
