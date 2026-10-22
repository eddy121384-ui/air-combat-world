// Minimal arcade HUD drawn on a 2D canvas over the WebGL view.
import { sub, norm, addScaled, forwardOf, DEG, angleBetween, dist } from '../sim/math.js';
import { LOCK, GUN } from '../sim/weapons.js';
import { gunLead, missilePk } from '../sim/fire.js';
import { attitudeOf } from './attitude.js';
import { bestTurn, instantTurnRate } from '../sim/aircraft.js';
import { pullUpWarning } from '../sim/warnings.js';

const GREEN = '#7dffb0', RED = '#ff4d5e', AMBER = '#ffc04d', WHITE = '#f4fbff', CYAN = '#7fe3ff';

export class Hud {
  constructor(canvas) {
    this.c = canvas;
    this.g = canvas.getContext('2d');
    this.msgs = [];      // floating centre messages
    this.radio = null;   // { who, text, t }
    this.t = 0;
    this.resize();
    window.addEventListener('resize', () => this.resize());
  }
  resize() {
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.w = window.innerWidth; this.h = window.innerHeight;
    this.c.width = this.w * this.dpr; this.c.height = this.h * this.dpr;
    this.c.style.width = this.w + 'px'; this.c.style.height = this.h + 'px';
  }
  flash(text, color = WHITE, life = 1.6, big = false) { this.msgs.push({ text, color, t: 0, life, big }); }
  say(who, text) { this.radio = { who, text, t: 0 }; }

