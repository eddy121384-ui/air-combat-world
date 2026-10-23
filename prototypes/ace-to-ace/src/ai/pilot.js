// Pilot AI: a classic, deterministic game AI (no ML, no network).
//
// Layers
//  1. Perception   — sees the opponent through a reaction delay (dead-reckoned), hears
//                    missile launches/locks via an RWR-style warning. Never reads player input.
//  2. Assessment   — BFM geometry: range, ATA (my nose to it), aspect (am I at its six?),
//                    its ATA on me, closure, specific-energy difference, missile threats.
//  3. Tactics      — mode selection with priorities, dwell time and hysteresis:
//                    ENGAGE, ATTACK, DEFEND, EVADE, EXTEND (+ stalemate breakers).
//                    An aggression meter rises when nothing is happening, so the AI can't
//                    run away forever; taking hits makes it briefly cautious.
//  4. Maneuver     — lift-vector controller turns a desired flight direction into the same
//                    stick/throttle inputs the player uses. Flight limits are identical.
import {
  sub, add, scale, addScaled, dot, cross, len, norm, clamp, lerp, angleBetween, perp, dist,
  G, UP, DEG, toBody, forwardOf, upOf, rightOf, makeRng, smoothstep,
} from '../sim/math.js';
import { availableG, pitchForG, specificEnergy } from '../sim/aircraft.js';
import { RULES } from '../sim/world.js';
import { gunLead, gunError, missilePk } from '../sim/fire.js';
import { GUN, MISSILE } from '../sim/weapons.js';
import { pickLine } from './radio.js';

// Difficulty = pilot quality. Same aircraft, same physics, same weapons for every level.
// `tactics` gates the advanced moves (forcing/return shots, lag & yo-yo, stalemate breakers,
// brake reversals): a rookie mostly pure-pursues and overshoots; an ace uses everything.
export const SKILLS = {
  rookie: {
    reaction: 0.6, gUse: 0.78, aimSigma: 1.3 * DEG, gunTol: 2.6 * DEG, leadAccel: 0,
    minShotGap: 8, pkBias: 0.1, evadeTTG: 2.8, flareTTG: [0.3, 3.0], smart: 0.2, burst: [0.3, 0.7], tactics: 0.3,
  },
  veteran: {
    reaction: 0.38, gUse: 0.9, aimSigma: 0.8 * DEG, gunTol: 1.9 * DEG, leadAccel: 0.5,
    minShotGap: 5.5, pkBias: 0.02, evadeTTG: 3.8, flareTTG: [0.8, 2.0], smart: 0.6, burst: [0.4, 1.0], tactics: 0.8,
  },
  ace: {
    reaction: 0.26, gUse: 0.97, aimSigma: 0.45 * DEG, gunTol: 1.5 * DEG, leadAccel: 0.9,
    minShotGap: 4, pkBias: -0.03, evadeTTG: 4.5, flareTTG: [1.0, 1.6], smart: 0.9, burst: [0.6, 1.2], tactics: 1,
  },
};

/** Damage the PLAYER takes per difficulty (arcade rule, shown on the title screen). */
export const PLAYER_DAMAGE_SCALE = { rookie: 0.75, veteran: 1.0, ace: 1.0 };

const MODES = ['ENGAGE', 'ATTACK', 'DEFEND', 'EVADE', 'EXTEND'];

export class PilotAI {
  constructor(ac, opts = {}) {
    this.ac = ac;
    this.skillName = opts.skill || 'veteran';
    this.skill = { ...SKILLS[this.skillName] };
    this.rng = makeRng(opts.seed ?? 11);
    this.baseAggr = opts.aggression ?? 0.55;
    this.aggr = this.baseAggr;
    this.mode = 'ENGAGE';
    this.modeT = 0;
    this.reason = 'initial contact';
    this.pending = null; this.pendingN = 0;
    this.hist = [];
    this.decT = 0;
    this.t = 0;
    this.lastShotT = -99;
    this.lastWeaponT = 0;
    this.extendCooldown = 0;
    this.breakSide = 0;
    this.jinkT = 0;
    this.brakeTrap = null;
    this.brakeAttempts = 0;
    this.brakeSuccesses = 0;
    this.lastBrakeT = -99;
    this.onTactic = opts.onTactic || null;
    this.burstT = 0;
    this.holdAfterShot = 0;
    this.flareAt = null;
    this.approach = this.rng() < 0.5 ? 'offset' : 'direct';
    this.offsetSide = this.rng.sign();
    this.stale = { flag: false, since: 0, samples: [], breaker: null, breakerT: 0 };
    this.timeInMode = Object.fromEntries(MODES.map((m) => [m, 0]));
    this.transitions = [];
    this.radio = []; // { time, text, mode }
    this.radioCooldown = 0;
    this.debug = {};
    this.lastHp = ac.hp;
    this.aimNoise = { x: 0, y: 0, z: 0 };
    this.aimNoiseT = 0;
    this.onRadio = opts.onRadio || null;
    // opponent model: does this opponent defend against my missiles? (0 = never, 1 = always)
    this.oppEvades = 0.6;
    this.watched = new Set();
  }

