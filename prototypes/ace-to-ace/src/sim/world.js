// Match state and rules: fixed-step simulation, damage, win/lose, timer, boundaries.
// No rendering here; the browser and the headless AI-vs-AI runner both drive this.
import { makeRng } from './math.js';
import { createAircraft, stepAircraft } from './aircraft.js';
import {
  updateLock, launchMissile, stepMissile, fireGun, stepBullet, dropFlares, stepFlare, FLARE,
} from './weapons.js';

export const RULES = {
  dt: 1 / 60,
  timeLimit: 300,          // 5 min regulation
  suddenDeath: 60,         // then next hit wins; after this a draw
  arenaRadius: 12000,      // horizontal combat area (m)
  ceiling: 10000,
  outOfBoundsGrace: 12,    // seconds outside before forfeit
};

export class Match {
  /**
   * @param {object} o
   * @param {number} o.seed
   * @param {object} o.blue  { type: 'F16V', name }
   * @param {object} o.red   { type: 'J16', name }
   * @param {object} [o.spawn] override spawn geometry
   */
  constructor(o) {
    this.rng = makeRng(o.seed ?? 1);
    this.seed = o.seed ?? 1;
    this.time = 0;
    this.tick = 0;
    this.nextId = 1;
    this.aircraft = [];
    this.missiles = [];
    this.bullets = [];
    this.flares = [];
    this.events = [];
    this.listeners = [];
    this.result = null; // { winner, loser, reason, time }
    this.phase = 'regulation'; // 'regulation' | 'sudden' | 'over'
    this.timeLimit = o.timeLimit ?? RULES.timeLimit;
    const sp = o.spawn || defaultSpawn(this.rng);
    this.blue = createAircraft(o.blue.type, 'blue', sp.blue.pos, sp.blue.fwd, sp.blue.speed);
    this.red = createAircraft(o.red.type, 'red', sp.red.pos, sp.red.fwd, sp.red.speed);
    // Legacy A remains the regression default; modes apply to both AI and human.
    const feel = ['arcade', 'tactical', 'B', 'A'].includes(o.flightFeel) ? o.flightFeel : 'A';
    this.blue.flightFeel = feel;
    this.red.flightFeel = feel;
    this.blue.callsign = o.blue.name || 'BLUE';
    this.red.callsign = o.red.name || 'RED';
    this.blue.enemy = this.red; this.red.enemy = this.blue;
    for (const ac of [this.blue, this.red]) { ac.oob = 0; ac.lastHitBy = null; }
    // arcade difficulty rule: scale damage a side takes (player side only, by difficulty)
    this.blue.damageScale = o.blue.damageScale ?? 1;
    this.red.damageScale = o.red.damageScale ?? 1;
    this.aircraft.push(this.blue, this.red);
    this.controllers = new Map(); // aircraft -> { update(dt, match) -> controls }
    this.log = [];
  }

  setController(ac, ctrl) { this.controllers.set(ac, ctrl); }
  on(fn) { this.listeners.push(fn); }
  emit(ev) {
    ev.time = this.time;
    this.events.push(ev);
    for (const fn of this.listeners) fn(ev);
  }

  damage(ac, amount, from, cause) {
    if (!ac.alive || this.result) return;
    amount *= ac.damageScale;
    ac.hp = Math.max(0, ac.hp - amount);
    ac.lastHitBy = from;
    if (from) from.stats.damageDealt += amount;
    this.emit({ type: 'damage', ac, amount, from, cause });
    if (this.phase === 'sudden' || ac.hp <= 0) this.kill(ac, cause, from);
  }

  kill(ac, cause, by) {
    if (!ac.alive) return;
    ac.alive = false; ac.hp = 0; ac.deathCause = cause;
    this.emit({ type: 'destroyed', ac, cause, by, pos: { ...ac.pos } });
    const other = ac === this.blue ? this.red : this.blue;
    this.finish(other.alive ? other : null, ac, cause);
  }

  finish(winner, loser, reason) {
    if (this.result) return;
    this.result = { winner, loser, reason, time: this.time };
    this.phase = 'over';
    this.emit({ type: 'matchOver', ...this.result });
  }

