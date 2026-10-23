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
import { TiltInput, tiltSettings } from './tilt-input.js';
import { LESSONS, lessonById } from '../academy/lessons.js';
import { createLessonSession } from '../academy/session.js';
import { radioDuration } from '../academy/runner.js';
import { loadProgress, recordAttempt, saveProgress } from '../academy/progress.js';

const $ = (s) => document.querySelector(s);
const params = new URLSearchParams(location.search);
const isTouch = matchMedia('(pointer: coarse)').matches || 'ontouchstart' in window;
// Identical opening geometry, skills and RNG seed for A/B and every rematch.
const experimentSeed = Number.isFinite(Number(params.get('seed'))) && params.has('seed')
  ? Number(params.get('seed')) : 71429;

const settings = Object.assign({ difficulty: 'veteran', assist: true, invert: false,
    muted: false, flightMode: 'arcade', controlMode: 'expert' },
  (() => { try { return JSON.parse(localStorage.getItem('ace2ace.settings') || '{}'); } catch { return {}; } })());
settings.inputDevice = settings.inputDevice === 'tilt' ? 'tilt' : 'stick';
settings.tilt = tiltSettings(settings.tilt);
const saveSettings = () => { try { localStorage.setItem('ace2ace.settings', JSON.stringify(settings)); } catch { /* private mode */ } };
// URL overrides persisted selections for shareable QA links. Legacy A/B remain
// available to headless tests but do not appear as player-facing presets.
let flightFeel = ['arcade', 'tactical'].includes(params.get('mode'))
  ? params.get('mode') : params.get('feel') === 'A' ? 'A'
    : params.get('feel') === 'B' ? 'tactical'
    : ['arcade', 'tactical'].includes(settings.flightMode) ? settings.flightMode : 'arcade';
let controlMode = ['assisted', 'expert'].includes(params.get('control'))
  ? params.get('control')
  : ['assisted', 'expert'].includes(settings.controlMode) ? settings.controlMode : 'expert';
let settingsReturn = 'title';
let draftFlight = flightFeel === 'A' ? 'arcade' : flightFeel;
let draftControl = controlMode, draftInvert = !!settings.invert, draftMuted = !!settings.muted;

let draftDevice = settings.inputDevice, draftTilt = {...settings.tilt};

const rend = new Renderer($('#gl'));
const hud = new Hud($('#hud'));
const input = new Input(document.body);
const tilt = new TiltInput({onChange:syncTiltUI});
input.axisSource = () => tilt.axes();
input.onRelease = () => tilt.stop();
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
// Ace Flight Academy: a lesson is a normal Match plus a LessonRunner on top.
let lessonRun = null, lessonId = null, debriefTimer = -1, briefId = null;
let academyProgress = loadProgress();
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
  $('#currentFlightPreset').textContent = formatFlight(flightFeel, controlMode);
  $('#pauseFlightPreset').textContent = '目前：' + formatFlight(flightFeel, controlMode);
  $('#keysHelp').classList.toggle('hidden', isTouch);
  $('#touchHelp').classList.toggle('hidden', !isTouch);
}
function saveModeQuery() {
  params.set('mode', flightFeel);
  params.set('control', controlMode);
  params.delete('feel');
  params.set('seed', String(experimentSeed));
  history.replaceState(null, '', location.pathname + '?' + params.toString());
}
const formatFlight = (flight, control) =>
  (flight === 'A' ? 'LEGACY' : flight.toUpperCase()) + ' / ' + control.toUpperCase();
