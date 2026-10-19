// Smoke test for the on-device benchmark page: it must play every route and print results.
// Timings here are SwiftShader and meaningless for phones; only completeness is asserted.
//   node tools/sky-bench-check.mjs
import http from 'node:http';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve, extname, sep } from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');
const root = fileURLToPath(new URL('../', import.meta.url));
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.jpg': 'image/jpeg' };
const server = http.createServer(async (req, res) => {
  try { const p = resolve(root, '.' + decodeURIComponent(new URL(req.url, 'http://x').pathname)); if (!p.startsWith(resolve(root) + sep)) throw 0;
    res.writeHead(200, { 'Content-Type': mime[extname(p)] || 'application/octet-stream' }); res.end(await readFile(p)); } catch { res.writeHead(404); res.end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 320, height: 180 } });
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/tools/sky-lab.html?bench=quick&quality=mobile`);
  await page.waitForFunction(() => window.__benchResults, null, { timeout: 300000 });
  const r = await page.evaluate(() => window.__benchResults);
  assert.deepEqual(errors, []);
  assert.equal(r.tier, 'mobile');
  assert.deepEqual(Object.keys(r.routes), ['approach', 'sidepass', 'orbit180', 'traverse', 'deck']);
  for (const v of Object.values(r.routes)) assert.ok(v.frames > 3 && v.medianMs > 0);
  assert.ok(await page.locator('pre').textContent().then(t => t.includes('Opus Sky bench')));
  console.log(JSON.stringify({ passed: true, tier: r.tier, routes: Object.fromEntries(Object.entries(r.routes).map(([k, v]) => [k, v.frames])) }));
} finally { await browser.close(); server.close(); }
