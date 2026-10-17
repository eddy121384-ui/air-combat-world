// Fire-control helpers shared by HUD (player) and AI.
import { sub, len, addScaled, angleBetween, forwardOf, clamp } from './math.js';
import { GUN } from './weapons.js';

/** Gun lead point for shooter vs target (optionally with target acceleration estimate). */
export function gunLead(shooter, tgtPos, tgtVel, tgtAcc = null) {
  const muzzle = GUN.speed + shooter.speed;
  let P = tgtPos;
  let t = len(sub(tgtPos, shooter.pos)) / muzzle;
  for (let i = 0; i < 3; i++) {
    P = addScaled(tgtPos, tgtVel, t);
    if (tgtAcc) P = addScaled(P, tgtAcc, 0.5 * t * t);
    // bullets carry the shooter's velocity: subtract the shooter's own drift
    P = addScaled(P, shooter.vel, -t);
    t = len(sub(P, shooter.pos)) / GUN.speed;
  }
  return { point: P, tof: t };
}

/** Angle between the nose and the gun lead direction. */
export function gunError(shooter, leadPoint) {
  return angleBetween(forwardOf(shooter.q), sub(leadPoint, shooter.pos));
}

/**
 * Heuristic kill probability for a missile shot (used by AI shot discipline and the
 * player's "SHOOT" cue). Rear-aspect, mid-range, non-maneuvering targets score highest.
 */
export function missilePk({ R, ata, aspect, mySpeed, tgSpeed, tgG }) {
  const tail = (1 + Math.cos(aspect)) / 2; // 1 = I'm at its six
  const head = Math.max(0, -Math.cos(aspect)); // 1 = nose-on
  const aspectF = clamp(0.28 + 0.64 * tail * tail + 0.12 * head * head, 0, 0.95);
  const rmaxTail = 1700 + (mySpeed - tgSpeed) * 4;
  const rmaxHead = 4600;
  const Rmax = clamp(rmaxTail + (rmaxHead - rmaxTail) * (1 - tail), 1200, 5000);
  // minimum range: the missile needs time to arm and build speed before it can turn
  const Rmin = 450, Ropt = 750;
  let rangeF = 0;
  if (R < Rmin) rangeF = 0.03;
  else if (R < Ropt) rangeF = 0.03 + 0.97 * (R - Rmin) / (Ropt - Rmin);
  else if (R < Rmax) rangeF = 1 - 0.75 * ((R - Ropt) / (Rmax - Ropt)) ** 1.5;
  const manF = tgG > 5 ? 0.7 : tgG > 3 ? 0.85 : 1;
  const ataF = 1 - 0.3 * clamp(ata / (45 * Math.PI / 180), 0, 1);
  return aspectF * rangeF * manF * ataF;
}
