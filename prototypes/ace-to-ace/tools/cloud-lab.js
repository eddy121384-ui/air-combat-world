import * as THREE from 'three';
import { createCloudField, CLOUD_PRESETS } from '../src/cloud/cloud-field.js';
import { createCloudDebugRenderer } from '../src/cloud/cloud-debug-renderer.js';
import { createCloudAnimeRenderer } from '../src/cloud/cloud-anime-renderer.js';
import { createCloudStableRenderer } from '../src/cloud/cloud-stable-renderer.js';
import { CLOUD_ANIMATION_PATHS,cloudAnimationPose } from './cloud-animation-paths.js';
import { makeAircraftMesh, outlineMaterial } from '../src/game/models.js';
import { SKY_VS, SKY_FS, SEA_VS, SEA_FS } from '../src/game/lookdev.js';

const $ = id => document.getElementById(id);
const requestedRenderer=new URLSearchParams(location.search).get('renderer');
if(['debug','anime','stable'].includes(requestedRenderer))$('renderer').value=requestedRenderer;
const canvas = $('gl'), scene = new THREE.Scene();
scene.background = new THREE.Color('#8eb3ce'); // Fallback behind the shared, read-only R2 sky.
const camera = new THREE.PerspectiveCamera(60, 1, 1, 24000);
const debug = createCloudDebugRenderer(canvas, scene, camera);
const anime = createCloudAnimeRenderer(debug.renderer,scene,camera);
const stable = createCloudStableRenderer(debug.renderer,scene,camera,anime.atlas);
const skyPainting=new THREE.TextureLoader().load('../assets/lookdev/sky-painting-r2.jpg');skyPainting.colorSpace=THREE.SRGBColorSpace;
const sunDirection=new THREE.Vector3(-0.64,0.3,-0.69).normalize();
const sky=new THREE.Mesh(new THREE.SphereGeometry(10000,32,16),new THREE.ShaderMaterial({vertexShader:SKY_VS,fragmentShader:SKY_FS,
  uniforms:{skyMap:{value:skyPainting},sunDir:{value:sunDirection},horizon:{value:new THREE.Vector3(0.76,0.82,0.88)}},side:THREE.BackSide,depthWrite:false}));
sky.renderOrder=-1000;scene.add(sky);
const sea = new THREE.Mesh(new THREE.PlaneGeometry(50000, 50000), new THREE.ShaderMaterial({vertexShader:SEA_VS,fragmentShader:SEA_FS,
  uniforms:{skyMap:{value:skyPainting},sunDir:{value:sunDirection},camPos:{value:camera.position},time:{value:0},fogColor:{value:new THREE.Vector3(0.76,0.82,0.88)},fogNear:{value:3500},fogFar:{value:18000}}}));
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

let field, debugField=null, mode = 'traverse', progress = 0, playing = false, time = 0, yaw = 0, pitch = 0, animation=true,inspectAircraft=false,densityView=false;
const isAnimationPath=id=>CLOUD_ANIMATION_PATHS.some(p=>p.id===id);
let last = performance.now(), stats = {}, diagnostic = {}, lastText = 0, explicitPose = false;
const keys = new Set(), forward = new THREE.Vector3(), right = new THREE.Vector3();
const planePosition = new THREE.Vector3(), target = new THREE.Vector3(), baseQuaternion = new THREE.Quaternion();
const offsetQuaternion = new THREE.Quaternion(), offsetEuler = new THREE.Euler(0, 0, 0, 'YXZ');

