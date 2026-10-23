// Touch + keyboard input -> abstract stick/buttons -> aircraft controls.
// The assist layer only shapes stick input; the aircraft still flies the shared flight model.
import { clamp, smoothstep, DEG, G } from '../sim/math.js';
import { bankAngle, pitchAngle, pitchForG, neutralG, availableG, MIN_SPEED } from '../sim/aircraft.js';

export class Input {
  constructor(root) {
    this.stick = { x: 0, y: 0 };        // x: right +, y: up + (screen)
    this.stickOffset = { x: 0, y: 0 }; // visual deflection; springs to neutral on release
    this.keys = new Set();
    this.btn = { msl: false, gun: false, brake: false, flare: false, look: false, boost: false, yawLeft: false, yawRight: false };
    this.pressed = new Set();           // one-shot presses this frame
    this.boostToggle = false;
    this.throttleValue = 0.72;  // latched 0..1, independent of AB and airbrake
    this.powerPointer = null;
    this.touchActive = false;
    this.root = root;
    this.stickTouch = null;
    this.buttonHolds = new Map();
    this.bindKeyboard();
    this.bindTouch();
    window.addEventListener('blur', () => this.releaseHeld());
    window.addEventListener('pagehide', () => this.releaseHeld());
    globalThis.document?.addEventListener('visibilitychange', () => {
      if (document.hidden) this.releaseHeld();
    });
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
      this.resetStick();
      this.stickTouch = t.identifier;
      this.origin = { x: t.clientX, y: t.clientY };
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
        this.resetStick();
      }
    };
    zone.addEventListener('touchmove', move, { passive: false });
    zone.addEventListener('touchend', end);
    zone.addEventListener('touchcancel', end);
    // Also catch termination outside the zone; only its owning finger releases it.
    window.addEventListener('touchend', end);
    window.addEventListener('touchcancel', end);

    // Power strip: track is absolute throttle (no spring return). One finger can
    // adjust it while the other controls flight; the two end buttons stay independent.
    const track = this.root.querySelector('#throttleTrack');
    if (track) {
      const drag = (y) => {
        const rect = track.getBoundingClientRect();
        const travel = Math.max(1, rect.height - 18);
        this.setThrottle(1 - (y - rect.top - 9) / travel);
      };
      track.addEventListener('pointerdown', (e) => {
        if (this.powerPointer !== null) return;
        e.preventDefault(); this.touchActive = true;
        this.powerPointer = e.pointerId;
        track.setPointerCapture?.(e.pointerId);
        drag(e.clientY);
      });
      track.addEventListener('pointermove', (e) => {
        if (e.pointerId === this.powerPointer) { e.preventDefault(); drag(e.clientY); }
      });
      const endPower = (e) => {
        if (e.pointerId === this.powerPointer) this.powerPointer = null;
      };
      track.addEventListener('pointerup', endPower);
      track.addEventListener('pointercancel', endPower);
      track.addEventListener('lostpointercapture', endPower);
      track.addEventListener('keydown', (e) => {
        const steps = { ArrowUp: 0.05, ArrowDown: -0.05, PageUp: 0.2, PageDown: -0.2 };
        if (e.code in steps) { e.preventDefault(); this.setThrottle(this.throttleValue + steps[e.code]); }
        else if (e.code === 'Home' || e.code === 'End') {
          e.preventDefault(); this.setThrottle(e.code === 'Home' ? 0 : 1);
        }
      });
      this.setThrottle(this.throttleValue);
    }

    // buttons: hold-type and tap-type
    for (const el of this.root.querySelectorAll('[data-btn]')) {
      const name = el.dataset.btn;
      const holds = new Set();
      this.buttonHolds.set(name, holds);
      const on = (e) => {
        if (e.cancelable) e.preventDefault(); // touchcancel is never cancelable
        this.touchActive = true;
        const wasHeld = holds.size > 0;
        if (e.changedTouches) for (const t of e.changedTouches) holds.add(t.identifier);
        else holds.add('mouse');
        if (wasHeld) return;
        el.classList.add('down');
        if (name === 'boost') {
          this.boostToggle = !this.boostToggle;
          el.classList.toggle('lit', this.boostToggle);
          el.setAttribute?.('aria-pressed', String(this.boostToggle));
          return;
        }
        if (name === 'msl' || name === 'flare') this.pressed.add(name);
        this.btn[name] = true;
        // BRK is momentary; do not change the pilot's latched AB setting.
      };
      const off = (e) => {
        if (e.cancelable) e.preventDefault();
        if (e.changedTouches) for (const t of e.changedTouches) holds.delete(t.identifier);
        else holds.delete('mouse');
        if (holds.size) return; // a second finger still owns this held button
        el.classList.remove('down');
        if (name !== 'boost') this.btn[name] = false;
      };
      el.addEventListener('touchstart', on, { passive: false });
      el.addEventListener('touchend', off, { passive: false });
      el.addEventListener('touchcancel', off, { passive: false });
      // mouse fallback so the touch UI can be clicked on desktop too
      el.addEventListener('mousedown', on);
      el.addEventListener('mouseup', off);
      el.addEventListener('mouseleave', (e) => { if (el.classList.contains('down')) off(e); });
    }
  }

  setThrottle(value) {
    this.throttleValue = clamp(value, 0, 1);
    const track = this.root.querySelector('#throttleTrack');
    const handle = this.root.querySelector('#throttleHandle');
    const fill = this.root.querySelector('#throttleFill');
    const readout = this.root.querySelector('#throttleValue');
    if (handle) {
      const inverse = 1 - this.throttleValue;
      handle.style.top = `calc(${inverse * 100}% - ${inverse * 18}px)`;
    }
    if (fill) fill.style.height = `${Math.round(this.throttleValue * 100)}%`;
    if (readout) readout.textContent = `${Math.round(this.throttleValue * 100)}%`;
    track?.setAttribute?.('aria-valuenow', String(Math.round(this.throttleValue * 100)));
  }

  resetPower() {
    // Each sortie starts at the familiar 72% cruise setting; no surprise AB.
    this.setThrottle(0.72);
    this.boostToggle = false;
    this.powerPointer = null;
    this.btn.brake = false;
    this.buttonHolds.get('boost')?.clear();
    this.buttonHolds.get('brake')?.clear();
    const boost = this.root.querySelector('[data-btn="boost"]');
    const brake = this.root.querySelector('[data-btn="brake"]');
    boost?.classList.remove('lit');
    boost?.classList.remove('down');
    boost?.setAttribute?.('aria-pressed', 'false');
    brake?.classList.remove('down');
  }

  resetStick() {
    // Neutral COMMAND, not an attitude hold or a wings-level command in Expert.
    this.stickTouch = null;
    this.stick.x = 0; this.stick.y = 0;
    this.stickOffset.x = 0; this.stickOffset.y = 0;
    const base = this.root.querySelector('#stickBase');
    base.style.left = ''; base.style.top = '';
    base.classList.remove('on');
    this.root.querySelector('#stickKnob').style.transform = 'translate(0px, 0px)';
  }

  /** Cancel transient input on pause/focus loss; power latches remain the pilot's. */
  releaseHeld() {
    this.resetStick();
    this.keys.clear(); this.pressed.clear();
    for (const key of Object.keys(this.btn)) this.btn[key] = false;
    for (const holds of this.buttonHolds.values()) holds.clear();
    for (const el of this.root.querySelectorAll('[data-btn]')) el.classList.remove('down');
    const track = this.root.querySelector('#throttleTrack'), pointer = this.powerPointer;
    this.powerPointer = null;
    if (pointer != null && track?.hasPointerCapture?.(pointer)) track.releasePointerCapture(pointer);
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
    // Mobile rudder pedals share the same neutral-centred axis as keyboard A/D.
    // Opposing inputs cancel. Releasing a pedal cannot leave yaw latched.
    const yaw = clamp(Number(k.has('KeyD')) - Number(k.has('KeyA'))
      + Number(this.btn.yawRight) - Number(this.btn.yawLeft), -1, 1);
    return { x, y, yaw };
  }
  throttle() { return this.throttleValue; }
  boost() { return this.keys.has('KeyW') || this.boostToggle; }
  brake() { return this.keys.has('KeyS') || this.btn.brake; }
  gun() { return this.keys.has('ShiftLeft') || this.keys.has('ShiftRight') || this.keys.has('KeyF') || this.btn.gun; }
  look() { return this.keys.has('KeyE') || this.btn.look; }
}

