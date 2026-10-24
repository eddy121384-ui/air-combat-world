// Ace Flight Academy — lesson runner. A thin layer ON TOP of the existing Match,
// flight model, controllers and HUD: it never changes physics or weapons rules.
// It only (1) sets up a scenario, (2) filters the player's controls where a lesson
// rule says so (e.g. "engine at idle"), (3) watches real sim state to judge each
// phase, and (4) explains success or failure from what actually happened.
// Pure JS (no DOM, no three.js) so every lesson can be verified headless in Node.
import {
  sub, norm, len, dot, clamp, angleBetween, forwardOf, qLook, qMul, qAxisAngle, qNormalize, DEG, G, UP,
} from '../sim/math.js';
import { headingOf, bankAngle, pitchAngle, specificEnergy, availableG, instantTurnRate, bestTurn, MIN_SPEED } from '../sim/aircraft.js';
import { controlText } from './control-text.js';
import { pullUpWarning } from '../sim/warnings.js';

export const KMH = 3.6;
export const wrapDeg = (a) => ((a % 360) + 540) % 360 - 180;
export const hdgDeg = (ac) => (headingOf(ac) / DEG + 360) % 360;
export const gammaDeg = (ac) => Math.asin(clamp(ac.vel.y / Math.max(ac.speed, 1), -1, 1)) / DEG;
export const bankDeg = (ac) => bankAngle(ac) / DEG;

// One clock and short, complete subtitle chunks: no clipped mobile instructions.
export const RADIO_CHARS = 28;
export const radioDuration = (text) => 2.2 + Array.from(text).length * 0.075;
export function radioChunks(text) {
  const chars = Array.from(text || ''), chunks = [];
  while (chars.length) {
    let count = Math.min(RADIO_CHARS, chars.length);
    if (chars.length > count) {
      // Prefer a completed sentence, then a clause, then a word boundary.
      // A late space must not override an earlier complete instruction.
      for (const stops of ['。！？；','，：',' ']) {
        let cut=-1;
        for (let i=count-1;i>=5;i--)if(stops.includes(chars[i])){cut=i+1;break;}
        if(cut>0){count=cut;break;}
      }
    }
    const chunk = chars.splice(0, count).join('').trim();
    if (chunk) chunks.push(chunk);
  }
  return chunks;
}

/** Put a jet into an exact scenario state (lesson start or a "situation" reset). */
export function placeJet(ac, { pos, alt, speed, heading = 0, pitch = 0, bank = 0, throttle } = {}) {
  if (pos) ac.pos = { ...pos };
  if (alt != null) ac.pos.y = alt;
  const h = heading * DEG, p = pitch * DEG;
  const fwd = { x: Math.sin(h) * Math.cos(p), y: Math.sin(p), z: -Math.cos(h) * Math.cos(p) };
  let q = qLook(fwd, UP);
  if (bank) q = qNormalize(qMul(q, qAxisAngle({ x: 0, y: 0, z: -1 }, bank * DEG)));
  ac.q = q;
  if (speed != null) ac.speed = speed;
  ac.vel = { x: fwd.x * ac.speed, y: fwd.y * ac.speed, z: fwd.z * ac.speed };
  ac.nCur = Math.cos(p); ac.rollRateCur = 0; ac.aoaVisual = 0;
  if (throttle != null) { ac.controls.throttle = throttle; ac.thrustCur = throttle; }
}

/** Point `dist` metres from `ac` along a heading (deg) at altitude `alt`. */
export function pointAhead(ac, headingDegrees, dist, alt) {
  const h = headingDegrees * DEG;
  return { x: ac.pos.x + Math.sin(h) * dist, y: alt ?? ac.pos.y, z: ac.pos.z - Math.cos(h) * dist };
}

function newTelemetry(me) {
  return {
    minSpeed: me.speed, maxSpeed: me.speed, maxG: me.nCur, minAlt: me.pos.y, maxAlt: me.pos.y,
    gHighSec: 0, abSec: 0, brakeSec: 0, slowSec: 0, bandSec: 0, flightSec: 0,
    pullUpAt: null, pullUpReact: null, rollNoPullSec: 0, pullNoRollSec: 0,
    events: [],
  };
}

