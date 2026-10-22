// Arcade flight model shared by the player and the AI.
// Point-mass energy model with bank-to-turn: the only way to change direction is to roll the
// lift vector and pull G. Turn rate peaks at corner speed, high-G turns bleed speed, climbing
// trades speed for altitude. The AI flies with exactly the same limits as the player.
import {
  v3, copy, add, sub, scale, addScaled, dot, cross, len, norm, clamp, perp, G, UP,
  qMul, qAxisAngle, qNormalize, forwardOf, upOf, rightOf, qLook,
} from './math.js';

// Numbers are arcade-tuned, not real performance data. The two types differ on purpose:
// F-16V rolls and accelerates faster; J-16 turns better at low speed (lower corner speed).
export const AIRCRAFT = {
  F16V: {
    id: 'F16V', name: 'F-16V',
    maxG: 10, minG: -3, cornerSpeed: 185,
    rollRate: 4.0, yawRate: 0.16,
    thrustMil: 8.6, thrustAB: 8.0, // m/s^2 equivalents
    dragK: 0.00012, inducedK: 0.26,
    gOnset: 0.12, rollOnset: 0.09, spool: 0.5,
    hp: 100, radius: 8,
    missiles: 12, gunRounds: 600, flares: 2,
  },
  J16: {
    id: 'J16', name: 'J-16',
    maxG: 9.5, minG: -3, cornerSpeed: 175,
    rollRate: 3.1, yawRate: 0.15,
    thrustMil: 8.3, thrustAB: 8.0,
    dragK: 0.000125, inducedK: 0.25,
    gOnset: 0.14, rollOnset: 0.12, spool: 0.6,
    hp: 100, radius: 8,
    missiles: 12, gunRounds: 600, flares: 2,
  },
};

export const MIN_SPEED = 45;
export const MAX_SPEED = 430;
export const MAX_ROT_RATE = 1.3; // rad/s, hard sanity cap on flight-path rotation
// Small airframe/velocity response time. The nose may lead the actual movement
// during a hard pull or rudder input (an arcade AoA/slip approximation), but the
// same kinematics apply to AI and player. 0.09s provides modest separation at high G.
export const FLIGHT_PATH_LAG = 0.09; // seconds, not a free HUD-only animation

// Same integrator, different arcade-tuned performance envelopes. Not aircraft data.
// Flight-feel polish (Oct 2026, docs/flight-feel-polish.md): both profiles gained a
// transonic drag rise so top speed is set by drag instead of the MAX_SPEED clamp;
// Arcade hard turns now cost a little energy; Tactical keeps its corner-speed peak
// but sheds the excess drag that made MIL unable to sustain more than ~3.4G; the
// roll stop is crisper in both. Historical values are in the baseline JSON.
export const WAVE_DRAG_SPEED = 300; // m/s, ~M0.9 at the fight altitude
export const FLIGHT_PROFILES = Object.freeze({
  arcade: Object.freeze({ engine: 1.12, parasite: 0.65, induced: 0.42, wave: 0.0011,
    spool: 0.70, abSpool: 0.85, gOnset: 0.45,
    roll: 1.16, rollOnset: 0.55, rollStop: 0.2, pathLag: 0.065 }),
  tactical: Object.freeze({ engine: 1.05, parasite: 0.72, induced: 0.82, wave: 0.0007,
    spool: 0.78, abSpool: 1.0, gOnset: 0.56,
    roll: 1.08, rollOnset: 0.64, rollStop: 0.28, pathLag: 0.075 }),
});

export function makeControls() {
  // pitch: +1 pull (nose up in body frame), roll: +1 roll right, yaw: +1 nose right
  // throttle 0..1 (1 = military power), boost = afterburner, brake = airbrake
  return { pitch: 0, roll: 0, yaw: 0, throttle: 0.75, boost: false, brake: false,
    fireMissile: false, fireGun: false, flare: false };
}

export function createAircraft(typeId, side, pos, fwd, speed) {
  const t = AIRCRAFT[typeId];
  return {
    type: t, side, name: t.name,
    pos: copy(pos), q: qLook(fwd, UP), speed,
    vel: scale(norm(fwd), speed),
    hp: t.hp, alive: true, deathCause: null,
    nCur: 1, rollRateCur: 0, thrustCur: 0.75, abCur: 0,
    missiles: t.missiles, gunRounds: t.gunRounds,
    flares: t.flares, flareRecharge: 0,
    railCooldown: [0, 0], nextRail: 0, gunCooldown: 0,
    lock: { target: null, timer: 0, locked: false },
    lockedBy: 0, // count of hostile locks on me this frame (RWR)
    controls: makeControls(),
    // stats for logs/tests
    stats: { missilesFired: 0, missileHits: 0, roundsFired: 0, roundHits: 0, damageDealt: 0, flaresUsed: 0 },
    gLoad: 1, aoaVisual: 0,
  };
}