  draw(match, me, rend, dt, opts = {}) {
    const g = this.g, w = this.w, h = this.h;
    this.t += dt;
    g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    if (!me) return;
    if (opts.minimal) { this.overlay(dt, Math.min(w, h) / 400); return; } // kill cam: banner + radio only
    const S = Math.min(w, h) / 400; // UI scale
    const tg = me.enemy;
    g.lineWidth = Math.max(1.5, 1.6 * S);
    g.font = `600 ${Math.round(12 * S)}px ui-monospace, Menlo, monospace`;
    g.textBaseline = 'middle';
    g.lineJoin = 'round';
    // every fillText gets a dark halo so numbers stay readable over white clouds
    if (!g.__halo) {
      const fill = g.fillText.bind(g);
      g.fillText = (txt, x, y) => {
        const lw = g.lineWidth, ss = g.strokeStyle;
        g.lineWidth = 3; g.strokeStyle = 'rgba(8,22,40,0.65)';
        g.strokeText(txt, x, y);
        g.lineWidth = lw; g.strokeStyle = ss;
        fill(txt, x, y);
      };
      g.__halo = true;
    }

    // speed lines (anime) when fast / boosting
    const speedK = Math.max(0, (me.speed - 280) / 120) + me.abCur * 0.35;
    if (speedK > 0.05 && me.alive) this.speedLines(speedK);

    if (me.alive) {
      // Aircraft-referenced HUD is readable even when there is no natural horizon.
      // Draw it beneath target locks, pippers, and weapon symbology.
      this.attitude(me, S);

      // Waterline W = nose; winged-circle FPM = actual travel direction.
      // Both use real camera projections; no fabricated pixel displacement.
      const f = forwardOf(me.q);
      const bs = rend.project(addScaled(me.pos, f, 1500));
      const travel = norm(me.vel);
      const fp = rend.project(addScaled(me.pos, travel, 1500));
      if (!fp.behind) this.flightPathMarker(fp.x, fp.y, 9 * S, GREEN);
      // Draw the nose last, remaining legible when straight flight overlaps FPM.
      if (!bs.behind) this.waterline(bs.x, bs.y, 10 * S, GREEN);

      // target box
      if (tg && tg.alive) {
        const R = dist(me.pos, tg.pos);
        const p = rend.project(tg.pos);
        const on = !p.behind && p.x > 0 && p.x < w && p.y > 0 && p.y < h;
        const L = me.lock;
        const color = L.locked ? RED : GREEN;
        if (on) {
          const s = Math.max(14 * S, Math.min(40 * S, 9000 / Math.max(R, 1) * S));
          g.strokeStyle = color;
          if (L.locked) this.diamond(p.x, p.y, s * 1.25); else g.strokeRect(p.x - s, p.y - s, s * 2, s * 2);
          // seeker ring closing in while acquiring
          if (!L.locked && L.timer > 0 && L.target === tg) {
            const k = 1 - L.timer / LOCK.time;
            g.beginPath(); g.arc(p.x, p.y, s * (1.3 + 2.2 * k), 0, Math.PI * 2); g.stroke();
          }
          g.fillStyle = color;
          g.textAlign = 'left';
          g.fillText(`${(R / 1000).toFixed(1)}km`, p.x + s + 6, p.y - s * 0.5);
          g.fillText(tg.name, p.x + s + 6, p.y + s * 0.5);
          if (L.locked) { g.textAlign = 'center'; g.fillText('LOCK', p.x, p.y + s * 1.25 + 12 * S); }
          // gun lead pipper
          if (R < GUN.range * 1.3) {
            const lead = gunLead(me, tg.pos, tg.vel);
            const dir = norm(sub(lead.point, me.pos));
            const lp = rend.project(addScaled(me.pos, dir, 1500));
            if (!lp.behind) {
              g.strokeStyle = AMBER;
              g.beginPath(); g.arc(lp.x, lp.y, 7 * S, 0, Math.PI * 2); g.stroke();
              g.beginPath(); g.arc(lp.x, lp.y, 1.5 * S, 0, Math.PI * 2); g.stroke();
            }
          }
          // shoot cue: good missile shot
          if (L.locked) {
            const los = norm(sub(tg.pos, me.pos));
            const aspect = Math.PI - angleBetween(forwardOf(tg.q), { x: -los.x, y: -los.y, z: -los.z });
            const pk = missilePk({ R, ata: L.ata, aspect, mySpeed: me.speed, tgSpeed: tg.speed, tgG: tg.nCur });
            if (pk > 0.45 && Math.floor(this.t * 4) % 2 === 0) {
              g.fillStyle = RED; g.textAlign = 'center';
              g.font = `700 ${Math.round(15 * S)}px ui-monospace, Menlo, monospace`;
              g.fillText('SHOOT', bs.x, bs.y + 34 * S);
              g.font = `600 ${Math.round(12 * S)}px ui-monospace, Menlo, monospace`;
            }
          }
        } else {
          this.edgeArrow(p, color, `${(R / 1000).toFixed(1)}km`, S);
        }
        // debug: show what the AI is thinking above it
        if (opts.debugText && on) {
          g.fillStyle = CYAN; g.textAlign = 'center';
          g.fillText(opts.debugText, p.x, p.y - 34 * S);
        }
      }

      // inbound missiles
      let inbound = 0, closest = Infinity;
      for (const m of match.missiles) {
        if (!m.alive || m.target !== me || !m.guided || m.decoy) continue;
        inbound++;
        const d = dist(m.pos, me.pos);
        closest = Math.min(closest, d);
        const p = rend.project(m.pos);
        const on = !p.behind && p.x > 0 && p.x < w && p.y > 0 && p.y < h;
        if (on) { g.strokeStyle = RED; this.diamond(p.x, p.y, 6 * S); }
        else this.edgeArrow(p, RED, `${(d / 1000).toFixed(1)}`, S, true);
      }
      if (inbound) {
        const blink = Math.floor(this.t * (closest < 1500 ? 8 : 4)) % 2 === 0;
        if (blink) this.banner('MISSILE', RED, h * 0.24, S);
      } else if (me.lockedBy > 0) {
        if (Math.floor(this.t * 2) % 2 === 0) this.banner('WARNING · LOCKED', AMBER, h * 0.24, S * 0.8);
      }
      // ground / stall warnings
      // Energy-aware: a 400 m/s dive needs far more room than a gentle descent.
      if (pullUpWarning(me)) {
        if (Math.floor(this.t * 5) % 2 === 0) this.banner('PULL UP', RED, h * 0.66, S);
      } else if (me.speed < 95) this.banner('STALL', AMBER, h * 0.66, S * 0.8);
      if (me.oob > 0) this.banner(`RETURN TO COMBAT AREA ${Math.max(0, 12 - me.oob).toFixed(0)}`, AMBER, h * 0.32, S * 0.75);

      // left: speed + G, right: altitude
      g.textAlign = 'right';
      g.fillStyle = WHITE;
      const kmh = Math.round(me.speed * 3.6);
      this.box(w * 0.5 - 150 * S, h * 0.5, `${kmh}`, 'SPD km/h', S, me.abCur > 0.3 ? AMBER : WHITE);
      this.energyCues(me, w * 0.5 - 150 * S, h * 0.5, dt, S);
      this.box(w * 0.5 + 150 * S, h * 0.5, `${Math.round(me.pos.y)}`, 'ALT m', S, me.pos.y < 600 ? RED : WHITE);
      g.textAlign = 'right'; g.fillStyle = me.nCur > 7 ? AMBER : WHITE;
      g.fillText(`${me.nCur.toFixed(1)}G`, w * 0.5 - 150 * S + 4 * S, h * 0.5 + 26 * S);
      g.fillStyle = WHITE;
      if (me.abCur > 0.3) g.fillText('AB', w * 0.5 - 150 * S + 4 * S, h * 0.5 - 26 * S);
      if (me.controls.brake) { g.fillStyle = AMBER; g.fillText('BRAKE', w * 0.5 - 150 * S + 4 * S, h * 0.5 - 26 * S); }

      // bottom: own status
      this.radar(match, me, w * 0.5, h - 48 * S, 38 * S, S);
      g.textAlign = 'right'; g.fillStyle = me.missiles ? WHITE : RED;
      g.fillText(`MSL ${me.missiles}`, w * 0.5 - 46 * S, h - 62 * S);
      g.fillStyle = me.flares ? WHITE : AMBER;
      g.fillText(`FLR ${me.flares}`, w * 0.5 - 46 * S, h - 44 * S);
      g.fillStyle = WHITE;
      g.fillText(`GUN ${me.gunRounds}`, w * 0.5 - 46 * S, h - 26 * S);
    }
    // top: timer + both HP bars
    const t = Math.max(0, match.timeLimit - match.time);
    g.textAlign = 'center'; g.fillStyle = match.phase === 'sudden' ? RED : WHITE;
    g.font = `700 ${Math.round(16 * S)}px ui-monospace, Menlo, monospace`;
    g.fillText(match.phase === 'sudden' ? 'SUDDEN DEATH' : `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`, w * 0.5, 16 * S);
    g.font = `600 ${Math.round(11 * S)}px ui-monospace, Menlo, monospace`;
    this.hpBar(w * 0.5 - 175 * S, 14 * S, 120 * S, me.hp / me.type.hp, `${me.name}`, CYAN, S);
    if (tg) this.hpBar(w * 0.5 + 55 * S, 14 * S, 120 * S, tg.hp / tg.type.hp, `${tg.name}`, RED, S);

    this.overlay(dt, S);
  }

