// Simple scripted opponents used only as test baselines for the pilot AI.
import { sub, norm, addScaled, scale, clamp, dist, toBody, angleBetween, DEG } from '../sim/math.js';
import { gunLead, gunError, missilePk } from '../sim/fire.js';
import { PilotAI } from './pilot.js';

/** Non-maneuvering drone: flies straight and level, gentle turn back at the arena edge. */
export class StraightBot {
  constructor(ac) { this.ac = ac; this.mode = 'STRAIGHT'; this.helper = new PilotAI(ac, { skill: 'veteran' }); }
  update() {
    const p = this.ac.pos, f = this.ac.vel;
    let dir = norm({ x: f.x, y: 0, z: f.z });
    if (Math.hypot(p.x, p.z) > 8000) dir = addScaled(dir, norm({ x: -p.x, y: 0, z: -p.z }), 0.25);
    const c = this.helper.steer(dir, 0.3);
    c.throttle = 0.8;
    return c;
  }
}

/** Holds a constant level hard turn forever (tests that the AI can kill a circling target). */
export class CircleBot {
  constructor(ac, g = 0.85) { this.ac = ac; this.g = g; this.mode = 'CIRCLE'; this.helper = new PilotAI(ac, { skill: 'veteran' }); }
  update() {
    const f = this.ac.vel;
    const h = norm({ x: f.x, y: 0, z: f.z });
    const side = { x: -h.z, y: 0, z: h.x };
    const c = this.helper.steer(addScaled(h, side, 2), this.g);
    c.throttle = 1; c.boost = true;
    return c;
  }
}

/**
 * "Naive aggressive player": pure pursuit at max G, fires every time it has a lock,
 * guns whenever roughly on target, never defends. Approximates a new player mashing fire.
 */
export class ChaserBot {
  /** perfect=true: zero-latency, exact pure pursuit (superhuman stress test). */
  constructor(ac, { perfect = false, seed = 5 } = {}) {
    this.ac = ac; this.mode = 'CHASE'; this.perfect = perfect;
    this.helper = new PilotAI(ac, { skill: 'veteran', seed });
    this.helper.skill.reaction = perfect ? 0 : 0.3;
    this.t = 0; this.last = -9; this.noise = { x: 0, y: 0, z: 0 }; this.noiseT = 0;
  }
  update(dt, match) {
    this.t += dt;
    this.helper.t += dt;
    const tg = this.helper.perceive(match); // human-ish: sees the target with a reaction delay
    this.noiseT -= dt;
    if (this.noiseT <= 0 && !this.perfect) {
      // imprecise thumb on a touch stick: the aim point wanders by a few degrees
      this.noiseT = 0.5;
      const R = Math.hypot(tg.pos.x - this.ac.pos.x, tg.pos.y - this.ac.pos.y, tg.pos.z - this.ac.pos.z);
      const s = R * 0.04;
      this.noise = { x: this.helper.rng.gauss() * s, y: this.helper.rng.gauss() * s, z: this.helper.rng.gauss() * s };
    }
    const dir = sub(addScaled(tg.pos, this.noise, 1), this.ac.pos);
    if (this.ac.pos.y < 600) dir.y = Math.abs(dir.y) + 800;
    const c = this.helper.steer(dir, this.perfect ? 1 : 0.85);
    c.throttle = 1; c.boost = this.ac.speed < 240;
    if (this.ac.lock.locked && this.t - this.last > 3) { c.fireMissile = true; this.last = this.t; }
    const R = Math.hypot(dir.x, dir.y, dir.z);
    c.fireGun = R < 900 && this.ac.lock.ata < 3 * DEG;
    return c;
  }
}

/**
 * Human proxy: flies through the REAL player input path (PlayerController + assist mapping),
 * using only what the HUD shows — target box direction, lock, SHOOT cue, MISSILE warning —
 * with a reaction delay, imprecise thumb input and typical habits. Used to estimate whether a
 * player can win and how long fights last. It is a model of a player, not a player.
 */
