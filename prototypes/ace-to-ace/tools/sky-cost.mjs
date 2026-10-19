// Workload measurement for the Opus Sky cloud pass on real frames. Not an FPS benchmark:
// SwiftShader timing says nothing about an iPhone GPU. Instead it counts, per pixel, how many
// cloud fragments are rasterised (shader invocations) and how many survive discard, then scales
// those counts to phone drawing-buffer sizes. Pair with tools/sky-bench.html on the device.
//
//   node tools/sky-cost.mjs --out docs/cloud-opus/cost.json
import http from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve, extname, sep, dirname } from 'node:path';
const { chromium } = createRequire(import.meta.url)('playwright');

const root = fileURLToPath(new URL('../', import.meta.url));
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const out = resolve(root, opt('--out', 'tools/out/sky/cost.json'));
const W = 640, H = 360; // counts per pixel are resolution-independent to first order
const shots = [['approach', 1], ['approach', 0.5], ['sidepass', 0.5], ['orbit180', 0.5], ['traverse', 0.5], ['deck', 0.3], ['deck', 0.5]];
// Drawing-buffer pixels for common targets (landscape). DPR caps follow sky-lab "auto" (≤2).
const targets = { 'iPhone 13 mini @2x': 812 * 375 * 4, 'iPhone 15 @2x': 852 * 393 * 4, 'iPhone 15 Pro Max @2x': 932 * 430 * 4, 'iPhone 15 @1.5x': 852 * 393 * 2.25 };

const mime = { '.html': 'text/html', '.js': 'text/javascript', '.jpg': 'image/jpeg', '.png': 'image/png' };
const server = http.createServer(async (req, res) => {
  try {
    const path = resolve(root, '.' + decodeURIComponent(new URL(req.url, 'http://x').pathname));
    if (!path.startsWith(resolve(root) + sep)) throw new Error('outside');
    res.writeHead(200, { 'Content-Type': mime[extname(path)] || 'application/octet-stream' }); res.end(await readFile(path));
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const report = { method: 'additive per-pixel fragment counting on real frames (SwiftShader); scaled to target drawing buffers', size: [W, H], shots: [] };
try {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  page.on('pageerror', e => { throw e; });
  await page.goto(`http://127.0.0.1:${server.address().port}/tools/sky-lab.html${opt('--query', '')}`);
  await page.waitForFunction(() => window.__sky?.snapshot().ready, null, { timeout: 120000 });
  await page.evaluate(() => { window.__sky.setAnimate(false); window.__sky.setUi(false); });
  report.puffs = await page.evaluate(() => window.__sky.snapshot().puffs);
  for (const [route, f] of shots) {
    const r = await page.evaluate(async ([route, f]) => {
      const S = window.__sky, m = S.sky.puffs.material, fs0 = m.fragmentShader, saved = { blending: m.blending, a2c: m.alphaToCoverage, dt: m.depthTest, dw: m.depthWrite, bs: m.blendSrc, bd: m.blendDst, bsa: m.blendSrcAlpha, bda: m.blendDstAlpha };
      const hide = [S.sky.sky, S.sky.sea, S.sky.streaks, S.sky.mist, ...S.extraHidden]; hide.forEach(o => { o.visible = false; });
      const gl = S.renderer.getContext();
      const count = (mode) => {
        // 'invocations': every rasterised fragment; 'survivors': fragments reaching the colour write.
        let fs = fs0.replace('void main(){', 'void main(){\n#ifdef COUNT_ALL\n gl_FragColor=vec4(vec3(1.0/255.0),1.0); return;\n#endif\n');
        fs = fs.replace(/gl_FragColor=vec4\(col,alpha\);/, 'gl_FragColor=vec4(vec3(1.0/255.0),1.0);');
        m.fragmentShader = fs; m.defines = mode === 'invocations' ? { COUNT_ALL: 1 } : {};
        m.alphaToCoverage = false; m.blending = 2 /* Additive */; m.depthTest = false; m.depthWrite = false; m.needsUpdate = true;
        S.renderer.setClearColor(0x000000, 1);
        S.renderAt(route, f * S.routes[route].duration);
        const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight, px = new Uint8Array(w * h * 4);
        gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
        let sum = 0, max = 0, covered = 0;
        for (let i = 0; i < px.length; i += 4) { const c = px[i]; sum += c; if (c > max) max = c; if (c) covered++; }
        return { mean: sum / (w * h), max, coverage: covered / (w * h) };
      };
      const inv = count('invocations'), sur = count('survivors');
      m.fragmentShader = fs0; m.defines = {}; Object.assign(m, { blending: saved.blending, alphaToCoverage: saved.a2c, depthTest: saved.dt, depthWrite: saved.dw,
        blendSrc: saved.bs, blendDst: saved.bd, blendSrcAlpha: saved.bsa, blendDstAlpha: saved.bda }); m.needsUpdate = true;
      hide.forEach(o => { o.visible = true; });
      const snap = S.renderAt(route, f * S.routes[route].duration);
      return { inv, sur, calls: snap.calls, triangles: snap.triangles, cpuMs: snap.cpuMs, streaks: snap.streaks, density: snap.density };
    }, [route, f]);
    const perTarget = Object.fromEntries(Object.entries(targets).map(([k, px]) => [k, { invocationsM: +(r.inv.mean * px / 1e6).toFixed(2), survivorsM: +(r.sur.mean * px / 1e6).toFixed(2) }]));
    report.shots.push({ route, at: f, invocationsPerPixel: +r.inv.mean.toFixed(2), invocationsMaxPixel: r.inv.max, survivorsPerPixel: +r.sur.mean.toFixed(2),
      cloudCoverage: +r.inv.coverage.toFixed(3), calls: r.calls, triangles: r.triangles, cpuUpdateMs: +r.cpuMs.toFixed(3), streaks: r.streaks, perTarget });
    console.log(route, f, JSON.stringify(report.shots.at(-1).perTarget['iPhone 15 @2x']), 'inv/px', r.inv.mean.toFixed(2), 'max', r.inv.max);
  }
} finally {
  await browser.close(); server.close();
  await mkdir(dirname(out), { recursive: true }); await writeFile(out, JSON.stringify(report, null, 1) + '\n');
}
