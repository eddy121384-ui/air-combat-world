// Real Chromium WebGL captures of the Opus Sky Lab: fixed-time stills, contact sheets and
// frame-stepped videos. Every frame is rendered at an exact route time, so the video shows
// what the renderer produces along the path — not playback speed or device FPS.
//
//   node tools/sky-capture.mjs --out tools/out/sky/r1 --stills
//   node tools/sky-capture.mjs --out docs/cloud-opus/final --video approach,sidepass --fps 30 --size 960x540
import http from 'node:http';
import { readFile, mkdir, writeFile, rm } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve, extname, sep, join } from 'node:path';
import { execFileSync } from 'node:child_process';
const { chromium } = createRequire(import.meta.url)('playwright');

const root = fileURLToPath(new URL('../', import.meta.url));
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const out = resolve(root, opt('--out', 'tools/out/sky/latest'));
const [W, H] = opt('--size', '1280x720').split('x').map(Number);
const fps = +opt('--fps', 30);
const query = opt('--query', '');
await mkdir(out, { recursive: true });

const mime = { '.html': 'text/html', '.js': 'text/javascript', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.json': 'application/json' };
const server = http.createServer(async (req, res) => {
  try {
    const path = resolve(root, '.' + decodeURIComponent(new URL(req.url, 'http://x').pathname));
    if (!path.startsWith(resolve(root) + sep)) throw new Error('outside');
    res.writeHead(200, { 'Content-Type': mime[extname(path)] || 'application/octet-stream' }); res.end(await readFile(path));
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const report = { size: [W, H], runtime: 'Chromium ANGLE SwiftShader (software); visual evidence only, not device FPS', errors: [], stills: [], videos: [] };
try {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  page.on('pageerror', e => report.errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') report.errors.push(`${m.type()}: ${m.text()}`); });
  await page.goto(`http://127.0.0.1:${server.address().port}/tools/sky-lab.html?dpr=1${query}`);
  await page.waitForFunction(() => window.__sky?.snapshot().ready, null, { timeout: 120000 });
  await page.evaluate(() => { window.__sky.setAnimate(false); window.__sky.setUi(false); document.querySelector('#dpr').value = '1'; });
  const routes = await page.evaluate(() => window.__sky.routes);
  report.routes = routes;

  if (args.includes('--stills')) {
    const only = opt('--routes', Object.keys(routes).join(',')).split(',');
    const fractions = opt('--at', '0,0.25,0.5,0.75,1').split(',').map(Number);
    for (const name of only) for (const f of fractions) {
      const t = routes[name].duration * f;
      const s = await page.evaluate(([n, t]) => window.__sky.renderAt(n, t), [name, t]);
      const file = `${name}-${String(Math.round(f * 100)).padStart(3, '0')}.jpg`;
      await page.screenshot({ path: join(out, file), type: 'jpeg', quality: 90 });
      report.stills.push({ file, route: name, t, camera: s.camera, density: s.density, streaks: s.streaks, calls: s.calls });
    }
    sheet(report.stills.map(s => s.file), fractions.length, 'stills-sheet.jpg');
  }

  const videos = opt('--video', '');
  if (videos) for (const name of videos.split(',')) {
    const dir = join(out, `frames-${name}`); await rm(dir, { recursive: true, force: true }); await mkdir(dir, { recursive: true });
    const T = routes[name].duration, n = Math.round(T * fps) + 1;
    const samples = [];
    for (let i = 0; i < n; i++) {
      const t = Math.min(T, i / fps);
      const s = await page.evaluate(([nm, t]) => window.__sky.renderAt(nm, t), [name, t]);
      await page.screenshot({ path: join(dir, `${String(i).padStart(4, '0')}.jpg`), type: 'jpeg', quality: 88 });
      samples.push({ t, density: +s.density.toFixed(3), streaks: s.streaks });
      if (i % 60 === 0) console.log(`${name} ${i}/${n}`);
    }
    const mp4 = join(out, `${name}.mp4`);
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(fps), '-i', join(dir, '%04d.jpg'),
      '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', opt('--crf', '23'), '-preset', 'slow', '-movflags', '+faststart', mp4]);
    // Contact sheet: 8 evenly spaced frames.
    const picks = Array.from({ length: 8 }, (_, k) => Math.round(k * (n - 1) / 7));
    sheet(picks.map(k => `frames-${name}/${String(k).padStart(4, '0')}.jpg`), 4, `${name}-sheet.jpg`);
    report.videos.push({ route: name, file: `${name}.mp4`, frames: n, fps, durationSimSeconds: T, samples });
    if (!args.includes('--keep-frames')) await rm(dir, { recursive: true, force: true });
  }
} finally {
  await browser.close(); server.close();
  await writeFile(join(out, 'report.json'), JSON.stringify(report, null, 1) + '\n');
}
console.log(JSON.stringify({ out, errors: report.errors.slice(0, 5), stills: report.stills.length, videos: report.videos.map(v => v.file) }));

function sheet(files, cols, name) {
  const py = `
import sys
from PIL import Image
files=sys.argv[3:]; cols=int(sys.argv[2]); out=sys.argv[1]
ims=[Image.open(f) for f in files]
w=480; h=int(ims[0].height*w/ims[0].width); rows=(len(ims)+cols-1)//cols
S=Image.new('RGB',(w*cols,h*rows),(20,20,20))
for i,im in enumerate(ims): S.paste(im.resize((w,h),Image.LANCZOS),((i%cols)*w,(i//cols)*h))
S.save(out,quality=88)`;
  execFileSync('python3', ['-c', py, join(out, name), String(cols), ...files.map(f => join(out, f))]);
}