  /** Floating banners and the radio subtitle (also shown during the kill cam). */
  overlay(dt, S) {
    const g = this.g, w = this.w, h = this.h;
    g.textBaseline = 'middle';
    // floating messages
    this.msgs = this.msgs.filter((m) => (m.t += dt) < m.life);
    let y = h * 0.27;
    for (const m of this.msgs) {
      const a = Math.min(1, (m.life - m.t) * 3);
      g.globalAlpha = a;
      g.textAlign = 'center'; g.fillStyle = m.color;
      g.font = `800 ${Math.round((m.big ? 30 : 16) * S)}px ui-sans-serif, system-ui, sans-serif`;
      g.fillText(m.text, w * 0.5, y);
      y += (m.big ? 34 : 22) * S;
      g.globalAlpha = 1;
    }
    // radio subtitle
    if (this.radio) {
      this.radio.t += dt;
      if (this.radio.t > 3.2) this.radio = null;
      else {
        g.globalAlpha = Math.min(1, (3.2 - this.radio.t) * 2);
        g.font = `600 ${Math.round(13 * S)}px ui-sans-serif, system-ui, "PingFang TC", "Noto Sans TC", sans-serif`;
        const txt = `${this.radio.who} ▸ ${this.radio.text}`;
        const tw = g.measureText(txt).width;
        g.fillStyle = 'rgba(10,20,35,0.55)';
        g.fillRect(w * 0.5 - tw / 2 - 10 * S, h * 0.78 - 12 * S, tw + 20 * S, 24 * S);
        g.fillStyle = this.radio.who === 'J-16' ? '#ffb3b3' : '#bfe8ff';
        g.textAlign = 'center';
        g.fillText(txt, w * 0.5, h * 0.78);
        g.globalAlpha = 1;
      }
    }
  }