  // ---------------- perception ----------------
  perceive(match) {
    const tg = this.ac.enemy;
    this.hist.push({ t: this.t, pos: { ...tg.pos }, vel: { ...tg.vel }, q: { ...tg.q }, speed: tg.speed, n: tg.nCur, alive: tg.alive });
    const cutoff = this.t - 2;
    while (this.hist.length > 2 && this.hist[0].t < cutoff) this.hist.shift();
    const want = this.t - this.skill.reaction;
    let s = this.hist[0];
    for (let i = this.hist.length - 1; i >= 0; i--) if (this.hist[i].t <= want) { s = this.hist[i]; break; }
    // estimate acceleration from 0.3 s of (delayed) history
    let acc = { x: 0, y: 0, z: 0 };
    const older = this.hist.find((h) => h.t >= s.t - 0.3) || s;
    if (s.t - older.t > 0.05) acc = scale(sub(s.vel, older.vel), 1 / (s.t - older.t));
    const lag = this.t - s.t;
    return {
      pos: addScaled(s.pos, s.vel, lag), vel: s.vel, q: s.q, speed: s.speed, n: s.n, acc, alive: s.alive,
      fwd: forwardOf(s.q),
    };
  }

  knownThreats(match) {
    const me = this.ac;
    const out = [];
    for (const m of match.missiles) {
      if (!m.alive || m.target !== me || !m.guided || m.decoy) continue;
      const r = sub(m.pos, me.pos);
      const R = len(r);
      const vc = dot(r, sub(me.vel, m.vel)) / R; // closing speed (+ = approaching)
      // threat discrimination: a missile that isn't closing fast, or isn't pointed at me,
      // can't hit — a good pilot keeps fighting instead of reacting to every launch
      if (vc < 110 || m.time < 0.2) continue;
      const aimErr = angleBetween(m.vel, scale(r, -1));
      if (aimErr > 50 * DEG) continue;
      const ttg = R / vc;
      // kinematics: a missile that will burn out / time out before reaching me is not a threat
      // (experienced pilots judge this; rookies react to everything)
      const lifeLeft = MISSILE.life - m.time;
      if (ttg > lifeLeft * 0.95 && this.useTactic('kinematic', 2)) continue;
      out.push({ m, R, vc, ttg, dir: scale(r, 1 / R) });
    }
    out.sort((a, b) => a.ttg - b.ttg);
    return out;
  }

  // ---------------- assessment ----------------
  assess(match, tg) {
    const me = this.ac;
    const f = forwardOf(me.q);
    const r = sub(tg.pos, me.pos);
    const R = len(r);
    const los = scale(r, 1 / R);
    const ata = angleBetween(f, los);
    const tgtAta = angleBetween(tg.fwd, scale(los, -1));
    const aspect = Math.PI - tgtAta;
    const vc = -dot(r, sub(tg.vel, me.vel)) / R;
    const myE = specificEnergy(me);
    const tgE = tg.pos.y + tg.speed * tg.speed / (2 * G);
    const dE = myE - tgE;
    const adv = (tgtAta - ata) / Math.PI; // +1 offensive, -1 defensive
    const threats = this.knownThreats(match);
    const pk = me.lock.locked && me.lock.target === me.enemy
      ? missilePk({ R, ata, aspect, mySpeed: me.speed, tgSpeed: tg.speed, tgG: tg.n }) : 0;
    const corner = me.type.cornerSpeed;
    return { f, r, R, los, ata, tgtAta, aspect, vc, dE, adv, threats, pk, corner, tg };
  }

  /**
   * Skill gate for an advanced move: rolled once per `window` seconds per move, so a rookie
   * isn't flickering between knowing and not knowing a tactic every frame.
   */
  useTactic(name, window) {
    this.tacticRoll = this.tacticRoll || {};
    const r = this.tacticRoll[name];
    if (!r || this.t - r.t > window) this.tacticRoll[name] = { t: this.t, ok: this.rng() < this.skill.tactics };
    return this.tacticRoll[name].ok;
  }

  /** Learn whether the opponent defends against missiles (watch its G when mine are close). */
  readOpponent(match) {
    const tg = this.ac.enemy;
    for (const m of match.missiles) {
      if (m.owner !== this.ac || !m.alive || !m.guided || this.watched.has(m.id)) continue;
      const R = dist(m.pos, tg.pos);
      if (R < 900) {
        this.watched.add(m.id);
        const evading = tg.nCur > 4 || tg.flares < tg.type.flares && tg.flareRecharge < 2;
        this.oppEvades += ((evading ? 1 : 0) - this.oppEvades) * 0.35;
      }
    }
  }