export const fwdOf = (ac) => forwardOf(ac.q);
export const upVecOf = (ac) => upOf(ac.q);
export const rightVecOf = (ac) => rightOf(ac.q);
export const specificEnergy = (ac) => ac.pos.y + (ac.speed * ac.speed) / (2 * G);

/** Max load factor available at the current speed (lift-limited below corner speed). */
export function availableG(ac, speed = ac.speed) {
  const t = ac.type;
  if (ac.flightFeel === 'arcade') {
    // Wider corner-speed band and gentler low-speed loss of turning authority than
    // Tactical. Exponent > 1 keeps the turn-RATE peak at corner speed: the former
    // 0.25*maxG floor made the jet turn fastest (~47 deg/s) at the 45 m/s clamp,
    // so braking to a crawl beat every other tactic. Slow now tightens the radius
    // (an AC-style brake turn) but no longer adds turn rate.
    const r = Math.max(speed, MIN_SPEED) / (t.cornerSpeed * 0.90);
    return Math.max(0.35, t.maxG * 1.05 * Math.min(1, Math.pow(r, 1.3)));
  }
  if (ac.flightFeel === 'tactical' || ac.flightFeel === 'B') {
    // RB-inspired speed-squared lift limit. No real AoA/stall computation yet.
    const r = Math.max(speed, MIN_SPEED) / t.cornerSpeed;
    return Math.max(0.35, Math.min(t.maxG, 9) * Math.min(1, r * r));
  }
  const r = speed / t.cornerSpeed;
  return Math.max(0.35, t.maxG * Math.min(1, r * r));
}

/** Rough sustained/instantaneous turn rate (rad/s) at a given G and speed. */
export const turnRate = (n, speed) => (n * G) / Math.max(speed, MIN_SPEED);

/** Level-turn rate (rad/s) the airframe can pull right now at `speed`. */
export function instantTurnRate(ac, speed = ac.speed) {
  const n = availableG(ac, speed);
  return Math.sqrt(Math.max(0, n * n - 1)) * G / Math.max(speed, MIN_SPEED);
}
const bestTurnCache = new Map();
/** Best instantaneous level-turn rate over the speed range, and the speed band
 *  where at least `share` of it is available (HUD "best turn speed" cue). */
export function bestTurn(ac, share = 0.92) {
  const key = `${ac.type.id}:${ac.flightFeel}:${share}`;
  if (!bestTurnCache.has(key)) {
    let best = 0;
    const rates = [];
    for (let v = MIN_SPEED; v <= MAX_SPEED; v += 2) { const w = instantTurnRate(ac, v); rates.push([v, w]); best = Math.max(best, w); }
    const band = rates.filter(([, w]) => w >= best * share).map(([v]) => v);
    bestTurnCache.set(key, { rate: best, lo: band[0], hi: band[band.length - 1] });
  }
  return bestTurnCache.get(key);
}


