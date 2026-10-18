import * as THREE from 'three';
import { createCloudField, CLOUD_PRESETS } from '../src/cloud/cloud-field.js';
import { createCloudDebugRenderer } from '../src/cloud/cloud-debug-renderer.js';
import { makeAircraftMesh, outlineMaterial } from '../src/game/models.js';

const $ = id => document.getElementById(id);
const canvas = $('gl'), scene = new THREE.Scene();
scene.background = new THREE.Color('#8eb3ce'); // Diagnostic sky, R2 art is never loaded or edited.
const camera = new THREE.PerspectiveCamera(60, 1, 1, 24000);
const debug = createCloudDebugRenderer(canvas, scene, camera);
const sea = new THREE.Mesh(new THREE.PlaneGeometry(50000, 50000), new THREE.MeshBasicMaterial({ color: '#416e85' }));
sea.rotation.x = -Math.PI / 2; scene.add(sea);
const grid = new THREE.GridHelper(24000, 48, '#9eb6b8', '#628fa2'); grid.position.y = 1; scene.add(grid);
const aircraft = makeAircraftMesh('F16V', outlineMaterial(), 1.35); scene.add(aircraft);
// Landmarks are opaque and share scene depth, so the cloud pass attenuates them correctly.
const beacons = [];
for (const [x, z, color] of [[0, -2100, '#e48155'], [0, 1700, '#73e8b2'], [-1700, 0, '#dfcd5c'], [1700, 0, '#cda0f3']]) {
  const group = new THREE.Group(); group.position.set(x, 0, z);
  const mast = new THREE.Mesh(new THREE.CylinderGeometry(5, 5, 3000, 8), new THREE.MeshBasicMaterial({ color: '#b0c1c8' }));
  mast.position.y = 1500;
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(60, 12, 8), new THREE.MeshBasicMaterial({ color }));
  beacon.position.y = 3000; group.add(mast, beacon); scene.add(group); beacons.push(group);
}

let field, mode = 'traverse', progress = 0, playing = false, time = 0, yaw = 0, pitch = 0;
let last = performance.now(), stats = {}, diagnostic = {}, lastText = 0, explicitPose = false;
const keys = new Set(), forward = new THREE.Vector3(), right = new THREE.Vector3();
const planePosition = new THREE.Vector3(), target = new THREE.Vector3(), baseQuaternion = new THREE.Quaternion();
const offsetQuaternion = new THREE.Quaternion(), offsetEuler = new THREE.Euler(0, 0, 0, 'YXZ');

function rebuild() {
  const next = createCloudField({ kind: $('kind').value, seed: +$('seed').value,
    ...Object.fromEntries(['base', 'top', 'width', 'depth', 'cellSize', 'density'].map(k => [k, +$(k).value])),
    wind: { x: +$('windX').value, z: +$('windZ').value } });
  debug.setField(next); field = next; time = 0; explicitPose = false;
}
function setRoute(next) {
  if (next === 'free') baseQuaternion.copy(camera.quaternion);
  mode = next; explicitPose = false; yaw = pitch = 0; progress = 0; $('timeline').value = 0;
}
function setProgress(next) { progress = Math.max(0, Math.min(1, next)); $('timeline').value = progress; explicitPose = false; }
function placeCamera() {
  if (mode === 'free' || explicitPose) return;
  const mid = (field.params.base + field.params.top) / 2;
  const dx = field.params.wind.x * time, dz = field.params.wind.z * time;
  // Routes stay fixed in world space when wind is enabled, rather than riding the cloud.
  if (mode === 'traverse') {
    const length = field.params.depth + 2400;
    planePosition.set(0, mid, length * (0.5 - progress));
    camera.position.copy(planePosition).add(new THREE.Vector3(0, 12, 60));
    target.copy(planePosition).add(new THREE.Vector3(0, 0, -800));
  } else {
    const a = progress * Math.PI * 2;
    const altitude = mode === 'above' ? field.params.top + 850 : mode === 'below' ? field.params.base - 750 : mid;
    const radius = mode === 'orbit' ? Math.max(field.params.width, field.params.depth) / 2 + 1800 : 2200;
    camera.position.set(Math.sin(a) * radius, altitude, Math.cos(a) * radius);
    target.set(dx, mid, dz); planePosition.copy(camera.position);
  }
  camera.up.set(0, 1, 0); camera.lookAt(target); baseQuaternion.copy(camera.quaternion);
  offsetQuaternion.setFromEuler(offsetEuler.set(pitch, yaw, 0));
  camera.quaternion.multiply(offsetQuaternion);
}
function resize() { debug.resize(innerWidth, innerHeight, +$('quality').value); }
window.addEventListener('resize', resize); $('quality').onchange = resize;
$('kind').onchange = () => {
  for (const [k, v] of Object.entries(CLOUD_PRESETS[$('kind').value])) $(k).value = v;
  rebuild();
};
$('apply').onclick = () => { try { rebuild(); } catch (e) { $('readout').textContent = e.message; } };
document.querySelectorAll('[data-view]').forEach(button => { button.onclick = () => setRoute(button.dataset.view); });
$('timeline').oninput = () => { playing = false; $('play').textContent = '播放路線'; setProgress(+$('timeline').value); };
$('play').onclick = () => { playing = !playing; $('play').textContent = playing ? '暫停路線' : '播放路線'; };
$('reset').onclick = () => { playing = false; time = 0; setRoute('traverse'); $('play').textContent = '播放路線'; };
window.addEventListener('keydown', e => {
  if (e.target.matches('input,select,textarea')) return;
  if (['KeyW', 'KeyS', 'KeyA', 'KeyD', 'KeyQ', 'KeyE', 'ShiftLeft', 'ShiftRight'].includes(e.code)) {
    e.preventDefault(); keys.add(e.code);
    if (mode !== 'free') { mode = 'free'; explicitPose = false; yaw = pitch = 0; baseQuaternion.copy(camera.quaternion); }
  }
});
window.addEventListener('keyup', e => keys.delete(e.code));
window.addEventListener('blur', () => keys.clear());
let pointer = null;
canvas.onpointerdown = e => { pointer = { x: e.clientX, y: e.clientY }; canvas.setPointerCapture(e.pointerId); };
canvas.onpointermove = e => {
  if (!pointer) return;
  yaw -= (e.clientX - pointer.x) * 0.004; pitch = Math.max(-1.45, Math.min(1.45, pitch - (e.clientY - pointer.y) * 0.004));
  pointer = { x: e.clientX, y: e.clientY };
};
canvas.onpointerup = canvas.onpointercancel = () => { pointer = null; };

