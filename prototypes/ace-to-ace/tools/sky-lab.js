import * as THREE from 'three';
import { createCloudscape } from '../src/sky/cloudscape.js';
import { createOpusSky, filterFog } from '../src/sky/sky-renderer.js';
import { makeAircraftMesh, outlineMaterial } from '../src/game/models.js';
import { buildRoutes } from './sky-routes.js';

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const canvas = $('gl');
// Opaque drawing buffer: alpha-to-coverage fringes must never let the page show through.
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, 1, 3, 70000);

const skyTexture = new THREE.TextureLoader().load('../assets/lookdev/sky-painting-r2.jpg');
skyTexture.wrapS = THREE.RepeatWrapping; // display-space painting, exactly as R2 samples it
const t0 = performance.now();
const scape = createCloudscape({ seed: +(params.get('seed') ?? 1801) });
const buildMs = performance.now() - t0;
// Quality tiers. 'mobile' is the intended iPhone default; 'high' is the desktop reference.
const TIERS = {
  high: { dprCap: 2, options: {} },
  mobile: { dprCap: 2, options: { sunDepthSize: [1024, 512], lodPx: 3.0, maxStreaks: 160 } },
  low: { dprCap: 1.25, options: { sunDepthSize: [1024, 512], lodPx: 4.0, bump: 0, maxStreaks: 90 } },
};
const tierName = TIERS[params.get('quality')] ? params.get('quality') : (/iPhone|iPad|Android/.test(navigator.userAgent) ? 'mobile' : 'high');
const tier = TIERS[tierName];
const sky = createOpusSky({ renderer, scene, camera, skyTexture, cloudscape: scape, options: tier.options });
const aircraft = makeAircraftMesh('F16V', outlineMaterial(), 1.35);
scene.add(aircraft);
scene.fog = new THREE.FogExp2(0xdcdff2, 0);

const routes = buildRoutes(scape);
let route = params.get('route') ?? 'approach', time = 0, playing = false, free = false, windOn = false, clock = 0;
const routeBox = $('routes');
for (const [key, r] of Object.entries(routes)) {
  const b = document.createElement('button'); b.textContent = r.label; b.dataset.route = key;
  b.onclick = () => { setRoute(key); }; routeBox.appendChild(b);
}
function markRoute() { routeBox.querySelectorAll('button').forEach(b => b.classList.toggle('on', !free && b.dataset.route === route)); $('free').classList.toggle('on', free); }
function setRoute(key) { route = key; free = false; time = 0; $('timeline').value = 0; markRoute(); }
markRoute();
$('play').onclick = () => { if (free) setRoute(route); playing = !playing; $('play').textContent = playing ? '❚❚ 暫停' : '▶ 播放'; };
$('timeline').oninput = () => { playing = false; $('play').textContent = '▶ 播放'; free = false; time = +$('timeline').value * routes[route].duration; markRoute(); };
$('free').onclick = () => startFree();
$('wind').onchange = () => { windOn = $('wind').checked; };
$('title').onclick = () => $('panel').classList.toggle('min');
$('dpr').onchange = resize;

