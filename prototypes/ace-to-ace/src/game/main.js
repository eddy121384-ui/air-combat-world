// Ace to Ace — game shell: screens, loop, wiring between sim, AI, renderer, HUD, audio.
import { Match, RULES } from '../sim/world.js';
import { dist } from '../sim/math.js';
import { PilotAI, PLAYER_DAMAGE_SCALE } from '../ai/pilot.js';
import { ChaserBot } from '../ai/bots.js';
import { pickLine } from '../ai/radio.js';
import { Renderer } from './render.js';
import { Hud } from './hud.js';
import { Input, PlayerController } from './input.js';
import { Audio } from './audio.js';

const $ = (s) => document.querySelector(s);
const params = new URLSearchParams(location.search);
const isTouch = matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;

const settings = Object.assign({ difficulty: 'veteran', assist: true, invert: false, muted: false },
  (() => { try { return JSON.parse(localStorage.getItem('ace2ace.settings') || '{}'); } catch { return {}; } })());
const saveSettings = () => { try { localStorage.setItem('ace2ace.settings', JSON.stringify(settings)); } catch { /* private mode */ } };

const rend = new Renderer($('#gl'));
const hud = new Hud($('#hud'));
const input = new Input(document.body);
const audio = new Audio();
audio.setMuted(settings.muted);

let match = null, mode = 'title', kind = 'pvai';
let player = null, enemyAI = null, blueAI = null;
let acc = 0, last = performance.now(), timeScale = 1, slowT = 0;
let debugOn = params.has('debug');
let view = { mode: 'chase', ac: null };
let resultTimer = -1;
let spectateTarget = 'blue';
let matchCount = 0;
const perf = { frames: 0, t: 0, fps: 0, ms: 0, worst: 0, samples: [] };
window.__perf = perf;

// ------------------------------------------------------------------ screens
function showScreen(id) {
  for (const el of document.querySelectorAll('.screen')) el.classList.toggle('hidden', el.id !== id);
}
function syncTitle() {
  for (const b of document.querySelectorAll('[data-diff]')) b.classList.toggle('sel', b.dataset.diff === settings.difficulty);
  const desc = {
    rookie: 'ROOKIE：反應慢、常衝過頭、少用進階戰術。你承受的傷害 ×0.75',
    veteran: 'VETERAN：會搶位置、會閃飛彈、會讀你的習慣。雙方傷害對等',
    ace: 'ACE：全套戰術、極限機動與精準射擊。雙方傷害對等',
  };
  $('#diffDesc').textContent = desc[settings.difficulty];
  $('#optAssist').textContent = settings.assist ? '操縱：輔助 ASSIST' : '操縱：手動 MANUAL';
  $('#optInvert').textContent = settings.invert ? '俯仰：上推＝爬升' : '俯仰：上推＝俯衝（搖桿式）';
  $('#optSound').textContent = settings.muted ? '音效：關' : '音效：開';
  $('#keysHelp').classList.toggle('hidden', isTouch);
  $('#touchHelp').classList.toggle('hidden', !isTouch);
}
for (const b of document.querySelectorAll('[data-diff]')) b.addEventListener('click', () => { settings.difficulty = b.dataset.diff; saveSettings(); syncTitle(); audio.unlock(); audio.ui(); });
$('#optAssist').addEventListener('click', () => { settings.assist = !settings.assist; saveSettings(); syncTitle(); });
$('#optInvert').addEventListener('click', () => { settings.invert = !settings.invert; saveSettings(); syncTitle(); });
$('#optSound').addEventListener('click', () => { settings.muted = !settings.muted; audio.setMuted(settings.muted); saveSettings(); syncTitle(); });
$('#btnStart').addEventListener('click', () => start('pvai'));
$('#btnWatch').addEventListener('click', () => start('aivai'));
$('#btnRematch').addEventListener('click', () => start(kind));
$('#btnTitle').addEventListener('click', toTitle);
$('#btnResume').addEventListener('click', () => setPaused(false));
$('#btnQuit').addEventListener('click', toTitle);
$('#pauseBtn').addEventListener('click', () => setPaused(mode !== 'paused'));
$('#dbgBtn').addEventListener('click', () => { debugOn = !debugOn; });
syncTitle();

