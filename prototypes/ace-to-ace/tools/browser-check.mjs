#!/usr/bin/env node
// Launch the real game in Chromium (Playwright), take screenshots, collect console errors and
// frame stats. Desktop + an iPhone-13-mini-sized touch emulation. NOT a substitute for a real
// iPhone: headless Chromium renders WebGL in software (SwiftShader), so FPS here is pessimistic
// for GPU cost and says nothing about Safari/WebKit specifics.
//
//   node tools/browser-check.mjs [--out tools/out/shots] [--scenario all|title|fight|touch|aivai]
import http from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';
import { dirname, join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const args = Object.fromEntries(process.argv.slice(2).map((a, i, arr) => a.startsWith('--') ? [a.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true] : null).filter(Boolean));
const OUT = join(ROOT, args.out || 'tools/out/shots');
const scenario = args.scenario || 'all';

function loadPlaywright() {
  const req = createRequire(import.meta.url);
  try { return req('playwright'); } catch { /* fall through */ }
  const g = execSync('npm root -g').toString().trim();
  return req(join(g, 'playwright'));
}
const { chromium, devices } = loadPlaywright();

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png' };
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

if (scenario === 'all' || scenario === 'title') {
  const { ctx, p } = await page(desktop, '', 'title');
  await sleep(1500); await shot(p, '01-title-desktop');
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
  await touch('touchEnd', []);
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
  await p.keyboard.press('Enter'); await sleep(1500);
  report.perf.rematch = await state(p);
  await shot(p, '13-rematch');
  await ctx.close();
}

await browser.close();
server.close();
console.log(JSON.stringify(report, null, 1));
if (report.errors.length) process.exitCode = 1;