function frame(dt = 0) {
  if ($('wind').checked) time += dt;
  if (playing && mode !== 'free') {
    progress = Math.min(1, progress + dt * 220 / (field.params.depth + 2400)); $('timeline').value = progress;
    if (progress === 1) { playing = false; $('play').textContent = '播放路線'; }
  }
  placeCamera();
  if (mode === 'free') {
    offsetQuaternion.setFromEuler(offsetEuler.set(pitch, yaw, 0)); camera.quaternion.copy(baseQuaternion).multiply(offsetQuaternion);
    camera.getWorldDirection(forward); right.set(1, 0, 0).applyQuaternion(camera.quaternion);
    const speed = keys.has('ShiftLeft') || keys.has('ShiftRight') ? 800 : 220;
    camera.position.addScaledVector(forward, ((keys.has('KeyW') ? 1 : 0) - (keys.has('KeyS') ? 1 : 0)) * speed * dt);
    camera.position.addScaledVector(right, ((keys.has('KeyD') ? 1 : 0) - (keys.has('KeyA') ? 1 : 0)) * speed * dt);
    camera.position.y += ((keys.has('KeyE') ? 1 : 0) - (keys.has('KeyQ') ? 1 : 0)) * speed * dt;
  }
  aircraft.visible = mode === 'traverse'; aircraft.position.copy(planePosition); aircraft.rotation.set(0, 0, 0);
  debug.uniforms.enabled.value = $('clouds').checked ? 1 : 0;
  const sun = +$('sun').value * Math.PI / 180;
  debug.uniforms.sun.value.set(Math.sin(sun), 0.6, -Math.cos(sun)).normalize();
  const cpuBegin = performance.now();
  camera.getWorldDirection(forward);
  const end = camera.position.clone().addScaledVector(forward, 500);
  const sightline = field.integrateSightline(camera.position, end, { time, step: 20 });
  const density = field.sampleDensity(camera.position.x, camera.position.y, camera.position.z, time);
  const planeDensity = field.sampleDensity(aircraft.position.x, aircraft.position.y, aircraft.position.z, time);
  diagnostic = { density, planeDensity, transmittance500: sightline.transmittance, cpuQueryMs: performance.now() - cpuBegin };
  stats = debug.render(time);
  if (performance.now() - lastText > 125 || dt === 0) {
    const p = camera.position;
    $('readout').textContent = `路線 ${mode}  ${(progress * 100).toFixed(1)}%  t=${time.toFixed(1)} s\n`
      + `XYZ ${p.x.toFixed(0)}, ${p.y.toFixed(0)}, ${p.z.toFixed(0)} m\n`
      + `密度 eye ${density.toFixed(3)} / plane ${planeDensity.toFixed(3)}\nT500 ${sightline.transmittance.toFixed(3)}\n`
      + `CPU 查詢 ${diagnostic.cpuQueryMs.toFixed(3)} ms\n提交 ${stats.renderSubmitMs.toFixed(2)} ms / GPU ${stats.gpuMs?.toFixed(2) ?? 'N/A'} ms\n`
      + `${stats.width}×${stats.height} · ${stats.calls} calls · cache ${(stats.cacheBytes / 1024).toFixed(0)} KiB`;
    lastText = performance.now();
  }
  return snapshot();
}
function snapshot() { return { ready: true, mode, progress, time, position: camera.position.toArray(),
  planePosition: aircraft.position.toArray(), direction: camera.getWorldDirection(new THREE.Vector3()).toArray(),
  ...diagnostic, ...stats }; }
rebuild(); resize(); frame();
// Explicit inspection API for reproducible real-browser tests. Never imported by the game.
window.__cloudLab = { get field() { return field; }, snapshot, frame, setRoute, setProgress,
  setPose(position, lookAt) { mode = 'inspect'; explicitPose = true; camera.position.fromArray(position); camera.lookAt(...lookAt); },
  rebuild, setTime(value) { time = value; },
};
function animate(now) { const dt = Math.min(0.05, (now - last) / 1000); last = now; frame(dt); requestAnimationFrame(animate); }
requestAnimationFrame(animate);