function toTitle() {
  mode = 'title'; showScreen('title');
  $('#touch').classList.add('hidden');
  $('#pauseBtn').classList.add('hidden');
}
function setPaused(p) {
  if (mode === 'title' || mode === 'result') return;
  mode = p ? 'paused' : 'playing';
  showScreen(p ? 'pause' : null);
  last = performance.now();
}

// ------------------------------------------------------------------ match setup
function start(k) {
  audio.unlock();
  kind = k;
  matchCount += 1;
  const seed = params.has('seed') ? +params.get('seed') + matchCount - 1 : (Date.now() & 0xffffff);
  rend.reset();
  const diff = params.get('skill') || settings.difficulty;
  const playerScale = k === 'pvai' ? PLAYER_DAMAGE_SCALE[diff] ?? 1 : 1;
  match = new Match({ seed, blue: { type: 'F16V', name: 'F-16V', damageScale: playerScale }, red: { type: 'J16', name: 'J-16' } });
  rend.addAircraft(match.blue); rend.addAircraft(match.red);
  enemyAI = new PilotAI(match.red, {
    skill: diff, seed: seed + 7,
    onRadio: (m) => { if (kind === 'pvai' || spectateTarget === 'blue') { hud.say('J-16', m.text); audio.radio(); } },
    onTactic: (ev) => {
      if (kind !== 'pvai') return;
      // A cue to a real manoeuvre, no forced cinematic camera or fake reversal.
      if (ev.type === 'brakeStart') hud.flash('J-16 減速！', '#ffc04d', 1.1);
      if (ev.type === 'overshoot') hud.flash('J-16 反咬！', '#ff8f8f', 1.8, true);
    },
  });
  match.setController(match.red, enemyAI);
  if (k === 'aivai') {
    blueAI = new PilotAI(match.blue, { skill: params.get('blueSkill') || 'veteran', seed: seed + 3, onRadio: (m) => { if (spectateTarget === 'red') { hud.say('F-16V', m.text); audio.radio(); } } });
    match.setController(match.blue, blueAI);
    player = null;
  } else if (params.get('autopilot') === 'chaser') {
    // automated player proxy for soak/visual tests
    blueAI = null;
    player = new ChaserBot(match.blue, { seed });
    match.setController(match.blue, player);
  } else {
    blueAI = null;
    player = new PlayerController(match.blue, input, settings);
    match.setController(match.blue, player);
  }
  match.on(onEvent);
  view = { mode: 'chase', ac: k === 'aivai' && spectateTarget === 'red' ? match.red : match.blue, target: match.red };
  acc = 0; timeScale = 1; slowT = 0; resultTimer = -1;
  mode = 'playing';
  showScreen(null);
  $('#touch').classList.toggle('hidden', !(isTouch && k === 'pvai'));
  $('#pauseBtn').classList.remove('hidden');
  input.resetStick();
  input.resetPower();
  input.clearPresses();
  hud.msgs = [];
  hud.flash(k === 'aivai' ? 'AI vs AI — 觀戰模式' : 'ENGAGE', '#7dffb0', 2.2, true);
  if (k === 'pvai') hud.flash('J-16 從正前方接近', '#f4fbff', 2.4);
  last = performance.now();
}