/**
 * Player pilot: converts Input into the same controls structure the AI produces.
 * settings.assist: stick-x banks to an angle and the turn is held level automatically;
 * neutral input rolls wings-level; touch release centres the command in both modes.
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
    const c = { pitch: 0, roll: 0, yaw: yaw * 0.9, throttle: inp.throttle?.() ?? 0.72, boost: inp.boost(), brake: inp.brake(), fireMissile: false, fireGun: inp.gun(), flare: false };
    if (inp.consume('msl')) c.fireMissile = true;
    if (inp.consume('flare')) c.flare = true;
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
        // Stick deflection is proportional to TURN RATE, not to G: G-linear mapping
        // made 10% stick bank the jet ~56 degrees for a 4 deg/s turn. Full stick is
        // unchanged (85% of available G); the G is still bounded by the airframe.
        const nFull = 1 + (nAvail - 1) * 0.85;
        const wFull = Math.sqrt(Math.max(0, nFull * nFull - 1)) * G / Math.max(ac.speed, MIN_SPEED);
        const w = wFull * Math.min(1, Math.abs(x)) * Math.max(ac.speed, MIN_SPEED) / G;
        let nTurn = Math.sqrt(1 + w * w);
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
      // fine aim: small sideways stick also yaws the nose a little (faded out
      // smoothly instead of switching off at |x| = 0.3 with a jolt)
      c.yaw += x * 1.6 * (1 - smoothstep(0.18, 0.36, Math.abs(x)));
      // No hidden afterburner override: Assisted and Expert share the same engine inputs.
    } else {
      c.roll = x;
      c.pitch = y;
    }
    return c;
  }
}
