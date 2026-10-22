// Automated Academy student. It can ONLY use the player's input path: a virtual
// stick (x, y), latched throttle, AB toggle, BRK, MSL/GUN/FLR presses — fed to the
// real PlayerController, so Expert has to roll then pull and Assisted has to
// request turns. Browser-safe (no Node imports): browser-check loads it in-page.
import { sub, norm, toBody, clamp, DEG, UP } from '../src/sim/math.js';
import { bankAngle, pitchForG } from '../src/sim/aircraft.js';
import { hdgDeg, wrapDeg, gammaDeg, KMH } from '../src/academy/runner.js';

/** Input object with the same surface the PlayerController reads. */
export function makeStudentInput() {
  const s = { stick: { x: 0, y: 0 }, thr: 0.72, ab: false, brk: false, gun: false, presses: new Set() };
  s.axes = () => ({ x: s.stick.x, y: s.stick.y, yaw: 0 });
  s.throttle = () => s.thr; s.boost = () => s.ab; s.brake = () => s.brk; s.gun = () => s.gun;
  s.look = () => false;
  s.consume = (n) => { const h = s.presses.has(n); s.presses.delete(n); return h; };
  return s;
}

/** Desired world direction for flying a heading with a climb angle (deg). */
export const dirFor = (headingDeg, climbDeg = 0) => {
  const h = headingDeg * DEG, c = climbDeg * DEG;
  return { x: Math.sin(h) * Math.cos(c), y: Math.sin(c), z: -Math.cos(h) * Math.cos(c) };
};

/**
 * Stick for flying toward `dir` (world). pullLimit caps aft stick (0..1): a
 * "moderate" thumb uses ~0.5, a hard break uses 1.
 */
export function stickToward(ac, dir, control, { pullLimit = 1, gain = 1 } = {}) {
  const b = toBody(ac.q, dir);
  const ahead = Math.max(-b.z, 1e-3);
  const ax = Math.atan2(b.x, ahead), ay = Math.atan2(b.y, ahead);
  const off = Math.hypot(ax, ay);
  let x, pull;
  if (control === 'assisted') {
    x = clamp(ax / (14 * DEG) * gain, -1, 1);
    pull = clamp(ay / (5 * DEG) * gain, -0.6, pullLimit);
    if (b.z > 0) { x = Math.sign(b.x || 1); pull = 0; } // target behind: full turn request
  } else if (off < 12 * DEG && b.z < 0) {
    // precision: a lift-vector thumb. Turn rate proportional to the error; bank to
    // tilt the lift, and pull exactly the G a banked turn needs (n = 1/cos bank),
    // read off the G meter. Same stick the player has.
    const v = Math.max(ac.speed, 60), g = 9.81;
    const latA = clamp(ax * 0.9 * gain, -0.2, 0.2) * v;          // m/s^2 sideways
    const upA = clamp(ay * 1.2 * gain, -0.12, 0.12) * v + g * Math.cos(Math.asin(clamp(ac.vel.y / v, -1, 1)));
    const wantBank = clamp(Math.atan2(latA, upA), -75 * DEG, 75 * DEG);
    x = clamp((wantBank - bankAngle(ac)) * 2.5 - ac.rollRateCur * 0.08, -1, 1);
    const nReq = Math.hypot(latA, upA) / g * Math.cos(clamp(wantBank - bankAngle(ac), -1.5, 1.5));
    pull = clamp(pitchForG(ac, nReq), -0.6, pullLimit);
  } else {
    // roll the target onto the canopy, then pull
    const rollErr = Math.atan2(b.x, b.y);
    x = clamp(rollErr / (40 * DEG), -1, 1) - ac.rollRateCur * 0.06;
    pull = Math.abs(rollErr) < 30 * DEG ? pullLimit : 0.1;
  }
  return { x: clamp(x, -1, 1), y: clamp(-pull, -1, 1) };
}

/** Throttle/AB/BRK to hold a speed (km/h). */
export function speedControl(st, ac, kmh, { allowAB = true, allowBrake = true } = {}) {
  const v = ac.speed * KMH, e = kmh - v;
  st.ab = allowAB && e > 60;
  st.brk = allowBrake && e < -60;
  st.thr = clamp(0.55 + e / 250, 0, 1);
}

/** Hold a heading and altitude (level-ish flight). */
export function holdHeadingAlt(ac, headingDeg, alt, control, opts) {
  const climb = clamp((alt - ac.pos.y) / 40, -12, 12);
  return stickToward(ac, dirFor(headingDeg, climb), control, opts);
}

// ---------------- per-lesson plans: (runner, input, control) -> void ----------------
export const PLANS = {
  L01(r, s, c) {
    const ac = r.me, id = r.phase?.id;
    const alt = id === 'climb' || id === 'descend' ? r.d.target : r.notes.climbTarget ? r.alt : 3000;
    Object.assign(s.stick, holdHeadingAlt(ac, 0, id === 'level' ? ac.pos.y - ac.vel.y * 0.5 : alt, c, { pullLimit: 0.5 }));
    speedControl(s, ac, 750);
  },
  L02(r, s, c) {
    const ac = r.me, id = r.phase?.id;
    const target = { h090: 90, h300: 300, h015: 15 }[id] ?? r.heading;
    const err = wrapDeg(target - hdgDeg(ac));
    const aim = Math.abs(err) < 30 ? target : hdgDeg(ac) + Math.sign(err) * 45;
    Object.assign(s.stick, stickToward(ac, dirFor(aim, clamp((3000 - ac.pos.y) / 60, -8, 8)), c, { pullLimit: 0.85 }));
    speedControl(s, ac, 760);
  },
  L03(r, s, c) {
    const ac = r.me, id = r.phase?.id;
    Object.assign(s.stick, holdHeadingAlt(ac, 0, 3000, c, { pullLimit: 0.5 }));
    if (id === 'accel') { s.thr = 1; s.ab = true; s.brk = false; }
    else if (id === 'decel') { s.thr = 0; s.ab = false; s.brk = r.kmh > 660; }
    else speedControl(s, ac, 650);
  },
};

/** Deliberately wrong students: each should fail with a specific, causal reason. */
export const BAD = {
  // Expert who rolls but never pulls: heading barely changes.
  'L02:rollNoPull'(r, s, c) { s.stick.x = Math.abs(bankAngle(r.me)) < 70 * DEG ? 0.6 : 0; s.stick.y = 0; },
  // Never uses AB in the acceleration phase.
  'L03:noAB'(r, s, c) { Object.assign(s.stick, holdHeadingAlt(r.me, 0, 3000, c, { pullLimit: 0.5 })); s.thr = 1; s.ab = false; },
  // Decelerates with throttle only, no speedbrake.
  'L03:noBrake'(r, s, c) {
    Object.assign(s.stick, holdHeadingAlt(r.me, 0, 3000, c, { pullLimit: 0.5 }));
    if (r.phase?.id === 'accel') { s.thr = 1; s.ab = true; } else { s.thr = 0; s.ab = false; s.brk = false; }
  },
  // Accelerates by diving instead of thrust.
  'L03:dive'(r, s, c) { Object.assign(s.stick, stickToward(r.me, dirFor(0, -20), c)); s.thr = 1; s.ab = true; },
  // Keeps a bank in "level flight": never satisfies wings-level.
  'L01:banked'(r, s, c) { Object.assign(s.stick, holdHeadingAlt(r.me, hdgDeg(r.me) + 4, 3000, c, { pullLimit: 0.5 })); },
};
export { gammaDeg, UP, norm, sub };
