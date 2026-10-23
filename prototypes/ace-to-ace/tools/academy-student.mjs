// Automated Academy student. It can ONLY use the player's input path: a virtual
// stick (x, y), latched throttle, AB toggle, BRK, MSL/GUN/FLR presses — fed to the
// real PlayerController, so Expert has to roll then pull and Assisted has to
// request turns. Browser-safe (no Node imports): browser-check loads it in-page.
import { sub, norm, toBody, clamp, DEG, UP } from '../src/sim/math.js';
import { bankAngle, pitchForG } from '../src/sim/aircraft.js';
import { hdgDeg, wrapDeg, gammaDeg, KMH } from '../src/academy/runner.js';
import { geometry } from '../src/academy/lessons.js';
import { gunLead, gunError, missilePk } from '../src/sim/fire.js';
import { HumanProxy } from '../src/ai/bots.js';
import { PilotAI } from '../src/ai/pilot.js';
import { PlayerController } from '../src/game/input.js';
import { addScaled, scale, cross, dot, len, angleBetween, forwardOf } from '../src/sim/math.js';

/** Input object with the same surface the PlayerController reads. */
export function makeStudentInput() {
  const s = { stick: { x: 0, y: 0 }, thr: 0.72, ab: false, brk: false, gunOn: false, presses: new Set() };
  s.axes = () => ({ x: s.stick.x, y: s.stick.y, yaw: 0 });
  s.throttle = () => s.thr; s.boost = () => s.ab; s.brake = () => s.brk; s.gun = () => s.gunOn;
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
export function stickToward(ac, dir, control, { pullLimit = 1, gain = 1, ff = { x: 0, y: 0 } } = {}) {
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
    const lim = 0.2 * Math.max(1, gain);
    const latA = (clamp(ax * 0.9 * gain, -lim, lim) + ff.x) * v;  // m/s^2 sideways (+ target turn feed-forward)
    const upA = (clamp(ay * 1.2 * gain, -0.6 * lim, 0.6 * lim) + ff.y) * v + g * Math.cos(Math.asin(clamp(ac.vel.y / v, -1, 1)));
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

/** Expert level turn at load factor n: bank = acos(1/n), pull exactly n (G meter). */
export function levelTurnStick(ac, n, side = 1, altHold = null) {
  const want = side * Math.acos(clamp(1 / Math.max(n, 1.01), 0, 1));
  const x = clamp((want - bankAngle(ac)) * 2.5 - ac.rollRateCur * 0.08, -1, 1);
  const climbFix = altHold == null ? 0 : clamp((altHold - ac.pos.y) / 300, -0.5, 0.5) - ac.vel.y / 120;
  return { x, y: clamp(-pitchForG(ac, n + climbFix), -1, 1) };
}
function turnHard(r, s, c, { pull = 1, side = 1 } = {}) {
  const ac = r.me;
  if (c === 'assisted') { s.stick.x = side * pull; s.stick.y = 0; return; }
  if (pull < 1) { Object.assign(s.stick, levelTurnStick(ac, 1 + (r.availG - 1) * pull, side, r.d.alt0 ?? 3000)); return; }
  Object.assign(s.stick, stickToward(ac, dirFor(hdgDeg(ac) + side * 90, clamp((3000 - ac.pos.y) / 80, -6, 6)), c, { pullLimit: pull }));
}
const towards = (r, p) => norm(sub(p, r.me.pos));
Object.assign(PLANS, {
  L04(r, s, c) {
    const id = r.phase?.id, [lo, hi] = r.bestBandKmh;
    if (id === 'band') {
      Object.assign(s.stick, holdHeadingAlt(r.me, hdgDeg(r.me), 3000, c, { pullLimit: 0.5 }));
      speedControl(s, r.me, (lo + hi) / 2);
      return;
    }
    s.thr = 1; s.ab = true; s.brk = false;
    if (id === 'sustain' && !r.d.armed) { Object.assign(s.stick, holdHeadingAlt(r.me, hdgDeg(r.me), 3000, c, { pullLimit: 0.5 })); return; }
    // MIL 360: spend speed down to a floor just above the requirement, then hold it
    const pull = id === 'sustain' ? clamp((r.kmh - (r.tune.sustainV + 25)) / 40 + 0.35, 0.1, 1) : 1;
    turnHard(r, s, c, { pull });
  },
  L05(r, s, c) {
    const ac = r.me, id = r.phase?.id;
    s.brk = false; s.ab = false;
    if (id === 'dive') { Object.assign(s.stick, stickToward(ac, dirFor(0, r.alt > 2700 ? -32 : -8), c, { pullLimit: 0.4 })); return; }
    // smooth zoom: ~40 degree climb at moderate G, wings level
    Object.assign(s.stick, stickToward(ac, dirFor(0, r.kmh > 430 ? 40 : 0), c, { pullLimit: 0.35 }));
  },
  L06(r, s, c) {
    const ac = r.me, id = r.phase?.id;
    if (id === 'slowturn') {
      if (!r.d.armed) { Object.assign(s.stick, holdHeadingAlt(ac, hdgDeg(ac), 3500, c, { pullLimit: 0.5 })); s.thr = 0; s.ab = false; s.brk = true; return; }
      s.brk = false; speedControl(s, ac, 400, { allowBrake: false });
      turnHard(r, s, c, { pull: 0.45 });
      return;
    }
    if (id === 'stall') {
      s.thr = 1; s.ab = true; s.brk = false;
      const climb = r.kmh < 470 ? -35 : 0;
      Object.assign(s.stick, stickToward(ac, dirFor(hdgDeg(ac), climb), c, { pullLimit: r.kmh < 470 ? 0.2 : 0.8 }));
      return;
    }
    if (id === 'dive') { s.thr = 0; s.ab = false; s.brk = true; Object.assign(s.stick, stickToward(ac, dirFor(hdgDeg(ac), 10), c)); return; }
    Object.assign(s.stick, holdHeadingAlt(ac, hdgDeg(ac), 3500, c));
  },
});

const lerpPt = (p, v, t) => addScaled(p, v, t);
/** Keep the nose out of the sea when chasing something below. */
function safeDir(ac, dir) {
  if (ac.pos.y < 1500 && dir.y < -0.1) return norm({ x: dir.x, y: -0.1 + (1500 - ac.pos.y) / 3000, z: dir.z });
  return dir;
}
/**
 * Expert tracking thumb: the AI's proven lift-vector controller, but ONLY its roll
 * and pitch outputs (x = roll rate, y = pitch) — the touch Expert player has no
 * rudder, so the AI's fine-aim yaw is dropped.
 */
function expertTrack(r, dir, gFrac = 1) {
  r.__steer ||= new PilotAI(r.me, { skill: 'ace', seed: 3 });
  const c = r.__steer.steer(dir, gFrac);
  return { x: clamp(c.roll, -1, 1), y: clamp(-c.pitch, -1, 1) };
}
function chase(r, s, c, aim, closeTo = 900, gain = 1) {
  const ac = r.me, foe = r.foe, g = geometry(ac, foe);
  if (c === 'expert' && gain > 1) {
    Object.assign(s.stick, expertTrack(r, safeDir(ac, norm(sub(aim, ac.pos)))));
    speedControl(s, ac, foe.speed * KMH + clamp((g.R - closeTo) / 4, -200, 250));
    return g;
  }
  // feed-forward: how fast the aim line rotates, in body axes (a thumb "leads" a turning target)
  const los = norm(sub(aim, ac.pos));
  const prev = r.__prevLos || los; r.__prevLos = los;
  const dl = toBody(ac.q, sub(los, prev));
  const ff = gain > 1 ? { x: dl.x * 60, y: dl.y * 60 } : { x: 0, y: 0 };
  Object.assign(s.stick, stickToward(ac, safeDir(ac, los), c, { pullLimit: 1, gain, ff }));
  speedControl(s, ac, foe.speed * KMH + clamp((g.R - closeTo) / 4, -200, 250));
  return g;
}
Object.assign(PLANS, {
  L07(r, s, c) {
    const foe = r.foe, g = geometry(r.me, foe);
    if (r.phase?.id === 'lead') { chase(r, s, c, gunLead(r.me, foe.pos, foe.vel).point, 600, 3); return; }
    const aim = g.R > 1250 ? lerpPt(foe.pos, foe.vel, 2) : g.R < 750 ? lerpPt(foe.pos, foe.vel, -1.2) : foe.pos;
    chase(r, s, c, aim, 950);
  },
  L08(r, s, c) {
    const ac = r.me, foe = r.foe;
    if (r.phase?.id === 'missile') {
      const g = chase(r, s, c, foe.pos, 1200);
      const aspect = Math.PI - angleBetween(forwardOf(foe.q), scale(norm(sub(foe.pos, ac.pos)), -1));
      const pk = ac.lock.locked ? missilePk({ R: g.R, ata: ac.lock.ata, aspect, mySpeed: ac.speed, tgSpeed: foe.speed, tgG: foe.nCur }) : 0;
      if (pk > 0.5 && r.t - (r.lastShotT ?? -9) > 3) { s.presses.add('msl'); r.lastShotT = r.t; }
      s.gunOn = false;
      return;
    }
    const lead = gunLead(ac, foe.pos, foe.vel).point;
    const g = chase(r, s, c, lead, 500, 3);
    s.gunOn = g.R < 850 && gunError(ac, lead) < 1.0 * DEG;
  },
  L09(r, s, c) {
    const ac = r.me, foe = r.foe;
    if (r.phase?.id === 'missiles') {
      const m = r.match.missiles.find((x) => x.alive && x.target === ac);
      s.thr = 1; s.ab = true; s.brk = false;
      if (!m) { Object.assign(s.stick, holdHeadingAlt(ac, hdgDeg(ac), 3200, c, { pullLimit: 0.5 })); return; }
      const rel = sub(m.pos, ac.pos), d = len(rel);
      const T = globalThis.__L09 || { flare: 2300, brk: 500 };
      if (d < T.flare && ac.flares > 0 && !m.flaredByStudent) { s.presses.add('flare'); m.flaredByStudent = true; }
      if (d < T.brk) {
        let side = norm(cross(UP, rel));
        if (dot(side, forwardOf(ac.q)) < 0) side = scale(side, -1);
        Object.assign(s.stick, stickToward(ac, norm(addScaled(side, UP, 0.05)), c, { pullLimit: 1 }));
      } else Object.assign(s.stick, holdHeadingAlt(ac, hdgDeg(ac), 3200, c, { pullLimit: 0.5 }));
      return;
    }
    const g = geometry(ac, foe), rev = geometry(foe, ac);
    if (g.ata > 90) { // it is behind: break toward it, bleed speed when it is close
      Object.assign(s.stick, stickToward(ac, safeDir(ac, norm(sub(foe.pos, ac.pos))), c, { pullLimit: 1 }));
      s.ab = rev.R > 700; s.brk = rev.R < 700; s.thr = rev.R < 700 ? 0 : 1;
      return;
    }
    chase(r, s, c, g.R > 900 ? lerpPt(foe.pos, foe.vel, 1.5) : foe.pos, 700);
  },
  L10(r, s, c) {
    // the "good" human proxy (HUD cues only, reaction delay, thumb drift) driving OUR input
    if (!r.__hp) r.__hp = new HumanProxy(r.me, { level: 'good', seed: 17, PlayerController, control: c });
    const out = r.__hp.update(1 / 60, r.match);
    Object.assign(s.stick, r.__hp.stick);
    s.ab = r.__hp.buttons.boost; s.brk = r.__hp.buttons.brake; s.gunOn = r.__hp.buttons.gun; s.thr = 1;
    if (out.fireMissile) s.presses.add('msl');
    if (out.flare) s.presses.add('flare');
  },
});

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
  // Full stick through the whole sustained 360: fast first half, no speed left.
  'L04:yank'(r, s, c) { if (r.phase?.id === 'sustain' && r.d.armed) { s.thr = 1; s.brk = false; turnHard(r, s, c, { pull: 1 }); } else PLANS.L04(r, s, c); },
  // Hauls the zoom climb at full G and rides the speedbrake.
  'L05:yank'(r, s, c) { PLANS.L05(r, s, c); if (r.phase?.id === 'zoom') { Object.assign(s.stick, stickToward(r.me, dirFor(0, r.kmh > 430 ? 70 : 0), c, { pullLimit: 1 })); s.brk = r.phaseT < 2; } },
  // Hauls the zoom at full G but leaves the speedbrake alone: G alone must cost the gate.
  'L05:yankNoBrake'(r, s, c) { PLANS.L05(r, s, c); if (r.phase?.id === 'zoom') Object.assign(s.stick, stickToward(r.me, dirFor(0, r.kmh > 430 ? 70 : 0), c, { pullLimit: 1 })); },
  // Pure pursuit at full burner: overshoots the turning target.
  'L07:pure'(r, s, c) { Object.assign(s.stick, stickToward(r.me, norm(sub(r.foe.pos, r.me.pos)), c, { pullLimit: 1 })); s.thr = 1; s.ab = true; s.brk = false; },
  // Fires missiles as soon as it can, locked or not, from far away.
  'L08:spray'(r, s, c) { PLANS.L08(r, s, c); if (r.phase?.id === 'missile') { s.presses.clear(); if (r.t - (r.lastShotT ?? -9) > 2.5) { s.presses.add('msl'); r.lastShotT = r.t; } } },
  // Tracks the target's current position accurately but ignores bullet travel time.
  'L08:bodyAim'(r,s,c) {
    if(r.phase?.id!=='guns') {PLANS.L08(r,s,c);return;}
    const geo=chase(r,s,c,r.foe.pos,500,3);
    s.gunOn=geo.R<850;
  },
  // Breaks hard as soon as it sees the missile (too early) and never drops flares.
  'L09:early'(r, s, c) { globalThis.__L09 = { flare: 0, brk: 2600 }; PLANS.L09(r, s, c); globalThis.__L09 = null; },
  // Ignores the missile warning: no flares, no break.
  'L09:ignore'(r, s, c) { Object.assign(s.stick, holdHeadingAlt(r.me, hdgDeg(r.me), 3200, c, { pullLimit: 0.5 })); s.thr = 1; s.ab = true; },
  // Keeps pulling during the stall instead of unloading.
  'L06:stallPull'(r, s, c) { PLANS.L06(r, s, c); if (r.phase?.id === 'stall') { s.stick.x = 0; s.stick.y = -1; s.thr = 0.72; s.ab = false; } },
  // Waits 1.5 s before reacting to the dive, then pulls without idle/brake.
  'L06:late'(r, s, c) { PLANS.L06(r, s, c); if (r.phase?.id === 'dive') { s.thr = 1; s.brk = false; if (r.phaseT < 1.5) { s.stick.x = 0; s.stick.y = 0; } } },
  'L01:banked'(r, s, c) { Object.assign(s.stick, holdHeadingAlt(r.me, hdgDeg(r.me) + 4, 3000, c, { pullLimit: 0.5 })); },
};
export { gammaDeg, UP, norm, sub };