const flightChoiceNotes = {
  'arcade:assisted': '搖桿推向哪就轉向哪，飛控協調滾轉與拉桿。AB 衝刺；收油或 BRK 轉得更急。速度旁的綠色菱形＝最佳轉彎速度。',
  'arcade:expert': 'AC 式手動操控：左右滾轉、拉桿轉彎，沒有自動改平，滾轉停得乾淨。AB 快而寬，收油／BRK 慢而急。',
  'tactical:assisted': '飛控幫你協調轉向，但物理照算：滿桿急轉每秒掉速 10 m/s 以上。看速度旁的趨勢條，守在綠色菱形附近。',
  'tactical:expert': '速度、高度與拉桿量都是資源：適度拉桿可以持續，滿桿換來瞬間機頭指向。會管能量的人贏。'
};
const settingsVisible = () => !$('#flightSettings').classList.contains('hidden');
function syncFlightSettings() {
  const key = draftFlight + ':' + draftControl;
  for (const b of document.querySelectorAll('[data-flight-choice]')) {
    const active = b.dataset.flightChoice === key;
    b.setAttribute('aria-pressed', String(active));
  }
  $('#settingsChoiceDescription').textContent = flightChoiceNotes[key];
  $('#optInvert').textContent = draftInvert ? '俯仰：上推＝爬升' : '俯仰：上推＝俯衝';
  $('#optSound').textContent = draftMuted ? '音效：關' : '音效：開';
  for(const b of document.querySelectorAll('[data-input-device]')) b.setAttribute('aria-pressed',String(b.dataset.inputDevice===draftDevice));
  $('#tiltOptions').classList.toggle('hidden',draftDevice!=='tilt');
  for(const [key,id,unit] of [['sensitivity','Sensitivity','×'],['deadzone','Deadzone','°'],['smoothing','Smoothing','ms']]) {
    $('#tilt'+id).value=draftTilt[key];$('#tilt'+id+'Value').textContent=draftTilt[key]+unit;
  }
  for(const key of ['X','Y']) {$('#tiltInvert'+key).textContent='反轉 '+key+'：'+(draftTilt['invert'+key]?'開':'關');$('#tiltInvert'+key).setAttribute('aria-pressed',String(draftTilt['invert'+key]));}
  syncTiltUI();
  const changed = flightFeel !== draftFlight || controlMode !== draftControl;
  const inFight = settingsReturn === 'pause';
  $('#settingsApplyNote').textContent = inFight
    ? changed ? '套用後將重新開始本局（相同起始條件），不會在空中突然變更物理。'
      : '只修改輸入設備、體感、音效或俯仰方向會繼續本局。'
    : settingsReturn === 'academy' ? '儲存後回到飛行學院，下一堂課使用新設定。' : '儲存後回到主選單，下次出擊使用新設定。';
  $('#btnSettingsApply').textContent = inFight
    ? changed ? '套用並重新出擊' : '儲存並繼續'
    : '儲存設定';
}
function openFlightSettings(from) {
  input.releaseHeld();
  draftDevice=settings.inputDevice;draftTilt={...settings.tilt};tilt.configure(draftTilt);
  settingsReturn = from;
  draftFlight = flightFeel === 'A' ? 'arcade' : flightFeel;
  draftControl = controlMode;
  draftInvert = !!settings.invert;
  draftMuted = !!settings.muted;
  syncFlightSettings();
  showScreen('flightSettings');
  $('.flight-settings-card').scrollTop=0;
}
function closeFlightSettings() {
  input.releaseHeld();tilt.configure(settings.tilt);
  showScreen(settingsReturn);
  last = performance.now();
}
function applyFlightSettings() {
  input.releaseHeld();
  settings.inputDevice=draftDevice;settings.tilt=tiltSettings(draftTilt);tilt.configure(settings.tilt);
  const changed = flightFeel !== draftFlight || controlMode !== draftControl;
  flightFeel = draftFlight; controlMode = draftControl;
  settings.flightMode = draftFlight; settings.controlMode = draftControl;
  settings.invert = draftInvert; settings.muted = draftMuted;
  audio.setMuted(settings.muted);
  saveSettings();
  saveModeQuery();
  syncTitle();
  if (settingsReturn === 'pause') {
    if (changed) { if (kind === 'lesson') startLesson(lessonId); else start(kind); } // same seed, both jets switch
    else {
      // The controller holds a per-sortie copy of settings: push the pitch
      // convention into it so "save and continue" takes effect immediately.
      if (player instanceof PlayerController) player.settings.invert = settings.invert;
      mode = 'playing'; showScreen(null); resumeTilt(); last = performance.now();
    }
  } else if (settingsReturn === 'academy') { renderAcademy(); showScreen('academy'); }
  else showScreen('title');
}
for (const b of document.querySelectorAll('[data-flight-choice]')) b.addEventListener('click', () => {
  [draftFlight, draftControl] = b.dataset.flightChoice.split(':');
  syncFlightSettings(); audio.ui();
});
const tiltMessages = {
  idle:'尚未啟用；暫用虛擬搖桿。', requesting:'等待感測器授權…', waiting:'保持握姿，等待有效資料校準。',
  ready:'已校準目前握姿；回到此姿勢即為中立。', denied:'授權未允許；暫用虛擬搖桿，可重新啟用。',
  insecure:'需要 HTTPS；暫用虛擬搖桿。', unavailable:'無有效姿態感測器；暫用虛擬搖桿。',
  stale:'感測資料中斷，已回中；暫用虛擬搖桿，請重新啟用。'
};
let tiltWasReady=false;
function syncTiltUI() {
  const ready=mode==='playing' && settings.inputDevice==='tilt' && tilt.state==='ready';
  if(ready!==tiltWasReady){input.resetStick();tiltWasReady=ready;}
  input.inputDevice=ready?'tilt':'stick';
  $('#stickZone').classList.toggle('hidden',ready);$('#stickBase').classList.toggle('hidden',ready);
  $('#tiltCalibrate').classList.toggle('hidden',!ready);
  $('#tiltStatus').textContent=tiltMessages[tilt.state] || '';
  $('#btnTiltCalibrate').disabled=tilt.state!=='ready';
  if(mode==='playing' && settings.inputDevice==='tilt' && ['stale','unavailable','denied'].includes(tilt.state))hud.say('FLIGHT',tiltMessages[tilt.state],4);
}
function resumeTilt() {
  if(settings.inputDevice==='tilt' && (kind==='pvai'||kind==='lesson') && tilt.allowed){tilt.configure(settings.tilt);tilt.start();}
  syncTiltUI();
}
for(const b of document.querySelectorAll('[data-input-device]'))b.addEventListener('click',()=>{
  input.releaseHeld();draftDevice=b.dataset.inputDevice;syncFlightSettings();
});
$('#btnTiltEnable').addEventListener('click',()=>{tilt.configure(draftTilt);void tilt.enable();});
$('#btnTiltCalibrate').addEventListener('click',()=>tilt.calibrate());
$('#tiltCalibrate').addEventListener('click',()=>{input.levelAssist.cancel();tilt.calibrate();});
for(const [key,id] of [['sensitivity','Sensitivity'],['deadzone','Deadzone'],['smoothing','Smoothing']])$('#tilt'+id).addEventListener('input',e=>{
  draftTilt[key]=Number(e.target.value);tilt.configure(draftTilt);syncFlightSettings();
});
for(const key of ['X','Y'])$('#tiltInvert'+key).addEventListener('click',()=>{
  draftTilt['invert'+key]=!draftTilt['invert'+key];tilt.configure(draftTilt);syncFlightSettings();
});
$('#btnTitleSettings').addEventListener('click', () => openFlightSettings('title'));
$('#btnPauseSettings').addEventListener('click', () => openFlightSettings('pause'));
$('#btnSettingsCancel').addEventListener('click', closeFlightSettings);
$('#btnSettingsApply').addEventListener('click', applyFlightSettings);
for (const b of document.querySelectorAll('[data-diff]')) b.addEventListener('click', () => { settings.difficulty = b.dataset.diff; saveSettings(); syncTitle(); audio.unlock(); audio.ui(); });
$('#optInvert').addEventListener('click', () => { draftInvert = !draftInvert; syncFlightSettings(); });
$('#optSound').addEventListener('click', () => { draftMuted = !draftMuted; syncFlightSettings(); });
$('#btnStart').addEventListener('click', () => start('pvai'));
$('#btnWatch').addEventListener('click', () => start('aivai'));
$('#btnRematch').addEventListener('click', () => start(kind));
$('#btnTitle').addEventListener('click', toTitle);
$('#btnResume').addEventListener('click', () => setPaused(false));
$('#btnQuit').addEventListener('click', () => (kind === 'lesson' ? openAcademy() : toTitle()));
$('#btnPauseRetry').addEventListener('click', () => startLesson(lessonId));
$('#btnAcademy').addEventListener('click', () => { audio.unlock(); audio.ui(); openAcademy(); });
$('#btnAcademySettings').addEventListener('click', () => openFlightSettings('academy'));
$('#btnAcademyBack').addEventListener('click', toTitle);
$('#btnBriefBack').addEventListener('click', openAcademy);
$('#btnBriefGo').addEventListener('click', () => startLesson(briefId));
$('#btnDebAcademy').addEventListener('click', openAcademy);
$('#btnDebRetry').addEventListener('click', () => startLesson(lessonId));
$('#btnDebNext').addEventListener('click', () => { const n = nextLesson(lessonId); if (n) openBriefing(n.id); else openAcademy(); });
const togglePause = () => { if (settingsVisible()) closeFlightSettings(); else setPaused(mode !== 'paused'); };
$('#pauseBtn').addEventListener('click', togglePause);
// A multi-touch gesture does not reliably synthesize a click while the other
// thumb is still down. Pause immediately and suppress the compatibility click.
$('#pauseBtn').addEventListener('touchstart', (e) => { e.preventDefault(); togglePause(); }, { passive: false });
$('#dbgBtn').addEventListener('click', () => { debugOn = !debugOn; });
syncTitle();