// ---- free flight: an arcade stand-in for the game's flight model (render lab only)
const flyer = { pos: new THREE.Vector3(), q: new THREE.Quaternion(), speed: 255 };
const keys = new Set(); let stick = null;
function startFree() {
  const s = routes[route].shot(time);
  flyer.pos.fromArray(s.plane.position);
  const m = new THREE.Matrix4().lookAt(new THREE.Vector3(), new THREE.Vector3(...s.plane.forward), new THREE.Vector3(...s.plane.up));
  flyer.q.setFromRotationMatrix(m); free = true; playing = false; markRoute();
}
addEventListener('keydown', e => { if (!e.target.matches('input,select')) { keys.add(e.code); if (!free && /Arrow|Key[WASD]/.test(e.code)) startFree(); } });
addEventListener('keyup', e => keys.delete(e.code));
const stickEl = $('stick');
stickEl.onpointerdown = e => { stick = { x0: e.clientX, y0: e.clientY, x: 0, y: 0 }; stickEl.setPointerCapture(e.pointerId); if (!free) startFree(); };
stickEl.onpointermove = e => { if (stick) { stick.x = Math.max(-1, Math.min(1, (e.clientX - stick.x0) / 80)); stick.y = Math.max(-1, Math.min(1, (e.clientY - stick.y0) / 80)); } };
stickEl.onpointerup = stickEl.onpointercancel = () => { stick = null; };
const tmpQ = new THREE.Quaternion(), axis = new THREE.Vector3();
function flyStep(dt) {
  const roll = (keys.has('ArrowLeft') || keys.has('KeyA') ? 1 : 0) - (keys.has('ArrowRight') || keys.has('KeyD') ? 1 : 0) - (stick?.x ?? 0);
  const pitch = (keys.has('ArrowDown') || keys.has('KeyS') ? 1 : 0) - (keys.has('ArrowUp') || keys.has('KeyW') ? 1 : 0) + (stick?.y ?? 0);
  flyer.speed = keys.has('ShiftLeft') || keys.has('ShiftRight') ? 420 : 255;
  tmpQ.setFromAxisAngle(axis.set(0, 0, 1), roll * 1.9 * dt); flyer.q.multiply(tmpQ);
  tmpQ.setFromAxisAngle(axis.set(1, 0, 0), pitch * 0.9 * dt); flyer.q.multiply(tmpQ);
  // Banked turn: heading follows the lift vector, so the horizon feels like an aircraft, not a drone.
  const rightY = new THREE.Vector3(1, 0, 0).applyQuaternion(flyer.q).y;
  tmpQ.setFromAxisAngle(axis.set(0, 1, 0), rightY * 0.6 * dt);
  flyer.q.premultiply(tmpQ).normalize();
  const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(flyer.q);
  flyer.pos.addScaledVector(fwd, flyer.speed * dt);
  flyer.pos.y = Math.max(60, Math.min(9000, flyer.pos.y));
  const upv = new THREE.Vector3(0, 1, 0).applyQuaternion(flyer.q);
  const right = new THREE.Vector3().crossVectors(fwd, upv);
  return { camera: flyer.pos.clone().addScaledVector(fwd, -38).addScaledVector(upv, 9).toArray(),
    target: flyer.pos.clone().addScaledVector(fwd, 70).addScaledVector(upv, 3).toArray(), up: upv.toArray(),
    plane: { position: flyer.pos.toArray(), forward: fwd.toArray(), up: upv.toArray() }, velocity: fwd.multiplyScalar(flyer.speed).toArray(), right };
}

function routeFog(name, t) {
  const at = tt => sky.fogSample(...routes[name].shot(Math.max(0, tt)).camera);
  const state = { ...at(t - 0.8) };
  for (let tt = t - 0.76; tt <= t + 1e-6; tt += 0.04) filterFog(state, at(tt), 0.04);
  return { sigma: state.sigma, sunVis: state.sunVis };
}
const windOffset = new THREE.Vector3(), velocity = new THREE.Vector3();
let lastShot = null, stats = {};
function render(dt = 0) {
  const shot = free ? flyStep(dt) : routes[route].shot(time);
  lastShot = shot;
  camera.position.fromArray(shot.camera); camera.up.fromArray(shot.up); camera.lookAt(...shot.target);
  aircraft.visible = $('plane').checked;
  aircraft.position.fromArray(shot.plane.position);
  const m = new THREE.Matrix4().lookAt(new THREE.Vector3(), new THREE.Vector3(...shot.plane.forward).negate(), new THREE.Vector3(...shot.plane.up));
  aircraft.quaternion.setFromRotationMatrix(m);
  aircraft.children[0].material.uniforms?.sunDir?.value.fromArray(scape.sun);
  if (windOn) windOffset.set(7, 0, 2.5).multiplyScalar(clock);
  velocity.fromArray(shot.velocity ?? [0, 0, 0]);
  const size = renderer.getDrawingBufferSize(new THREE.Vector2());
  // Route playback replays the same fog filter over the last 0.8 s of the path, so frame k of a
  // capture is identical however slowly the machine renders it.
  const fog = free ? null : routeFog(route, time);
  const st = sky.update({ time: clock, velocity, windOffset, viewportHeight: size.y, dt: dt || 1 / 60, fog });
  sky.streaks.visible = $('streaks').checked;
  // Aircraft inside cloud fog: three's exp2 fog on the airframe shader.
  scene.fog.density = Math.sqrt(st.fogSigma) * 0.06;
  const g0 = performance.now();
  renderer.render(scene, camera);
  stats = { ...st, submitMs: performance.now() - g0, calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, width: size.x, height: size.y };
  return snapshot();
}
function snapshot() {
  return { ready: !!skyTexture.image, tier: tierName, route, time, free, duration: routes[route].duration, camera: camera.position.toArray(),
    puffs: scape.count, levels: scape.levels, buildMs, ...stats };
}
function resize() {
  const v = $('dpr').value;
  const dpr = v === 'auto' ? Math.min(devicePixelRatio || 1, tier.dprCap) : +v;
  renderer.setPixelRatio(dpr); renderer.setSize(innerWidth, innerHeight, false);
  camera.aspect = innerWidth / innerHeight;
  const hFov = 92 * Math.PI / 180; // same horizontal-FOV rule as the game
  camera.fov = Math.min(68, Math.max(44, 2 * Math.atan(Math.tan(hFov / 2) / camera.aspect) * 180 / Math.PI));
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize); resize();

