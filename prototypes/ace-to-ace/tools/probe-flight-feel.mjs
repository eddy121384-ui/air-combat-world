#!/usr/bin/env node
// Deterministic flight-feel probe for the four player-facing combinations
// (Arcade / Tactical physics x Assisted / Expert controls). Every scenario drives
// the REAL PlayerController with a scripted stick, then steps the shared
// stepAircraft() at 60 Hz. Numbers describe response, not fun: they are compared
// before/after a tuning change, alongside browser play and iPhone acceptance.
//
//   node tools/probe-flight-feel.mjs [--write docs/flight-feel-polish-<tag>.json]
import { writeFileSync } from 'node:fs';
import { createAircraft, stepAircraft, availableG, bankAngle, headingOf, pitchAngle, specificEnergy } from '../src/sim/aircraft.js';
import { PlayerController } from '../src/game/input.js';
import { forwardOf, sub, norm, toBody, angleBetween, clamp, DEG } from '../src/sim/math.js';

const dt = 1 / 60, deg = (r) => r / DEG;
const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const r2 = (x) => (x == null ? null : Math.round(x * 100) / 100);

function craft(feel, speed = 230, y = 3200) {
  const ac = createAircraft('F16V', 'blue', { x: 0, y, z: 0 }, { x: 0, y: 0, z: -1 }, speed);
  ac.flightFeel = feel;
  return ac;
}
/** Scripted thumb: x/y are already-shaped stick values (screen y up +). */
function pilot(ac, control, invert = false) {
  const stick = { x: 0, y: 0, throttle: 0.72, boost: false, brake: false };
  const input = {
    axes: () => ({ x: stick.x, y: stick.y, yaw: 0 }),
    throttle: () => stick.throttle, boost: () => stick.boost, brake: () => stick.brake,
    gun: () => false, consume: () => false,
  };
  const pc = new PlayerController(ac, input, { invert, assist: control === 'assisted' });
  // pull = +1 means "aft stick"; default convention is stick DOWN = pull.
  const tick = () => { Object.assign(ac.controls, pc.update(dt)); stepAircraft(ac, dt); };
  return { stick, tick, setPull: (p) => { stick.y = invert ? p : -p; } };
}

// ---- roll: full-stick 90 deg capture, release overshoot and settle (Expert only) ----
function rollCapture(feel) {
  const ac = craft(feel), p = pilot(ac, 'expert');
  p.stick.x = 1;
  let t = 0;
  while (deg(bankAngle(ac)) < 90 && t < 3) { p.tick(); t += dt; }
  const t90 = t;
  p.stick.x = 0;
  let peak = deg(bankAngle(ac)), settle = null;
  for (let i = 0; i < 90; i++) {
    p.tick(); peak = Math.max(peak, deg(bankAngle(ac)));
    if (settle == null && Math.abs(deg(ac.rollRateCur)) < 3) settle = (i + 1) * dt;
  }
  return { t90: r2(t90), overshootDeg: r2(peak - 90), stopSec: r2(settle), peakRateDps: r2(deg(ac.type.rollRate * 1.0)) };
}
// tap granularity: 0.1 s full stick, then release — how far does the jet roll?
function rollTap(feel, amount = 1, hold = 0.1) {
  const ac = craft(feel), p = pilot(ac, 'expert');
  p.stick.x = amount;
  for (let i = 0; i < Math.round(hold / dt); i++) p.tick();
  p.stick.x = 0;
  for (let i = 0; i < 60; i++) p.tick();
  return r2(deg(bankAngle(ac)));
}
// ---- pitch: wings level, full aft stick ----
function pitchStep(feel, pull = 1, speed = 230) {
  const ac = craft(feel, speed), p = pilot(ac, 'expert');
  p.setPull(pull);
  const f0 = forwardOf(ac.q);
  let t63 = null, t90 = null, peakG = 0;
  const target = availableG(ac) * pull;
  const nose = {};
  for (let i = 1; i <= 60; i++) {
    p.tick();
    peakG = Math.max(peakG, ac.gLoad);
    if (t63 == null && ac.gLoad >= 1 + 0.63 * (target - 1)) t63 = i * dt;
    if (t90 == null && ac.gLoad >= 1 + 0.9 * (target - 1)) t90 = i * dt;
    if (i === 15 || i === 30 || i === 60) nose[`${i / 60}s`] = r2(deg(angleBetween(f0, forwardOf(ac.q))));
  }
  return { gT63: r2(t63), gT90: r2(t90), peakG: r2(peakG), noseDeg: nose, aoaVisDeg: r2(deg(ac.aoaVisual)) };
}