function toTitle() {
  input.releaseHeld();
  mode = 'title'; showScreen('title');
  $('#touch').classList.add('hidden');
  $('#pauseBtn').classList.add('hidden');
}
function setPaused(p) {
  if (mode !== 'playing' && mode !== 'paused') return;
  input.releaseHeld();
  $('#btnPauseRetry').classList.toggle('hidden', kind !== 'lesson');
  $('#btnQuit').textContent = kind === 'lesson' ? '回到學院' : '回到標題';
  mode = p ? 'paused' : 'playing';
  showScreen(p ? 'pause' : null);
  if(!p)resumeTilt();
  last = performance.now();
}

// ------------------------------------------------------------------ match setup
function start(k) {
  audio.unlock();
  kind = k;
  lessonRun = null; debriefTimer = -1;
  matchCount += 1;
  const seed = experimentSeed;
  rend.reset();
  const diff = params.get('skill') || settings.difficulty;
  const playerScale = k === 'pvai' ? PLAYER_DAMAGE_SCALE[diff] ?? 1 : 1;
  match = new Match({ seed, flightFeel, blue: { type: 'F16V', name: 'F-16V', damageScale: playerScale }, red: { type: 'J16', name: 'J-16' } });
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
    player = new PlayerController(match.blue, input, { ...settings, assist: controlMode === 'assisted' });
    match.setController(match.blue, player);
  }
  match.on(onEvent);
  view = { mode: 'chase', ac: k === 'aivai' && spectateTarget === 'red' ? match.red : match.blue, target: match.red };
  acc = 0; timeScale = 1; slowT = 0; resultTimer = -1;
  mode = 'playing';
  showScreen(null);
  $('#touch').classList.toggle('hidden', !(isTouch && k === 'pvai'));
  $('#pauseBtn').classList.remove('hidden');
  input.releaseHeld();
  input.resetPower();
  input.clearPresses();
  resumeTilt();
  hud.msgs = [];
  hud.flash(k === 'aivai' ? 'AI vs AI — 觀戰模式' : 'ENGAGE', '#7dffb0', 2.2, true);
  if (k === 'pvai') hud.flash('J-16 從正前方接近', '#f4fbff', 2.4);
  if (k === 'pvai') hud.flash(`${flightFeel.toUpperCase()} / ${controlMode.toUpperCase()}`, '#7fe3ff', 2.2);
  last = performance.now();
}