  // ---------------- tactics ----------------
  decide(match, S) {
    const me = this.ac, sk = this.skill;
    const threat = S.threats[0];
    let want = this.mode, why = this.reason;

    // threatened: bandit in my rear hemisphere with its nose coming onto me
    const threatened = (S.ata > 95 * DEG && S.tgtAta < 65 * DEG && S.R < 2500)
      || (S.tgtAta < 40 * DEG && S.R < 2300 && S.ata > 75 * DEG)
      || (me.lockedBy > 0 && S.tgtAta < 25 * DEG && S.R < 3200 && S.ata > 60 * DEG);
    const offensive = S.ata < 75 * DEG && (S.aspect < 110 * DEG || S.R > 2500);
    const lowEnergy = me.speed < S.corner * 0.62;
    const canExtend = this.extendCooldown <= 0 && this.aggr < 0.8;

    if (threat && threat.ttg < sk.evadeTTG && threat.R < 5500) {
      want = 'EVADE'; why = `missile ${Math.round(threat.R)}m ttg ${threat.ttg.toFixed(1)}s`;
    } else if (this.mode === 'EXTEND' && !this.extendDone(S)) {
      want = 'EXTEND'; why = this.reason;
    } else if (threatened) {
      want = 'DEFEND'; why = `bandit on my six ${Math.round(S.R)}m, its ATA ${Math.round(S.tgtAta / DEG)}°`;
      // out of ideas while defending with energy to spare: break away and reset
      if (this.mode === 'DEFEND' && this.modeT > 14 && canExtend && S.R > 1600 && me.speed > S.corner) {
        want = 'EXTEND'; why = 'defensive stalemate, separating';
      }
    } else if (lowEnergy && canExtend && S.R > 1500 && S.tgtAta > 50 * DEG && !offensive) {
      want = 'EXTEND'; why = `low energy ${Math.round(me.speed)}m/s, rebuilding`;
    } else if (this.stale.flag && this.stale.breaker === 'extend' && this.extendCooldown <= 0) {
      // a reset is allowed even when aggressive: it is how a deadlocked circle gets broken
      want = 'EXTEND'; why = 'turning stalemate, resetting the fight';
    } else if (S.R > this.mergeRange(S) && !(S.aspect < 90 * DEG && S.ata < 45 * DEG)) {
      want = 'ENGAGE'; why = `setting up from ${(S.R / 1000).toFixed(1)}km`;
    } else {
      want = 'ATTACK'; why = offensive ? `nose on, ATA ${Math.round(S.ata / DEG)}° aspect ${Math.round(S.aspect / DEG)}°` : 'turning for angles';
    }

    // hysteresis: non-urgent switches need two consecutive votes and a minimum dwell
    if (want !== this.mode) {
      const urgent = want === 'EVADE' || want === 'DEFEND' && this.mode !== 'EVADE';
      const dwellOk = this.modeT > (this.mode === 'EXTEND' ? 3 : 1.0);
      if (this.pending === want) this.pendingN += 1; else { this.pending = want; this.pendingN = 1; }
      if (urgent || (dwellOk && this.pendingN >= 2)) this.setMode(want, why, match);
    } else {
      this.pending = null; this.reason = why;
    }
  }

  /** Range at which the setup ends and the turning fight starts (lead turn before a merge). */
  mergeRange(S) {
    const me = this.ac;
    const radius = me.speed * me.speed / (availableG(me) * G * 0.8);
    const headOn = S.tgtAta < 60 * DEG ? 1 : 0;
    return clamp(2 * radius + headOn * Math.max(0, S.vc) * 1.2, 1400, 3600);
  }

  extendDone(S) {
    const me = this.ac;
    if (S.threats.length) return true;
    // it turned its nose onto me: stop running and fight (good pilots notice from further out)
    if (S.tgtAta < 25 * DEG && S.R < (this.useTactic('extendWatch', 3) ? 2600 : 1500)) return true;
    const reset = this.reason.startsWith('turning stalemate');
    const maxT = reset ? 9 : 5 + 5 * (1 - this.aggr);
    if (reset) return (S.R > 3200 && me.speed > 260) || this.modeT > maxT;
    return (S.R > 3600 && this.modeT > 3) || (me.speed > 320 && this.modeT > 2.5) || this.modeT > maxT;
  }

  setMode(mode, why, match) {
    const prev = this.mode;
    this.transitions.push({ t: this.t, from: prev, to: mode, why });
    if (this.transitions.length > 200) this.transitions.shift();
    this.mode = mode; this.modeT = 0; this.reason = why; this.pending = null;
    if (prev === 'EXTEND') this.extendCooldown = 14;
    if (mode === 'DEFEND') this.breakSide = 0;
    if (mode === 'EXTEND') this.extendSide = this.rng.sign();
    if (mode === 'ENGAGE') { this.approach = this.rng() < 0.45 + 0.3 * this.aggr ? 'direct' : 'offset'; this.offsetSide = this.rng.sign(); }
    this.say(mode === 'ATTACK' && prev === 'DEFEND' ? 'reversal' : mode, match);
  }

  say(key, match, force = false) {
    if (!force && this.radioCooldown > 0) return;
    const text = pickLine(key, this.rng);
    if (!text) return;
    this.radioCooldown = 6.5;
    const msg = { time: this.t, text, key };
    this.radio.push(msg);
    if (this.onRadio) this.onRadio(msg);
  }