let last = performance.now(), frames = 0, fpsT = 0, fps = 0, animate = true;
function loop(now) {
  const dt = Math.min(0.05, (now - last) / 1000); last = now;
  if (animate) {
    clock += dt;
    if (playing && !free) { time += dt; if (time >= routes[route].duration) { time = routes[route].duration; playing = false; $('play').textContent = '▶ 播放'; } $('timeline').value = time / routes[route].duration; }
    render(dt);
    frames++; fpsT += dt; if (fpsT > 0.5) { fps = frames / fpsT; frames = 0; fpsT = 0; }
    $('readout').textContent = `${free ? 'free' : route} t=${time.toFixed(2)}s  ${fps.toFixed(0)} fps (此裝置)\n`
      + `puffs ${scape.count}  calls ${stats.calls}  ${stats.width}×${stats.height}\n`
      + `density ${stats.density.toFixed(2)}  streaks ${stats.streaks}  cpu ${stats.cpuMs.toFixed(2)} ms\n`
      + `XYZ ${camera.position.toArray().map(v => v.toFixed(0)).join(', ')}  build ${buildMs.toFixed(0)} ms`;
  }
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

// On-device benchmark (?bench): plays every route in real time and records rAF frame times.
// This is the number that matters for iPhone Safari; SwiftShader captures are visuals only.
if (params.has('bench')) runBench();
async function runBench() {
  $('panel').classList.add('min');
  const results = { userAgent: navigator.userAgent, tier: tierName, dpr: renderer.getPixelRatio(), routes: {} };
  const wait = ms => new Promise(r => setTimeout(r, ms));
  await new Promise(r => { const k = () => skyTexture.image ? r() : setTimeout(k, 50); k(); });
  for (const key of Object.keys(routes)) {
    setRoute(key); playing = true; await wait(600);           // warm-up, shader compile
    setRoute(key); playing = true;
    const dts = []; let prev = performance.now();
    await new Promise(r => { const tick = now => { dts.push(now - prev); prev = now; if (playing) requestAnimationFrame(tick); else r(); }; requestAnimationFrame(tick); });
    dts.sort((a, b) => a - b);
    const q = f => dts[Math.min(dts.length - 1, Math.floor(f * dts.length))];
    results.routes[key] = { frames: dts.length, medianMs: +q(0.5).toFixed(2), p95Ms: +q(0.95).toFixed(2), worstMs: +dts.at(-1).toFixed(2) };
  }
  const size = renderer.getDrawingBufferSize(new THREE.Vector2()); results.drawingBuffer = [size.x, size.y];
  const pre = document.createElement('pre');
  pre.style.cssText = 'position:absolute;inset:auto 8px 8px 8px;max-height:60%;overflow:auto;background:#000c;color:#dff;padding:10px;font:12px/1.4 ui-monospace,monospace;white-space:pre-wrap;user-select:text';
  pre.textContent = 'Opus Sky bench (copy this):\n' + JSON.stringify(results, null, 1);
  document.body.appendChild(pre);
  window.__benchResults = results;
}

// Deterministic capture API for tools/sky-capture.mjs. Never used by the game.
window.__sky = {
  routes: Object.fromEntries(Object.entries(routes).map(([k, r]) => [k, { label: r.label, duration: r.duration }])),
  setAnimate(v) { animate = v; },
  setUi(v) { $('panel').style.display = v ? '' : 'none'; },
  renderAt(name, t, { clockTime = t, wind = false } = {}) { route = name; free = false; time = t; clock = clockTime; windOn = wind; if (!wind) windOffset.set(0, 0, 0); return render(0); },
  snapshot, scape, sky, renderer, tier: tierName, extraHidden: [aircraft],
};