function onEvent(ev) {
  const me = view.ac;
  switch (ev.type) {
    case 'missileLaunch': {
      const own = ev.ac === match.blue && kind === 'pvai';
      audio.missileLaunch(own);
      if (own) hud.flash(ev.guided ? 'FOX 2' : 'FOX 2 (NO LOCK)', ev.guided ? '#f4fbff' : '#ffc04d', 0.9);
      break;
    }
    case 'missileHit': {
      rend.spawnExplosion(ev.pos, false);
      audio.explosion(dist(ev.pos, rend.camera.position));
      if (ev.target === me) { rend.shake = 1; audio.hit(); hud.flash(`被擊中 −${ev.damage}`, '#ff4d5e', 1.4); }
      else if (ev.missile.owner === me) hud.flash(`HIT −${ev.damage}`, '#7dffb0', 1.4);
      break;
    }
    case 'missileMiss':
      if (ev.missile.owner === match.blue && kind === 'pvai') {
        hud.flash(ev.decoyed ? 'MISS — 熱焰彈誘餌' : 'MISS', '#ffc04d', 1.1);
        if (Math.random() < 0.5) enemyAI.say('dodged', match);
      } else if (ev.missile.target === me) hud.flash('閃過飛彈', '#7fe3ff', 1.0);
      break;
    case 'gunFire': audio.gun(ev.ac === me); break;
    case 'gunHit':
      rend.spawnSpark(ev.pos);
      if (ev.target === me) rend.shake = Math.max(rend.shake, 0.35);
      break;
    case 'flares': audio.flares(); if (ev.ac !== me) hud.flash(`${ev.ac.name} 投放熱焰彈`, '#ffc04d', 1.0); break;
    case 'destroyed': {
      rend.spawnExplosion(ev.pos, true);
      rend.spawnWreck(ev.ac);
      audio.explosion(dist(ev.pos, rend.camera.position) * 0.5);
      const byCrash = ev.cause === 'crash';
      // last words on the radio: the loser ejects, or the J-16 calls its kill
      if (ev.ac === match.red || kind === 'aivai') hud.say(ev.ac.name, pickLine('lose'));
      else hud.say('J-16', pickLine('win'));
      if (ev.ac === match.red) {
        hud.flash(byCrash ? 'J-16 墜海' : 'J-16 DESTROYED', '#7dffb0', 3, true);
        view = { mode: 'kill', ac: match.blue, killPos: ev.pos };
        timeScale = 0.3; slowT = 1.2;
      } else {
        hud.flash(byCrash ? '墜海' : ev.cause === 'outOfBounds' ? '脫離戰區' : 'SHOT DOWN', '#ff4d5e', 3, true);
        view = { mode: 'kill', ac: match.red, killPos: ev.pos };
        timeScale = 0.4; slowT = 1.0;
      }
      break;
    }
    case 'suddenDeath': hud.flash('SUDDEN DEATH — 下一擊定勝負', '#ff4d5e', 3, true); break;
    case 'matchOver': resultTimer = ev.reason === 'timeDecision' || ev.reason === 'draw' ? 1.5 : 3.2; break;
    default: break;
  }
}

function showResult() {
  mode = 'result';
  const r = match.result;
  const me = match.blue, foe = match.red;
  const won = r.winner === me;
  const titleEl = $('#resTitle');
  if (kind === 'aivai') titleEl.textContent = r.winner ? `${r.winner.name} WINS` : 'DRAW';
  else titleEl.textContent = !r.winner ? 'DRAW' : won ? 'MISSION ACCOMPLISHED' : 'MISSION FAILED';
  titleEl.className = !r.winner ? '' : won || kind === 'aivai' ? 'win' : 'lose';
  const reasons = { missile: '飛彈擊墜', gun: '機砲擊墜', crash: '墜海', outOfBounds: '脫離戰區', timeDecision: '時間到：依剩餘耐久判定', draw: '平手' };
  $('#resSub').textContent = `${reasons[r.reason] || r.reason} · ${fmtTime(r.time)}`;
  const st = me.stats;
  const ai = enemyAI;
  const share = Object.entries(ai.timeInMode).filter(([, v]) => v > 0.5)
    .map(([k, v]) => `${k} ${Math.round(100 * v / Math.max(1, ai.t))}%`).join(' · ');
  const read = ai.oppEvades > 0.7 ? '你很會閃飛彈——它開始只在好位置才開火' : ai.oppEvades < 0.4 ? '你常不閃飛彈——它會更大膽地發射' : '它還在判斷你的閃避習慣';
  $('#resStats').innerHTML = `
    <div><b>${st.missileHits}/${st.missilesFired}</b><span>飛彈命中/發射</span></div>
    <div><b>${st.roundHits}</b><span>機砲命中</span></div>
    <div><b>${Math.round(st.damageDealt)}</b><span>造成傷害</span></div>
    <div><b>${Math.round(foe.stats.damageDealt)}</b><span>受到傷害</span></div>
    <div><b>${foe.stats.missileHits}/${foe.stats.missilesFired}</b><span>J-16 飛彈命中/發射</span></div>
    <div><b>${foe.stats.flaresUsed}</b><span>J-16 熱焰彈</span></div>`;
  $('#resAI').innerHTML = `<p><b>J-16 戰術時間：</b>${share}</p><p><b>減速誘敵：</b>${ai.brakeAttempts} 次嘗試、${ai.brakeSuccesses} 次觀測到衝過頭</p><p><b>J-16 對你的判讀：</b>${read}（閃避指數 ${ai.oppEvades.toFixed(2)}）</p>
    <p class="dim">最後的決策：${ai.transitions.slice(-4).map((t) => `${fmtTime(t.t)} ${t.to} — ${t.why}`).join('<br>')}</p>`;
  showScreen('result');
  $('#touch').classList.add('hidden');
  window.__lastResult = { winner: r.winner?.side ?? null, reason: r.reason, time: r.time, stats: { ...st }, foe: { ...foe.stats }, aiModes: { ...ai.timeInMode } };
}
const fmtTime = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