  updateStalemate(S, dt) {
    const st = this.stale;
    if (this.decCount % 5 === 0) {
      st.samples.push({ t: this.t, adv: S.adv, R: S.R, g: this.ac.nCur, hp: this.ac.hp + this.ac.enemy.hp, v: this.ac.speed, ata: S.ata });
      while (st.samples.length && st.samples[0].t < this.t - 12) st.samples.shift();
    }
    if (st.flag) {
      st.breakerT -= dt;
      if (st.breakerT <= 0) { st.flag = false; st.breaker = null; st.samples = []; }
      return;
    }
    const s = st.samples;
    if (s.length < 20 || s[s.length - 1].t - s[0].t < 11) return;
    const advs = s.map((x) => x.adv);
    const Rs = s.map((x) => x.R);
    const spread = Math.max(...advs) - Math.min(...advs);
    const turning = s.filter((x) => x.g > 2.5).length / s.length;
    const close = Math.max(...Rs) < 3000;
    const noProgress = s[0].hp === s[s.length - 1].hp; // misses don't count as progress
    const slow = s.filter((x) => x.v < this.ac.type.cornerSpeed * 0.75).length / s.length > 0.6;
    const meanAdv = advs.reduce((a, b) => a + b, 0) / advs.length;
    // ahead on angles is only progress if it ever turns into a shot: in a level circle of two
    // equal turners, "40° behind its tail" can last forever
    const neverNoseOn = Math.min(...s.map((x) => x.ata)) > 22 * DEG;
    if (close && turning > 0.5 && spread < 0.4 && noProgress && (meanAdv < 0.35 || neverNoseOn)) {
      st.flag = true;
      const energyOk = this.ac.speed > this.ac.type.cornerSpeed || S.dE > 600;
      // escalate: if the last breaker (<45 s ago) didn't change anything, reset the fight
      const repeat = st.lastT != null && this.t - st.lastT < 45;
      const low = this.ac.pos.y < 1500;
      // a less skilled pilot just bugs out (which hands the opponent a shot); a good one picks
      st.breaker = slow || repeat || !this.useTactic('breaker', 1) ? 'extend'
        : energyOk && !low && this.rng() < 0.6 ? 'vertical' : this.rng() < 0.5 ? 'reverse' : 'extend';
      st.breakerT = st.breaker === 'vertical' ? 7 : st.breaker === 'extend' ? 2 : 5;
      st.lastT = this.t;
      st.count = (st.count || 0) + 1;
      this.reason = `stalemate → ${st.breaker}`;
      this.transitions.push({ t: this.t, from: this.mode, to: this.mode, why: `stalemate breaker: ${st.breaker}` });
      this.say(`stale_${st.breaker}`, null);
    }
  }

  // ---------------- main update ----------------
  update(dt, match) {
    const me = this.ac;
    this.t += dt;
    this.lastDt = dt;
    this.modeT += dt;
    this.timeInMode[this.mode] += dt;
    this.extendCooldown = Math.max(0, this.extendCooldown - dt);
    this.radioCooldown = Math.max(0, this.radioCooldown - dt);
    this.holdAfterShot = Math.max(0, this.holdAfterShot - dt);
    if (!me.alive) return null;

    const tg = this.perceive(match);
    const S = this.assess(match, tg);
    this.S = S;

    // aggression dynamics (anti-avoidance)
    // react to a meaningful hit (a missile or a real burst), not to every single gun round
    if (this.lastHp - me.hp >= 10) {
      if (this.t - (this.lastHitReactT ?? -99) > 2) { this.aggr = Math.max(0.15, this.aggr - 0.18); this.say('hit', match, true); this.lastHitReactT = this.t; }
      this.lastHp = me.hp;
    } else if (me.hp > this.lastHp) this.lastHp = me.hp;
    const idle = this.t - this.lastWeaponT;
    this.aggr += dt * ((idle > 12 ? 0.014 : 0) + (S.R > 4000 ? 0.02 : 0) + (this.aggr < this.baseAggr ? 0.01 : 0));
    this.aggr = clamp(this.aggr, 0.1, 1);

    this.readOpponent(match);
    this.decT -= dt;
    this.decCount = (this.decCount || 0) + 1;
    if (this.decT <= 0) { this.decT = 0.1; this.decide(match, S); }
    this.updateStalemate(S, dt);

    let cmd;
    switch (this.mode) {
      case 'EVADE': cmd = this.doEvade(S, match); break;
      case 'DEFEND': cmd = this.doDefend(S, dt); break;
      case 'EXTEND': cmd = this.doExtend(S); break;
      case 'ATTACK': cmd = this.doAttack(S, dt); break;
      default: cmd = this.doEngage(S);
    }
    // The pass can change our strategic mode; finish the tactical action only if safe.
    const trapCmd = this.brakeTrapCommand(S, match);
    if (trapCmd) cmd = trapCmd;
    cmd = this.safety(cmd, S);
    const out = this.steer(cmd.dir, cmd.g ?? 1, cmd);
    this.throttle(out, cmd);
    this.weapons(out, S, dt, match, cmd);

    this.debug = {
      mode: this.mode, reason: this.reason, R: S.R, ata: S.ata / DEG, tgtAta: S.tgtAta / DEG,
      aspect: S.aspect / DEG, vc: S.vc, dE: S.dE, aggr: this.aggr, pk: S.pk, speed: me.speed,
      g: me.nCur, stale: this.stale.flag ? this.stale.breaker : '', maneuver: cmd.name || '',
      threats: S.threats.length, flares: me.flares, missiles: me.missiles, oppEvades: this.oppEvades,
      brakeTrap: this.brakeTrap?.phase || '', brakeAttempts: this.brakeAttempts, brakeSuccesses: this.brakeSuccesses,
    };
    return out;
  }