// ---- level turn flown by the given control mode at the given stick ----
// Expert: a competent thumb — rolls to the level-turn bank for the commanded
// pull and holds it, so physics (not pilot error) dominates the comparison.
function levelTurn(feel, control, { amount = 1, seconds = 12, speed = 230, throttle = 1, boost = true } = {}) {
  const ac = craft(feel, speed), p = pilot(ac, control);
  Object.assign(p.stick, { throttle, boost });
  const h0 = headingOf(ac), e0 = specificEnergy(ac), y0 = ac.pos.y;
  let heading = 0, prevH = h0, t360 = null, t180 = null, peakG = 0, gOverAvail = 0, minSpeed = ac.speed;
  const rates = [];
  for (let i = 1; i <= Math.round(seconds / dt); i++) {
    if (control === 'assisted') p.stick.x = amount;
    else {
      // expert thumb: bank for level flight at the G this pull would produce, then pull
      const nTarget = 1 + (availableG(ac) - 1) * amount;
      const want = Math.acos(clamp(1 / nTarget, 0, 1));
      const err = wrap(want - bankAngle(ac));
      p.stick.x = clamp(err * 2.2, -1, 1);
      const climb = pitchAngle(ac);
      p.setPull(Math.abs(err) < 25 * DEG ? clamp(amount - climb * 3, -1, 1) : 0.2);
    }
    p.tick();
    const h = headingOf(ac);
    const dh = Math.abs(wrap(h - prevH)); prevH = h;
    heading += dh;
    rates.push(dh / dt);
    peakG = Math.max(peakG, ac.gLoad);
    gOverAvail = Math.max(gOverAvail, ac.gLoad - availableG(ac));
    minSpeed = Math.min(minSpeed, ac.speed);
    if (t180 == null && deg(heading) >= 180) t180 = i * dt;
    if (t360 == null && deg(heading) >= 360) t360 = i * dt;
  }
  const tail = rates.slice(-120);
  const sustained = tail.reduce((a, b) => a + b, 0) / tail.length;
  return {
    t180: r2(t180), t360: r2(t360), sustainedDps: r2(deg(sustained)), endSpeed: r2(ac.speed), minSpeed: r2(minSpeed),
    endG: r2(ac.gLoad), peakG: r2(peakG), gOverAvail: r2(Math.max(0, gOverAvail)),
    radiusM: r2(ac.speed / Math.max(sustained, 1e-3)), altDeltaM: r2(ac.pos.y - y0), energyLossM: r2(e0 - specificEnergy(ac)),
  };
}

// ---- Assisted roll-out: from a held hard turn, centre stick -> wings level ----
function assistedRollout(feel) {
  const ac = craft(feel), p = pilot(ac, 'assisted');
  p.stick.x = 1;
  for (let i = 0; i < 90; i++) p.tick();
  const bank0 = deg(bankAngle(ac));
  p.stick.x = 0;
  let t5 = null, maxOpp = 0;
  for (let i = 1; i <= 120; i++) {
    p.tick();
    const b = deg(bankAngle(ac));
    if (t5 == null && Math.abs(b) < 5) t5 = i * dt;
    if (Math.sign(b) !== Math.sign(bank0)) maxOpp = Math.max(maxOpp, Math.abs(b));
  }
  return { bankHeldDeg: r2(bank0), levelSec: r2(t5), overshootDeg: r2(maxOpp) };
}
// Assisted full-stick entry: time to 90 deg heading change and bank overshoot.
function assistedEntry(feel, amount = 1) {
  const ac = craft(feel), p = pilot(ac, 'assisted');
  p.stick.x = amount;
  const h0 = headingOf(ac);
  let peakBank = 0, t90 = null, t30 = null;
  for (let i = 1; i <= 300; i++) {
    p.tick();
    peakBank = Math.max(peakBank, deg(bankAngle(ac)));
    const dh = deg(Math.abs(wrap(headingOf(ac) - h0)));
    if (t30 == null && dh >= 30) t30 = i * dt;
    if (t90 == null && dh >= 90) t90 = i * dt;
  }
  return { t30: r2(t30), t90: r2(t90), peakBankDeg: r2(peakBank) };
}

// ---- engine: AB acceleration and recovery from low speed ----
function accel(feel, from, to, boost = true, throttle = 1) {
  const ac = craft(feel, from), p = pilot(ac, 'expert');
  Object.assign(p.stick, { boost, throttle });
  for (let i = 1; i <= 60 * 40; i++) { p.tick(); if (ac.speed >= to) return r2(i * dt); }
  return null;
}
function topSpeed(feel, boost) {
  const ac = craft(feel, 250), p = pilot(ac, 'expert');
  Object.assign(p.stick, { boost, throttle: 1 });
  for (let i = 0; i < 60 * 60; i++) p.tick();
  return r2(ac.speed);
}
// low-speed authority: full pull for 3 s from 110 m/s with AB
function lowSpeed(feel, control) {
  const r = levelTurn(feel, control, { speed: 110, seconds: 3 });
  return { sustainedDps: r.sustainedDps, endSpeed: r.endSpeed, altDeltaM: r.altDeltaM, gAvail110: r2(availableG(craft(feel, 110), 110)) };
}

