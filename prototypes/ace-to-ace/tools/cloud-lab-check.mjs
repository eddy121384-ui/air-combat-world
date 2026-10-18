// Real Chromium screenshots + bounded spatial/input/GPU evidence. No generated images.
import http from 'node:http';
import assert from 'node:assert/strict';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve, extname, sep } from 'node:path';
import { createHash } from 'node:crypto';
const req = createRequire(import.meta.url), { chromium } = req('playwright');
const root = fileURLToPath(new URL('../', import.meta.url));
const outArg=process.argv.indexOf('--out');
const rendererArg=process.argv.indexOf('--renderer');
const rendererMode=rendererArg>=0?process.argv[rendererArg+1]:'debug';
assert.ok(['debug','anime'].includes(rendererMode));
const out = new URL('../'+(outArg>=0?process.argv[outArg+1]:'docs/cloud-engine-b0')+'/', import.meta.url);
await mkdir(new URL('screens/', out), { recursive: true });
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.jpg': 'image/jpeg', '.png': 'image/png' };
const server = http.createServer(async (request, response) => {
  try {
    const path = resolve(root, '.' + decodeURIComponent(new URL(request.url, 'http://local').pathname));
    assert.ok(path.startsWith(resolve(root) + sep));
    const data = await readFile(path);
    response.writeHead(200, { 'Content-Type': mime[extname(path)] || 'application/octet-stream' }); response.end(data);
  } catch { response.writeHead(404); response.end('not found'); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
let browser;
const report = { rendererMode, errors: [], views: {}, spatial: {}, perf: {}, discardedFirstQueryAfterStateChange: true,
  runtime: 'Chromium / ANGLE SwiftShader; desktop diagnostic only, no iPhone GPU claim' };
report.provenance = { baseline: '0db84b5953eaffd75c3256ad0579f3c098dd0147', capturedAt: new Date().toISOString(), sourceSha256: {} };
for (const path of ['src/cloud/cloud-field.js', 'src/cloud/cloud-debug-renderer.js', 'tools/cloud-lab.html', 'tools/cloud-lab.js'])
  report.provenance.sourceSha256[path] = createHash('sha256').update(await readFile(resolve(root, path))).digest('hex');
try {
  browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  report.provenance.browser = browser.version();
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  page.on('pageerror', e => report.errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') report.errors.push(m.text()); });
  page.on('response', r => { if (r.status() >= 400) report.errors.push(`HTTP ${r.status()}: ${r.url()}`); });
  page.on('requestfailed', r => report.errors.push(`requestfailed: ${r.url()}`));
  await page.goto(`http://127.0.0.1:${server.address().port}/tools/cloud-lab.html?renderer=${rendererMode}`);
  await page.waitForFunction(() => window.__cloudLab?.snapshot().ready, null, { timeout: 60000 });
  async function capture(name, mode, progress) {
    const s = await page.evaluate(({ mode, progress }) => {
      const lab = window.__cloudLab; lab.setRoute(mode); lab.setProgress(progress); return lab.frame();
    }, { mode, progress });
    assert.ok(s.programsRunnable, 'all shaders link');
    assert.ok(s.calls < 20, 'bounded debug geometry');
    await page.screenshot({ path: fileURLToPath(new URL(`screens/${name}.png`, out)) });
    report.views[name] = s; return s;
  }
  const approach = await capture('01-approach', 'traverse', 0.08);
  const inside = await capture('02-inside', 'traverse', 0.5);
  const exit = await capture('03-exit', 'traverse', 0.96);
  assert.equal(approach.density, 0); assert.ok(inside.density > 0.5); assert.equal(exit.density, 0);
  assert.ok(approach.transmittance500 > 0.99 && inside.transmittance500 < 0.1 && exit.transmittance500 > 0.99);
  for (const [name, mode, progress] of [['04-side', 'orbit', 0.25], ['05-above', 'above', 0.125], ['06-below', 'below', 0.125]]) {
    const s = await capture(name, mode, progress); assert.equal(s.density, 0, 'outside observation point');
  }
  // Same eye, six directions: density must not change with the camera, visibility can.
  report.spatial.directions = await page.evaluate(() => {
    const l = window.__cloudLab, pos = [0, 3020, 0];
    return [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]].map(d => {
      l.setPose(pos, pos.map((p, i) => p + d[i] * 500)); return l.frame();
    });
  });
  assert.ok(report.spatial.directions.every(s => Math.abs(s.density - report.spatial.directions[0].density) < 1e-10));
  // Turn away and return to exact pose; compare actual rendered pixels, not only CPU values.
  const pose = async target => page.evaluate(target => { const l = window.__cloudLab; l.setPose([1800, 3050, 1700], target); l.frame(); }, target);
  const pixels = () => page.evaluate(() => {
    window.__cloudLab.frame();
    const gl = document.querySelector('canvas').getContext('webgl2');
    const data = new Uint8Array(gl.drawingBufferWidth * gl.drawingBufferHeight * 4);
    gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, data);
    let h = 2166136261; for (const b of data) h = Math.imul(h ^ b, 16777619);
    return h >>> 0;
  });
  await pose([0, 3020, 0]); const original = await pixels();
  await pose([3600, 3050, 3400]); await pose([0, 3020, 0]); const returned = await pixels();
  assert.equal(original, returned, 'world framebuffer is identical after turn-away/return (excludes changing HTML timing text)');
  report.spatial.returnToPosePixelsIdentical = true;
  // Real controls: slider, playback, mouse look, keyboard flight, wind.
  await page.locator('[data-view="traverse"]').click();
  await page.locator('#timeline').fill('0.5');
  await page.waitForFunction(() => window.__cloudLab.snapshot().density > 0.5);
  await page.locator('#play').click(); await page.waitForTimeout(500); await page.locator('#play').click();
  assert.ok((await page.evaluate(() => window.__cloudLab.snapshot())).progress > 0.5);
  await page.locator('[data-view="free"]').click();
  const before = await page.evaluate(() => window.__cloudLab.snapshot());
  await page.mouse.move(900, 400); await page.mouse.down(); await page.mouse.move(1010, 440, { steps: 6 }); await page.mouse.up();
  await page.keyboard.down('KeyW'); await page.waitForTimeout(500); await page.keyboard.up('KeyW');
  const after = await page.evaluate(() => window.__cloudLab.snapshot());
  assert.notDeepEqual(after.direction, before.direction); assert.notDeepEqual(after.position, before.position);
  await page.locator('#wind').check(); await page.waitForTimeout(500); await page.locator('#wind').uncheck();
  assert.ok((await page.evaluate(() => window.__cloudLab.snapshot())).time > 0);
  report.spatial.interactiveControlsPassed = true;
  // Display continuity at the actual front boundary, 220 m/s at 60 Hz.
  // Read the framebuffer after each render, excluding HTML overlays and timing text.
  await page.locator('details').last().evaluate(el => { el.open = true; });
  await page.locator('#quality').selectOption('0.25');
  report.spatial.boundaryPixelSweep = await page.evaluate(() => {
    const lab = window.__cloudLab, gl = document.querySelector('canvas').getContext('webgl2');
    const data = new Uint8Array(16 * 16 * 4), means = [];
    for (let i = 0; i < 96; i++) {
      const z = 2600 - i * 220 / 60;
      lab.setTime(0); lab.setPose([0, 3062, z], [0, 3062, z - 500]); lab.frame();
      gl.readPixels(Math.floor(gl.drawingBufferWidth / 2) - 8, Math.floor(gl.drawingBufferHeight / 2) - 8, 16, 16, gl.RGBA, gl.UNSIGNED_BYTE, data);
      let mean = 0; for (let j = 0; j < data.length; j += 4) mean += data[j] + data[j + 1] + data[j + 2];
      means.push(mean / (256 * 3 * 255));
    }
    return { samples: means.length, maxMeanRgbDelta: Math.max(...means.slice(1).map((m, i) => Math.abs(m - means[i]))) };
  });
  assert.ok(report.spatial.boundaryPixelSweep.maxMeanRgbDelta < 0.06, 'rendered boundary has no large frame-to-frame flash');
  await page.locator('#kind').selectOption('stratocumulus');
  await capture('07-stratocumulus', 'above', 0.125);
  const sc = await capture('08-stratocumulus-inside', 'traverse', 0.5);
  assert.ok(sc.density > 0.5 && sc.transmittance500 < 0.1);
  // Timer-query GPU cost is separate from JS render submission and CPU field benchmark.
  for (const quality of process.argv.includes('--skip-perf')?[]:['0.25', '0.5', '1']) {
    // The current route is through Sc, providing a full cloud-covered workload.
    await page.locator('details').last().evaluate(el => { el.open = true; });
    await page.locator('#quality').selectOption(quality);
    for (const enabled of [true, false]) {
      await page.locator('#clouds').setChecked(enabled);
      await page.waitForTimeout(1000);
      const samples = [];
      let lastSample = (await page.evaluate(() => window.__cloudLab.snapshot())).gpuSample;
      // Renderer allows one pending query. Discard the first completed query so
      // an in-flight frame from before the quality/enable switch is never labelled as the new state.
      let discardFirst = true;
      for (let i = 0; i < 400 && samples.length < 6; i++) {
        await page.waitForTimeout(80);
        const s = await page.evaluate(() => window.__cloudLab.snapshot());
        if (!s.gpuTimerAvailable || s.gpuSample !== lastSample) {
          lastSample = s.gpuSample;
          if (discardFirst) discardFirst = false; else samples.push(s);
        }
      }
      assert.equal(samples.length, 6, 'six fresh timer query samples (or explicit unavailable)');
      report.perf[`${quality}-${enabled ? 'cloud' : 'clear'}`] = samples;
      console.log(`GPU ${quality} ${enabled ? 'cloud' : 'clear'}: ${samples.length} fresh samples`);
    }
  }
  // Touch-sized browser checks layout and an actual touch drag on the scene.
  const touch = await browser.newContext({ viewport: { width: 812, height: 375 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 });
  const tp = await touch.newPage();
  tp.on('pageerror', e => report.errors.push(`touch: ${e.message}`));
  await tp.goto(page.url()); await tp.waitForFunction(() => window.__cloudLab?.snapshot().ready);
  const session = await touch.newCDPSession(tp), startDirection = await tp.evaluate(() => window.__cloudLab.snapshot().direction);
  await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: 650, y: 190, id: 1 }] });
  await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: 730, y: 220, id: 1 }] });
  await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await tp.waitForTimeout(150);
  assert.notDeepEqual(await tp.evaluate(() => window.__cloudLab.snapshot().direction), startDirection);
  await tp.screenshot({ path: fileURLToPath(new URL('screens/09-touch.png', out)) });
  report.spatial.touchDragPassed = true;
  await touch.close();
  assert.deepEqual(report.errors, []);
  report.passed = true;
} finally {
  await browser?.close(); server.close();
  await writeFile(new URL('browser-validation.json', out), JSON.stringify(report, null, 2) + '\n');
}
console.log(JSON.stringify({ passed: report.passed, errors: report.errors, views: Object.keys(report.views), spatial: report.spatial.returnToPosePixelsIdentical }, null, 2));