  // ---------------- behaviours ----------------
  doEngage(S) {
    const me = this.ac, tg = S.tg;
    const closing = Math.max(150, me.speed + tg.speed * Math.max(0, Math.cos(S.aspect)));
    const tl = clamp(S.R / closing, 0, 10) * 0.45;
    let aim = addScaled(tg.pos, tg.vel, tl);
    // altitude: try to arrive a little higher than the bandit, climb if energy-poor
    const wantAlt = clamp(tg.pos.y + (S.dE < -400 ? 1200 : 500), 1200, 7500);
    aim.y += clamp((wantAlt - me.pos.y) * 1.5, -S.R * 0.35, S.R * 0.45);
    let name = 'intercept';
    if (this.approach === 'offset' && S.tgtAta < 50 * DEG && S.R > 2500) {
      // offset for a lead turn instead of a pure head-on pass
      const lat = norm(cross(S.los, UP));
      aim = addScaled(aim, lat, this.offsetSide * clamp(S.R * 0.18, 600, 1500));
      name = 'offset lead-turn setup';
    }
    return { dir: sub(aim, me.pos), g: 0.7, speed: 270, name, nose: S.ata < 20 * DEG };
  }

  doAttack(S, dt) {
    const me = this.ac, tg = S.tg, sk = this.skill;
    const corner = S.corner;
    let aim, name, g = sk.gUse, speed = corner * 1.08;
    const R = S.R;
    if (R < 1300) {
      // gun/close-range: lead pursuit on the gun solution (with noisy aim)
      const lead = gunLead(me, tg.pos, tg.vel, scale(tg.acc, sk.leadAccel));
      this.aimNoiseT -= dt;
      if (this.aimNoiseT <= 0) {
        this.aimNoiseT = 0.35;
        const s = sk.aimSigma * R;
        this.aimNoise = { x: this.rng.gauss() * s, y: this.rng.gauss() * s, z: this.rng.gauss() * s };
      }
      aim = add(lead.point, this.aimNoise);
      name = 'gun pursuit';
      // overshoot protection: too much closure / angle -> lag & go out of plane (high yo-yo)
      if (S.vc > 70 && R < 900 && S.aspect > 35 * DEG && this.useTactic('lag', 2)) {
        aim = addScaled(addScaled(tg.pos, tg.fwd, -350), UP, R * 0.5);
        name = 'lag + high yo-yo';
        speed = corner * 0.9;
      }
      if (S.vc > 40 && R < 500) speed = Math.min(speed, tg.speed - 10);
    } else {
      const tl = clamp(R / 700, 0.4, 2.5);
      aim = addScaled(tg.pos, tg.vel, tl);
      name = 'lead pursuit';
      speed = R > 2200 ? 330 : corner * 1.12;
    }
    // stalemate breakers
    if (this.stale.flag) {
      if (this.stale.breaker === 'vertical') {
        // high yo-yo: climb out of the circle's plane, then roll over and dive onto the lead
        if (this.stale.breakerT > 3.5) { aim = addScaled(tg.pos, UP, R * 0.8 + 700); name = 'high yo-yo: climb'; speed = 400; }
        else { name = 'high yo-yo: dive onto lead'; g = sk.gUse; }
      } else if (this.stale.breaker === 'reverse') {
        // reverse the turn: aim to the other side of the bandit's flight path
        const side = norm(cross(tg.fwd, UP));
        const s = dot(sub(me.pos, tg.pos), side) > 0 ? -1 : 1;
        aim = addScaled(addScaled(tg.pos, side, s * 900), UP, -200);
        name = 'reversal (scissors)';
        speed = corner * 0.85;
      }
    } else if (S.dE < -900 && S.ata > 90 * DEG && me.pos.y > 1800 && this.useTactic('lowyoyo', 3)) {
      // energy-poor and behind on angles: low yo-yo, trade altitude for turn
      aim = addScaled(aim, UP, -R * 0.4);
      name = 'low yo-yo';
    }
    // energy management: below ~70% corner speed, stop bleeding — ease the pull and
    // let the nose fall to rebuild speed (a human ace does this; a circling bot does not)
    const slowF = smoothstep(0.55 * corner, 0.8 * corner, me.speed);
    const banditBehind = S.ata > 90 * DEG && R < 2000;
    if (slowF < 1 && !(R < 900 && S.ata < 15 * DEG) && !banditBehind) {
      g = Math.min(g, lerp(0.35, g, slowF));
      if (me.pos.y > 1200) aim = addScaled(aim, UP, -R * 0.5 * (1 - slowF));
      speed = 400;
      if (slowF < 0.5) name += ' (unload for speed)';
    }
    if (this.holdAfterShot > 0) { g = Math.min(g, 0.6); name += ' (guiding)'; }
    return { dir: sub(aim, me.pos), g, speed, name, nose: true };
  }

  doDefend(S, dt) {
    const me = this.ac, tg = S.tg, sk = this.skill;
    const f = S.f;
    // break turn into the attacker: put its position on my lift vector
    const toward = norm(sub(tg.pos, me.pos));
    let side = perp(toward, f);
    if (len(side) < 0.15) {
      // directly behind: pick a side and stick with it
      if (!this.breakSide) this.breakSide = this.rng.sign();
      side = scale(rightOf(me.q), this.breakSide);
    }
    side = norm(side);
    let dir = add(scale(side, 2.2), f);
    let name = 'break turn';
    let speed = S.corner;
    let g = sk.gUse;
    // nose-low break uses gravity when there's altitude to spare
    if (me.pos.y > 2200) dir = addScaled(dir, UP, -0.35);
    // big energy edge: go vertical where a slower bandit can't follow
    if (S.dE > 900 && me.speed > S.corner && S.R > 700) {
      dir = add(scale(UP, 2), scale(side, 0.6)); name = 'vertical escape'; speed = 400;
    }
    // Trigger only if a *faster* pursuer really closes from behind.
    if (!this.brakeTrap && this.canBrakeTrap(S)) {
      this.brakeTrap = { phase: 'brake', start: this.t, forward: { ...f } };
      this.lastBrakeT = this.t;
      this.brakeAttempts++;
      this.transitions.push({ t: this.t, from: 'DEFEND', to: 'DEFEND', why: 'brake trap: faster pursuer from six' });
      if (this.onTactic) this.onTactic({ type: 'brakeStart', time: this.t, range: S.R });
    }
    // inside gun range: jink (periodic reversals) to spoil the solution
    if (S.R < 1000 && S.tgtAta < 12 * DEG) {
      this.jinkT -= dt;
      if (this.jinkT <= 0) { this.jinkT = this.rng.range(0.7, 1.4); this.jinkSign = -(this.jinkSign || 1); }
      if (this.jinkSign < 0) { dir = add(scale(side, -1.5), addScaled(f, UP, 0.6)); name = 'guns jink'; }
    }
    return { dir, g, speed, name, nose: false };
  }

