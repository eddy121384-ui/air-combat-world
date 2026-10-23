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
import { pullUpWarning } from '../sim/warnings.js';

export const KMH = 3.6;
export const wrapDeg = (a) => ((a % 360) + 540) % 360 - 180;
export const hdgDeg = (ac) => (headingOf(ac) / DEG + 360) % 360;
export const gammaDeg = (ac) => Math.asin(clamp(ac.vel.y / Math.max(ac.speed, 1), -1, 1)) / DEG;
export const bankDeg = (ac) => bankAngle(ac) / DEG;

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

const clone = (x) => JSON.parse(JSON.stringify(x ?? {}));
// The player's kinematic / stores state, so a checkpoint retry starts exactly where the phase began.
const JET_KEYS = ['pos', 'q', 'vel', 'speed', 'nCur', 'rollRateCur', 'thrustCur', 'abCur', 'gLoad', 'aoaVisual', 'hp', 'flares', 'flareRecharge', 'missiles', 'gunRounds'];
const snapJet = (ac) => clone(Object.fromEntries(JET_KEYS.map((k) => [k, ac[k]])));
const RETRY_LINES = ['再來。這次照你知道的飛。', '重來。深呼吸，手放輕。', '再一次。剛才那段，你已經懂一半了。', '好，再飛一次。慢一點，比較快。'];
/** Lesson thresholds for a mode: all -> flight -> flight:control. */
export function resolveTune(lesson, flight, control) {
  return { ...(lesson.tune?.all || {}), ...(lesson.tune?.[flight] || {}), ...(lesson.tune?.[`${flight}:${control}`] || {}) };
}
/** Subtitle time on screen / before the next line, seconds. */
export const radioSeconds = (text) => Math.min(4.8, 1.0 + text.length * 0.1);
export const RADIO_MAX = 30;
/**
 * Split a radio line into phone-sized subtitles (<= RADIO_MAX chars where possible):
 * first at sentence ends, then at commas / dashes.
 */
