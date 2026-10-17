// Touch + keyboard input -> abstract stick/buttons -> aircraft controls.
// The assist layer only shapes stick input; the aircraft still flies the shared flight model.
import { clamp, DEG } from '../sim/math.js';
import { bankAngle, pitchAngle, pitchForG, neutralG, availableG } from '../sim/aircraft.js';

export class Input {
  constructor(root) {
    this.stick = { x: 0, y: 0 };        // x: right +, y: up + (screen)
    this.stickOffset = { x: 0, y: 0 }; // visual stick deflection persists after touch release
    this.keys = new Set();
    this.btn = { msl: false, gun: false, brake: false, flare: false, look: false, boost: false };
    this.pressed = new Set();           // one-shot presses this frame
    this.boostToggle = false;
    this.touchActive = false;
    this.root = root;
    this.stickTouch = null;
    this.bindKeyboard();
    this.bindTouch();
  }

  bindKeyboard() {
    const down = (e) => {
      if (e.repeat) return;
      const k = e.code;
      this.keys.add(k);
      if (k === 'Space') this.pressed.add('msl');
      if (k === 'KeyQ') this.pressed.add('flare');
      if (k === 'Enter' || k === 'KeyR') this.pressed.add('restart');
      if (k === 'Backquote' || k === 'Tab') { this.pressed.add('debug'); e.preventDefault(); }
      if (k === 'Escape' || k === 'KeyP') this.pressed.add('pause');
      if (k === 'KeyC') this.pressed.add('camera');
      if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(k)) e.preventDefault();
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', (e) => this.keys.delete(e.code));
    window.addEventListener('blur', () => this.keys.clear());
  }

  bindTouch() {
    const zone = this.root.querySelector('#stickZone');
    const base = this.root.querySelector('#stickBase');
    const knob = this.root.querySelector('#stickKnob');
    const R = 62;
    const setKnob = (dx, dy) => { knob.style.transform = `translate(${dx}px, ${dy}px)`; };
    zone.addEventListener('touchstart', (e) => {
      e.preventDefault();
      this.touchActive = true;
      if (this.stickTouch != null) return;
      const t = e.changedTouches[0];
      this.stickTouch = t.identifier;
      // Keep the last stick deflection. Re-anchor the floating base so a new
      // touch continues from that value instead of snapping to neutral.
      this.origin = { x: t.clientX - this.stickOffset.x, y: t.clientY - this.stickOffset.y };
      base.style.left = `${this.origin.x}px`; base.style.top = `${this.origin.y}px`;
      base.classList.add('on');
      setKnob(this.stickOffset.x, this.stickOffset.y);
    }, { passive: false });
    const move = (e) => {
      for (const t of e.changedTouches) {
        if (t.identifier !== this.stickTouch) continue;
        e.preventDefault();
        let dx = t.clientX - this.origin.x, dy = t.clientY - this.origin.y;
        const l = Math.hypot(dx, dy);
        if (l > R) { dx *= R / l; dy *= R / l; }
        this.stickOffset.x = dx; this.stickOffset.y = dy;
        setKnob(dx, dy);
        // small dead zone, then a gentle expo curve for fine aiming
        const shape = (v) => { const a = Math.max(0, Math.abs(v) - 0.06) / 0.94; return Math.sign(v) * (0.35 * a + 0.65 * a * a); };
        this.stick.x = shape(dx / R); this.stick.y = shape(-dy / R);
      }
    };
    const end = (e) => {
      for (const t of e.changedTouches) {
        if (t.identifier !== this.stickTouch) continue;
        // A lifted finger is NOT a neutral-stick command: maintain the
        // player's chosen turn / pitch until the next drag or a new match.
        this.stickTouch = null;
        base.classList.remove('on');
      }
    };
    zone.addEventListener('touchmove', move, { passive: false });
    zone.addEventListener('touchend', end);
    zone.addEventListener('touchcancel', end);

    // buttons: hold-type and tap-type
    for (const el of this.root.querySelectorAll('[data-btn]')) {
      const name = el.dataset.btn;
      const on = (e) => {
        e.preventDefault(); this.touchActive = true;
        el.classList.add('down');
        if (name === 'boost') { this.boostToggle = !this.boostToggle; el.classList.toggle('lit', this.boostToggle); return; }
        if (name === 'msl' || name === 'flare') this.pressed.add(name);
        this.btn[name] = true;
        if (name === 'brake') { this.boostToggle = false; this.root.querySelector('[data-btn="boost"]').classList.remove('lit'); }
      };
      const off = (e) => { e.preventDefault(); el.classList.remove('down'); if (name !== 'boost') this.btn[name] = false; };
      el.addEventListener('touchstart', on, { passive: false });
      el.addEventListener('touchend', off, { passive: false });
      el.addEventListener('touchcancel', off, { passive: false });
      // mouse fallback so the touch UI can be clicked on desktop too
      el.addEventListener('mousedown', on);
      el.addEventListener('mouseup', off);
      el.addEventListener('mouseleave', (e) => { if (el.classList.contains('down')) off(e); });
    }
  }