  // Airbrake overshoot: shared physical limits, no forced animation or scripted win.
  canBrakeTrap(S) {
    const me = this.ac;
    return this.mode === 'DEFEND' && !this.brakeTrap && this.t - this.lastBrakeT > 18 &&
      S.threats.length === 0 && S.R > 150 && S.R < 700 &&
      S.ata > 115 * DEG && S.tgtAta < 25 * DEG &&
      S.vc > 35 && S.tg.speed > me.speed + 32 &&
      me.speed > 135 && me.pos.y > 700 && this.useTactic('brakeTrap', 6);
  }

  brakeTrapCommand(S, match) {
    const trap = this.brakeTrap;
    if (!trap) return null;
    // Missile evasion and survival override showmanship.
    if (this.mode === 'EVADE' || S.threats.length || !this.ac.alive) {
      this.brakeTrap = null;
      return null;
    }
    if (trap.phase === 'brake') {
      // Confirm that the pursuer crossed the defender's ORIGINAL forward plane.
      // Otherwise a defender rolling its own nose cannot create a fake reversal.
      const passed = dot(sub(S.tg.pos, this.ac.pos), trap.forward) > 60 && S.R < 1000;
      if (passed) {
        trap.phase = 'reverse';
        trap.reversedAt = this.t;
        this.brakeSuccesses++;
        this.transitions.push({ t: this.t, from: this.mode, to: this.mode, why: 'brake trap: observed actual overshoot' });
        this.say('reversal', match, true);
        if (this.onTactic) this.onTactic({ type: 'overshoot', time: this.t, range: S.R });
      } else if (this.t - trap.start > 1.8 || this.ac.speed < 105) {
        // Failed trap costs energy; no success notification and no free reversal.
        this.brakeTrap = null;
        return null;
      }
    }
    if (trap.phase === 'reverse') {
      if (this.t - trap.reversedAt > 2.5 || S.R > 1700) {
        this.brakeTrap = null;
        return null;
      }
      const lead = addScaled(S.tg.pos, S.tg.vel, clamp(S.R / 750, 0, 1.1));
      return { dir: sub(lead, this.ac.pos), g: this.skill.gUse, speed: S.corner * 1.1,
        name: 'brake trap: reverse pursuit', nose: true };
    }
    const f = S.f, toward = norm(sub(S.tg.pos, this.ac.pos));
    let side = perp(toward, f);
    if (len(side) < 0.15) side = rightOf(this.ac.q);
    side = norm(side);
    return { dir: add(add(scale(f, 0.9), scale(side, 0.55)), scale(UP, 0.2)),
      g: this.skill.gUse, speed: S.corner * 0.9, brake: true,
      name: 'brake trap: baiting overshoot', nose: false };
  }

  doEvade(S, match) {
    const me = this.ac, sk = this.skill;
    const th = S.threats[0];
    if (!th) return this.doDefend(S, 0);
    const f = S.f;
    const mdir = norm(th.m.vel);
    let dir, name, g = sk.gUse;
    const fromFront = dot(th.dir, f) > 0.3;
    // shooter close behind me: the missile and the guns come from the same place, so the
    // break goes INTO the shooter (denies the gun shot too) and starts earlier
    const shooter = th.m.owner;
    const toShooter = sub(shooter.pos, me.pos);
    const shooterClose = len(toShooter) < 1800 && dot(norm(toShooter), f) < 0;
    if (th.ttg > (shooterClose ? 3.0 : 2.2)) {
      const losH = norm({ x: th.dir.x, y: 0, z: th.dir.z });
      const beam = norm(cross(losH, UP));
      const s = dot(beam, f) >= 0 ? 1 : -1;
      if (fromFront) {
        // crank: ~55° off the missile, keep the shooter in view and the fight neutral
        dir = addScaled(add(scale(beam, s * 1.4), losH), UP, me.pos.y > 1500 ? -0.15 : 0.1);
        name = 'crank missile';
      } else {
        // beam: perpendicular to its line of sight, slightly nose-low
        dir = addScaled(scale(beam, s), UP, me.pos.y > 1500 ? -0.25 : 0.1);
        name = 'beam missile';
      }
      g = Math.min(g, 0.85);
    } else {
      // last-ditch break: turn hard across the missile's flight path
      let across = perp(f, mdir);
      if (len(across) < 0.2) across = perp(upOf(me.q), mdir);
      across = norm(across);
      dir = add(scale(across, 3), me.pos.y > 900 ? scale(UP, -0.5) : scale(UP, 0.3));
      name = 'last-ditch break';
    }
    // flares: timing depends on skill; one salvo per inbound
    if (me.flares > 0 && th.m !== this.flaredFor) {
      if (this.flareAt == null || this.flareFor !== th.m) {
        this.flareFor = th.m; this.flareAt = this.rng.range(sk.flareTTG[0], sk.flareTTG[1]);
      }
      if (th.ttg < this.flareAt) { this.flaredFor = th.m; this.wantFlare = true; this.say('flare', match); }
    }
    return { dir, g, speed: 400, name, nose: false };
  }