  step(dt = RULES.dt) {
    if (this.phase === 'over') {
      // keep the world animating (missiles/flares/wreck) but no more rules
      this.stepProjectiles(dt);
      for (const ac of this.aircraft) if (ac.alive) stepAircraft(ac, dt);
      this.time += dt;
      return;
    }
    this.tick += 1;
    for (const ac of this.aircraft) ac.lockedBy = 0;
    for (const ac of this.aircraft) updateLock(ac, ac.enemy, dt);

    for (const ac of this.aircraft) {
      if (!ac.alive) continue;
      const ctrl = this.controllers.get(ac);
      if (ctrl) {
        const c = ctrl.update(dt, this);
        if (c) Object.assign(ac.controls, c);
      }
      const c = ac.controls;
      ac.railCooldown[0] = Math.max(0, ac.railCooldown[0] - dt);
      ac.railCooldown[1] = Math.max(0, ac.railCooldown[1] - dt);
      if (ac.flares < ac.type.flares) {
        ac.flareRecharge += dt;
        if (ac.flareRecharge >= FLARE.recharge) { ac.flares += 1; ac.flareRecharge = 0; }
      }
      if (c.fireMissile) { launchMissile(this, ac); c.fireMissile = false; }
      if (c.fireGun) fireGun(this, ac, dt); else ac.gunCooldown = Math.max(0, ac.gunCooldown - dt);
      if (c.flare) { dropFlares(this, ac); c.flare = false; }
      stepAircraft(ac, dt);
      // sea / ceiling / arena
      if (ac.pos.y <= 2) { ac.pos.y = 2; this.kill(ac, 'crash', ac.lastHitBy); continue; }
      const horiz = Math.hypot(ac.pos.x, ac.pos.z);
      if (horiz > RULES.arenaRadius || ac.pos.y > RULES.ceiling) {
        ac.oob += dt;
        if (ac.oob > RULES.outOfBoundsGrace) this.kill(ac, 'outOfBounds', null);
      } else ac.oob = Math.max(0, ac.oob - dt * 2);
    }
    this.stepProjectiles(dt);
    this.time += dt;

    if (!this.result) {
      if (this.phase === 'regulation' && this.time >= this.timeLimit) {
        const b = this.blue.hp, r = this.red.hp;
        if (b !== r) this.finish(b > r ? this.blue : this.red, b > r ? this.red : this.blue, 'timeDecision');
        else { this.phase = 'sudden'; this.emit({ type: 'suddenDeath' }); }
      } else if (this.phase === 'sudden' && this.time >= this.timeLimit + RULES.suddenDeath) {
        this.finish(null, null, 'draw');
      }
    }
  }

  stepProjectiles(dt) {
    for (const m of this.missiles) stepMissile(this, m, dt);
    for (const b of this.bullets) stepBullet(this, b, dt);
    for (const f of this.flares) if (f.alive) stepFlare(f, dt);
    if (this.tick % 30 === 0) {
      this.missiles = this.missiles.filter((m) => m.alive);
      this.bullets = this.bullets.filter((b) => b.alive);
      this.flares = this.flares.filter((f) => f.alive);
    } else {
      // bullets churn fast; prune them every step
      if (this.bullets.length > 64) this.bullets = this.bullets.filter((b) => b.alive);
    }
  }
}

/** Default arcade opening: two fighters approach roughly head-on, ~7 km apart. */
export function defaultSpawn(rng) {
  const sep = rng.range(6500, 8000);
  const off = rng.range(-1200, 1200);
  const altB = rng.range(2600, 3600), altR = rng.range(2600, 4000);
  const heading = rng.range(0, Math.PI * 2);
  const dir = { x: Math.sin(heading), y: 0, z: -Math.cos(heading) };
  const lat = { x: -dir.z, y: 0, z: dir.x };
  const blue = { pos: { x: -dir.x * sep / 2 + lat.x * off / 2, y: altB, z: -dir.z * sep / 2 + lat.z * off / 2 }, fwd: dir, speed: 230 };
  const red = { pos: { x: dir.x * sep / 2 - lat.x * off / 2, y: altR, z: dir.z * sep / 2 - lat.z * off / 2 }, fwd: { x: -dir.x, y: 0, z: -dir.z }, speed: 230 };
  return { blue, red };
}

/** Randomised geometry for AI-vs-AI testing (any relative heading). */
export function randomSpawn(rng) {
  const sep = rng.range(3500, 8500);
  const brg = rng.range(0, Math.PI * 2);
  const blue = { pos: { x: 0, y: rng.range(1500, 5000), z: 0 } };
  const red = { pos: { x: Math.sin(brg) * sep, y: rng.range(1500, 5000), z: -Math.cos(brg) * sep } };
  const hb = rng.range(0, Math.PI * 2), hr = rng.range(0, Math.PI * 2);
  blue.fwd = { x: Math.sin(hb), y: 0, z: -Math.cos(hb) };
  red.fwd = { x: Math.sin(hr), y: 0, z: -Math.cos(hr) };
  blue.speed = rng.range(180, 280); red.speed = rng.range(180, 280);
  // centre the pair
  const cx = red.pos.x / 2, cz = red.pos.z / 2;
  blue.pos.x -= cx; blue.pos.z -= cz; red.pos.x -= cx; red.pos.z -= cz;
  return { blue, red };
}