export class LessonRunner {
  /**
   * @param {object} lesson   lesson definition (see lessons.js)
   * @param {Match} match     the live match (already constructed by the caller)
   * @param {object} o        { flight: 'arcade'|'tactical', control: 'assisted'|'expert' }
   */
  constructor(lesson, match, { flight = 'arcade', control = 'expert', inputDevice = () => 'stick' } = {}) {
    this.lesson = lesson; this.match = match;
    this.flight = flight; this.control = control; this.inputDevice = inputDevice;
    this.me = match.blue; this.foe = match.red;
    this.tune = { ...(lesson.tune?.all || {}), ...(lesson.tune?.[flight] || {}), ...(lesson.tune?.[`${flight}:${control}`] || {}) };
    this.rules = { weapons: false };
    this.t = 0; this.phaseIdx = -1; this.phase = null; this.phaseT = 0; this.d = {};
    this.lines = []; this.queue = []; this.nextLineT = 0; this.spoken = [];
    this.result = null; this.notes = {}; this.flashes = [];
    this.onSay = null; this.onFlash = null; // UI hooks (browser)
    this.coached = new Set(); this.lastCoachT = -10;
    lesson.setup?.(this);
    this.tel = newTelemetry(this.me);
    match.on((ev) => this.onEvent(ev));
    // Narrative belongs in the briefing. The first airborne line must be the task.
    this.next();
  }

  // ---------------- helpers used by lesson definitions ----------------
  get kmh() { return this.me.speed * KMH; }
  get heading() { return hdgDeg(this.me); }
  get gamma() { return gammaDeg(this.me); }
  get bank() { return bankDeg(this.me); }
  get pitch() { return pitchAngle(this.me) / DEG; }
  get g() { return this.me.nCur; }
  get alt() { return this.me.pos.y; }
  get energyHeight() { return specificEnergy(this.me); }
  get availG() { return availableG(this.me); }
  get inBestBand() { return instantTurnRate(this.me) >= bestTurn(this.me).rate * 0.92; }
  get bestBandKmh() { const b = bestTurn(this.me); return [Math.round(b.lo * KMH), Math.round(b.hi * KMH)]; }
  get assisted() { return this.control === 'assisted'; }
  get tactical() { return this.flight === 'tactical'; }
  /** Text variant by control mode: pick(assistedText, expertText). */
  pick(a, e) { return this.assisted ? a : e; }
  say(text, { urgent = false } = {}) {
    if (urgent) { this.queue.length = 0; this.nextLineT = 0; }
    this.queue.push(...radioChunks(text));
  }
  coachOnce(key, text, { urgent = false } = {}) {
    const id = `${this.phaseIdx}:${key}`;
    if (this.coached.has(id) || (!urgent && this.t-this.lastCoachT < 7)) return;
    this.coached.add(id); this.lastCoachT = this.t;
    this.say(text, { urgent });
  }
  flash(text, color = '#7fe3ff') { this.flashes.push({ text, color }); this.onFlash?.(text, color); }
  note(key, value) { this.notes[key] = value; }

  // ---------------- control filter (lesson rules, never physics) ----------------
  filter(c) {
    const r = this.rules;
    if (!r.weapons) { c.fireMissile = false; c.fireGun = false; }
    if (r.missiles === false) c.fireMissile = false;
    if (r.throttle != null) c.throttle = r.throttle;
    if (r.ab === false) c.boost = false;
    if (r.brake === false) c.brake = false;
    return c;
  }

  // ---------------- phases ----------------
  next() {
    if (this.phase) this.flash(`CHECK ${this.phaseIdx+1}/${this.lesson.phases.length}`, '#7dffb0');
    if (this.phase?.exit) this.phase.exit(this);
    this.queue.length = 0; this.nextLineT = 0; // never issue a previous phase's command
    this.phaseIdx += 1;
    this.phase = this.lesson.phases[this.phaseIdx] || null;
    this.phaseT = 0; this.d = {};
    if (!this.phase) { this.finish(true); return; }
    const rules = (x) => (typeof x === 'function' ? x(this) : x) || {};
    this.rules = { weapons: false, ...rules(this.lesson.rules), ...rules(this.phase.rules) };
    this.phase.enter?.(this);
    const s = typeof this.phase.say === 'function' ? this.phase.say(this) : this.phase.say;
    this.say(s);
  }