  doExtend(S) {
    const me = this.ac;
    const away = norm({ x: -S.los.x, y: 0, z: -S.los.z });
    const side = norm(cross(away, UP));
    let dir = add(away, scale(side, 0.6 * (this.extendSide || 1)));
    dir.y = me.pos.y > 2600 ? -0.3 : me.pos.y < 1400 ? 0.18 : -0.05;
    return { dir, g: 0.45, speed: 420, name: 'extend (unload, burner)', nose: false };
  }

  // ---------------- safety layer ----------------
  safety(cmd, S) {
    const me = this.ac;
    const f = S.f;
    let dir = norm(cmd.dir);
    // don't play chicken: in a fast head-on with its nose on me, slide out of its gun line
    if ((this.mode === 'ENGAGE' || this.mode === 'ATTACK') && S.R < 1400 && S.R > 150 && S.tgtAta < 9 * DEG && S.vc > 250 && this.useTactic('mergeJink', 4)) {
      const off = perp(sub(me.pos, S.tg.pos), S.tg.fwd);
      const away = len(off) > 1 ? norm(off) : rightOf(me.q);
      dir = norm(addScaled(dir, away, 0.7));
      cmd = { ...cmd, name: (cmd.name || '') + ' +merge jink', g: Math.max(cmd.g ?? 1, 0.9) };
    }
    // ground (sea) avoidance with look-ahead scaled by speed
    const T = 2.2 + me.speed / 110;
    const predAlt = me.pos.y + me.vel.y * T;
    const floor = 380;
    if (predAlt < floor || me.pos.y < 260) {
      const sev = clamp((floor - predAlt) / 500, 0, 1);
      const horiz = norm({ x: f.x, y: 0, z: f.z });
      const recover = norm(addScaled(horiz, UP, 0.8));
      dir = norm(add(scale(dir, 1 - sev), scale(recover, sev * 2 + 0.2)));
      if (dir.y < 0.05) dir = norm({ ...dir, y: 0.25 });
      cmd = { ...cmd, g: Math.max(cmd.g ?? 1, 0.95), name: (cmd.name || '') + ' +PULL UP', speed: Math.max(cmd.speed ?? 0, 260), brake: false };
      this.debug.safety = 'ground';
    }
    // ceiling
    if (me.pos.y > RULES.ceiling - 1500 && dir.y > -0.1) { dir = norm({ ...dir, y: -0.3 }); }
    // arena boundary: steer back toward the centre
    const horizR = Math.hypot(me.pos.x, me.pos.z);
    const edge = RULES.arenaRadius - 2200;
    if (horizR > edge) {
      const w = clamp((horizR - edge) / 1500, 0, 1.5);
      const home = norm({ x: -me.pos.x, y: 0, z: -me.pos.z });
      dir = norm(add(dir, scale(home, w * 1.6)));
      cmd = { ...cmd, name: (cmd.name || '') + ' +boundary' };
    }
    // stall protection: don't hang the nose up at low speed
    if (me.speed < 105 && dir.y > 0) {
      dir = norm({ ...dir, y: Math.min(dir.y, -0.15) });
      cmd = { ...cmd, g: Math.min(cmd.g ?? 1, 0.5), speed: 400 };
    }
    return { ...cmd, dir };
  }