  /**
   * Ace Combat 7 cockpit HUD reference, adapted for an unobstructed chase view.
   * Open-corner side guides, compass ribbon, sparse pitch ladder and whiskey mark.
   * There is deliberately NO enclosed square or dashboard of numeric labels.
   * The ladder rotates with actual aircraft attitude, not smoothed camera motion.
   */
  attitude(me, S) {
    const g = this.g;
    const { pitch, bank, heading } = attitudeOf(me.q);
    const cx = this.w * 0.5, cy = this.h * 0.5 - 10 * S;
    const halfW = 102 * S, halfH = 67 * S;
    const top = cy - halfH, bottom = cy + halfH;
    const ink = 'rgba(170,255,193,0.77)';
    const soft = 'rgba(170,255,193,0.5)';
    const faint = 'rgba(170,255,193,0.32)';
    g.save();
    g.lineWidth = Math.max(1, 1.2 * S);
    g.strokeStyle = ink;
    g.fillStyle = ink;
    g.font = `600 ${Math.max(9, Math.round(10 * S))}px ui-monospace, Menlo, monospace`;

    // Only four very short corners and discreet side bars: no picture frame.
    g.beginPath();
    for (const side of [-1, 1]) {
      const x = cx + side * halfW;
      const inward = -side * 11 * S;
      g.moveTo(x, top + 7 * S);
      g.lineTo(x, top);
      g.lineTo(x + inward, top);
      g.moveTo(x, top + 7 * S);
      g.lineTo(x, bottom - 11 * S);
      g.moveTo(x, bottom - 11 * S);
      g.lineTo(x, bottom);
      g.lineTo(x + inward, bottom);
    }
    g.stroke();

    // AC-style heading ribbon across the top, with a fixed central index.
    // These ticks move as heading changes; horizon/pitch ladder does not affect it.
    const hY = top - 12 * S, pixelsPerHeadingDeg = 2.55 * S;
    const nearest5 = Math.round(heading / 5) * 5;
    g.textAlign = 'center';
    for (let diff = -45; diff <= 45; diff += 5) {
      const compass = nearest5 + diff;
      const d = ((compass - heading + 540) % 360) - 180;
      const x = cx + d * pixelsPerHeadingDeg;
      if (Math.abs(x - cx) > halfW - 9 * S) continue;
      const major = ((compass % 30) + 30) % 30 === 0;
      g.strokeStyle = major ? ink : faint;
      g.beginPath(); g.moveTo(x, hY); g.lineTo(x, hY + (major ? 5 : 3) * S); g.stroke();
      if (major) {
        const value = ((compass % 360) + 360) % 360;
        g.fillStyle = ink;
        g.fillText(String(value).padStart(3, '0'), x, hY - 8 * S);
      }
    }
    g.strokeStyle = ink;
    g.beginPath(); g.moveTo(cx, hY - 2 * S); g.lineTo(cx, hY + 7 * S); g.stroke();

    // Roll does not require a giant BANK box: the whole horizontal reference
    // tilts, and a tiny top-side bank readout stays legible during inversion.
    g.font = `500 ${Math.max(8, Math.round(9 * S))}px ui-monospace, Menlo, monospace`;
    g.textAlign = 'right'; g.fillStyle = soft;
    g.fillText(`${Math.round(Math.abs(bank))}°${bank > 1 ? 'R' : bank < -1 ? 'L' : ''}`,
      cx + halfW - 3 * S, hY - 8 * S);

    // The ladder is cut by the side guides. No translucent background panel.
    g.beginPath();
    g.rect(cx - halfW + 5 * S, top + 9 * S, 2 * (halfW - 5 * S), 2 * halfH - 18 * S);
    g.clip();
    g.translate(cx, cy);
    g.rotate(-bank * DEG);

    const pxPerDegree = 4 * S;
    const minimum = Math.max(-90, Math.ceil((pitch - 40) / 5) * 5);
    const maximum = Math.min(90, Math.floor((pitch + 40) / 5) * 5);
    g.font = `500 ${Math.max(8, Math.round(9 * S))}px ui-monospace, Menlo, monospace`;
    for (let deg = minimum; deg <= maximum; deg += 5) {
      const y = (pitch - deg) * pxPerDegree;
      const zero = deg === 0, major = deg % 10 === 0;
      const inner = zero ? 20 * S : 31 * S; // central gap leaves room for W
      const outer = (zero ? 77 : major ? 65 : 51) * S;
      g.strokeStyle = zero ? ink : major ? soft : faint;
      g.lineWidth = zero ? 1.3 * S : 1 * S;
      g.beginPath();
      for (const side of [-1, 1]) {
        if (deg < 0) {
          // Broken lines under the horizon, as in the AC cockpit pitch scale.
          for (let a = inner; a < outer; a += 11 * S) {
            g.moveTo(side * a, y);
            g.lineTo(side * Math.min(a + 6 * S, outer), y);
          }
        } else {
          g.moveTo(side * inner, y);
          g.lineTo(side * outer, y);
        }
      }
      g.stroke();
      if (major && !zero) {
        g.textAlign = 'right'; g.fillStyle = soft;
        g.fillText(String(deg), -outer - 3 * S, y);
        g.textAlign = 'left';
        g.fillText(String(deg), outer + 3 * S, y);
      }
    }
    g.restore();
  }