// ------------------------------------------------------------------ loop
function frame(now) {
  requestAnimationFrame(frame);
  const realDt = Math.min(0.1, (now - last) / 1000);
  last = now;
  // perf / adaptive resolution
  perf.frames++; perf.t += realDt; perf.samples.push(realDt);
  if (perf.samples.length > 120) perf.samples.shift();
  if (perf.t >= 1) {
    perf.fps = perf.frames / perf.t; perf.frames = 0; perf.t = 0;
    const avg = perf.samples.reduce((a, b) => a + b, 0) / perf.samples.length;
    perf.ms = avg * 1000; perf.worst = Math.max(...perf.samples) * 1000;
    if (mode === 'playing') {
      if (avg > 0.026 && rend.dpr > 1) rend.setDpr(Math.max(1, rend.dpr - 0.25));
      else if (avg < 0.015 && rend.dpr < rend.maxDpr) rend.setDpr(Math.min(rend.maxDpr, rend.dpr + 0.25));
    }
    perf.dpr = rend.dpr;
    perf.calls = rend.renderer.info.render.calls;
    perf.tris = rend.renderer.info.render.triangles;
  }

  if (input.consume('debug')) debugOn = !debugOn;
  if (input.consume('pause')) setPaused(mode !== 'paused');
  if (mode === 'result' && input.consume('restart')) start(kind);
  if (mode === 'title' && input.consume('restart')) start('pvai');
  if (input.consume('camera') && kind === 'aivai' && match) {
    spectateTarget = spectateTarget === 'blue' ? 'red' : 'blue';
    view.ac = spectateTarget === 'blue' ? match.blue : match.red;
    view.target = spectateTarget === 'blue' ? match.red : match.blue;
  }

  if (match && (mode === 'playing' || mode === 'result')) {
    if (slowT > 0) { slowT -= realDt; if (slowT <= 0) timeScale = 1; }
    acc += realDt * timeScale;
    let steps = 0;
    while (acc >= RULES.dt && steps < 8) { match.step(RULES.dt); acc -= RULES.dt; steps++; }
    if (steps === 8) acc = 0;
    if (resultTimer > 0 && mode === 'playing') { resultTimer -= realDt; if (resultTimer <= 0) showResult(); }
    if (view.mode !== 'kill') view.mode = input.look() && kind === 'pvai' ? 'look' : 'chase';
    rend.update(match, view, realDt * timeScale);
    rend.updateCamera(view, realDt);
    rend.render();
    const me = view.ac;
    const showHud = mode === 'playing';
    hud.draw(match, showHud ? me : null, rend, realDt, { minimal: view.mode === 'kill', debugText: debugOn ? aiLabel(me === match.blue ? enemyAI : blueAI) : null });
    const L = me.lock;
    let mw = false, mc = false;
    for (const m of match.missiles) if (m.alive && m.target === me && m.guided && !m.decoy) { mw = true; if (dist(m.pos, me.pos) < 1500) mc = true; }
    audio.frame({ throttle: me.thrustCur, ab: me.abCur, speed: me.speed, locking: L.timer > 0 && !L.locked, locked: L.locked, missileWarn: mw, missileClose: mc, lockWarn: me.lockedBy > 0, alive: me.alive && showHud && kind === 'pvai' }, now / 1000);
  } else {
    // title backdrop: slow orbit over the sea
    const t = now / 1000;
    rend.camera.position.set(Math.cos(t * 0.05) * 600, 2600, Math.sin(t * 0.05) * 600);
    rend.camera.up.set(0, 1, 0);
    rend.camera.lookAt(Math.cos(t * 0.05 + 1.2) * 4000, 2300, Math.sin(t * 0.05 + 1.2) * 4000);
    rend.sky.position.copy(rend.camera.position);
    rend.sea.position.set(rend.camera.position.x, 0, rend.camera.position.z);
    rend.seaMat.uniforms.camPos.value.copy(rend.camera.position);
    rend.cloudMat.uniforms.camPos.value.copy(rend.camera.position);
    rend.seaMat.uniforms.time.value = t;
    rend.render();
    hud.draw(match || { missiles: [], timeLimit: 0, time: 0, phase: '' }, null, rend, realDt);
  }
  drawDebug();
  input.pressed.delete('msl'); input.pressed.delete('flare');
}