// ------------------------------------------------------------------ academy
const modeKey = () => `${flightFeel === 'A' ? 'arcade' : flightFeel}:${controlMode}`;
function nextLesson(id) {
  const i = LESSONS.findIndex((l) => l.id === id);
  return LESSONS[i + 1] || null;
}
function renderAcademy() {
  $('#academyMode').textContent = formatFlight(flightFeel, controlMode);
  const grid = $('#lessonGrid');
  const firstOpen = LESSONS.find((l) => !academyProgress.lessons[l.id]?.cleared);
  grid.innerHTML = '';
  for (const l of LESSONS) {
    const p = academyProgress.lessons[l.id];
    const b = document.createElement('button');
    b.type = 'button'; b.setAttribute('role', 'listitem');
    b.className = 'lesson-card' + (p?.cleared ? ' cleared' : '') + (l === firstOpen ? ' next' : '') + (l.final ? ' final' : '');
    b.dataset.lesson = l.id;
    const st = p?.cleared ? `✓ ${p.best}${p.bestTime ? ` · ${p.bestTime}s` : ''}` : l === firstOpen ? '建議下一課' : p?.attempts ? `嘗試 ${p.attempts} 次` : '未完成';
    b.innerHTML = `<span class="no">${String(l.no).padStart(2, '0')} ${l.en}</span><span class="t">${l.title}</span><span class="st">${st}</span>`;
    b.addEventListener('click', () => { audio.ui(); openBriefing(l.id); });
    grid.appendChild(b);
  }
}
function openAcademy() {
  input.releaseHeld();
  mode = 'academy'; kind = 'menu'; lessonRun = null; debriefTimer = -1;
  renderAcademy();
  showScreen('academy');
  $('#touch').classList.add('hidden');
  $('#pauseBtn').classList.add('hidden');
}
function openBriefing(id) {
  const l = lessonById(id);
  if (!l) return openAcademy();
  briefId = id; mode = 'academy';
  $('#briefKicker').textContent = `LESSON ${String(l.no).padStart(2, '0')} · ${l.en} · ${formatFlight(flightFeel, controlMode)}`;
  $('#briefTitle').textContent = l.title;
  const context = { pick: (a, e) => controlMode === 'assisted' ? a : e };
  $('#briefHook').textContent = 'KITE ▸ ' + (l.intro || []).map(line => typeof line === 'function' ? line(context) : line).join(' ');
  if(['L01','L02'].includes(id))$('#briefHook').textContent+=' VIRTUAL STICK 放手回中；TILT 回到校準握姿回中。Expert 回中不會自動改平。';
  $('#briefPrinciple').textContent = l.principle;
  $('#briefGoals').innerHTML = l.goals.map((g) => `<li>${g}</li>`).join('');
  $('#briefReal').textContent = l.real || '';
  $('#briefModel').textContent = l.model || '';
  showScreen('briefing');
  $('#touch').classList.add('hidden');
  $('#pauseBtn').classList.add('hidden');
}
function startLesson(id) {
  const lesson = lessonById(id);
  if (!lesson) return;
  audio.unlock();
  kind = 'lesson'; lessonId = id; debriefTimer = -1;
  rend.reset();
  const [flight, control] = modeKey().split(':');
  const session = createLessonSession(lesson, { flight, control, input, settings });
  match = session.match; lessonRun = session.runner; player = session.player;
  enemyAI = session.foeAI || null; blueAI = null;
  lessonRun.onSay = (text) => { hud.say('KITE', text, radioDuration(text)); audio.radio(); };
  lessonRun.onFlash = (text, color) => hud.flash(text, color, 1.8);
  rend.addAircraft(match.blue); rend.addAircraft(match.red);
  match.on(onEvent);
  view = { mode: 'chase', ac: match.blue, target: match.red };
  acc = 0; timeScale = 1; slowT = 0; resultTimer = -1;
  mode = 'playing';
  showScreen(null);
  $('#touch').classList.toggle('hidden', !isTouch);
  $('#pauseBtn').classList.remove('hidden');
  input.releaseHeld(); input.resetPower(); input.clearPresses();
  resumeTilt();
  hud.msgs = [];
  hud.radio = null;
  hud.flash(`LESSON ${String(lesson.no).padStart(2, '0')}`, '#ffe2a3', 2.0, true);
  hud.flash(lesson.title, '#f4fbff', 2.2);
  last = performance.now();
  window.__game?.onLessonStart?.(); // test hook: runs before the first simulation step
}
/** Show lesson power rules on the touch strip (locked throttle, AB unavailable). */
function syncLessonPower(rules) {
  if (rules.throttle != null && Math.abs(input.throttle() - rules.throttle) > 1e-3) input.setThrottle(rules.throttle);
  if (rules.ab === false && input.boostToggle) {
    input.boostToggle = false;
    const b = document.querySelector('[data-btn="boost"]');
    b?.classList.remove('lit'); b?.setAttribute('aria-pressed', 'false');
  }
}
function showDebrief() {
  input.releaseHeld();
  const r = lessonRun.result, l = lessonById(lessonId);
  mode = 'debrief';
  recordAttempt(academyProgress, lessonId, { success: r.success, grade: r.grade, time: r.time, mode: modeKey() });
  saveProgress(academyProgress);
  $('#debKicker').textContent = `LESSON ${String(l.no).padStart(2, '0')} · ${l.title} · ${formatFlight(flightFeel, controlMode)}`;
  const title = $('#debTitle');
  title.textContent = r.success ? (l.final ? `ACE RATING ${r.grade}` : `CLEAR · ${r.grade}`) : 'NOT YET · 未通過';
  title.className = r.success ? 'win' : 'lose';
  $('#debCitation').textContent = `KITE ▸ ${r.citation}`;
  $('#debBadge').classList.toggle('hidden', !(l.final && r.success));
  $('#debBadge').textContent = `ACE QUALIFIED · ${r.grade}`;
  $('#debSub').textContent = r.success ? `用時 ${Math.round(r.time)} 秒` : (r.reason || '');
  $('#debStats').innerHTML = r.stats.map(([k, v]) => `<div><b>${v}</b><span>${k}</span></div>`).join('');
  const li = (a, empty) => (a.length ? a : [empty]).map((x) => `<li>${x}</li>`).join('');
  $('#debGood').innerHTML = li(r.good, r.success ? '完成了每一個步驟。' : '—');
  $('#debImprove').innerHTML = li(r.improve, r.success ? '保持這個節奏。' : '照著教官的提示再飛一次。');
  const next = nextLesson(lessonId);
  $('#btnDebNext').classList.toggle('hidden', !next);
  $('#btnDebNext').textContent = r.success ? '下一課' : '跳到下一課';
  showScreen('debrief');
  $('#touch').classList.add('hidden');
  $('#pauseBtn').classList.add('hidden');
  window.__lastLesson = { id: lessonId, ...r, mode: modeKey() };
}

