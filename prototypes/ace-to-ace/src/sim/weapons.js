// Missiles, gun rounds and flares. Rules are shared by player and AI.
import {
  copy, add, sub, scale, addScaled, dot, len, norm, clamp, angleBetween, perp, dist, G,
  segmentPointDistance, forwardOf, upOf, rightOf,
} from './math.js';

export const MISSILE = {
  boostTime: 2.0, boostAccel: 165, maxSpeed: 600, dragK: 0.000075, turnBleed: 0.09,
  maxG: 20, gRefSpeed: 420, life: 9, armTime: 0.45, gimbal: 55 * Math.PI / 180,
  navN: 3.5, fuse: 12, damageNear: 75, damageFar: 50, lag: 0.4,
};
export const LOCK = { range: 3000, keepRange: 3600, cone: 30 * Math.PI / 180, keepCone: 45 * Math.PI / 180, time: 0.85 };
export const GUN = { speed: 1050, rate: 15, life: 1.15, spread: 0.45 * Math.PI / 180, damage: 4, range: 1000, hitRadius: 5.5 };
export const RAIL_RELOAD = 5;
export const FLARE = { recharge: 25, decoyRange: 2600, life: 3.2, count: 4 };

/** Lock-on is a weapon-system rule (same for player and AI): keep the target in the cone. */
export function updateLock(ac, target, dt) {
  const L = ac.lock;
  if (!target || !target.alive || !ac.alive) { L.target = null; L.timer = 0; L.locked = false; return; }
  const r = sub(target.pos, ac.pos);
  const R = len(r);
  const ata = angleBetween(forwardOf(ac.q), r);
  if (L.target !== target) { L.target = target; L.timer = 0; L.locked = false; }
  if (L.locked) {
    if (R > LOCK.keepRange || ata > LOCK.keepCone) { L.locked = false; L.timer = 0; }
  } else if (R < LOCK.range && ata < LOCK.cone) {
    L.timer += dt;
    if (L.timer >= LOCK.time) L.locked = true;
  } else {
    L.timer = Math.max(0, L.timer - dt * 2);
  }
  L.range = R; L.ata = ata;
  if (L.locked) target.lockedBy += 1;
}

export function launchMissile(world, ac) {
  if (ac.missiles <= 0) return null;
  const rail = ac.railCooldown[0] <= 0 ? 0 : ac.railCooldown[1] <= 0 ? 1 : -1;
  if (rail < 0) return null;
  ac.railCooldown[rail] = RAIL_RELOAD;
  ac.missiles -= 1;
  const f = forwardOf(ac.q), right = rightOf(ac.q), up = upOf(ac.q);
  const side = rail === 0 ? -1 : 1;
  const target = ac.lock.locked ? ac.lock.target : null;
  const m = {
    id: world.nextId++, kind: 'missile', owner: ac, target, side,
    pos: addScaled(addScaled(ac.pos, right, side * 3.2), up, -1.2),
    vel: scale(f, ac.speed + 15), speed: ac.speed + 15, time: 0, alive: true,
    guided: !!target, minDist: Infinity, decoy: null, result: null,
  };
  world.missiles.push(m);
  ac.stats.missilesFired += 1;
  world.emit({ type: 'missileLaunch', ac, missile: m, guided: m.guided });
  return m;
}

export function stepMissile(world, m, dt) {
  if (!m.alive) return;
  m.time += dt;
  const P = MISSILE;
  const fwd = norm(m.vel);
  // speed
  let accel = m.time < P.boostTime ? P.boostAccel : 0;
  accel -= P.dragK * m.speed * m.speed;
  accel -= G * fwd.y * 0.5;
  let latMag = 0;
  // guidance (proportional navigation) towards target or decoy
  const tgt = m.decoy && m.decoy.alive ? m.decoy : m.target && m.target.alive ? m.target : null;
  if (m.guided && tgt && m.time > P.armTime) {
    const r = sub(tgt.pos, m.pos);
    const R = len(r);
    if (angleBetween(fwd, r) > P.gimbal) {
      m.guided = false; // seeker lost the target, missile goes ballistic
      if (m.result == null && !m.decoy) world.emit({ type: 'missileLost', missile: m });
    } else {
      const tv = tgt.vel || { x: 0, y: 0, z: 0 };
      const vr = sub(tv, m.vel);
      const los = scale(r, 1 / R);
      const omega = scale({ x: r.y * vr.z - r.z * vr.y, y: r.z * vr.x - r.x * vr.z, z: r.x * vr.y - r.y * vr.x }, 1 / (R * R));
      const vc = -dot(r, vr) / R;
      // a = N * Vc * (omega x los)
      let a = scale({ x: omega.y * los.z - omega.z * los.y, y: omega.z * los.x - omega.x * los.z, z: omega.x * los.y - omega.y * los.x }, P.navN * Math.max(vc, 50));
      a = add(a, { x: 0, y: G, z: 0 }); // gravity compensation
      a = perp(a, fwd);
      const gAvail = P.maxG * Math.min(1, (m.speed / P.gRefSpeed) ** 2) * G;
      latMag = len(a);
      if (latMag > gAvail) { a = scale(a, gAvail / latMag); latMag = gAvail; }
      // autopilot/airframe lag: the missile can't change its pull instantly. This is what
      // lets a well-timed last-ditch break beat it.
      const prev = m.acc || { x: 0, y: 0, z: 0 };
      const k = Math.min(1, dt / P.lag);
      m.acc = perp(addScaled(prev, sub(a, prev), k), fwd);
      latMag = len(m.acc);
      m.vel = addScaled(m.vel, m.acc, dt);
    }
  } else if (!m.guided) {
    m.vel = addScaled(m.vel, { x: 0, y: -G * 0.6, z: 0 }, dt);
  }
  accel -= P.turnBleed * latMag;
  m.speed = clamp(m.speed + accel * dt, 120, P.maxSpeed);
  m.vel = scale(norm(m.vel), m.speed);
  m.lateralG = latMag / G;

  const p0 = m.pos;
  const p1 = addScaled(m.pos, m.vel, dt);
  // proximity fuse against any hostile aircraft (closest approach during the step)
  for (const ac of world.aircraft) {
    if (!ac.alive || ac === m.owner) continue;
    // move the aircraft into the missile's frame: relative segment
    const relA = sub(p0, ac.pos);
    const relB = sub(p1, addScaled(ac.pos, ac.vel, dt));
    const { dist: d } = segmentPointDistance(relA, relB, { x: 0, y: 0, z: 0 });
    if (ac === m.target) m.minDist = Math.min(m.minDist, d);
    if (d < P.fuse && m.time > P.armTime) {
      const dmg = Math.round(P.damageFar + (P.damageNear - P.damageFar) * clamp(1 - (d - 4) / (P.fuse - 4), 0, 1));
      m.alive = false; m.result = 'hit';
      m.owner.stats.missileHits += 1;
      world.damage(ac, dmg, m.owner, 'missile');
      world.emit({ type: 'missileHit', missile: m, target: ac, damage: dmg, pos: copy(p1) });
      return;
    }
  }
  m.pos = p1;
  // miss detection: was close and is now opening
  if (m.target && m.target.alive && m.result == null) {
    const R = dist(m.pos, m.target.pos);
    if (m.minDist < 400 && R > m.minDist + 60) {
      m.result = m.decoy ? 'decoyed' : 'miss';
      m.guided = false; // overshot: the seeker can't come back around
      world.emit({ type: 'missileMiss', missile: m, decoyed: !!m.decoy });
    }
  }
  if (m.time > P.life || m.pos.y < 0) {
    m.alive = false;
    if (m.result == null) m.result = 'expired';
    world.emit({ type: 'missileExpire', missile: m, pos: copy(m.pos) });
  }
}