  finish(success, reason = null) {
    if (this.result) return;
    const fb = this.lesson.debrief ? this.lesson.debrief(this, success) : {};
    const grade = success ? (this.lesson.grade ? this.lesson.grade(this) : 'B') : null;
    const citation = success ? (fb.closing || this.lesson.closing || '漂亮。回場。')
      : this.lesson.final ? fb.closing : '先修正結算中的一個動作，再飛同一個開局。我還在你的頻道上。';
    this.result = {
      success, reason, grade, time: this.t,
      good: fb.good || [], improve: fb.improve || [], stats: fb.stats || [],
      phase: this.phase?.id || null,
      citation,
    };
    this.say(success ? this.result.citation : reason, { urgent: true });
  }

  fail(reason) { this.finish(false, reason); }

  onEvent(ev) {
    this.tel.events.push({ t: this.t, type: ev.type, ev });
    this.phase?.onEvent?.(this, ev);
    this.lesson.onEvent?.(this, ev);
  }

  /** Call once per fixed simulation step, after match.step(dt). */
  step(dt) {
    if (this.result) { this.tickRadio(dt); return; }
    this.t += dt; this.phaseT += dt;
    const me = this.me, tel = this.tel;
    tel.flightSec += dt;
    tel.minSpeed = Math.min(tel.minSpeed, me.speed); tel.maxSpeed = Math.max(tel.maxSpeed, me.speed);
    tel.maxG = Math.max(tel.maxG, me.nCur);
    tel.minAlt = Math.min(tel.minAlt, me.pos.y); tel.maxAlt = Math.max(tel.maxAlt, me.pos.y);
    if (me.nCur > 7) tel.gHighSec += dt;
    if (me.abCur > 0.5) tel.abSec += dt;
    if (me.controls.brake) tel.brakeSec += dt;
    if (me.speed < 95) tel.slowSec += dt;
    if (this.inBestBand) tel.bandSec += dt;
    const banked = Math.abs(this.bank) > 40 && Math.abs(this.bank) < 140;
    if (banked && me.nCur < 1.4) tel.rollNoPullSec += dt;
    if (!banked && Math.abs(this.bank) < 15 && me.nCur > 3) tel.pullNoRollSec += dt;
    const warn = pullUpWarning(me);
    if (warn && tel.pullUpAt == null) tel.pullUpAt = this.t;
    if (tel.pullUpAt != null && tel.pullUpReact == null && me.nCur > 0.7 * this.availG) tel.pullUpReact = this.t - tel.pullUpAt;
    if (!warn && me.vel.y > 0) { tel.pullUpAt = null; tel.pullUpReact = null; }

    if (!me.alive) {
      const cause = me.deathCause;
      const why = cause === 'crash'
        ? (this.lesson.crashReason?.(this) || crashReason(this))
        : cause === 'outOfBounds' ? '脫離訓練空域太久——注意 RETURN 警告，回頭飛向空域中心。'
          : '你被擊落了。';
      this.fail(why);
      return;
    }
    const limit = this.tune.timeLimit ?? this.lesson.timeLimit;
    if (limit && this.t > limit) {
      this.fail(this.phase?.timeout?.(this) || `時間到（${Math.round(limit)} 秒）。${this.lesson.timeoutHint || ''}`);
      return;
    }
    const r = this.phase.update?.(this, dt);
    if (r === 'done') this.next();
    else if (r && r.fail) this.fail(r.fail);
    this.tickRadio(dt);
  }

  tickRadio(dt) {
    this.nextLineT -= dt;
    if (this.nextLineT <= 0 && this.queue.length) {
      const chunks=radioChunks(controlText(this.queue.shift(),this.inputDevice()));
      const text=chunks.shift();this.queue.unshift(...chunks);
      this.spoken.push({ t: this.t, text });
      this.onSay?.(text);
      this.nextLineT = radioDuration(text) + 0.15;
    }
  }