  /**
   * Waterline / Whiskey Mark (small flying W).
   *
   * Aircraft nose reference only; unlike the velocity-vector/FPM it does not
   * claim to show angle of attack or side slip. The separate, existing gun
   * lead pipper remains the weapon-aiming cue.
   */
  waterline(x, y, s, color) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    const g = this.g;
    g.save();
    g.strokeStyle = color;
    g.lineWidth = Math.max(1.1, 1.35 * s / 10);
    g.lineJoin = 'miter';
    g.lineCap = 'square';
    g.beginPath();
    // Long, unobtrusive shoulders + two shallow valleys + high center peak.
    // The open silhouette remains legible on a compact iPhone HUD.
    g.moveTo(x - 1.35 * s, y - 0.32 * s);
    g.lineTo(x - 0.91 * s, y - 0.32 * s);
    g.lineTo(x - 0.50 * s, y + 0.37 * s);
    g.lineTo(x, y - 0.54 * s);
    g.lineTo(x + 0.50 * s, y + 0.37 * s);
    g.lineTo(x + 0.91 * s, y - 0.32 * s);
    g.lineTo(x + 1.35 * s, y - 0.32 * s);
    g.stroke();
    g.restore();
  }
  /**
   * Flight Path Marker / Velocity Vector (winged circle).
   * Its position is projected from ac.vel, which also drives displacement.
   * No angle-of-attack estimate, fake screen offset or extra pilot control.
   */
  flightPathMarker(x, y, s, color) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    const g = this.g;
    g.save();
    g.globalAlpha *= 0.83;
    g.strokeStyle = color;
    g.lineWidth = Math.max(1, 1.15 * s / 10);
    g.lineCap = 'square';
    g.beginPath();
    const radius = 0.40 * s;
    g.arc(x, y, radius, 0, Math.PI * 2);
    g.moveTo(x - radius, y);
    g.lineTo(x - 1.20 * s, y);
    g.moveTo(x + radius, y);
    g.lineTo(x + 1.20 * s, y);
    g.moveTo(x, y - radius);
    g.lineTo(x, y - 1.16 * s);
    g.stroke();
    g.restore();
  }

  diamond(x, y, s) {
    const g = this.g;
    g.beginPath(); g.moveTo(x, y - s); g.lineTo(x + s, y); g.lineTo(x, y + s); g.lineTo(x - s, y); g.closePath(); g.stroke();
  }
  edgeArrow(p, color, label, S, small = false) {
    const g = this.g, w = this.w, h = this.h;
    let dx = p.x - w / 2, dy = p.y - h / 2;
    if (p.behind) { dx = -dx; dy = -dy; }
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) dy = 1;
    let a = Math.atan2(dy, dx);
    // target nearly dead astern: keep the arrow on the side it was, don't flicker left/right
    if (p.behind && !small) {
      const side = Math.cos(a) >= 0 ? 1 : -1;
      if (this.behindSide && side !== this.behindSide && Math.abs(Math.cos(a)) < 0.35) a = Math.PI - a;
      else this.behindSide = side;
    } else if (!small) this.behindSide = 0;
    const rx = w / 2 - 46 * S, ry = h / 2 - (Math.sin(a) > 0 ? 110 : 46) * S;
    const k = Math.min(rx / Math.abs(Math.cos(a) || 1e-6), ry / Math.abs(Math.sin(a) || 1e-6));
    const x = w / 2 + Math.cos(a) * k, y = h / 2 + Math.sin(a) * k;
    const s = (small ? 9 : 14) * S;
    g.fillStyle = color;
    g.save(); g.translate(x, y); g.rotate(a);
    g.beginPath(); g.moveTo(s, 0); g.lineTo(-s * 0.7, s * 0.7); g.lineTo(-s * 0.35, 0); g.lineTo(-s * 0.7, -s * 0.7); g.closePath(); g.fill();
    g.restore();
    g.textAlign = 'center';
    g.fillText(label, x - Math.cos(a) * 24 * S, y - Math.sin(a) * 20 * S);
  }
  banner(text, color, y, S) {
    const g = this.g;
    g.font = `800 ${Math.round(20 * S)}px ui-sans-serif, system-ui, sans-serif`;
    g.textAlign = 'center';
    const tw = g.measureText(text).width;
    g.strokeStyle = color; g.lineWidth = 2;
    g.strokeRect(this.w / 2 - tw / 2 - 12, y - 16 * S, tw + 24, 32 * S);
    g.fillStyle = color; g.fillText(text, this.w / 2, y + 1);
    g.font = `600 ${Math.round(12 * S)}px ui-monospace, Menlo, monospace`;
  }
  box(x, y, value, label, S, color) {
    // AC7's small green speed/altitude chevron, not a giant detached number.
    const g = this.g, speed = label.startsWith('SPD');
    const ink = color === RED ? RED : GREEN;
    g.save();
    g.fillStyle = ink; g.strokeStyle = ink; g.textAlign = 'center';
    g.font = `600 ${Math.max(9, Math.round(10 * S))}px ui-monospace, Menlo, monospace`;
    g.fillText(speed ? 'SPEED' : 'ALT', x, y - 17 * S);
    g.font = `600 ${Math.max(12, Math.round(13 * S))}px ui-monospace, Menlo, monospace`;
    const valueText = String(value);
    const halfW = Math.max(28 * S, g.measureText(valueText).width / 2 + 7 * S);
    const h = 8 * S, tip = 8 * S;
    g.lineWidth = Math.max(1, 1.1 * S);
    g.beginPath();
    if (speed) {
      g.moveTo(x - halfW, y - h);
      g.lineTo(x + halfW - tip, y - h);
      g.lineTo(x + halfW, y);
      g.lineTo(x + halfW - tip, y + h);
      g.lineTo(x - halfW, y + h);
      g.closePath();
    } else {
      g.moveTo(x + halfW, y - h);
      g.lineTo(x - halfW + tip, y - h);
      g.lineTo(x - halfW, y);
      g.lineTo(x - halfW + tip, y + h);
      g.lineTo(x + halfW, y + h);
      g.closePath();
    }
    g.stroke();
    g.fillText(valueText, x, y);
    g.restore();
    g.font = `600 ${Math.round(12 * S)}px ui-monospace, Menlo, monospace`;
  }
  /** Speed-trend bar and best-turn-speed diamond beside the speed box. Both read
   *  the shared flight model; nothing here changes what the aircraft can do. */
  energyCues(me, x, y, dt, S) {
    const g = this.g;
    if (dt > 0) {
      if (this.trendAc !== me) { this.trendAc = me; this.prevSpeed = me.speed; this.accel = 0; }
      const a = (me.speed - this.prevSpeed) / dt;
      this.prevSpeed = me.speed;
      this.accel += (a - this.accel) * Math.min(1, dt / 0.35);
    }
    const bx = x - 40 * S, len = Math.max(-1, Math.min(1, this.accel / 12)) * 16 * S;
    g.save();
    g.strokeStyle = this.accel < -4 ? AMBER : GREEN;
    g.lineWidth = Math.max(2, 2.2 * S);
    g.beginPath(); g.moveTo(bx - 4 * S, y); g.lineTo(bx + 4 * S, y); g.stroke();
    if (Math.abs(len) > 1) {
      g.beginPath(); g.moveTo(bx, y); g.lineTo(bx, y - len); g.stroke();
      g.beginPath(); g.moveTo(bx - 3 * S, y - len + Math.sign(len) * 3 * S); g.lineTo(bx, y - len); g.lineTo(bx + 3 * S, y - len + Math.sign(len) * 3 * S); g.stroke();
    }
    const best = bestTurn(me);
    if (instantTurnRate(me) >= best.rate * 0.92) {
      g.fillStyle = GREEN;
      const dx = x - 40 * S, dy = y + 15 * S, r = 4 * S;
      g.beginPath(); g.moveTo(dx, dy - r); g.lineTo(dx + r, dy); g.lineTo(dx, dy + r); g.lineTo(dx - r, dy); g.closePath(); g.fill();
    }
    g.restore();
  }
  hpBar(x, y, w, k, label, color, S) {
    const g = this.g;
    g.fillStyle = 'rgba(10,20,35,0.45)'; g.fillRect(x, y - 5 * S, w, 10 * S);
    g.fillStyle = k < 0.35 ? RED : color; g.fillRect(x, y - 5 * S, w * Math.max(0, k), 10 * S);
    g.strokeStyle = 'rgba(244,251,255,0.8)'; g.lineWidth = 1; g.strokeRect(x, y - 5 * S, w, 10 * S);
    g.fillStyle = WHITE; g.textAlign = 'left';
    g.fillText(label, x, y + 14 * S);
  }
  radar(match, me, cx, cy, r, S) {
    const g = this.g;
    g.fillStyle = 'rgba(10,30,45,0.45)';
    g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.fill();
    g.strokeStyle = 'rgba(127,227,255,0.55)'; g.lineWidth = 1;
    g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.stroke();
    g.beginPath(); g.arc(cx, cy, r * 0.5, 0, Math.PI * 2); g.stroke();
    const f = forwardOf(me.q);
    const hd = Math.atan2(f.x, -f.z);
    const range = 6000;
    const plot = (p, color, size) => {
      const dx = p.x - me.pos.x, dz = p.z - me.pos.z;
      // rotate so that my heading points up
      const x = dx * Math.cos(-hd) - (-dz) * Math.sin(-hd);
      const y = dx * Math.sin(-hd) + (-dz) * Math.cos(-hd);
      let rx = x / range * r, ry = -y / range * r;
      const l = Math.hypot(rx, ry);
      if (l > r) { rx *= r / l; ry *= r / l; }
      g.fillStyle = color; g.fillRect(cx + rx - size / 2, cy + ry - size / 2, size, size);
    };
    // arena edge hint
    const toCenter = Math.hypot(me.pos.x, me.pos.z);
    if (toCenter > 7000) plot({ x: 0, y: 0, z: 0 }, 'rgba(127,227,255,0.6)', 3 * S);
    for (const m of match.missiles) if (m.alive) plot(m.pos, m.owner === me ? WHITE : RED, 2.5 * S);
    if (me.enemy && me.enemy.alive) plot(me.enemy.pos, RED, 5 * S);
    g.fillStyle = CYAN;
    g.beginPath(); g.moveTo(cx, cy - 5 * S); g.lineTo(cx + 4 * S, cy + 4 * S); g.lineTo(cx - 4 * S, cy + 4 * S); g.closePath(); g.fill();
  }
  speedLines(k) {
    const g = this.g, w = this.w, h = this.h;
    const n = Math.floor(10 + 26 * Math.min(1, k));
    g.strokeStyle = `rgba(255,255,255,${0.12 + 0.2 * Math.min(1, k)})`;
    g.lineWidth = 1.5;
    const seed = Math.floor(this.t * 30);
    for (let i = 0; i < n; i++) {
      const a = ((i * 137.5 + seed * 31) % 360) * DEG;
      const r0 = Math.max(w, h) * (0.42 + ((i * 53 + seed * 7) % 20) / 100);
      const r1 = r0 + Math.max(w, h) * (0.12 + 0.1 * k);
      g.beginPath();
      g.moveTo(w / 2 + Math.cos(a) * r0, h / 2 + Math.sin(a) * r0);
      g.lineTo(w / 2 + Math.cos(a) * r1, h / 2 + Math.sin(a) * r1);
      g.stroke();
    }
  }
}