  resetStick() {
    // Explicit neutral only at the start of a fresh match.
    this.stickTouch = null;
    this.stick.x = 0; this.stick.y = 0;
    this.stickOffset.x = 0; this.stickOffset.y = 0;
    const base = this.root.querySelector('#stickBase');
    base.style.left = ''; base.style.top = '';
    base.classList.remove('on');
    this.root.querySelector('#stickKnob').style.transform = 'translate(0px, 0px)';
  }

  consume(name) { const had = this.pressed.has(name); this.pressed.delete(name); return had; }
  clearPresses() { this.pressed.clear(); }

  /** Combined stick from keyboard + touch. */
  axes() {
    const k = this.keys;
    let x = this.stick.x, y = this.stick.y;
    if (k.has('ArrowLeft')) x = -1;
    if (k.has('ArrowRight')) x = 1;
    if (k.has('ArrowUp')) y = 1;
    if (k.has('ArrowDown')) y = -1;
    let yaw = 0;
    if (k.has('KeyA')) yaw -= 1;
    if (k.has('KeyD')) yaw += 1;
    return { x, y, yaw };
  }
  boost() { return this.keys.has('KeyW') || this.boostToggle; }
  brake() { return this.keys.has('KeyS') || this.btn.brake; }
  gun() { return this.keys.has('ShiftLeft') || this.keys.has('ShiftRight') || this.keys.has('KeyF') || this.btn.gun; }
  look() { return this.keys.has('KeyE') || this.btn.look; }
}

/**
 * Player pilot: converts Input into the same controls structure the AI produces.
 * settings.assist: stick-x banks to an angle and the turn is held level automatically;
 * neutral input rolls wings-level, but releasing touch holds the last stick setting.
 * settings.invert: stick-up = climb.
 */
export class PlayerController {
  constructor(ac, input, settings) {
    this.ac = ac; this.input = input; this.settings = settings;
  }
  update() {
    const ac = this.ac, s = this.settings, inp = this.input;
    const { x, y: yRaw, yaw } = inp.axes();
    const y = s.invert ? yRaw : -yRaw; // default: stick up = nose down (flight convention)
    const c = { pitch: 0, roll: 0, yaw: yaw * 0.9, throttle: 0.72, boost: inp.boost(), brake: inp.brake(), fireMissile: false, fireGun: inp.gun(), flare: false };
    if (inp.consume('msl')) c.fireMissile = true;
    if (inp.consume('flare')) c.flare = true;
    if (c.brake) c.boost = false;
    if (s.assist) {
      // ASSIST = level-turn controller. Stick sideways asks for turn G; the bank angle is solved
      // from that G (bank = acos(1/n)) so a hard turn stays level instead of becoming a
      // climbing loop that bleeds the jet into a stall. Pull tightens the turn. With the stick
      // centred it is plain pitch, so loops and dives are still yours. The aircraft itself
      // flies the same flight model as the AI.
      const bank = bankAngle(ac);
      const nearVertical = Math.abs(pitchAngle(ac)) > 60 * DEG;
      const nAvail = availableG(ac), n0 = neutralG(ac);
      const turning = Math.abs(x) > 0.05;
      if (nearVertical) { c.roll = x; c.pitch = y; }
      else if (turning) {
        let nTurn = 1 + (nAvail - 1) * Math.min(1, Math.abs(x)) * 0.85;
        if (y > 0) nTurn += (nAvail - nTurn) * y;
        nTurn = clamp(nTurn, 1.05, Math.max(1.05, nAvail));
        const bankT = Math.sign(x) * Math.acos(clamp(1 / nTurn, 0, 1));
        const rollErr = Math.atan2(Math.sin(bankT - bank), Math.cos(bankT - bank));
        c.roll = clamp(rollErr * 3.2 - ac.rollRateCur * 0.12, -1, 1);
        // roll first, then pull (pulling while the lift vector points elsewhere loops the nose)
        const align = Math.max(0, Math.cos(Math.min(Math.abs(rollErr), Math.PI / 2)));
        let n = n0 + (nTurn - n0) * align;
        if (y < 0) n += y * (n - n0 + 1.5); // push in a turn: ease off / descend
        c.pitch = pitchForG(ac, n);
      } else {
        // centred stick: wings auto-level, stick y is direct pitch
        const rollErr = Math.atan2(Math.sin(-bank), Math.cos(-bank));
        c.roll = clamp(rollErr * 2.5 - ac.rollRateCur * 0.12, -1, 1);
        c.pitch = y;
      }
      // fine aim: small sideways stick also yaws the nose a little
      if (Math.abs(x) < 0.3) c.yaw += x * 1.6;
      // auto-burner when slow (keeps a thumb-only player out of the stall spiral)
      if (ac.speed < 0.7 * ac.type.cornerSpeed && !c.brake) c.boost = true;
    } else {
      c.roll = x;
      c.pitch = y;
    }
    return c;
  }
}
