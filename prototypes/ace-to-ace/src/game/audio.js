// Procedural WebAudio sound: no asset files. Must be unlocked by a user gesture (iOS).
export class Audio {
  constructor() { this.ctx = null; this.muted = false; this.lastGun = 0; }

  unlock() {
    if (this.ctx) { if (this.ctx.state === 'suspended') this.ctx.resume(); return; }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    this.ctx = new AC();
    const c = this.ctx;
    this.master = c.createGain(); this.master.gain.value = this.muted ? 0 : 0.7; this.master.connect(c.destination);
    // shared noise buffer
    const len = c.sampleRate * 2;
    this.noiseBuf = c.createBuffer(1, len, c.sampleRate);
    const d = this.noiseBuf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    // engine: low saw + filtered noise
    this.engOsc = c.createOscillator(); this.engOsc.type = 'sawtooth'; this.engOsc.frequency.value = 55;
    this.engNoise = c.createBufferSource(); this.engNoise.buffer = this.noiseBuf; this.engNoise.loop = true;
    this.engFilter = c.createBiquadFilter(); this.engFilter.type = 'lowpass'; this.engFilter.frequency.value = 500;
    this.engGain = c.createGain(); this.engGain.gain.value = 0;
    const oscGain = c.createGain(); oscGain.gain.value = 0.18;
    this.engOsc.connect(oscGain).connect(this.engFilter);
    this.engNoise.connect(this.engFilter);
    this.engFilter.connect(this.engGain).connect(this.master);
    this.engOsc.start(); this.engNoise.start();
    // continuous tone for lock / warnings
    this.tone = c.createOscillator(); this.tone.type = 'square'; this.tone.frequency.value = 900;
    this.toneGain = c.createGain(); this.toneGain.gain.value = 0;
    this.tone.connect(this.toneGain).connect(this.master); this.tone.start();
    this.warn = c.createOscillator(); this.warn.type = 'square'; this.warn.frequency.value = 1150;
    this.warnGain = c.createGain(); this.warnGain.gain.value = 0;
    this.warn.connect(this.warnGain).connect(this.master); this.warn.start();
  }

  setMuted(m) { this.muted = m; if (this.master) this.master.gain.value = m ? 0 : 0.7; }

  /** Per-frame continuous sounds. state: { throttle, ab, speed, locking, locked, missileWarn, lockWarn, alive } */
  frame(st, t) {
    if (!this.ctx) return;
    const now = this.ctx.currentTime;
    const on = st.alive ? 1 : 0;
    this.engOsc.frequency.setTargetAtTime(48 + st.throttle * 30 + st.ab * 25, now, 0.1);
    this.engFilter.frequency.setTargetAtTime(380 + st.ab * 900 + st.speed * 1.2, now, 0.1);
    this.engGain.gain.setTargetAtTime(on * (0.10 + st.throttle * 0.07 + st.ab * 0.1), now, 0.15);
    // lock: slow growl while acquiring, steady high tone when locked
    let tg = 0;
    if (st.locked) { this.tone.frequency.setTargetAtTime(1320, now, 0.01); tg = 0.05; }
    else if (st.locking) { this.tone.frequency.setTargetAtTime(760, now, 0.01); tg = (Math.floor(t * 10) % 2) * 0.04; }
    this.toneGain.gain.setTargetAtTime(on * tg, now, 0.01);
    let wg = 0;
    if (st.missileWarn) wg = (Math.floor(t * (st.missileClose ? 14 : 8)) % 2) * 0.06;
    else if (st.lockWarn) wg = (Math.floor(t * 3) % 2) * 0.035;
    this.warnGain.gain.setTargetAtTime(on * wg, now, 0.005);
  }

  noise(dur, { freq = 1000, q = 1, type = 'bandpass', gain = 0.5, sweepTo = null, attack = 0.005 } = {}) {
    if (!this.ctx) return;
    const c = this.ctx, now = c.currentTime;
    const src = c.createBufferSource(); src.buffer = this.noiseBuf;
    src.playbackRate.value = 0.8 + Math.random() * 0.4;
    const f = c.createBiquadFilter(); f.type = type; f.frequency.value = freq; f.Q.value = q;
    if (sweepTo) f.frequency.exponentialRampToValueAtTime(sweepTo, now + dur);
    const gn = c.createGain();
    gn.gain.setValueAtTime(0.0001, now);
    gn.gain.exponentialRampToValueAtTime(gain, now + attack);
    gn.gain.exponentialRampToValueAtTime(0.0001, now + dur);
    src.connect(f).connect(gn).connect(this.master);
    src.start(now, Math.random()); src.stop(now + dur + 0.05);
  }
  thump(freq = 60, dur = 0.6, gain = 0.6) {
    if (!this.ctx) return;
    const c = this.ctx, now = c.currentTime;
    const o = c.createOscillator(); o.type = 'sine'; o.frequency.setValueAtTime(freq * 2, now); o.frequency.exponentialRampToValueAtTime(freq * 0.5, now + dur);
    const gn = c.createGain(); gn.gain.setValueAtTime(gain, now); gn.gain.exponentialRampToValueAtTime(0.0001, now + dur);
    o.connect(gn).connect(this.master); o.start(now); o.stop(now + dur + 0.05);
  }
  beep(freq, dur = 0.08, gain = 0.08) {
    if (!this.ctx) return;
    const c = this.ctx, now = c.currentTime;
    const o = c.createOscillator(); o.type = 'square'; o.frequency.value = freq;
    const gn = c.createGain(); gn.gain.setValueAtTime(gain, now); gn.gain.exponentialRampToValueAtTime(0.0001, now + dur);
    o.connect(gn).connect(this.master); o.start(now); o.stop(now + dur + 0.02);
  }

  missileLaunch(own) { this.noise(1.1, { freq: 2500, sweepTo: 300, q: 0.7, gain: own ? 0.5 : 0.18, attack: 0.02 }); }
  gun(own) {
    if (!this.ctx) return;
    const now = this.ctx.currentTime;
    if (now - this.lastGun < 0.06) return;
    this.lastGun = now;
    this.noise(0.07, { freq: own ? 700 : 500, q: 0.8, type: 'lowpass', gain: own ? 0.35 : 0.12 });
  }
  explosion(dist = 500) {
    const k = Math.max(0.15, Math.min(1, 1200 / (dist + 300)));
    this.noise(1.6, { freq: 900, sweepTo: 120, q: 0.5, type: 'lowpass', gain: 0.9 * k, attack: 0.01 });
    this.thump(55, 0.9, 0.7 * k);
  }
  hit() { this.noise(0.25, { freq: 1800, q: 2, gain: 0.35 }); this.thump(90, 0.3, 0.4); }
  flares() { for (let i = 0; i < 4; i++) setTimeout(() => this.noise(0.12, { freq: 3000, q: 3, gain: 0.15 }), i * 70); }
  radio() { this.noise(0.08, { freq: 2200, q: 4, gain: 0.12 }); setTimeout(() => this.beep(1600, 0.05, 0.03), 60); }
  ui() { this.beep(880, 0.06, 0.05); }
}