export function splitRadio(text, max = RADIO_MAX) {
  const out = [];
  // keep the delimiter on the left piece (no regex lookbehind: older iOS Safari lacks it)
  const pieces = (str, ends) => {
    const res = []; let cur = '';
    for (const ch of str) { cur += ch; if (ends.includes(ch)) { res.push(cur); cur = ''; } }
    if (cur) res.push(cur);
    return res;
  };
  for (const sentence of pieces(text, '。！？!?')) {
    if (sentence.length <= max) { out.push(sentence); continue; }
    let cur = '';
    for (const part of pieces(sentence, '，、；：—')) {
      if (cur && (cur + part).length > max) { out.push(cur); cur = part; } else cur += part;
    }
    if (cur) out.push(cur);
  }
  // merge tiny neighbours so we do not flash two-word subtitles
  const merged = [];
  for (const s of out) {
    const last = merged[merged.length - 1];
    if (last && (last + s).length <= max && (last.length < 9 || s.length < 9)) merged[merged.length - 1] = last + s;
    else merged.push(s);
  }
  return merged;
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
  constructor(lesson, match, { flight = 'arcade', control = 'expert', retry = 0, resume = null } = {}) {
    this.lesson = lesson; this.match = match;
    this.flight = flight; this.control = control;
    this.me = match.blue; this.foe = match.red;
    this.tune = resolveTune(lesson, flight, control);
    this.retry = retry; // attempts already flown in this sitting (UI only: no intro repeat)
    this.rules = { weapons: false };
    this.t = 0; this.phaseIdx = -1; this.phase = null; this.phaseT = 0; this.d = {};
    this.lines = []; this.queue = []; this.nextLineT = 0; this.spoken = [];
    this.result = null; this.notes = {}; this.flashes = [];
    this.onSay = null; this.onFlash = null; // UI hooks (browser)
    lesson.setup?.(this);
    this.tel = newTelemetry(this.me);
    match.on((ev) => this.onEvent(ev));
    this.checkpoint = false;
    const cp = resume && lesson.phases[resume.from]?.checkpoint ? resume : null;
    if (cp) {
      // Checkpoint retry: earlier phases already flown in the failed attempt keep
      // their notes / clock; the jet is put into the phase's own starting situation.
      this.checkpoint = true;
      Object.assign(this.notes, clone(cp.notes));
      this.t = cp.t;
      this.tel = { ...clone(cp.tel), events: [] };
      if (cp.jet) Object.assign(this.me, clone(cp.jet));
      const c = lesson.phases[cp.from].checkpoint;
      if (typeof c === 'function') c(this);
      this.phaseIdx = cp.from - 1;
      this.say(`從「${lesson.phases[cp.from].name || `第 ${cp.from + 1} 段`}」接著飛。`);
    } else if (retry) {
      this.say(RETRY_LINES[(retry - 1) % RETRY_LINES.length]);
    } else {
      for (const line of lesson.intro || []) this.say(typeof line === 'function' ? line(this) : line);
    }
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
  /** Instructor radio. Long lines are split into short subtitles so a phone HUD stays readable. */
  say(text, kind = 'line') {
    if (!text) return;
    for (const t of splitRadio(text)) this.queue.push({ text: t, kind, phase: this.phaseIdx, at: this.t });
  }
  /** Urgent call (BREAK! / PULL UP!): jumps the queue and is spoken this step. */
  urgent(text) {
    if (!text) return;
    this.queue = splitRadio(text).map((t) => ({ text: t, kind: 'urgent', phase: this.phaseIdx, at: this.t })).concat(this.queue);
    this.nextLineT = 0;
  }
  /** True while KITE still has instructions to deliver (a scenario may wait for this). */
  get radioBusy() { return this.nextLineT > 0 || this.queue.some((q) => q.kind === 'line'); }
  /**
   * Behaviour-triggered coaching line, at most once per phase per key (or again
   * after `cooldown` seconds). Returns true when spoken.
   */
  cue(key, text, { cooldown = Infinity, urgent = false } = {}) {
    const c = (this.d.__cues ||= {});
    if (c[key] != null && this.phaseT - c[key] < cooldown) return false;
    c[key] = this.phaseT;
    if (urgent) this.urgent(text); else this.say(text, 'cue');
    (this.cues ||= []).push({ t: this.t, phase: this.phase?.id, key });
    return true;
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
    if (this.phase?.exit) this.phase.exit(this);
    if (this.phase) {
      const p = typeof this.phase.praise === 'function' ? this.phase.praise(this) : this.phase.praise;
      if (p) this.say(p, 'praise');
      if (this.phaseIdx + 1 < this.lesson.phases.length) this.flash(`✓ ${this.phaseIdx + 1}/${this.lesson.phases.length}`, '#7dffb0');
    }
    // Instructions and coaching for a finished phase are obsolete: never let the
    // radio lag behind the flying. Praise for it (short) is kept.
    if (this.phase) this.queue = this.queue.filter((q) => q.kind === 'praise' || q.kind === 'closing');
    this.phaseIdx += 1;
    this.phase = this.lesson.phases[this.phaseIdx] || null;
    this.phaseT = 0; this.d = {};
    if (!this.phase) { this.finish(true); return; }
    const rules = (x) => (typeof x === 'function' ? x(this) : x) || {};
    this.rules = { weapons: false, ...rules(this.lesson.rules), ...rules(this.phase.rules) };
    // checkpoint snapshot: what a "retry from this phase" restores
    this.entry = { from: this.phaseIdx, t: this.t, notes: clone(this.notes), tel: clone({ ...this.tel, events: [] }), jet: snapJet(this.me) };
    this.phase.enter?.(this);
    const s = typeof this.phase.say === 'function' ? this.phase.say(this) : this.phase.say;
    this.say(s);
  }

  finish(success, reason = null) {
    if (this.result) return;
    const fb = this.lesson.debrief ? this.lesson.debrief(this, success) : {};
    let grade = success ? (this.lesson.grade ? this.lesson.grade(this) : 'B') : null;
    // A checkpoint clear is real, but S needs one clean run from the start.
    if (this.checkpoint && grade === 'S') grade = 'A';
    this.result = {
      success, reason, grade, time: this.t, checkpoint: this.checkpoint,
      good: fb.good || [], improve: fb.improve || [], stats: fb.stats || [], extra: fb.extra || null,
      phase: this.phase?.id || null, phaseIdx: this.phaseIdx,
      resume: !success && this.phase?.checkpoint && this.entry ? this.entry : null,
    };
    if (!success) this.queue = []; // drop pending coaching; a clear keeps the last praise
    if (success) for (const line of [].concat(fb.closing || this.lesson.closing || '漂亮。回場。')) this.say(line, 'closing');
    else if (reason) this.say(splitRadio(reason)[0], 'closing'); // headline on the radio; the full why is on the debrief
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
    this.phase.coach?.(this, dt);
    const r = this.phase.update?.(this, dt);
    if (r === 'done') this.next();
    else if (r && r.fail) this.fail(r.fail);
    this.tickRadio(dt);
  }

  tickRadio(dt) {
    this.nextLineT -= dt;
    // a coaching cue that could not be spoken within 2.5 s no longer matches what the pilot sees
    this.queue = this.queue.filter((q) => q.kind !== 'cue' || this.t - q.at < 2.5);
    if (this.nextLineT <= 0 && this.queue.length) {
      const { text } = this.queue.shift();
      this.spoken.push({ t: this.t, text });
      this.onSay?.(text);
      this.nextLineT = radioSeconds(text);
    }
  }

  /** Data for the HUD objective panel and markers. */
  view() {
    const ph = this.phase;
    const limit = this.tune.timeLimit ?? this.lesson.timeLimit;
    return {
      lesson: `${String(this.lesson.no).padStart(2, '0')} ${this.lesson.title}`,
      step: ph ? `${this.phaseIdx + 1}/${this.lesson.phases.length}` : '',
      text: ph?.text ? ph.text(this) : '',
      progress: ph?.progress ? clamp(ph.progress(this), 0, 1) : null,
      timer: limit ? Math.max(0, limit - this.t) : null,
      markers: ph?.markers ? ph.markers(this) : [],
      done: !!this.result,
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
export function holdPhase({ id, say, text, cond, need = 4, strict = false, enter, why, timeout, markers, onEvent, ...extra }) {
  return {
    ...extra, // coach / praise / name / checkpoint
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