  // ---------------- maneuver controller ----------------
  steer(dirIn, gFrac, cmd = {}) {
    const me = this.ac, t = me.type;
    const f = forwardOf(me.q);
    const d = norm(dirIn);
    const err = angleBetween(f, d);
    const v = me.speed;
    const nAvail = availableG(me);
    const nMax = Math.max(1, nAvail * clamp(gFrac, 0.1, 1));

    let dp = perp(d, f);
    const dpl = len(dp);
    dp = dpl > 1e-6 ? scale(dp, 1 / dpl) : { x: 0, y: 0, z: 0 };
    const wDes = Math.min(err * 2.4, (nMax * G) / v + 0.5);
    // feed-forward: the aim direction itself rotates (a turning target); without this term a
    // P-only controller trails a 20°/s target by ~9° and can never settle a gun solution
    let ff = { x: 0, y: 0, z: 0 };
    if (this.prevDir && this.prevDirT > 0) {
      const rate = scale(sub(d, this.prevDir), 1 / this.prevDirT);
      if (len(rate) < 1.2) ff = perp(rate, f);
    }
    this.prevDir = d; this.prevDirT = this.lastDt || 1 / 60;
    let aDes = scale(add(scale(dp, wDes), scale(ff, err < 30 * DEG ? 1 : 0)), v);
    const gc = scale(perp(UP, f), G); // lift needed to cancel gravity across the path
    // G-limited: keep gravity compensation and shorten the turn demand to fit nMax
    const M = nMax * G, aa = dot(aDes, aDes), ab = dot(aDes, gc), bb = dot(gc, gc);
    if (aa > 1e-6 && aa + 2 * ab + bb > M * M) {
      const disc = ab * ab - aa * (bb - M * M);
      const k = disc > 0 ? clamp((-ab + Math.sqrt(disc)) / aa, 0, 1) : 0;
      aDes = scale(aDes, k);
    }
    const lift = add(aDes, gc);
    const nReq = len(lift) / G;
    const lb = toBody(me.q, lift);
    let rollErr = Math.atan2(lb.x, lb.y);
    let nCmd = nReq;
    // small corrections with the lift vector "below": push instead of rolling inverted
    if (Math.abs(rollErr) > 115 * DEG && err < 20 * DEG && nReq < 2.5) {
      rollErr = rollErr - Math.sign(rollErr) * Math.PI;
      nCmd = -nReq;
    }
    // fine tracking: tiny errors handled without big rolls (rudder + pitch)
    const fine = smoothstep(1.5 * DEG, 6 * DEG, err);
    rollErr *= lerp(0.15, 1, fine);
    const desRollRate = clamp(rollErr * 4.5, -t.rollRate, t.rollRate);
    const roll = clamp(desRollRate / t.rollRate - me.rollRateCur * 0.04, -1, 1);
    // pull only the component of the lift we're already aligned with
    const align = Math.cos(clamp(Math.abs(rollErr), 0, Math.PI));
    let n = nCmd >= 0 ? nCmd * Math.max(align, Math.abs(rollErr) > 70 * DEG ? 0.15 : align) : nCmd;
    n = clamp(n, t.minG, nMax);
    const pitch = pitchForG(me, n);
    const db = toBody(me.q, d);
    // Rudder is for fine tracking only. Holding 30% rudder in a hard, steeply banked
    // turn yawed the nose toward the ground and made sustained turns sink.
    const yaw = clamp(db.x * 25, -1, 1) * (1 - fine);
    return { pitch, roll, yaw, throttle: 0.8, boost: false, brake: false, fireMissile: false, fireGun: false, flare: false };
  }

  throttle(out, cmd) {
    const v = this.ac.speed;
    const target = cmd.speed ?? 260;
    if (cmd.brake) { out.throttle = 0; out.brake = true; return; }
    if (v < target - 12) { out.boost = true; out.throttle = 1; }
    else if (v > target + 55) { out.throttle = 0; out.brake = true; }
    else if (v > target + 20) out.throttle = 0.2;
    else out.throttle = 0.85;
  }

  weapons(out, S, dt, match, cmd) {
    const me = this.ac, sk = this.skill;
    if (this.wantFlare) { out.flare = true; this.wantFlare = false; }
    if (!S.tg.alive) return;
    // missiles: shot discipline by estimated Pk, lowered by aggression and by what we've
    // learned about the opponent (a target that never defends is worth more shots)
    const thr = lerp(0.46, 0.18, this.aggr) + sk.pkBias + (this.oppEvades - 0.6) * 0.12;
    const gapOk = this.t - this.lastShotT > sk.minShotGap;
    // pressure: even a likely miss forces a turn and burns a flare — a tactic, not a hope
    const pressure = this.aggr > 0.62 && this.t - this.lastShotT > 10 && S.pk > 0.12 && S.R > 1300 && this.useTactic('pressure', 4);
    // forcing shot: it's nose-on and about to shoot me — shoot first, make it defend
    const forcing = this.useTactic('forcing', 3) && S.tgtAta < 25 * DEG && S.R > 1500 && S.R < 4200 && S.pk > 0.17 && this.t - this.lastShotT > 8;
    // return fire: I'm being shot at by a target I have locked — fox two back
    const inbound = S.threats.find((th) => th.m.owner === me.enemy);
    const returnFire = inbound && this.useTactic('return', 4) && inbound.ttg > 2 && S.pk > 0.12 && this.t - this.lastShotT > 3;
    const allowed = this.mode !== 'EVADE' || returnFire;
    if (me.lock.locked && gapOk && me.missiles > 0 && allowed && (S.pk >= thr || pressure || forcing || returnFire)) {
      out.fireMissile = true;
      this.lastShotT = this.t; this.lastWeaponT = this.t;
      me.lastShotT = match.time;
      this.holdAfterShot = returnFire ? 0 : 1.2;
      this.aggr = Math.max(0.1, this.aggr - 0.06);
      this.lastShotKind = S.pk >= thr ? 'pk' : returnFire ? 'return' : forcing ? 'forcing' : 'pressure';
      this.say(S.pk >= thr ? 'fox2' : 'pressure', match);
    }
    // gun: short bursts when the nose is on the lead point
    if (S.R < GUN.range * 0.95 && S.ata < 20 * DEG) {
      const lead = gunLead(me, S.tg.pos, S.tg.vel, scale(S.tg.acc, sk.leadAccel));
      const err = gunError(me, lead.point);
      if (err < sk.gunTol && this.burstT <= 0) this.burstT = this.rng.range(sk.burst[0], sk.burst[1]);
    }
    if (this.burstT > 0) {
      this.burstT -= dt;
      if (S.ata < 25 * DEG) { out.fireGun = true; this.lastWeaponT = this.t; me.lastShotT = match.time; }
    }
  }
}