export function fireGun(world, ac, dt) {
  ac.gunCooldown -= dt;
  if (ac.gunCooldown > 0 || ac.gunRounds <= 0) return;
  ac.gunCooldown += 1 / GUN.rate;
  if (ac.gunCooldown < 0) ac.gunCooldown = 0;
  ac.gunRounds -= 1;
  const f = forwardOf(ac.q), right = rightOf(ac.q), up = upOf(ac.q);
  const rng = world.rng;
  const a = rng.gauss() * GUN.spread, b = rng.gauss() * GUN.spread;
  const dir = norm(addScaled(addScaled(f, right, a), up, b));
  world.bullets.push({
    owner: ac, pos: addScaled(addScaled(ac.pos, right, -1.0), f, 6),
    vel: add(scale(dir, GUN.speed), ac.vel), time: 0, alive: true,
  });
  ac.stats.roundsFired += 1;
  world.emit({ type: 'gunFire', ac });
}

export function stepBullet(world, b, dt) {
  if (!b.alive) return; // dead rounds stay in the array until pruned — never let them re-hit
  b.time += dt;
  const p1 = addScaled(b.pos, b.vel, dt);
  for (const ac of world.aircraft) {
    if (!ac.alive || ac === b.owner) continue;
    const relA = sub(b.pos, ac.pos);
    const relB = sub(p1, addScaled(ac.pos, ac.vel, dt));
    const { dist: d } = segmentPointDistance(relA, relB, { x: 0, y: 0, z: 0 });
    if (d < GUN.hitRadius) {
      b.alive = false;
      b.owner.stats.roundHits += 1;
      world.damage(ac, GUN.damage, b.owner, 'gun');
      world.emit({ type: 'gunHit', target: ac, pos: copy(p1), owner: b.owner });
      return;
    }
  }
  b.pos = p1;
  if (b.time > GUN.life) b.alive = false;
}

export function dropFlares(world, ac) {
  if (ac.flares <= 0) return false;
  ac.flares -= 1;
  ac.stats.flaresUsed += 1;
  const rng = world.rng;
  const f = forwardOf(ac.q), up = upOf(ac.q), right = rightOf(ac.q);
  const fl = [];
  for (let i = 0; i < FLARE.count; i++) {
    const s = i % 2 === 0 ? -1 : 1;
    const vel = add(scale(ac.vel, 0.55), add(scale(right, s * rng.range(25, 45)), scale(up, rng.range(-30, -5))));
    const flare = { pos: addScaled(ac.pos, f, -6), vel, time: 0, alive: true, owner: ac };
    world.flares.push(flare);
    fl.push(flare);
  }
  // each missile tracking this aircraft gets one decoy roll; IR seekers looking at the
  // hot tail (missile behind the target) are easier to spoof.
  for (const m of world.missiles) {
    if (!m.alive || m.target !== ac || !m.guided || m.decoy) continue;
    const R = dist(m.pos, ac.pos);
    if (R > FLARE.decoyRange) continue;
    const fromBehind = dot(norm(sub(m.pos, ac.pos)), f) < 0;
    const p = fromBehind ? 0.55 : 0.4;
    if (rng() < p) m.decoy = fl[Math.floor(rng() * fl.length)];
  }
  world.emit({ type: 'flares', ac });
  return true;
}

export function stepFlare(f, dt) {
  f.time += dt;
  f.vel = addScaled(scale(f.vel, 1 - 0.9 * dt), { x: 0, y: -G * 0.5, z: 0 }, dt);
  f.pos = addScaled(f.pos, f.vel, dt);
  if (f.time > FLARE.life) f.alive = false;
}