export class HumanProxy {
  constructor(ac, { level = 'average', seed = 9, PlayerController } = {}) {
    this.ac = ac; this.mode = 'HUMAN';
    const L = level === 'good'
      ? { reaction: 0.25, noise: 0.1, think: 0.1, spam: 0.3, breakAt: 1700, flareAt: 1000, gunTol: 2.0 }
      : { reaction: 0.4, noise: 0.2, think: 0.16, spam: 0.6, breakAt: 1300, flareAt: 700, gunTol: 3.0 };
    if (globalThis.process?.env?.HP_OVERRIDE) Object.assign(L, JSON.parse(process.env.HP_OVERRIDE));
    this.L = L;
    this.helper = new PilotAI(ac, { skill: 'veteran', seed });
    this.helper.skill.reaction = L.reaction;
    this.rng = this.helper.rng;
    this.stick = { x: 0, y: 0 }; this.thinkT = 0; this.flared = new Set();
    this.wobble = { x: 0, y: 0 }; // thumb imprecision: smooth drift (Ornstein-Uhlenbeck), not white noise
    this.buttons = { boost: true, brake: false, gun: false };
    this.pressed = new Set();
    const self = this;
    this.fakeInput = {
      axes: () => ({ x: self.stick.x, y: self.stick.y, yaw: 0 }),
      boost: () => self.buttons.boost, brake: () => self.buttons.brake, gun: () => self.buttons.gun, look: () => false,
      consume: (n) => { const h = self.pressed.has(n); self.pressed.delete(n); return h; },
    };
    this.pc = new PlayerController(ac, this.fakeInput, { assist: true, invert: false });
  }
  update(dt, match) {
    this.helper.t += dt;
    const me = this.ac, L = this.L;
    const tg = this.helper.perceive(match);
    this.thinkT -= dt;
    if (this.thinkT <= 0) {
      this.thinkT = L.think;
      const r = sub(tg.pos, me.pos);
      const R = Math.hypot(r.x, r.y, r.z);
      // aim: the box, or the gun pipper when close
      let aim = tg.pos;
      if (R < 1200) aim = gunLead(me, tg.pos, tg.vel).point;
      const b = toBody(me.q, sub(aim, me.pos));
      const ahead = -b.z;
      const ax = Math.atan2(b.x, Math.max(ahead, 1)), ay = Math.atan2(b.y, Math.max(ahead, 1));
      let x, pull;
      if (ahead < 0) {
        // behind: hard turn toward the HUD arrow; like a human, commit to one side
        if (!this.behindSide || Math.abs(b.x) > 0.5 * R) this.behindSide = Math.sign(b.x || 1);
        x = this.behindSide; pull = 1;
      } else { this.behindSide = 0; x = clamp(ax / (35 * DEG), -1, 1); pull = clamp(ay / (12 * DEG), -1, 1); }
      // missile warning: break hard when it gets close, then flares
      let inbound = null;
      for (const m of match.missiles) if (m.alive && m.target === me && m.guided && !m.decoy) { const d = dist(m.pos, me.pos); if (!inbound || d < inbound.d) inbound = { m, d }; }
      if (inbound && inbound.d < L.breakAt) {
        const bm = toBody(me.q, sub(inbound.m.pos, me.pos));
        x = bm.x > 0 ? -1 : 1; pull = 1;
        if (inbound.d < L.flareAt && !this.flared.has(inbound.m.id) && me.flares > 0) { this.pressed.add('flare'); this.flared.add(inbound.m.id); }
      }
      if (me.pos.y < 700 && me.vel.y < -15) { x = 0; pull = 1; } // PULL UP
      const a = L.think / 0.6; // ~0.6 s correlation time
      this.wobble.x += -this.wobble.x * a + this.rng.gauss() * L.noise * Math.sqrt(2 * a);
      this.wobble.y += -this.wobble.y * a + this.rng.gauss() * L.noise * Math.sqrt(2 * a);
      x += this.wobble.x; pull += this.wobble.y;
      this.stick.x = clamp(x, -1, 1);
      this.stick.y = clamp(-pull, -1, 1); // default convention: pull = stick down
      // throttle habits: burner most of the time, brake if about to overshoot
      this.buttons.brake = R < 450 && ahead > 0 && me.speed > tg.speed + 40;
      this.buttons.boost = !this.buttons.brake;
      // weapons from HUD cues
      if (me.lock.locked && me.missiles > 0) {
        const los = scale(r, 1 / R);
        const aspect = Math.PI - angleBetween(tg.fwd, scale(los, -1));
        const pk = missilePk({ R, ata: me.lock.ata, aspect, mySpeed: me.speed, tgSpeed: tg.speed, tgG: tg.n });
        if (pk > 0.45 || this.rng() < L.spam * L.think) this.pressed.add('msl');
      }
      this.buttons.gun = R < 950 && ahead > 0 && gunError(me, gunLead(me, tg.pos, tg.vel).point) < L.gunTol * DEG;
    }
    return this.pc.update(dt, match);
  }
}