// ---- tracking: human-like thumb keeps the nose on a target in a 12 deg/s level turn ----
// Same reaction delay, gains and stick slew limit for every mode; only the
// control interpretation and the physics differ. ATA = nose-to-target angle.
function tracking(feel, control, { targetRate = 12, seconds = 14, delay = 0.15 } = {}) {
  const ac = craft(feel, 220), p = pilot(ac, control);
  Object.assign(p.stick, { throttle: 0.85, boost: false });
  const tv = 210, w = targetRate * DEG; // target kinematics (not a flown jet)
  let th = 0; const tp = { x: 30, y: 3240, z: -650 };
  const hist = [];
  let on2 = 0, on5 = 0, sumAta = 0, n = 0, reversals = 0, lastSx = 0;
  for (let i = 0; i < Math.round(seconds / dt); i++) {
    th += w * dt;
    tp.x += Math.sin(th) * tv * dt; tp.z += -Math.cos(th) * tv * dt;
    hist.push({ ...tp });
    const seen = hist[Math.max(0, hist.length - 1 - Math.round(delay / dt))];
    const b = toBody(ac.q, sub(seen, ac.pos));
    const ahead = Math.max(-b.z, 1);
    const ax = Math.atan2(b.x, ahead), ay = Math.atan2(b.y, ahead);
    let sx, pull;
    if (control === 'assisted') { sx = clamp(ax / (20 * DEG), -1, 1); pull = clamp(ay / (8 * DEG), -1, 1); }
    else {
      // expert thumb: roll the target toward the canopy, pull on it once roughly aligned
      const roll = Math.atan2(b.x, Math.max(b.y, 1e-3 + Math.abs(b.x) * 0.05));
      const off = Math.hypot(ax, ay);
      sx = clamp(roll / (40 * DEG) * clamp(off / (3 * DEG), 0.2, 1), -1, 1);
      pull = clamp(ay / (8 * DEG), -0.5, 1);
    }
    // thumbs cannot teleport: ~0.12 s full-scale slew
    const slew = dt / 0.12;
    p.stick.x += clamp(sx - p.stick.x, -slew, slew);
    const want = -pull, cur = p.stick.y; p.stick.y = cur + clamp(want - cur, -slew, slew);
    if (Math.sign(p.stick.x) !== Math.sign(lastSx) && Math.abs(p.stick.x) > 0.15) { reversals++; lastSx = p.stick.x; }
    p.tick();
    if (i * dt < 4) continue; // acquisition phase excluded
    const ata = deg(angleBetween(forwardOf(ac.q), sub(tp, ac.pos)));
    sumAta += ata; n++;
    if (ata < 2) on2++; if (ata < 5) on5++;
  }
  return { meanAtaDeg: r2(sumAta / n), within2: r2(on2 / n), within5: r2(on5 / n), stickReversals: reversals };
}

const out = { generated: 'tools/probe-flight-feel.mjs', note: 'F-16V, 60 Hz, deterministic; not real aircraft data', modes: {} };
for (const feel of ['arcade', 'tactical']) {
  out.modes[feel] = {
    roll: { capture90: rollCapture(feel), tap100msDeg: rollTap(feel), halfTap200msDeg: rollTap(feel, 0.35, 0.2) },
    pitch: { full230: pitchStep(feel), half230: pitchStep(feel, 0.5), full140: pitchStep(feel, 1, 140) },
    engine: {
      ab150to250s: accel(feel, 150, 250), mil150to250s: accel(feel, 150, 250, false), ab100toCornerS: accel(feel, 100, 185),
      topSpeedAB: topSpeed(feel, true), topSpeedMil: topSpeed(feel, false),
    },
  };
  for (const control of ['assisted', 'expert']) {
    out.modes[`${feel}:${control}`] = {
      fullTurnAB: levelTurn(feel, control),
      fullTurnMil: levelTurn(feel, control, { boost: false }),
      moderateTurn: levelTurn(feel, control, { amount: 0.55, boost: false, throttle: 0.85 }),
      lowSpeed110: lowSpeed(feel, control),
      tracking12dps: tracking(feel, control),
      tracking20dps: tracking(feel, control, { targetRate: 20 }),
      ...(control === 'assisted' ? { entry: assistedEntry(feel), halfEntry: assistedEntry(feel, 0.5), rollout: assistedRollout(feel) } : {}),
    };
  }
}
const args = process.argv.slice(2);
const wi = args.indexOf('--write');
if (wi >= 0) writeFileSync(args[wi + 1], JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out, null, 1));