function aiLabel(ai) {
  if (!ai || !ai.debug.mode) return null;
  return `${ai.debug.mode} · ${ai.debug.maneuver}`;
}

function drawDebug() {
  const el = $('#debug');
  el.classList.toggle('hidden', !debugOn || !match);
  if (!debugOn || !match) return;
  const block = (name, ai) => {
    if (!ai) return '';
    const d = ai.debug;
    if (!d.mode) return '';
    const tr = ai.transitions.slice(-6).reverse().map((t) => `<div class="dim">${fmtTime(t.t)} ${t.from}→${t.to} ${t.why}</div>`).join('');
    return `<div class="dbgblk"><b>${name}</b> <span class="m">${d.mode}</span> ${d.maneuver}<br>
      why: ${ai.reason}<br>
      R ${d.R.toFixed(0)}m · ATA ${d.ata.toFixed(0)}° · its ATA ${d.tgtAta.toFixed(0)}° · aspect ${d.aspect.toFixed(0)}°<br>
      Vc ${d.vc.toFixed(0)} · ΔE ${d.dE.toFixed(0)}m · v ${d.speed.toFixed(0)} · ${d.g.toFixed(1)}G<br>
      aggr ${d.aggr.toFixed(2)} · Pk ${d.pk.toFixed(2)} · oppEvades ${d.oppEvades.toFixed(2)} · stale ${d.stale || '-'}<br>
      msl ${d.missiles} · flr ${d.flares} · threats ${d.threats}${tr}</div>`;
  };
  el.innerHTML = block('J-16 AI', enemyAI) + block('F-16V AI', blueAI) +
    `<div class="dim">fps ${perf.fps.toFixed(0)} · ${perf.ms.toFixed(1)}ms (worst ${perf.worst.toFixed(0)}) · dpr ${rend.dpr} · calls ${perf.calls} · tris ${perf.tris} · t ${match.time.toFixed(0)}s</div>`;
}

// test hooks (Playwright)
window.__game = {
  get match() { return match; }, get mode() { return mode; }, get enemyAI() { return enemyAI; }, settings, start, input,
  setTimeScale(s) { timeScale = s; },
};

window.addEventListener('orientationchange', () => setTimeout(() => { rend.resize(); hud.resize(); }, 300));
document.addEventListener('visibilitychange', () => { if (document.hidden && mode === 'playing') setPaused(true); });
// iOS: prevent pinch zoom / double-tap zoom
document.addEventListener('gesturestart', (e) => e.preventDefault());
document.addEventListener('dblclick', (e) => e.preventDefault());

if (params.has('mode')) setTimeout(() => start(params.get('mode') === 'aivai' ? 'aivai' : 'pvai'), 50);
else showScreen('title');
requestAnimationFrame(frame);