function stepLegacyAircraft(ac, dt) {
  if (!ac.alive) return;
  const t = ac.type;
  const c = ac.controls;
  const fwd = forwardOf(ac.q);

  // --- engine ---
  // Airbrake adds drag independently; engine/afterburner obey their own commands.
  const thrCmd = clamp(c.boost ? 1 : c.throttle, 0, 1);
  ac.thrustCur += (thrCmd - ac.thrustCur) * Math.min(1, dt / t.spool);
  ac.abCur += ((c.boost ? 1 : 0) - ac.abCur) * Math.min(1, dt / (t.spool * 1.2));
  const altFactor = clamp(1 - ac.pos.y / 16000, 0.35, 1);
  const thrust = (ac.thrustCur * t.thrustMil + ac.abCur * t.thrustAB) * altFactor;

  // --- load factor (G) ---
  // Arcade auto-trim: neutral stick holds the flight path against gravity along the lift axis,
  // so letting go of the stick does not make the nose sag. Same rule for player and AI.
  const nAvail = availableG(ac);
  const nMin = t.minG * Math.min(1, nAvail / t.maxG);
  const n0 = neutralG(ac);
  const pitchIn = clamp(c.pitch, -1, 1);
  const nCmd = pitchIn >= 0 ? n0 + pitchIn * (nAvail - n0) : n0 + pitchIn * (n0 - nMin);
  ac.nCur += (nCmd - ac.nCur) * Math.min(1, dt / t.gOnset);

  // --- speed / energy ---
  const v = ac.speed;
  const drag = t.dragK * v * v * (c.brake ? 2.6 : 1) + t.inducedK * ac.nCur * ac.nCur * (200 / v) ** 1.5
    + Math.abs(c.yaw) * 1.2;
  const gravityAlong = -G * fwd.y;
  ac.speed = clamp(v + (thrust - drag + gravityAlong) * dt, MIN_SPEED, MAX_SPEED);

  // --- roll ---
  ac.rollRateCur += (clamp(c.roll, -1, 1) * t.rollRate - ac.rollRateCur) * Math.min(1, dt / t.rollOnset);
  // roll right = rotate about forward axis clockwise as seen by pilot => negative around -Z... use body axis
  let q = ac.q;
  q = qMul(q, qAxisAngle({ x: 0, y: 0, z: -1 }, ac.rollRateCur * dt));

  // --- flight path change from lift + gravity (world frame) ---
  const up = upOf(q);
  const f = forwardOf(q);
  const gPerp = perp({ x: 0, y: -G, z: 0 }, f); // gravity component bending the path
  const aPerp = addScaled(gPerp, up, ac.nCur * G);
  const aMag = len(aPerp);
  if (aMag > 1e-4) {
    let rate = aMag / Math.max(ac.speed, MIN_SPEED);
    rate = Math.min(rate, MAX_ROT_RATE);
    const axis = norm(cross(f, aPerp));
    q = qMul(qAxisAngle(axis, rate * dt), q);
  }
  // --- rudder (small, for fine aim) ---
  const yawRate = clamp(c.yaw, -1, 1) * t.yawRate * clamp(ac.speed / 120, 0.3, 1);
  q = qMul(q, qAxisAngle({ x: 0, y: -1, z: 0 }, yawRate * dt));
  ac.q = qNormalize(q);

  // --- independent flight-path direction ---
  // Previously velocity was forcibly snapped onto the nose every tick,
  // making the flight-path marker (FPM) identical to the waterline W.
  // Preserve the existing nose/roll/G controller and scalar energy model, but
  // let actual displacement catch up to the nose with a short response time.
  // The HUD reads this genuine velocity, not a fabricated screen offset.
  const nose = forwardOf(ac.q);
  const path = norm(ac.vel);
  const response = 1 - Math.exp(-dt / FLIGHT_PATH_LAG); // frame-rate independent
  const travel = norm(addScaled(path, sub(nose, path), response));
  ac.vel = scale(travel, ac.speed);
  ac.pos = addScaled(ac.pos, ac.vel, dt);
  // For debug/visualisation: unsigned divergence in radians (not a CFD AoA).
  ac.aoaVisual = Math.acos(clamp(dot(nose, travel), -1, 1));
  ac.gLoad = ac.nCur;
}

/** Bank angle relative to the horizon, radians (+ = right wing down). */
export function bankAngle(ac) {
  const up = upOf(ac.q), right = rightOf(ac.q);
  return Math.atan2(-right.y, up.y);
}

/** Load factor that exactly cancels gravity along the lift axis (auto-trim point). */
export function neutralG(ac) {
  const f = forwardOf(ac.q), up = upOf(ac.q);
  const t = ac.type;
  const nAvail = availableG(ac);
  const nMin = t.minG * Math.min(1, nAvail / t.maxG);
  // gravity perpendicular to the path, projected on body up; we need n*G to cancel it
  const gUp = -G * (up.y - f.y * dot(f, up)); // dot(gPerp, up), f.up = 0
  return clamp(-gUp / G, nMin, nAvail);
}

/** Inverse of the stick mapping: pitch input that produces load factor n. */
export function pitchForG(ac, n) {
  const t = ac.type;
  const nAvail = availableG(ac);
  const nMin = t.minG * Math.min(1, nAvail / t.maxG);
  const n0 = neutralG(ac);
  if (n >= n0) return clamp((n - n0) / Math.max(nAvail - n0, 1e-3), 0, 1);
  return clamp((n - n0) / Math.max(n0 - nMin, 1e-3), -1, 0);
}

export function pitchAngle(ac) {
  return Math.asin(clamp(forwardOf(ac.q).y, -1, 1));
}

export function headingOf(ac) {
  const f = forwardOf(ac.q);
  return Math.atan2(f.x, -f.z); // 0 = north (-Z), +90deg = east (+X)
}

export { add, v3 };


