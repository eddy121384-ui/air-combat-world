// Drive the look-dev preview in headless Chromium and write PNGs.
// usage: node tools/lookdev/preview/render.mjs [--shots a,b] [--light day,dusk] [--w 1600 --h 900 --ss 2] [--out dir]
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..', '..');
const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright-core')); } catch {
  ({ chromium } = require(process.env.PLAYWRIGHT_CORE || '/tmp/claude-0/pw/node_modules/playwright-core'));
}

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, arr) => (v.startsWith('--') ? [...a, [v.slice(2), arr[i + 1]]] : a), []));
const cfg = JSON.parse(fs.readFileSync(path.join(HERE, 'shots.json'), 'utf8'));
const shots = (args.shots || Object.keys(cfg.shots).join(',')).split(',');
const lights = (args.light || 'day').split(',');
const W = +(args.w || 1600), H = +(args.h || 900), SS = +(args.ss || 2);
const OUT = path.resolve(args.out || path.join(REPO, 'unreal/Saved/XinyiLook/preview/renders'));
fs.mkdirSync(OUT, { recursive: true });

// scene manifest from the look-dev build outputs
const look = path.join(REPO, 'unreal/Saved/XinyiLook');
const rep = JSON.parse(fs.readFileSync(path.join(look, 'look_tiles.report.json'), 'utf8'));
const hero = JSON.parse(fs.readFileSync(path.join(look, 'hero/taipei101.anchor.json'), 'utf8'));
const objects = [
  { url: '/unreal/Saved/XinyiLook/preview/xinyi_terrain_preview.glb', offset: [0, 0, 0], kind: 1 },
  ...(args.nobackdrop ? [] : [{ url: '/unreal/Saved/XinyiLook/backdrop/taipei_basin_backdrop.glb', offset: [0, 0, 0], kind: 2, castShadow: false }]),
  ...rep.tiles.map((t) => ({ url: `/unreal/Saved/XinyiLook/tiles/${t.path}`, offset: [t.origin_enu_m[0], t.origin_enu_m[1], 0], kind: 0 })),
];
if (!args.nohero) objects.push({ url: '/unreal/Saved/XinyiLook/hero/taipei101.glb', offset: [hero.anchor.centre_enu_m[0], hero.anchor.centre_enu_m[1], hero.anchor.ground_elev_m], kind: 0 });
objects.push({ url: '/unreal/Saved/XinyiLook/ground/xinyi_road_paint.glb', offset: [0, 0, 0], kind: 3, castShadow: false });
objects.push({ url: '/unreal/Saved/XinyiLook/ground/xinyi_tree.glb', offset: [0, 0, 0], kind: 4, instances: '/unreal/Saved/XinyiLook/ground/xinyi_trees.json' });
for (const t of ['shed', 'tank', 'solar', 'antenna', 'ac', 'cooling', 'machine', 'bmu', 'avlight']) {
  objects.push({ url: `/unreal/Saved/XinyiLook/rooftops/props_${t}.glb`, offset: [0, 0, 0], kind: 5,
    instances: '/unreal/Saved/XinyiLook/rooftops/rooftop_instances.json', instanceKey: t });
}
const manifest = { objects, groundTexture: '/unreal/Saved/XinyiLook/ground/xinyi_ground_2048.png' };

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.glb': 'model/gltf-binary', '.hlsl': 'text/plain', '.png': 'image/png' };
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split('?')[0]);
  if (u === '/manifest.json') { res.writeHead(200, { 'content-type': 'application/json' }); return res.end(JSON.stringify(manifest)); }
  const p = path.join(REPO, u);
  if (!p.startsWith(REPO) || !fs.existsSync(p)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': MIME[path.extname(p)] || 'application/octet-stream' });
  fs.createReadStream(p).pipe(res);
}).listen(0, '127.0.0.1');
await new Promise((r) => server.once('listening', r));
const port = server.address().port;

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium',
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage();
page.on('console', (m) => console.log('[page]', m.text()));
page.on('pageerror', (e) => console.log('[pageerror]', e.message));
await page.goto(`http://127.0.0.1:${port}/tools/lookdev/preview/viewer.html`);
await page.waitForFunction(() => window.__ready === true);
const t0 = Date.now();
const info = await page.evaluate(() => window.XL.init('/manifest.json'));
console.log('loaded', info, (Date.now() - t0) / 1000, 's');
for (const l of lights) for (const s of shots) {
  const t = Date.now();
  const url = await page.evaluate(([shot, light, w, h, ss]) => window.XL.render(shot, light, w, h, ss), [cfg.shots[s], cfg.light[l], W, H, SS]);
  const file = path.join(OUT, `${s}__${l}.png`);
  fs.writeFileSync(file, Buffer.from(url.split(',')[1], 'base64'));
  console.log('wrote', file, (Date.now() - t) / 1000, 's');
}
await browser.close();
server.close();
