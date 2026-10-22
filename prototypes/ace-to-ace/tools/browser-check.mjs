#!/usr/bin/env node
// Launch the real game in Chromium (Playwright), take screenshots, collect console errors and
// frame stats. Desktop + an iPhone-13-mini-sized touch emulation. NOT a substitute for a real
// iPhone: headless Chromium renders WebGL in software (SwiftShader), so FPS here is pessimistic
// for GPU cost and says nothing about Safari/WebKit specifics.
//
//   node tools/browser-check.mjs [--out tools/out/shots] [--scenario all|lookdev|title|settings|modes|academy|fight|manual|touch|aivai|result]
import http from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';
import { dirname, join, resolve, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const args = Object.fromEntries(process.argv.slice(2).map((a, i, arr) => a.startsWith('--') ? [a.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true] : null).filter(Boolean));
const OUT = resolve(ROOT, args.out || 'tools/out/shots');
const scenario = args.scenario || 'all';

function loadPlaywright() {
  const req = createRequire(import.meta.url);
  try { return req('playwright'); } catch { /* fall through */ }
  const g = execSync('npm root -g').toString().trim();
  return req(join(g, 'playwright'));
}
const { chromium, devices } = loadPlaywright();

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg' };
const server = http.createServer(async (req, res) => {
  try {
    const p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    const f = join(ROOT, p === '/' ? 'index.html' : p);
    if (!f.startsWith(ROOT)) throw new Error('bad path');
    const data = await readFile(f);
    res.writeHead(200, { 'content-type': MIME[extname(f)] || 'application/octet-stream' });
    res.end(data);
  } catch { res.writeHead(404); res.end('nf'); }
});
await new Promise((r) => server.listen(0, r));
const base = `http://127.0.0.1:${server.address().port}/`;
await mkdir(OUT, { recursive: true });

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const report = { errors: [], shots: [], perf: {} };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function page(ctxOpts, url, label) {
  const ctx = await browser.newContext(ctxOpts);
  const p = await ctx.newPage();
  p.on('console', (m) => { if (m.type() === 'error') report.errors.push(`[${label}] ${m.text()}`); });
  p.on('pageerror', (e) => report.errors.push(`[${label}] pageerror: ${e.message}`));
  p.on('requestfailed', (r) => report.errors.push(`[${label}] request failed: ${r.url()}`));
  p.on('response', (r) => { if (r.status() >= 400) report.errors.push(`[${label}] HTTP ${r.status()}: ${r.url()}`); });
  await p.goto(base + url);
  return { ctx, p };
}
async function shot(p, name) {
  const f = join(OUT, `${name}.png`);
  await p.screenshot({ path: f });
  report.shots.push(f);
}
const state = (p) => p.evaluate(() => {
  const g = window.__game, m = g.match;
  if (!m) return { mode: g.mode };
  const ai = g.enemyAI;
  return { mode: g.mode, t: +m.time.toFixed(1), blue: { hp: m.blue.hp, alive: m.blue.alive, v: Math.round(m.blue.speed), alt: Math.round(m.blue.pos.y) },
    red: { hp: m.red.hp, alive: m.red.alive, v: Math.round(m.red.speed), alt: Math.round(m.red.pos.y) },
    ai: ai ? `${ai.debug.mode}/${ai.debug.maneuver}` : null, missiles: m.missiles.length, result: window.__lastResult || null,
    perf: { fps: +window.__perf.fps.toFixed(1), ms: +(window.__perf.ms || 0).toFixed(1), calls: window.__perf.calls, tris: window.__perf.tris, dpr: window.__perf.dpr } };
});

const desktop = { viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 };
const iphone = { ...devices['iPhone 13 Mini'], viewport: { width: 812, height: 375 }, isMobile: true, hasTouch: true };

if (scenario === 'all' || scenario === 'lookdev') {
  report.perf.lookdev = {};
  for (const view of ['chase', 'bank', 'cloud', 'ocean', 'dive', 'seam', 'zenith']) {
    const { ctx, p } = await page(desktop, `tools/lookdev-viewer.html?view=${view}`, `lookdev-${view}`);
    await p.waitForFunction(() => window.__lookdev?.ready).catch(e => {
      throw new Error(report.errors.join('\n') || e.message);
    });
    const stats = await p.evaluate(() => window.__lookdev);
    assert.equal(stats.textureWidth, 1024, 'painted cloud atlas loaded');
    assert.equal(stats.clouds, 8, 'bounded painted mid-cloud instance count');
    assert.equal(stats.skyWidth, 1536, 'painted sky and sea environment loaded');
    assert.ok(stats.calls < 40 && stats.triangles < 10000, 'bounded art-scene geometry');
    assert.ok(stats.programs.every(p => p.runnable), 'all lookdev shaders link');
    report.perf.lookdev[view] = stats;
    await shot(p, `00-lookdev-${view}`);
    await ctx.close();
  }
  const { ctx, p } = await page(desktop, 'tools/model-viewer.html', 'lookdev-models');
  await p.waitForFunction(() => window.__done);
  await shot(p, '00-lookdev-models');
  await ctx.close();
  // Controlled destruction checks the new airframe tint on cloned wreck
  // materials, independently of whether an AI smoke match ends by gun or timer.
  const wreck = await page(desktop, '?mode=pvai&seed=21', 'lookdev-wreck');
  await wreck.p.waitForFunction(() => window.__game?.mode === 'playing');
  await wreck.p.evaluate(() => {
    const m = window.__game.match; m.damage(m.red, 100, m.blue, 'gun');
  });
  await sleep(700);
  assert.equal(await wreck.p.evaluate(() => window.__game.match.red.alive), false);
  await shot(wreck.p, '00-lookdev-wreck');
  report.perf.wreck = { controlledDestruction: true };
  await wreck.ctx.close();
}

if (scenario === 'all' || scenario === 'title') {
  const { ctx, p } = await page(desktop, '', 'title');
  await sleep(1500); await shot(p, '01-title-desktop');
  await ctx.close();
}
if (scenario === 'all' || scenario === 'settings') {
  // Four-mode flight settings, driven through the real DOM: select, cancel,
  // save, reload persistence, pause-menu change (same-seed restart) and a
  // pitch-only change that must resume the SAME sortie with the new convention.
  for (const [label, opts, press] of [['settings-desktop', desktop, 'click'], ['settings-touch', iphone, 'tap']]) {
    const { ctx, p } = await page(opts, '?seed=31', label);
    const act = (sel) => p[press](sel);
    const visible = (id) => p.evaluate((i) => !document.getElementById(i).classList.contains('hidden'), id);
    const stored = () => p.evaluate(() => JSON.parse(localStorage.getItem('ace2ace.settings') || '{}'));
    const pressed = () => p.evaluate(() => [...document.querySelectorAll('[data-flight-choice]')]
      .filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.dataset.flightChoice));
    await p.waitForFunction(() => window.__game && window.__game.mode === 'title');
    assert.equal(await p.textContent('#currentFlightPreset'), 'ARCADE / EXPERT', `${label}: default preset`);
    await act('#btnTitleSettings');
    assert.ok(await visible('flightSettings'), `${label}: settings opens from title`);
    assert.deepEqual(await pressed(), ['arcade:expert'], `${label}: exactly one preset selected`);
    await act('[data-flight-choice="tactical:assisted"]');
    assert.deepEqual(await pressed(), ['tactical:assisted'], `${label}: selection moves`);
    await p.keyboard.press('Enter'); await sleep(200);
    assert.equal(await p.evaluate(() => window.__game.mode), 'title', `${label}: Enter in settings must not launch`);
    await act('#btnSettingsCancel');
    assert.ok(await visible('title'), `${label}: cancel returns to title`);
    assert.equal(await p.textContent('#currentFlightPreset'), 'ARCADE / EXPERT', `${label}: cancel discards draft`);
    assert.equal((await stored()).flightMode, undefined, `${label}: cancel persists nothing`);
    await act('#btnTitleSettings');
    assert.deepEqual(await pressed(), ['arcade:expert'], `${label}: reopen shows committed preset`);
    await act('[data-flight-choice="tactical:assisted"]');
    await act('#btnSettingsApply');
    assert.ok(await visible('title'), `${label}: apply from title returns to title`);
    assert.equal(await p.textContent('#currentFlightPreset'), 'TACTICAL / ASSISTED');
    assert.deepEqual([(await stored()).flightMode, (await stored()).controlMode], ['tactical', 'assisted']);
    assert.match(p.url(), /mode=tactical/); assert.match(p.url(), /control=assisted/);
    await p.reload();
    await p.waitForFunction(() => window.__game && window.__game.mode === 'title');
    assert.equal(await p.textContent('#currentFlightPreset'), 'TACTICAL / ASSISTED', `${label}: preset survives reload`);
    await act('#btnStart');
    await p.waitForFunction(() => window.__game.mode === 'playing');
    const sortie = () => p.evaluate(() => {
      const g = window.__game, m = g.match;
      return { mode: g.mode, blue: m.blue.flightFeel, red: m.red.flightFeel, control: g.controlMode,
        assist: g.player.settings.assist, invert: g.player.settings.invert, t: m.time,
        seed: m.seed, spawn: { x: m.blue.pos.x, z: m.blue.pos.z } };
    });
    const first = await sortie();
    assert.deepEqual([first.blue, first.red, first.assist], ['tactical', 'tactical', true], `${label}: both jets fly the chosen physics`);
    await sleep(1200);
    // Pitch-only change while paused: same sortie continues, new convention live.
    await act('#pauseBtn');
    assert.ok(await visible('pause'));
    await sleep(500);
    const camGap = () => p.evaluate(() => {
      const g = window.__game, c = g.rend.camera.position, b = g.match.blue.pos;
      return Math.hypot(c.x - b.x, c.y - b.y, c.z - b.z);
    });
    assert.ok(await camGap() < 150, `${label}: pause freezes the chase view instead of the title orbit`);
    await act('#btnPauseSettings');
    assert.match(await p.textContent('#btnSettingsApply'), /儲存並繼續/);
    await act('#optInvert');
    await act('#btnSettingsApply');
    await sleep(400);
    const resumed = await sortie();
    assert.equal(resumed.mode, 'playing', `${label}: pitch-only change resumes`);
    assert.ok(resumed.t > first.t + 0.5, `${label}: same sortie, not a restart`);
    assert.equal(resumed.invert, true, `${label}: invert applies to the live PlayerController`);
    const stick = await p.evaluate(() => {
      const g = window.__game; g.input.stick.y = 0.5; const c = g.player.update(); g.input.stick.y = 0; return c.pitch;
    });
    assert.ok(stick > 0 || resumed.assist, `${label}: inverted stick-up now pulls`);
    // Physics/control change while paused: same seed, fresh sortie.
    await act('#pauseBtn');
    await act('#btnPauseSettings');
    await act('[data-flight-choice="arcade:expert"]');
    assert.match(await p.textContent('#btnSettingsApply'), /套用並重新出擊/);
    await act('#btnSettingsApply');
    await sleep(300);
    const restarted = await sortie();
    assert.deepEqual([restarted.blue, restarted.red, restarted.control, restarted.assist],
      ['arcade', 'arcade', 'expert', false], `${label}: pause apply switches both jets`);
    assert.ok(restarted.t < 1, `${label}: physics change restarts the sortie`);
    assert.equal(restarted.seed, first.seed, `${label}: restart keeps the seed`);
    assert.ok(Math.hypot(restarted.spawn.x - first.spawn.x, restarted.spawn.z - first.spawn.z) < 250,
      `${label}: restart keeps the seeded opening geometry`);
    assert.equal(restarted.invert, true, `${label}: pitch convention carries over`);
    // Cancel from pause leaves the fight untouched and returns to PAUSED.
    await act('#pauseBtn');
    await act('#btnPauseSettings');
    await act('[data-flight-choice="tactical:expert"]');
    await act('#btnSettingsCancel');
    assert.ok(await visible('pause'), `${label}: cancel returns to pause`);
    await act('#btnResume');
    assert.ok(await camGap() < 150, `${label}: resume does not swoop the camera in from afar`);
    assert.equal((await sortie()).blue, 'arcade', `${label}: cancel keeps current physics`);
    await shot(p, `01-${label}-sortie`);
    // Re-sortie after a finished match keeps the chosen preset.
    await p.evaluate(() => { const m = window.__game.match; m.damage(m.red, 100, m.blue, 'gun'); });
    await p.waitForFunction(() => window.__game.mode === 'result', null, { timeout: 15000 });
    await act('#btnRematch');
    await p.waitForFunction(() => window.__game.mode === 'playing');
    const again = await sortie();
    assert.deepEqual([again.blue, again.red, again.control], ['arcade', 'arcade', 'expert'], `${label}: rematch keeps preset`);
    report.perf[label] = { passed: true };
    await ctx.close();
  }
}
if (scenario === 'all' || scenario === 'modes') {
  // Each of the four combinations on the iPhone-sized touch layout, driven by real
  // CDP touches on the floating stick. Checks the control interpretation in the
  // live game (Expert: x = roll rate, no auto-level; Assisted: x = level turn,
  // centred stick rolls out) and that AB/BRK/throttle stay the player's.
  report.perf.modes = {};
  for (const combo of ['arcade:assisted', 'arcade:expert', 'tactical:assisted', 'tactical:expert']) {
    const [flight, control] = combo.split(':');
    const label = `mode-${flight}-${control}`;
    const { ctx, p } = await page(iphone, `?mode=${flight}&control=${control}&seed=41&autostart=1`, label);
    await p.waitForFunction(() => window.__game?.mode === 'playing');
    const cdp = await ctx.newCDPSession(p);
    const touch = (type, pts) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: pts });
    const probe = () => p.evaluate(() => {
      const b = window.__game.match.blue, u = { x: 0, y: 1, z: 0 };
      const q = b.q, rot = (v) => { // body right/up in world, via three-free math
        const { x, y, z, w } = q, ix = w * v.x + y * v.z - z * v.y, iy = w * v.y + z * v.x - x * v.z,
          iz = w * v.z + x * v.y - y * v.x, iw = -x * v.x - y * v.y - z * v.z;
        return { x: ix * w + iw * -x + iy * -z - iz * -y, y: iy * w + iw * -y + iz * -x - ix * -z, z: iz * w + iw * -z + ix * -y - iy * -x };
      };
      const r = rot({ x: 1, y: 0, z: 0 }), up = rot(u), f = rot({ x: 0, y: 0, z: -1 });
      return { t: window.__game.match.time, bank: Math.atan2(-r.y, up.y) * 180 / Math.PI,
        hdg: Math.atan2(f.x, -f.z) * 180 / Math.PI, g: b.nCur, v: b.speed, boost: b.controls.boost,
        brake: b.controls.brake, throttle: b.controls.throttle, flight: b.flightFeel, red: window.__game.match.red.flightFeel };
    });
    const s0 = await probe();
    assert.deepEqual([s0.flight, s0.red], [flight, flight], `${label}: both jets fly ${flight}`);
    // right stick, ~55% deflection, then lift the finger (stick stays latched)
    await touch('touchStart', [{ x: 150, y: 260, id: 1 }]);
    for (let i = 1; i <= 6; i++) { await touch('touchMove', [{ x: 150 + i * 6, y: 260, id: 1 }]); await sleep(30); }
    await touch('touchEnd', []);
    await sleep(1200);
    const s1 = await probe();
    if (control === 'expert') assert.ok(Math.abs(s1.bank) > 60, `${label}: held right stick keeps rolling (bank ${s1.bank.toFixed(0)})`);
    else {
      assert.ok(s1.bank > 30 && s1.bank < 95, `${label}: assisted right stick banks into a level turn (bank ${s1.bank.toFixed(0)})`);
      const dh = Math.abs(((s1.hdg - s0.hdg + 540) % 360) - 180);
      assert.ok(dh > 3, `${label}: assisted right stick turns the jet (${dh.toFixed(1)} deg)`);
    }
    // centre the stick: Assisted rolls out, Expert holds whatever bank it has
    await touch('touchStart', [{ x: 300, y: 260, id: 2 }]);
    await touch('touchMove', [{ x: 300 - 36, y: 260, id: 2 }]);
    await touch('touchEnd', []);
    const stick = await p.evaluate(() => ({ ...window.__game.input.stick }));
    assert.ok(Math.abs(stick.x) < 1e-9, `${label}: dragging back to the anchor centres the stick`);
    const s2a = await probe(); await sleep(1500); const s2 = await probe();
    if (control === 'assisted') assert.ok(Math.abs(s2.bank) < 15, `${label}: centred assisted stick rolls wings level (${s2.bank.toFixed(0)})`);
    else assert.ok(Math.abs(s2.bank - s2a.bank) < 12, `${label}: centred expert stick holds bank (no auto-level)`);
    // pull while banked (Expert) / pull straight (Assisted): G must rise, capped by the model
    await touch('touchStart', [{ x: 300, y: 260, id: 3 }]);
    for (let i = 1; i <= 6; i++) { await touch('touchMove', [{ x: 300, y: 260 + i * 9, id: 3 }]); await sleep(30); }
    await sleep(700);
    const s3 = await probe();
    assert.ok(s3.g > 2.5, `${label}: aft stick pulls G (${s3.g.toFixed(1)})`);
    await shot(p, `14-${label}-pull`);
    await touch('touchEnd', []);
    // player-owned power: AB toggle and momentary BRK, throttle untouched by any mode
    await p.tap('[data-btn="boost"]'); await sleep(250);
    const s4 = await probe();
    assert.equal(s4.boost, true, `${label}: AB toggles on`);
    assert.ok(Math.abs(s4.throttle - 0.72) < 1e-9, `${label}: throttle stays at the player's 72%`);
    await p.tap('[data-btn="boost"]'); await sleep(250);
    assert.equal((await probe()).boost, false, `${label}: AB toggles off; Assisted never re-lights it`);
    report.perf.modes[combo] = { s1: { bank: +s1.bank.toFixed(1) }, s2: { bank: +s2.bank.toFixed(1) }, pullG: +s3.g.toFixed(1),
      fps: await p.evaluate(() => +window.__perf.fps.toFixed(1)) };
    await ctx.close();
  }
  // One complete 1v1 per physics profile, to the result screen and a rematch.
  for (const flight of ['arcade', 'tactical']) {
    const label = `match-${flight}`;
    const { ctx, p } = await page(desktop, `?mode=${flight}&control=expert&autostart=1&autopilot=chaser&seed=21`, label);
    await p.waitForFunction(() => window.__game?.mode === 'playing');
    await p.evaluate(() => window.__game.setTimeScale(6));
    let st;
    for (let i = 0; i < 420; i++) { await sleep(1000); st = await state(p); if (st.mode === 'result') break; }
    assert.equal(st.mode, 'result', `${label}: full match reaches the result screen`);
    await shot(p, `15-${label}-result`);
    await p.keyboard.press('Enter'); await sleep(1200);
    const again = await p.evaluate(() => ({ mode: window.__game.mode, b: window.__game.match.blue.flightFeel, r: window.__game.match.red.flightFeel }));
    assert.deepEqual(again, { mode: 'playing', b: flight, r: flight }, `${label}: rematch keeps ${flight} for both jets`);
    report.perf.modes[label] = { result: st.result };
    await ctx.close();
  }
}
if (scenario === 'all' || scenario === 'academy') {
  // Ace Flight Academy through the real menus on the iPhone-sized touch layout.
  // The automated student drives the game's own Input object (stick values,
  // throttle strip, AB toggle, BRK) before every simulation step, i.e. the same
  // PlayerController path as a thumb. Flow: title -> academy -> briefing ->
  // sortie -> causal failure -> retry -> clear -> progress saved -> reload.
  const { fly } = await import('./test-academy.mjs');
  const { lessonById } = await import('../src/academy/lessons.js');
  const { PLANS } = await import('./academy-student.mjs');
  const l10Expect = {};
  for (const m of ['arcade:expert', 'arcade:assisted']) {
    const r = fly(lessonById('L10'), m, PLANS.L10, { maxT: 420 }).result;
    l10Expect[m] = { success: r.success, reason: r.reason ?? null, grade: r.grade, t: +r.time.toFixed(2) };
  }
  const { ctx, p } = await page(iphone, '?seed=3', 'academy');
  await p.waitForFunction(() => window.__game?.mode === 'title');
  // The student is attached by the game's onLessonStart hook, i.e. BEFORE the first
  // simulation step, so a browser lesson is the same fixed-step run as the Node
  // test with the same seed. The lesson itself is still launched from the menus.
  await p.evaluate(async () => {
    const S = await import('/tools/academy-student.mjs');
    window.__studentMod = S;
    window.__game.onLessonStart = () => {
      const g = window.__game, m = g.match, ctl = m.controllers.get(m.blue);
      const badKey = window.__studentBad || null;
      const st = S.makeStudentInput();
      const plan = badKey ? S.BAD[badKey] : S.PLANS[g.lessonId];
      const orig = ctl.update;
      ctl.update = (dt, mm) => {
      plan(g.lesson, st, g.controlMode);
      g.input.stick.x = st.stick.x; g.input.stick.y = st.stick.y;
      if (Math.abs(g.input.throttle() - st.thr) > 1e-3) g.input.setThrottle(st.thr);
      g.input.boostToggle = st.ab; g.input.btn.brake = st.brk;
      if (st.presses.size) { for (const k of st.presses) g.input.pressed.add(k); st.presses.clear(); }
      g.input.btn.gun = !!st.gunOn;
      return orig(dt, mm);
      };
      g.setTimeScale(4);
    };
  });
  const hook = (bad = null) => p.evaluate((b) => { window.__studentBad = b; }, bad);
  const waitDebrief = () => p.waitForFunction(() => window.__game.mode === 'debrief', null, { timeout: 240000 });
  const lessonIds = await p.evaluate(async () => (await import('/src/academy/lessons.js')).LESSONS.map((l) => l.id));
  await p.waitForFunction(() => window.__game?.mode === 'title');
  await p.tap('#btnAcademy');
  assert.equal(await p.locator('#lessonGrid .lesson-card').count(), lessonIds.length, 'academy lists every lesson');
  await shot(p, '16-academy-grid');
  // L03 power: a student who dives for speed must fail with the causal reason
  await p.tap('[data-lesson="L03"]');
  await shot(p, '17-academy-briefing');
  await hook('L03:dive');
  await p.tap('#btnBriefGo');
  await p.waitForFunction(() => window.__game.mode === 'playing');
  await waitDebrief();
  const fail = await p.evaluate(() => window.__lastLesson);
  assert.equal(fail.success, false, 'diving student fails L03');
  assert.match(await p.textContent('#debSub'), /第五課/, 'failure explains WHY (thrust lesson, not a dive)');
  await shot(p, '18-academy-fail');
  // Retry the same lesson with a correct student
  await hook();
  await p.tap('#btnDebRetry');
  await p.waitForFunction(() => window.__game.mode === 'playing' && window.__game.lesson && !window.__game.lesson.result);
  await sleep(1500); await shot(p, '19-academy-flying');
  await waitDebrief();
  const clear = await p.evaluate(() => window.__lastLesson);
  assert.equal(clear.success, true, 'student clears L03 on retry');
  await shot(p, '20-academy-clear');
  const saved = await p.evaluate(() => JSON.parse(localStorage.getItem('ace2ace.academy.v1')));
  assert.equal(saved.lessons.L03.cleared, true); assert.equal(saved.lessons.L03.attempts, 2);
  // Every lesson clears in the browser in the current mode via Next / grid
  for (const id of lessonIds) {
    if (id === 'L03') continue;
    await p.evaluate((lid) => window.__game.openBriefing(lid), id);
    if (id === 'L08' || id === 'L10') await shot(p, `22-academy-brief-${id}`);
    await p.tap('#btnBriefGo');
    await p.waitForFunction(() => window.__game.mode === 'playing' && window.__game.lesson && !window.__game.lesson.result);
    if (id === 'L07' || id === 'L09') { await sleep(2500); await shot(p, `23-academy-fly-${id}`); }
    await waitDebrief();
    const res = await p.evaluate(() => window.__lastLesson);
    if (id === 'L10') {
      // The checkride is a real 1v1 vs VETERAN with a fixed opening: it is completable
      // (12-seed headless check), not guaranteed. The browser run must reproduce the
      // headless fixed-step run of the same mode exactly (outcome, reason, time).
      const want = l10Expect[res.mode];
      assert.deepEqual([res.success, res.reason ?? null, +res.time.toFixed(2)], [want.success, want.reason, want.t],
        `L10 ${res.mode}: browser run reproduces the headless run`);
      if (!res.success) {
        await shot(p, '24a-academy-checkride-lost');
        // switch the airframe/control preset from the academy menu and fly it again
        await p.tap('#btnDebAcademy');
        await p.tap('#btnAcademySettings');
        await p.tap('[data-flight-choice="arcade:assisted"]');
        await p.tap('#btnSettingsApply');
        assert.equal(await p.textContent('#academyMode'), 'ARCADE / ASSISTED', 'academy shows the new preset');
        await p.tap('[data-lesson="L10"]');
        await p.tap('#btnBriefGo');
        await waitDebrief();
        const win = await p.evaluate(() => window.__lastLesson);
        const w2 = l10Expect[win.mode];
        assert.deepEqual([win.mode, win.success, win.grade, +win.time.toFixed(2)], ['arcade:assisted', w2.success, w2.grade, w2.t],
          'L10 arcade:assisted: browser run reproduces the headless win');
        report.perf['academy-L10-lost'] = { mode: res.mode, t: Math.round(res.time), reason: res.reason };
        Object.assign(res, win);
      }
      assert.equal(res.success, true, 'the checkride is cleared in at least one preset');
      assert.match(await p.textContent('#debTitle'), /ACE RATING [SAB]/); await shot(p, '24-academy-ace-rating');
    } else assert.equal(res.success, true, `${id} clears in the browser (${res.reason || ''})`);
    report.perf[`academy-${id}`] = { grade: res.grade, t: Math.round(res.time), mode: res.mode };
  }
  await p.reload();
  await p.waitForFunction(() => window.__game?.mode === 'title');
  await p.tap('#btnAcademy');
  const cleared = await p.locator('#lessonGrid .lesson-card.cleared').count();
  assert.equal(cleared, lessonIds.length, 'progress survives a reload');
  await shot(p, '21-academy-progress');
  report.perf.academy = { passed: true, lessons: lessonIds.length };
  await ctx.close();
}
if (scenario === 'all' || scenario === 'fight') {
  // automated player proxy so the fight actually happens
  const { ctx, p } = await page(desktop, '?mode=pvai&autopilot=chaser&seed=3&debug', 'fight');
  const timeline = [];
  for (const [i, wait] of [[0, 2500], [1, 6000], [2, 5000], [3, 5000], [4, 6000], [5, 8000]].entries()) {
    await sleep(wait[1]);
    timeline.push(await state(p));
    await shot(p, `02-fight-${i}`);
  }
  report.perf.fightDesktop = timeline;
  await ctx.close();
}
if (scenario === 'all' || scenario === 'manual') {
  // real keyboard input path: fly with the arrow keys and fire
  const { ctx, p } = await page(desktop, '?seed=5', 'manual');
  await sleep(800);
  await p.click('#btnStart');
  await sleep(1500);
  await p.keyboard.down('KeyW'); await sleep(1500); await p.keyboard.up('KeyW');
  await p.keyboard.down('ArrowRight'); await sleep(500); await p.keyboard.up('ArrowRight');
  await p.keyboard.down('ArrowDown'); await sleep(1200); await p.keyboard.up('ArrowDown');
  await shot(p, '03-manual-turn');
  await p.keyboard.press('Space');
  await sleep(600); await shot(p, '04-manual-fox2');
  await p.keyboard.down('KeyE'); await sleep(900); await shot(p, '05-look-at-target'); await p.keyboard.up('KeyE');
  report.perf.manual = await state(p);
  await ctx.close();
}
if (scenario === 'all' || scenario === 'touch') {
  const { ctx, p } = await page(iphone, '?seed=7', 'touch');
  await sleep(1200); await shot(p, '06-title-iphone');
  await p.tap('#btnStart');
  await sleep(2500); await shot(p, '07-touch-hud');
  // drag the virtual stick with a synthetic touch sequence via CDP
  const cdp = await ctx.newCDPSession(p);
  const touch = (type, pts) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: pts });
  await touch('touchStart', [{ x: 150, y: 260, id: 1 }]);
  for (let i = 1; i <= 10; i++) { await touch('touchMove', [{ x: 150 + i * 5, y: 260 + i * 4, id: 1 }]); await sleep(60); }
  await sleep(800);
  await shot(p, '08-touch-stick-turn');
  const beforeRelease = await p.evaluate(() => ({ ...window.__game.input.stick }));
  await touch('touchEnd', []);
  const afterRelease = await p.evaluate(() => ({ ...window.__game.input.stick }));
  const equalStick = (a, b) => Math.abs(a.x - b.x) < 1e-8 && Math.abs(a.y - b.y) < 1e-8;
  if (Math.hypot(beforeRelease.x, beforeRelease.y) < 0.1 || !equalStick(beforeRelease, afterRelease))
    throw new Error('Touch release must hold the last joystick command (not auto-center)');
  await touch('touchStart', [{ x: 150, y: 260, id: 2 }]);
  const afterRetouch = await p.evaluate(() => ({ ...window.__game.input.stick }));
  if (!equalStick(afterRelease, afterRetouch))
    throw new Error('Re-touch must not jump the joystick back to neutral');
  await touch('touchMove', [{ x: 160, y: 255, id: 2 }]);
  const adjusted = await p.evaluate(() => ({ ...window.__game.input.stick }));
  if (equalStick(adjusted, afterRetouch))
    throw new Error('A new drag should adjust the held joystick command');
  await touch('touchEnd', []);
  const afterSecondRelease = await p.evaluate(() => ({ ...window.__game.input.stick }));
  if (!equalStick(adjusted, afterSecondRelease))
    throw new Error('Second touch release must also hold the adjusted command');
  // Real CDP touches, including simultaneous stick + throttle. The style pass
  // must leave latched throttle, AB toggle and momentary BRK independent.
  const track = await p.locator('#throttleTrack').boundingBox();
  const tx = track.x + track.width / 2;
  await touch('touchStart', [{ x: 150, y: 260, id: 3 }]);
  await touch('touchMove', [{ x: 175, y: 250, id: 3 }]);
  await touch('touchStart', [{ x: 175, y: 250, id: 3 }, { x: tx, y: track.y + track.height / 2, id: 4 }]);
  await touch('touchMove', [{ x: 175, y: 250, id: 3 }, { x: tx, y: track.y + track.height * 0.65, id: 4 }]);
  const heldPower = await p.evaluate(() => ({ throttle: window.__game.input.throttle(), stick: { ...window.__game.input.stick } }));
  await touch('touchEnd', []);
  const powerState = () => p.evaluate(() => ({ throttle: window.__game.input.throttle(), boost: window.__game.input.boost(), brake: window.__game.input.brake() }));
  assert.ok(heldPower.throttle > 0.1 && heldPower.throttle < 0.6, 'touch drag changes throttle');
  assert.ok(equalStick(heldPower.stick, await p.evaluate(() => ({ ...window.__game.input.stick }))), 'throttle touch leaves stick latched');
  assert.equal((await powerState()).throttle, heldPower.throttle, 'release holds throttle');
  await p.tap('[data-btn="boost"]');
  assert.equal((await powerState()).boost, true, 'AB toggles on');
  const brake = await p.locator('[data-btn="brake"]').boundingBox();
  await touch('touchStart', [{ x: brake.x + brake.width / 2, y: brake.y + brake.height / 2, id: 5 }]);
  const braking = await powerState();
  assert.ok(braking.brake && braking.boost, 'BRK coexists with latched AB');
  assert.equal(braking.throttle, heldPower.throttle, 'BRK preserves throttle');
  await touch('touchEnd', []);
  assert.equal((await powerState()).brake, false, 'release clears BRK');
  assert.equal((await powerState()).boost, true, 'release preserves AB');
  await p.tap('[data-btn="boost"]');
  assert.equal((await powerState()).boost, false, 'AB toggles off');
  report.perf.powerStrip = { passed: true, throttle: heldPower.throttle };
  await p.tap('[data-btn="msl"]');
  await sleep(500); await shot(p, '09-touch-msl');
  report.perf.touch = await state(p);
  await ctx.close();
}
if (scenario === 'all' || scenario === 'aivai') {
  const { ctx, p } = await page(desktop, '?mode=aivai&seed=11&debug', 'aivai');
  await sleep(12000); await shot(p, '10-aivai');
  report.perf.aivai = await state(p);
  await ctx.close();
}
if (scenario === 'all' || scenario === 'result') {
  // play a full player-vs-AI match with the autopilot at accelerated time to reach the
  // kill cam and the result / rematch screen, then press Enter to rematch
  const { ctx, p } = await page(desktop, '?mode=pvai&autopilot=chaser&seed=21', 'result');
  await sleep(1500);
  await p.evaluate(() => window.__game.setTimeScale(6));
  let killShot = false;
  for (let i = 0; i < 360; i++) {
    await sleep(1000);
    const st = await state(p);
    if (!killShot && st.result == null && (!st.blue.alive || !st.red.alive)) { await shot(p, '11-killcam'); killShot = true; }
    if (st.mode === 'result') break;
  }
  await sleep(500); await shot(p, '12-result');
  report.perf.result = await state(p);
  assert.equal(report.perf.result.mode, 'result', 'full match reaches result');
  await p.keyboard.press('Enter'); await sleep(1500);
  report.perf.rematch = await state(p);
  assert.equal(report.perf.rematch.mode, 'playing', 'Enter restarts the match');
  await shot(p, '13-rematch');
  await ctx.close();
}

await browser.close();
server.close();
await writeFile(join(OUT, 'report.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 1));
if (report.errors.length) process.exitCode = 1;