  /** Data for the HUD objective panel and markers. */
  view() {
    const ph = this.phase;
    const limit = this.tune.timeLimit ?? this.lesson.timeLimit;
    const guidance=this.lesson.guidance?.(this) || null;
    if(guidance)guidance.tip=controlText(guidance.tip,this.inputDevice());
    return {
      lesson: `${String(this.lesson.no).padStart(2, '0')} ${this.lesson.title}`,
      step: ph ? `${this.phaseIdx + 1}/${this.lesson.phases.length}` : '',
      text: ph?.text ? ph.text(this) : '',
      progress: ph?.progress ? clamp(ph.progress(this), 0, 1) : null,
      timer: this.lesson.advanced ? (this.result?null:Math.max(0,this.lesson.attemptLimit-this.phaseT))
        : limit ? Math.max(0, limit - this.t) : null,
      markers: ph?.markers ? ph.markers(this) : [],
      done: !!this.result,
      guidance,
      // Advanced training observes trigger discipline but never advertises a
      // combat SHOOT/LOCK cue as permission to bypass its position exercise.
      weapons: !!this.rules.weapons && !this.lesson.advanced,
      enemyWeapons: this.lesson.id !== 'L07',
      trace: this.lesson.advanced ? this.d.m?.trace : null,
      traceKind: this.lesson.id === 'A01' ? 'vertical' : 'plan',
    };
  }
}

function crashReason(r) {
  const tel = r.tel;
  if (tel.pullUpReact != null && tel.pullUpReact > 1) return `墜海。PULL UP 亮起後 ${tel.pullUpReact.toFixed(1)} 秒才全力拉起——警告一亮就收油、拉桿。`;
  if (tel.pullUpAt != null && tel.pullUpReact == null) return '墜海。PULL UP 亮了，但你始終沒有用力拉起。';
  return '墜海。高度和下沉率要一起看：俯衝越快，需要的拉起高度越多。';
}

// ---------------- reusable phase builders ----------------

/** Hold a condition for `need` seconds (cumulative, or continuous if `strict`). */
export function holdPhase({ id, say, text, cond, need = 4, strict = false, enter, why, timeout, markers, onEvent }) {
  return {
    id, say, enter, markers, onEvent,
    text: (r) => (typeof text === 'function' ? text(r) : text),
    progress: (r) => (r.d.held || 0) / need,
    update(r, dt) {
      const ok = cond(r);
      if (ok) r.d.held = (r.d.held || 0) + dt;
      else { if (strict) r.d.held = 0; why?.(r, dt); }
      return r.d.held >= need ? 'done' : undefined;
    },
    timeout,
  };
}

/** Fly through a gate (world point) within `radius`; optional speed / extra conditions. */
export function gatePhase({ id, say, label = 'GATE', pos, radius = 260, cond, text, onPass, enter, why, missAfter }) {
  return {
    id, say, enter,
    text: (r) => (typeof text === 'function' ? text(r) : text) || `飛過 ${label}`,
    markers: (r) => [{ pos: typeof pos === 'function' ? pos(r) : pos, label, kind: 'gate', radius }],
    progress: (r) => {
      const p = typeof pos === 'function' ? pos(r) : pos;
      r.d.startDist ??= len(sub(p, r.me.pos));
      return 1 - len(sub(p, r.me.pos)) / r.d.startDist;
    },
    update(r) {
      const p = typeof pos === 'function' ? pos(r) : pos;
      const rel = sub(p, r.me.pos), d = len(rel);
      r.d.minDist = Math.min(r.d.minDist ?? Infinity, d);
      // passed = the gate is now behind us after being close
      const behind = dot(rel, norm(r.me.vel)) < 0;
      if (d < radius) {
        if (cond && !cond(r)) { r.d.badPass = true; }
        else { onPass?.(r); return 'done'; }
      }
      if (behind && r.d.minDist < (missAfter ?? 1500) && d > radius) {
        return { fail: why ? why(r) : `錯過 ${label}：最近距離 ${Math.round(r.d.minDist)} m（需要 ${radius} m 內）。` };
      }
      return undefined;
    },
  };
}