function onEvent(ev) {
  const me = view.ac;
  switch (ev.type) {
    case 'missileLaunch': {
      const own = ev.ac === match.blue && (kind === 'pvai' || kind === 'lesson');
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
        // UI-only taunt: never call enemyAI.say() here — it draws from the AI's
        // decision RNG and sets its radio cooldown, so the browser fight diverged
        // from the same seed (rematch / headless / Academy retry).
        if (enemyAI && enemyAI.radioCooldown <= 0 && Math.random() < 0.5) { hud.say('J-16', pickLine('dodged')); audio.radio(); }
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
    case 'matchOver': if (kind !== 'lesson') resultTimer = ev.reason === 'timeDecision' || ev.reason === 'draw' ? 1.5 : 3.2; break;
    default: break;
  }
}

function showResult() {
  input.releaseHeld();
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
let levelVersion=0;
function frame(now) {
  requestAnimationFrame(frame);
  const realDt = Math.min(0.1, (now - last) / 1000);
  last = now;
  tilt.tick();
  if(settingsVisible() && tilt.active){const a=tilt.axes()||{x:0,y:0};$('#tiltReadout').textContent=`X ${a.x.toFixed(2)} · Y ${a.y.toFixed(2)}`;}
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
  if (input.consume('pause')) {
    if (settingsVisible()) closeFlightSettings();
    else setPaused(mode !== 'paused');
  }
  // Always consume restart presses, even while the settings dialog is open.
  // Otherwise an Enter tap can unexpectedly launch a sortie after Cancel.
  const restart = input.consume('restart');
  if (mode === 'result' && restart) start(kind);
  if (mode === 'debrief' && restart) startLesson(lessonId);
  if (mode === 'title' && !settingsVisible() && restart) start('pvai');
  if (input.consume('camera') && kind === 'aivai' && match) {
    spectateTarget = spectateTarget === 'blue' ? 'red' : 'blue';
    view.ac = spectateTarget === 'blue' ? match.blue : match.red;
    view.target = spectateTarget === 'blue' ? match.red : match.blue;
  }

  if (match && (mode === 'playing' || mode === 'result' || mode === 'debrief')) {
    if (slowT > 0) { slowT -= realDt; if (slowT <= 0) timeScale = 1; }
    acc += realDt * timeScale;
    let steps = 0;
    while (acc >= RULES.dt && steps < 8) { match.step(RULES.dt); lessonRun?.step(RULES.dt); acc -= RULES.dt; steps++; }
    if (steps === 8) acc = 0;
    if (lessonRun && mode === 'playing') syncLessonPower(lessonRun.rules);
    if (lessonRun?.result && debriefTimer < 0 && mode === 'playing') debriefTimer = lessonRun.result.success ? 3.0 : 0.8;
    if (debriefTimer > 0 && mode === 'playing') { debriefTimer -= realDt; if (debriefTimer <= 0) showDebrief(); }
    if (resultTimer > 0 && mode === 'playing') { resultTimer -= realDt; if (resultTimer <= 0) showResult(); }
    if (view.mode !== 'kill') view.mode = input.look() && kind === 'pvai' ? 'look' : 'chase';
    rend.update(match, view, realDt * timeScale);
    rend.updateCamera(view, realDt);
    rend.render();
    const me = view.ac;
    const showHud = mode === 'playing';
    hud.draw(match, showHud ? me : null, rend, realDt, { minimal: view.mode === 'kill', debugText: debugOn ? aiLabel(me === match.blue ? enemyAI : blueAI) : null,
      academy: kind === 'lesson' && lessonRun ? lessonRun.view() : null });
    const L = me.lock;
    let mw = false, mc = false;
    for (const m of match.missiles) if (m.alive && m.target === me && m.guided && !m.decoy) { mw = true; if (dist(m.pos, me.pos) < 1500) mc = true; }
    const weaponCues = kind !== 'lesson' || lessonRun.rules.weapons;
    audio.frame({ throttle: me.thrustCur, ab: me.abCur, speed: me.speed, locking: weaponCues && L.timer > 0 && !L.locked, locked: weaponCues && L.locked, missileWarn: mw, missileClose: mc, lockWarn: me.lockedBy > 0 && (kind !== 'lesson' || lessonRun.lesson.id !== 'L07'), alive: me.alive && showHud && (kind === 'pvai' || kind === 'lesson') }, now / 1000);
  } else if (match && mode === 'paused') {
    // Freeze the fight behind the pause/settings card. Moving the camera to the
    // title orbit here made it swoop back from ~4 km away on resume.
    rend.render();
    hud.draw(match, view.ac, rend, 0, { minimal: true });
    audio.frame({ throttle: 0, ab: 0, speed: 0, alive: false }, now / 1000);
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
  const level=input.levelAssist, levelButton=$('[data-btn="level"]');
  levelButton.classList.toggle('lit',level.active);
  levelButton.setAttribute('aria-pressed',String(level.active));
  if(level.version!==levelVersion) {
    levelVersion=level.version;
    if(mode==='playing' && level.message)hud.say('FLIGHT',level.message,2.8);
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
  get match() { return match; }, get mode() { return mode; }, get enemyAI() { return enemyAI; }, get flightFeel() { return flightFeel; }, get controlMode() { return controlMode; },
  get player() { return player; }, get rend() { return rend; },
  get hud() { return hud; },
  get lesson() { return lessonRun; }, get lessonId() { return lessonId; }, get academyProgress() { return academyProgress; },
  startLesson, openAcademy, openBriefing,
  get experimentSeed() { return experimentSeed; }, settings, start, input, tilt, openFlightSettings,
  setTimeScale(s) { timeScale = s; },
};

window.addEventListener('resize',()=>{if(innerHeight>innerWidth && mode==='playing')setPaused(true);});
window.addEventListener('orientationchange', () => setTimeout(() => { rend.resize(); hud.resize(); }, 300));
document.addEventListener('visibilitychange', () => { if (document.hidden && mode === 'playing') setPaused(true); });
window.addEventListener('blur', () => { if (mode === 'playing') setPaused(true); });
// iOS: prevent pinch zoom / double-tap zoom
document.addEventListener('gesturestart', (e) => e.preventDefault());
document.addEventListener('dblclick', (e) => e.preventDefault());

// ?mode=arcade/tactical describes physics, not a request to skip the menu.
// Explicit QA auto-start plus the legacy match-kind URLs (?mode=pvai, ?mode=aivai)
// still launch directly; their physics then come from settings or ?feel.
const legacyKind = ['pvai', 'aivai'].includes(params.get('mode')) ? params.get('mode') : null;
if (lessonById(params.get('lesson') || '')) {
  // QA / share link straight to a lesson briefing (or the lesson with autostart=1)
  const id = params.get('lesson');
  setTimeout(() => (params.get('autostart') === '1' ? startLesson(id) : openBriefing(id)), 50);
} else if (params.get('autostart') === '1' || legacyKind)
  setTimeout(() => start(legacyKind || 'pvai'), 50);
else showScreen('title');
requestAnimationFrame(frame);