function rebuild() {
  const next = createCloudField({ kind: $('kind').value, seed: +$('seed').value,
    ...Object.fromEntries(['base', 'top', 'width', 'depth', 'cellSize', 'density'].map(k => [k, +$(k).value])),
    wind: { x: +$('windX').value, z: +$('windZ').value } });
  anime.setField(next);stable.setField(next);field = next; time = 0; explicitPose = false;
}
function setRoute(next) {
  if (next === 'free') baseQuaternion.copy(camera.quaternion);
  mode = next; explicitPose = false;inspectAircraft=isAnimationPath(next); yaw = pitch = 0; progress = 0; $('timeline').value = 0;
}
function setProgress(next) { progress = Math.max(0, Math.min(1, next)); $('timeline').value = progress; explicitPose = false; }
function placeCamera() {
  if (mode === 'free' || explicitPose) return;
  const mid = (field.params.base + field.params.top) / 2;
  const dx = field.params.wind.x * time, dz = field.params.wind.z * time;
  // Routes stay fixed in world space when wind is enabled, rather than riding the cloud.
  if(isAnimationPath(mode)){
    const pose=cloudAnimationPose(field,mode,progress);camera.position.fromArray(pose.eye);target.fromArray(pose.target);planePosition.copy(camera.position);
  }else if (mode === 'traverse' || mode === 'skim') {
    const length = field.params.depth + 2400;
    planePosition.set(0, mid, length * (0.5 - progress));
    if(mode==='skim')planePosition.x=field.params.width*0.40;
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
function resize() { debug.resize(innerWidth, innerHeight, +$('quality').value);const size=debug.renderer.getDrawingBufferSize(new THREE.Vector2());anime.resize(size.x,size.y);stable.resize(size.x,size.y); }
window.addEventListener('resize', resize); $('quality').onchange = resize;
$('kind').onchange = () => {
  for (const [k, v] of Object.entries(CLOUD_PRESETS[$('kind').value])) $(k).value = v;
  rebuild();
};
$('apply').onclick = () => { try { rebuild(); } catch (e) { $('readout').textContent = e.message; } };
document.querySelectorAll('[data-view]').forEach(button => { button.onclick = () => setRoute(button.dataset.view); });
for(const path of CLOUD_ANIMATION_PATHS)$('scenario').add(new Option(path.label,path.id));
function setScenario(id){
 const path=CLOUD_ANIMATION_PATHS.find(p=>p.id===id);if(!path)throw new RangeError('unknown scenario');
 if($('kind').value!==path.kind){$('kind').value=path.kind;$('kind').onchange();}
 $('scenario').value=id;setRoute(id);
}
$('scenario').onchange=()=>setScenario($('scenario').value);
$('scenarioPlay').onclick=()=>{setScenario($('scenario').value);playing=true;$('play').textContent='暫停路線';};
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
    progress = Math.min(1, progress + dt * (isAnimationPath(mode)?1/12:220 / (field.params.depth + 2400))); $('timeline').value = progress;
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
  aircraft.visible = mode === 'traverse'||mode==='skim'; aircraft.position.copy(planePosition); aircraft.rotation.set(0, 0, 0);
  if(inspectAircraft){aircraft.visible=true;aircraft.position.set(0,-12,-65).applyQuaternion(camera.quaternion).add(camera.position);aircraft.quaternion.copy(camera.quaternion);}
  debug.uniforms.enabled.value = $('clouds').checked ? 1 : 0;
  const sun = +$('sun').value * Math.PI / 180;
  const elevation=+$('sunHeight').value*Math.PI/180;
  sunDirection.set(Math.sin(sun)*Math.cos(elevation),Math.sin(elevation),-Math.cos(sun)*Math.cos(elevation));
  debug.uniforms.sun.value.copy(sunDirection);anime.uniforms.sun.value.copy(sunDirection);
  stable.uniforms.sun.value.copy(sunDirection);
  aircraft.children[0].material.uniforms.sunDir.value.copy(sunDirection);
  sky.position.copy(camera.position);sea.material.uniforms.time.value=time;
  grid.visible=$('guides').checked;beacons.forEach(b=>{b.visible=$('guides').checked;});
  const cpuBegin = performance.now();
  camera.getWorldDirection(forward);
  const end = camera.position.clone().addScaledVector(forward, 500);
  const sightline = field.integrateSightline(camera.position, end, { time, step: 20 });
  const density = field.sampleDensity(camera.position.x, camera.position.y, camera.position.z, time);
  const planeDensity = field.sampleDensity(aircraft.position.x, aircraft.position.y, aircraft.position.z, time);
  diagnostic = { density, planeDensity, transmittance500: sightline.transmittance, cpuQueryMs: performance.now() - cpuBegin };
  const rendererMode=$('renderer').value;
  if(rendererMode==='debug'){
    anime.clouds.visible=false;if(debugField!==field){debug.setField(field);debugField=field;}
    stats=debug.render(time);
  }else if(rendererMode==='stable'){
    anime.clouds.visible=false;stats=stable.render(time,{enabled:$('clouds').checked,wire:$('wire').checked,diagnostic:densityView});
  }else stats=anime.render(time,{enabled:$('clouds').checked,wire:$('wire').checked,fogEnabled:$('fog').checked});
  if (performance.now() - lastText > 125 || dt === 0) {
    const p = camera.position;
    $('readout').textContent = `路線 ${mode}  ${(progress * 100).toFixed(1)}%  t=${time.toFixed(1)} s\n`
      + `XYZ ${p.x.toFixed(0)}, ${p.y.toFixed(0)}, ${p.z.toFixed(0)} m\n`
      + `密度 eye ${density.toFixed(3)} / plane ${planeDensity.toFixed(3)}\nT500 ${sightline.transmittance.toFixed(3)}\n`
      + `CPU 查詢 ${diagnostic.cpuQueryMs.toFixed(3)} ms\n提交 ${stats.renderSubmitMs.toFixed(2)} ms / GPU ${stats.gpuMs?.toFixed(2) ?? 'N/A'} ms\n`
      + `${rendererMode} · ${stats.width}×${stats.height} · ${stats.calls} calls\n`
      + (stats.volume?`固定體積 ${stats.volume.grid.join('×')} · 32 probes\nCPU update ${stats.updateCpuMs.toFixed(2)} ms`:`${stats.layers?.triangles??stats.triangles} triangles · ${stats.fogCpuMs?.toFixed(2)??'—'} ms fog CPU`);
    lastText = performance.now();
  }
  return snapshot();
}
function snapshot() { return { ready: anime.ready&&stable.ready&&!!skyPainting.image, rendererMode:$('renderer').value, mode, progress, time, position: camera.position.toArray(),
  field:{kind:field.params.kind,seed:field.params.seed,base:field.params.base,top:field.params.top},
  planePosition: aircraft.position.toArray(), direction: camera.getWorldDirection(new THREE.Vector3()).toArray(),
  ...diagnostic, ...stats }; }
rebuild(); resize(); frame();
// Explicit inspection API for reproducible real-browser tests. Never imported by the game.
window.__cloudLab = { get field() { return field; }, get camera(){return camera;}, snapshot, frame, setRoute, setProgress,
  setPose(position, lookAt,{aircraft:showAircraft=false}={}) { mode = 'inspect'; explicitPose = true;inspectAircraft=showAircraft; camera.position.fromArray(position); camera.lookAt(...lookAt); },
  rebuild, setTime(value) { time = value; },
  setRenderer(value){$('renderer').value=value;return frame();},
  setAnimation(value){animation=value;},
  setScenario,setDensityView(value){densityView=value;},
};
function animate(now) { const dt = Math.min(0.05, (now - last) / 1000); last = now;if(animation)frame(dt);requestAnimationFrame(animate); }
requestAnimationFrame(animate);