// Flight-feel experiment: A routes through the original, byte-for-byte legacy integration
// above. B is a separate integration, applied identically to the player and both AI aircraft.
// No orientation teleport, arbitrary nose steering, or HUD-only FPM substitution.
export function stepAircraft(ac, dt) {
  return ['arcade', 'tactical', 'B'].includes(ac.flightFeel)
    ? stepModeAircraft(ac, dt) : stepLegacyAircraft(ac, dt);
}
function stepModeAircraft(ac, dt) {
  if (!ac.alive) return;
  const t = ac.type, c = ac.controls;
  const profile = ac.flightFeel === 'arcade' ? FLIGHT_PROFILES.arcade : FLIGHT_PROFILES.tactical;
  const fwd = forwardOf(ac.q);
  // AB, throttle and brake remain independent in both physics profiles.
  const thrCmd = clamp(c.boost ? 1 : c.throttle, 0, 1);
  ac.thrustCur += (thrCmd - ac.thrustCur) * Math.min(1, dt / (t.spool * profile.spool));
  ac.abCur += ((c.boost ? 1 : 0) - ac.abCur) * Math.min(1, dt / (t.spool * profile.abSpool));
  const altitude = clamp(1 - ac.pos.y / 16000, 0.35, 1);
  const thrust = (ac.thrustCur * t.thrustMil + ac.abCur * t.thrustAB)
    * profile.engine * altitude;

  const pitchIn = clamp(c.pitch, -1, 1), nAvail = availableG(ac);
  const nMin = t.minG * Math.min(1, nAvail / t.maxG), n0 = neutralG(ac);
  // Stick directly requests the G currently available from the airframe.
  // No brake-triggered G unlock: at low speed, full pull is still lift-limited.
  const nCmd = pitchIn >= 0
    ? n0 + pitchIn * (nAvail - n0)
    : n0 + pitchIn * (n0 - nMin);
  // Faster G onset and more decisive roll stop without snapping orientation.
  ac.nCur += (nCmd - ac.nCur) * Math.min(1, dt / (t.gOnset * profile.gOnset));

  const v = ac.speed;
  // Induced drag grows ~G squared: instant nose authority costs energy.
  // BRK is independent parasite drag, not a source of extra lift or turn G.
  const drag = t.dragK * profile.parasite * v * v * (c.brake ? 2.6 : 1)
    + t.inducedK * profile.induced * ac.nCur * ac.nCur
      * (200 / Math.max(v, MIN_SPEED)) ** 1.5
    + profile.wave * Math.max(0, v - WAVE_DRAG_SPEED) ** 2
    + Math.abs(c.yaw) * 1.2;
  ac.speed = clamp(v + (thrust - drag - G * fwd.y) * dt, MIN_SPEED, MAX_SPEED);

  const rollCmd = clamp(c.roll, -1, 1);
  const rollOnset = t.rollOnset * (rollCmd === 0 ? profile.rollStop : profile.rollOnset);
  ac.rollRateCur += (rollCmd * t.rollRate * profile.roll - ac.rollRateCur)
    * Math.min(1, dt / rollOnset);
  let q = qMul(ac.q, qAxisAngle({ x: 0, y: 0, z: -1 }, ac.rollRateCur * dt));
  const up = upOf(q), f = forwardOf(q);
  const gPerp = perp({ x: 0, y: -G, z: 0 }, f);
  const acceleration = addScaled(gPerp, up, ac.nCur * G);
  const aMag = len(acceleration);
  if (aMag > 1e-4) {
    const rate = Math.min(aMag / Math.max(ac.speed, MIN_SPEED), MAX_ROT_RATE);
    q = qMul(qAxisAngle(norm(cross(f, acceleration)), rate * dt), q);
  }
  const yawRate = clamp(c.yaw, -1, 1) * t.yawRate * clamp(ac.speed / 120, 0.3, 1);
  q = qMul(q, qAxisAngle({ x: 0, y: -1, z: 0 }, yawRate * dt));
  ac.q = qNormalize(q);

  // The true world-space velocity follows the nose over a short finite lag;
  // FPM continues to report the direction of actual displacement.
  const nose = forwardOf(ac.q), path = norm(ac.vel);
  const response = 1 - Math.exp(-dt / profile.pathLag);
  const travel = norm(addScaled(path, sub(nose, path), response));
  ac.vel = scale(travel, ac.speed);
  ac.pos = addScaled(ac.pos, ac.vel, dt);
  ac.aoaVisual = Math.acos(clamp(dot(nose, travel), -1, 1));
  ac.gLoad = ac.nCur;
}
