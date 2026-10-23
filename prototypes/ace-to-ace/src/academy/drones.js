// Scripted training aircraft for the Academy. They fly the SAME shared flight
// model through the AI's existing lift-vector controller (PilotAI.steer); only
// their intent is scripted. No special physics, no hidden advantages.
import { PilotAI } from '../ai/pilot.js';
import { launchMissile } from '../sim/weapons.js';
import { clamp, DEG } from '../sim/math.js';
import { headingOf } from '../sim/aircraft.js';

function holdSpeed(c, ac, v) {
  const e = v - ac.speed;
  c.boost = e > 25; c.brake = e < -35;
  c.throttle = clamp(0.6 + e / 60, 0, 1);
  return c;
}

/** Straight and level at a fixed heading / altitude / speed. */
export class StraightDrone {
  constructor(ac, { speed = 220, alt = null } = {}) {
    this.ac = ac; this.speed = speed; this.alt = alt ?? ac.pos.y; this.hdg = headingOf(ac);
    this.helper = new PilotAI(ac, { skill: 'veteran', seed: 1 });
  }
  update() {
    const climb = clamp((this.alt - this.ac.pos.y) / 300, -0.25, 0.25);
    const dir = { x: Math.sin(this.hdg), y: climb, z: -Math.cos(this.hdg) };
    return holdSpeed(this.helper.steer(dir, 0.4), this.ac, this.speed);
  }
}

/** Level turn at a steady rate, reversing direction every `reverseEvery` seconds. */
export class TurnDrone {
  constructor(ac, { speed = 230, rate = 9, reverseEvery = 0, alt = null, side = 1 } = {}) {
    this.ac = ac; this.speed = speed; this.rate = rate * DEG; this.alt = alt ?? ac.pos.y;
    this.reverseEvery = reverseEvery; this.side = side; this.t = 0;
    this.hdg = headingOf(ac);
    this.helper = new PilotAI(ac, { skill: 'veteran', seed: 2 });
  }
  update(dt) {
    this.t += dt;
    if (this.reverseEvery && this.t > this.reverseEvery) { this.t = 0; this.side = -this.side; }
    // stay near the middle of the training area (turn the long way home when far out)
    const far = Math.hypot(this.ac.pos.x, this.ac.pos.z);
    if (far > 6000) {
      const home = Math.atan2(-this.ac.pos.x, this.ac.pos.z);
      const err = Math.atan2(Math.sin(home - this.hdg), Math.cos(home - this.hdg));
      if (Math.abs(err) > 0.3) this.side = Math.sign(err);
    }
    this.hdg += this.side * this.rate * dt;
    const look = this.hdg + this.side * this.rate * 1.2;
    const climb = clamp((this.alt - this.ac.pos.y) / 300, -0.2, 0.2);
    const dir = { x: Math.sin(look), y: climb, z: -Math.cos(look) };
    return holdSpeed(this.helper.steer(dir, 0.9), this.ac, this.speed);
  }
}

/** Fire one guided missile from `shooter` at `target` (instructor-scripted launch). */
export function scriptedLaunch(match, shooter, target) {
  shooter.lock.target = target; shooter.lock.locked = true; shooter.lock.timer = 1;
  shooter.railCooldown[0] = 0;
  if (shooter.missiles < 1) shooter.missiles = 1;
  return launchMissile(match, shooter);
}
