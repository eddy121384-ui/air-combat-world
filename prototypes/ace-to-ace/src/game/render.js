// Three.js presentation layer: reads sim state, never writes it.
import * as THREE from 'three';
import { makeAircraftMesh, outlineMaterial } from './models.js';
import { makeRng } from '../sim/math.js';

const SKY_HORIZON = [0.82, 0.91, 0.97];
const FOG_HEX = 0xd1e8f7;
const SUN_DIR = new THREE.Vector3(-0.45, 0.62, -0.64).normalize();
const v3 = (a) => new THREE.Vector3(a.x, a.y, a.z);

// ------------------------------------------------------------------ shaders
const SKY_VS = `varying vec3 vDir; void main(){ vDir = position; vec4 p = projectionMatrix * modelViewMatrix * vec4(position,1.0); gl_Position = p.xyww; }`;
const SKY_FS = `
  varying vec3 vDir; uniform vec3 sunDir; uniform vec3 horizon;
  void main(){
    vec3 d = normalize(vDir);
    float h = max(d.y, 0.0);
    vec3 zenith = vec3(0.17, 0.43, 0.82);
    vec3 col = mix(horizon, zenith, pow(smoothstep(0.0, 0.75, h), 0.65));
    // soft anime band just above the horizon
    col = mix(col, vec3(0.93, 0.96, 1.0), (1.0 - smoothstep(0.0, 0.06, h)) * 0.5);
    float s = dot(d, sunDir);
    col += vec3(1.0, 0.94, 0.78) * (smoothstep(0.9993, 0.9996, s) + pow(max(s, 0.0), 48.0) * 0.28);
    gl_FragColor = vec4(col, 1.0);
  }`;
const SEA_VS = `varying vec3 vWorld; void main(){ vec4 w = modelMatrix * vec4(position,1.0); vWorld = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`;
const SEA_FS = `
  varying vec3 vWorld; uniform vec3 camPos; uniform float time; uniform vec3 sunDir; uniform vec3 fogColor; uniform float fogNear; uniform float fogFar;
  float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float noise(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f*f*(3.0-2.0*f);
    return mix(mix(hash(i), hash(i+vec2(1.0,0.0)), u.x), mix(hash(i+vec2(0.0,1.0)), hash(i+vec2(1.0,1.0)), u.x), u.y); }
  void main(){
    vec2 p = vWorld.xz;
    float d = length(vWorld - camPos);
    float n = noise(p * 0.0021 + time * 0.01) * 0.6 + noise(p * 0.0073 - time * 0.02) * 0.4;
    vec3 deep = vec3(0.07, 0.33, 0.60);
    vec3 light = vec3(0.12, 0.43, 0.70);
    vec3 col = mix(deep, light, smoothstep(0.54, 0.58, n));
    // toon wave crests near the camera (speed reference when low)
    float near = 1.0 - smoothstep(700.0, 2600.0, d);
    float w = noise(p * 0.035 + vec2(time * 0.25, time * 0.05));
    col = mix(col, vec3(0.80, 0.93, 1.0), smoothstep(0.80, 0.83, w) * near * 0.75);
    float w2 = noise(p * 0.009 + vec2(-time * 0.04, time * 0.03));
    col = mix(col, vec3(0.30, 0.62, 0.85), smoothstep(0.74, 0.76, w2) * (1.0 - smoothstep(2000.0, 9000.0, d)) * 0.6);
    vec3 V = normalize(camPos - vWorld);
    vec3 H = normalize(V + sunDir);
    float spec = pow(max(H.y, 0.0), 260.0) * (0.4 + n);
    col += step(0.35, spec) * vec3(1.0, 0.96, 0.85) * 0.55;
    float fres = pow(1.0 - max(V.y, 0.0), 5.0);
    col = mix(col, vec3(0.55, 0.76, 0.90), fres * 0.6);
    col = mix(col, fogColor, smoothstep(fogNear, fogFar, d));
    gl_FragColor = vec4(col, 1.0);
  }`;
const CLOUD_VS = `
  varying vec3 vN; varying vec3 vWorld;
  void main(){
    vec4 p = vec4(position, 1.0);
    vec3 n = normal;
    #ifdef USE_INSTANCING
      p = instanceMatrix * p; n = mat3(instanceMatrix) * n;
    #endif
    vec4 w = modelMatrix * p; vWorld = w.xyz; vN = normalize(mat3(modelMatrix) * n);
    gl_Position = projectionMatrix * viewMatrix * w;
  }`;
const CLOUD_FS = `
  varying vec3 vN; varying vec3 vWorld; uniform vec3 sunDir; uniform vec3 camPos; uniform vec3 fogColor; uniform float fogNear; uniform float fogFar;
  void main(){
    float d = length(vWorld - camPos);
    float r = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453);
    if (r > smoothstep(30.0, 240.0, d)) discard; // dissolve when flying through
    float l = dot(normalize(vN), sunDir);
    vec3 col = l > 0.2 ? vec3(1.0) : l > -0.25 ? vec3(0.87, 0.91, 0.98) : vec3(0.70, 0.77, 0.91);
    float rim = pow(1.0 - abs(dot(normalize(vN), normalize(camPos - vWorld))), 3.0);
    col = mix(col, vec3(1.0), rim * 0.25);
    col = mix(col, fogColor, smoothstep(fogNear, fogFar, d) * 0.9);
    gl_FragColor = vec4(col, 1.0);
  }`;
const RIBBON_VS = `
  attribute float aAlpha; attribute float aSide; varying float vA; varying float vS;
  void main(){ vA = aAlpha; vS = aSide; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const RIBBON_FS = `
  uniform vec3 color; varying float vA; varying float vS;
  void main(){ float e = 1.0 - vS * vS; gl_FragColor = vec4(color, vA * (0.35 + 0.65 * e)); }`;
const FLAME_FS = `
  uniform vec3 color; uniform float t; varying vec2 vUv;
  void main(){ float a = (1.0 - vUv.y) * (0.75 + 0.25 * sin(t * 60.0 + vUv.y * 20.0)); gl_FragColor = vec4(color * a, a); }`;
const FLAME_VS = `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;

function glowTexture(inner = 'rgba(255,255,255,1)', outer = 'rgba(255,200,120,0)') {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grd.addColorStop(0, inner); grd.addColorStop(0.35, 'rgba(255,220,150,0.8)'); grd.addColorStop(1, outer);
  g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// ------------------------------------------------------------------ ribbon trail
class Ribbon {
  constructor(scene, max, color, opacity = 1) {
    this.max = max;
    this.pts = []; // {p: Vector3, t, w}
    const g = new THREE.BufferGeometry();
    this.posArr = new Float32Array(max * 2 * 3);
    this.alphaArr = new Float32Array(max * 2);
    const side = new Float32Array(max * 2);
    for (let i = 0; i < max; i++) { side[i * 2] = -1; side[i * 2 + 1] = 1; }
    const idx = [];
    for (let i = 0; i < max - 1; i++) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    g.setIndex(idx);
    g.setAttribute('position', new THREE.BufferAttribute(this.posArr, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('aAlpha', new THREE.BufferAttribute(this.alphaArr, 1).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('aSide', new THREE.BufferAttribute(side, 1));
    this.mat = new THREE.ShaderMaterial({
      uniforms: { color: { value: new THREE.Vector3(...color) } }, vertexShader: RIBBON_VS, fragmentShader: RIBBON_FS,
      transparent: true, depthWrite: false, side: THREE.DoubleSide,
    });
    this.opacity = opacity;
    this.mesh = new THREE.Mesh(g, this.mat);
    this.mesh.frustumCulled = false;
    this.geo = g;
    scene.add(this.mesh);
    this.life = 4; this.grow = 0; this.minStep = 6;
  }
  push(p, t, w) {
    const last = this.pts[this.pts.length - 1];
    if (last && last.p.distanceToSquared(p) < this.minStep * this.minStep) { last.p.copy(p); last.t = t; return; }
    this.pts.push({ p: p.clone(), t, w });
    if (this.pts.length > this.max) this.pts.shift();
  }
  breakTrail() { this.pts = []; }
  update(cam, now) {
    while (this.pts.length && now - this.pts[0].t > this.life) this.pts.shift();
    const n = this.pts.length;
    const tmp = new THREE.Vector3(), tan = new THREE.Vector3(), side = new THREE.Vector3();
    for (let i = 0; i < this.max; i++) {
      if (i >= n) { this.alphaArr[i * 2] = this.alphaArr[i * 2 + 1] = 0; const q = n ? this.pts[n - 1].p : cam.position; for (let k = 0; k < 2; k++) { this.posArr[(i * 2 + k) * 3] = q.x; this.posArr[(i * 2 + k) * 3 + 1] = q.y; this.posArr[(i * 2 + k) * 3 + 2] = q.z; } continue; }
      const pt = this.pts[i];
      const a = this.pts[Math.max(0, i - 1)].p, b = this.pts[Math.min(n - 1, i + 1)].p;
      tan.subVectors(b, a); if (tan.lengthSq() < 1e-6) tan.set(0, 0, 1);
      tmp.subVectors(cam.position, pt.p);
      side.crossVectors(tan, tmp).normalize();
      const age = now - pt.t;
      const w = (pt.w + this.grow * age) * 0.5;
      const k = 1 - age / this.life;
      const fadeIn = Math.min(1, (n - 1 - i) / 2 + 0.2);
      const alpha = Math.max(0, k * k) * this.opacity * fadeIn;
      for (let s = 0; s < 2; s++) {
        const sg = s === 0 ? -w : w;
        this.posArr[(i * 2 + s) * 3] = pt.p.x + side.x * sg;
        this.posArr[(i * 2 + s) * 3 + 1] = pt.p.y + side.y * sg;
        this.posArr[(i * 2 + s) * 3 + 2] = pt.p.z + side.z * sg;
        this.alphaArr[i * 2 + s] = alpha;
      }
    }
    this.geo.attributes.position.needsUpdate = true;
    this.geo.attributes.aAlpha.needsUpdate = true;
  }
}

// ------------------------------------------------------------------ renderer
export class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
    this.maxDpr = Math.min(window.devicePixelRatio || 1, 2);
    this.dpr = this.maxDpr;
    this.renderer.setPixelRatio(this.dpr);
    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.Fog(FOG_HEX, 4000, 32000);
    this.camera = new THREE.PerspectiveCamera(62, 1, 2, 80000);
    this.outline = outlineMaterial(0x16202c, 1.7);
    this.clock = 0;

    // lights (toon ramp does the stylisation)
    this.scene.add(new THREE.HemisphereLight(0xdfefff, 0x5d7d99, 1.25));
    const sun = new THREE.DirectionalLight(0xfff4e0, 2.4);
    sun.position.copy(SUN_DIR).multiplyScalar(1000);
    this.scene.add(sun);

    // sky
    this.sky = new THREE.Mesh(new THREE.SphereGeometry(60000, 32, 16), new THREE.ShaderMaterial({
      uniforms: { sunDir: { value: SUN_DIR }, horizon: { value: new THREE.Vector3(...SKY_HORIZON) } },
      vertexShader: SKY_VS, fragmentShader: SKY_FS, side: THREE.BackSide, depthWrite: false,
    }));
    this.sky.renderOrder = -10;
    this.scene.add(this.sky);

    // sea
    this.seaMat = new THREE.ShaderMaterial({
      uniforms: {
        camPos: { value: new THREE.Vector3() }, time: { value: 0 }, sunDir: { value: SUN_DIR },
        fogColor: { value: new THREE.Vector3(...SKY_HORIZON) }, fogNear: { value: 3000 }, fogFar: { value: 45000 },
      }, vertexShader: SEA_VS, fragmentShader: SEA_FS,
    });
    this.sea = new THREE.Mesh(new THREE.PlaneGeometry(140000, 140000, 1, 1), this.seaMat);
    this.sea.rotation.x = -Math.PI / 2;
    this.scene.add(this.sea);

    this.buildClouds();

    // pools
    this.planes = new Map();
    this.missileMeshes = new Map();
    this.missileTrails = [];
    this.flareTex = glowTexture('rgba(255,255,240,1)', 'rgba(255,170,90,0)');
    this.flashTex = glowTexture('rgba(255,255,255,1)', 'rgba(255,200,120,0)');
    this.bulletGeo = new THREE.BufferGeometry();
    this.bulletPos = new Float32Array(160 * 2 * 3);
    this.bulletGeo.setAttribute('position', new THREE.BufferAttribute(this.bulletPos, 3).setUsage(THREE.DynamicDrawUsage));
    this.bullets = new THREE.LineSegments(this.bulletGeo, new THREE.LineBasicMaterial({ color: 0xffe08a, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false }));
    this.bullets.frustumCulled = false;
    this.scene.add(this.bullets);
    this.flarePoints = new THREE.Points(new THREE.BufferGeometry(), new THREE.PointsMaterial({ size: 26, map: this.flareTex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, color: 0xffffff }));
    this.flarePos = new Float32Array(64 * 3);
    this.flarePoints.geometry.setAttribute('position', new THREE.BufferAttribute(this.flarePos, 3).setUsage(THREE.DynamicDrawUsage));
    this.flarePoints.frustumCulled = false;
    this.scene.add(this.flarePoints);
    this.flareTrails = [];
    this.effects = [];
    this.wrecks = [];
    this.camState = null;
    this.shake = 0;
    window.addEventListener('resize', () => this.resize());
    this.resize();
  }

  buildClouds() {
    const rng = makeRng(20261016);
    const g2 = new THREE.IcosahedronGeometry(1, 1); // already non-indexed => flat facets
    g2.computeVertexNormals();
    this.cloudMat = new THREE.ShaderMaterial({
      uniforms: { sunDir: { value: SUN_DIR }, camPos: { value: new THREE.Vector3() }, fogColor: { value: new THREE.Vector3(...SKY_HORIZON) }, fogNear: { value: 6000 }, fogFar: { value: 42000 } },
      vertexShader: CLOUD_VS, fragmentShader: CLOUD_FS,
    });
    const puffs = [];
    const add = (cx, cy, cz, size, count) => {
      for (let i = 0; i < count; i++) {
        const r = size * rng.range(0.45, 0.9);
        puffs.push([cx + rng.range(-1, 1) * size * 1.3, cy + rng.range(0, 0.6) * size * 0.6 + r * 0.2, cz + rng.range(-1, 1) * size * 1.1, r * 1.25, r * 0.85, r]);
      }
    };
    // mid-level cumulus field around the arena: altitude references for 3D flight
    for (let i = 0; i < 70; i++) {
      const a = rng() * Math.PI * 2, d = Math.sqrt(rng()) * 16000;
      add(Math.cos(a) * d, rng.range(1300, 3400), Math.sin(a) * d, rng.range(160, 420), 5 + Math.floor(rng() * 4));
    }
    // a few high towers and a distant ring of big clouds for the anime horizon
    for (let i = 0; i < 6; i++) {
      const a = rng() * Math.PI * 2, d = rng.range(6000, 14000);
      for (let k = 0; k < 5; k++) add(Math.cos(a) * d, 900 + k * 900, Math.sin(a) * d, 650 - k * 60, 4);
    }
    for (let i = 0; i < 26; i++) {
      const a = (i / 26) * Math.PI * 2 + rng() * 0.2, d = rng.range(24000, 30000);
      add(Math.cos(a) * d, rng.range(600, 1400), Math.sin(a) * d, rng.range(1400, 2400), 4);
    }
    const mesh = new THREE.InstancedMesh(g2, this.cloudMat, puffs.length);
    const m = new THREE.Matrix4();
    puffs.forEach((p, i) => { m.makeScale(p[3], p[4], p[5]); m.setPosition(p[0], p[1], p[2]); mesh.setMatrixAt(i, m); });
    mesh.instanceMatrix.needsUpdate = true;
    mesh.frustumCulled = false;
    this.scene.add(mesh);
    this.clouds = mesh;
  }

  resize() {
    const w = window.innerWidth, h = window.innerHeight;
    this.renderer.setSize(w, h, false);
    this.canvas.style.width = w + 'px'; this.canvas.style.height = h + 'px';
    this.camera.aspect = w / h;
    // derive vertical FOV from a target horizontal FOV so wide phones don't shrink the jet
    const hFov = 92 * Math.PI / 180;
    this.baseFov = Math.min(68, Math.max(44, 2 * Math.atan(Math.tan(hFov / 2) / this.camera.aspect) * 180 / Math.PI));
    this.camera.updateProjectionMatrix();
    this.outline.uniforms.resolution.value.set(w * this.dpr, h * this.dpr);
    this.outline.uniforms.thickness.value = 1.25 * this.dpr;
  }

  setDpr(d) {
    if (Math.abs(d - this.dpr) < 0.01) return;
    this.dpr = d; this.renderer.setPixelRatio(d); this.resize();
  }

  /** Remove everything that belongs to a match. */
  reset() {
    for (const p of this.planes.values()) { this.scene.remove(p.group); p.trails.forEach((t) => t.pair.forEach((r) => this.scene.remove(r.mesh))); }
    this.planes.clear();
    for (const m of this.missileMeshes.values()) this.scene.remove(m);
    this.missileMeshes.clear();
    for (const t of this.missileTrails) this.scene.remove(t.mesh);
    this.missileTrails = [];
    for (const t of this.flareTrails) this.scene.remove(t.mesh);
    this.flareTrails = [];
    for (const e of this.effects) this.scene.remove(e.obj);
    this.effects = [];
    for (const w of this.wrecks) { this.scene.remove(w.group); this.scene.remove(w.smoke.mesh); }
    this.wrecks = [];
    this.camState = null;
  }

  addAircraft(ac) {
    const group = makeAircraftMesh(ac.type.id, this.outline);
    this.scene.add(group);
    const flames = group.userData.nozzles.map((pos) => {
      const geo = new THREE.ConeGeometry(0.6, 5, 10, 1, true);
      geo.rotateX(Math.PI / 2); geo.translate(0, 0, 2.5);
      const mat = new THREE.ShaderMaterial({ uniforms: { color: { value: new THREE.Vector3(1.0, 0.62, 0.25) }, t: { value: 0 } }, vertexShader: FLAME_VS, fragmentShader: FLAME_FS, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
      const f = new THREE.Mesh(geo, mat);
      f.position.copy(pos).divideScalar(group.scale.x);
      group.children[0].add(f);
      return f;
    });
    // two alternating ribbons per wingtip so a new vapour burst never bridges to the old one
    const trails = group.userData.wingtips.map(() => {
      const pair = [0, 1].map(() => { const r = new Ribbon(this.scene, 70, [1, 1, 1], 0.55); r.life = 1.6; r.minStep = 8; return r; });
      return { pair, cur: 0, active: false };
    });
    this.planes.set(ac, { group, flames, trails, prev: null });
  }

  spawnExplosion(pos, big = false) {
    const p = v3(pos);
    const fire = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 1), new THREE.MeshBasicMaterial({ color: 0xffb340, transparent: true }));
    fire.position.copy(p);
    const core = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 1), new THREE.MeshBasicMaterial({ color: 0xfff6c8, transparent: true }));
    core.position.copy(p);
    this.scene.add(fire, core);
    this.effects.push({ obj: fire, t: 0, life: big ? 1.6 : 0.9, kind: 'fire', size: big ? 32 : 18 });
    this.effects.push({ obj: core, t: 0, life: big ? 0.9 : 0.5, kind: 'fire', size: big ? 20 : 10 });
    const rng = makeRng((pos.x * 7 + pos.z * 13) | 0);
    const n = big ? 9 : 4;
    for (let i = 0; i < n; i++) {
      const s = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 0), new THREE.MeshToonMaterial({ color: 0x5f6670, transparent: true }));
      s.position.copy(p).add(new THREE.Vector3(rng.range(-1, 1), rng.range(-0.5, 1), rng.range(-1, 1)).multiplyScalar(big ? 22 : 9));
      this.scene.add(s);
      this.effects.push({ obj: s, t: 0, life: big ? 4.5 : 2.5, kind: 'smoke', size: (big ? 28 : 12) * rng.range(0.7, 1.3), rise: rng.range(4, 12) });
    }
    const flash = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.flashTex, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
    flash.position.copy(p);
    this.scene.add(flash);
    this.effects.push({ obj: flash, t: 0, life: 0.35, kind: 'flash', size: big ? 170 : 90 });
  }

  spawnSpark(pos) {
    const flash = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.flashTex, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, color: 0xffd27a }));
    flash.position.copy(v3(pos));
    this.scene.add(flash);
    this.effects.push({ obj: flash, t: 0, life: 0.15, kind: 'flash', size: 18 });
  }

  spawnWreck(ac) {
    const pl = this.planes.get(ac);
    if (!pl) return;
    pl.group.visible = false;
    pl.trails.forEach((t) => t.pair.forEach((r) => r.breakTrail()));
    const g = pl.group.clone(true);
    g.traverse((o) => { if (o.material && o.material.isMeshToonMaterial) { o.material = o.material.clone(); o.material.color = new THREE.Color(0x5a5550); } });
    g.visible = true;
    this.scene.add(g);
    const smoke = new Ribbon(this.scene, 120, [0.22, 0.22, 0.25], 0.85);
    smoke.life = 6; smoke.grow = 9; smoke.minStep = 10;
    const fire = new Ribbon(this.scene, 30, [1.0, 0.55, 0.2], 0.9);
    fire.life = 0.5; fire.grow = 4; fire.minStep = 4;
    this.wrecks.push({ group: g, vel: v3(ac.vel).multiplyScalar(0.6), spin: new THREE.Vector3(1.3, 0.4, 2.2), smoke, fire, t: 0 });
  }

  /** Called every frame with the sim + interpolation alpha. */
  update(match, view, dt) {
    this.clock += dt;
    const now = this.clock;
    // aircraft
    for (const ac of match.aircraft) {
      const pl = this.planes.get(ac);
      if (!pl) continue;
      if (!ac.alive) continue;
      const g = pl.group;
      g.position.set(ac.pos.x, ac.pos.y, ac.pos.z);
      g.quaternion.set(ac.q.x, ac.q.y, ac.q.z, ac.q.w);
      const ab = ac.abCur, thr = ac.thrustCur;
      for (const f of pl.flames) {
        const len = 0.25 + thr * 0.5 + ab * 1.5;
        f.scale.set(0.8 + ab * 0.5, 0.8 + ab * 0.5, len);
        f.material.uniforms.t.value = now;
        f.material.uniforms.color.value.set(ab > 0.3 ? 1.0 : 0.75, ab > 0.3 ? 0.6 : 0.75, ab > 0.3 ? 0.25 : 1.0);
      }
      // wingtip vapour under high G
      const vapor = ac.nCur > 4.5;
      pl.group.updateMatrixWorld();
      pl.trails.forEach((t, i) => {
        if (vapor) {
          if (!t.active) { t.cur ^= 1; t.pair[t.cur].breakTrail(); t.active = true; }
          const wp = pl.group.userData.wingtips[i].clone().divideScalar(pl.group.scale.x).applyMatrix4(pl.group.matrixWorld);
          t.pair[t.cur].push(wp, now, 1.2 + (ac.nCur - 4.5) * 0.25);
        } else t.active = false;
        t.pair[0].update(this.camera, now); t.pair[1].update(this.camera, now);
      });
    }
    // missiles
    const alive = new Set();
    for (const m of match.missiles) {
      if (!m.alive) continue;
      alive.add(m.id);
      let mesh = this.missileMeshes.get(m.id);
      if (!mesh) {
        mesh = new THREE.Group();
        const body = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 3.2, 6).rotateX(Math.PI / 2), new THREE.MeshToonMaterial({ color: 0xf2f2f2 }));
        const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.flashTex, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, color: 0xffc070 }));
        glow.scale.setScalar(9); glow.position.z = 2.4;
        mesh.add(body, glow);
        this.scene.add(mesh);
        this.missileMeshes.set(m.id, mesh);
        const trail = new Ribbon(this.scene, 140, m.owner.side === 'blue' ? [0.97, 0.98, 1.0] : [0.98, 0.95, 0.93], 0.8);
        trail.life = 5.5; trail.grow = 2.2; trail.minStep = 7;
        trail.missileId = m.id;
        this.missileTrails.push(trail);
        mesh.userData.trail = trail;
      }
      mesh.position.set(m.pos.x, m.pos.y, m.pos.z);
      const dir = v3(m.vel).normalize();
      mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, -1), dir);
      mesh.children[1].visible = m.time < 7.5;
      mesh.userData.trail.push(mesh.position.clone().addScaledVector(dir, -2.5), now, 3.2);
    }
    for (const [id, mesh] of this.missileMeshes) {
      if (!alive.has(id)) { this.scene.remove(mesh); this.missileMeshes.delete(id); }
    }
    this.missileTrails = this.missileTrails.filter((t) => {
      t.update(this.camera, now);
      if (!alive.has(t.missileId) && t.pts.length === 0) { this.scene.remove(t.mesh); return false; }
      return true;
    });
    // bullets as short tracer streaks
    let bi = 0;
    for (const b of match.bullets) {
      if (!b.alive || bi >= 160) continue;
      const k = bi * 6;
      this.bulletPos[k] = b.pos.x; this.bulletPos[k + 1] = b.pos.y; this.bulletPos[k + 2] = b.pos.z;
      this.bulletPos[k + 3] = b.pos.x - b.vel.x * 0.03; this.bulletPos[k + 4] = b.pos.y - b.vel.y * 0.03; this.bulletPos[k + 5] = b.pos.z - b.vel.z * 0.03;
      bi++;
    }
    this.bulletGeo.setDrawRange(0, bi * 2);
    this.bulletGeo.attributes.position.needsUpdate = true;
    // flares
    let fi = 0;
    for (const f of match.flares) {
      if (!f.alive || fi >= 64) continue;
      this.flarePos[fi * 3] = f.pos.x; this.flarePos[fi * 3 + 1] = f.pos.y; this.flarePos[fi * 3 + 2] = f.pos.z;
      fi++;
      if (!f.trail) {
        f.trail = new Ribbon(this.scene, 40, [1.0, 0.98, 0.95], 0.6);
        f.trail.life = 2.0; f.trail.grow = 3; f.trail.minStep = 5;
        this.flareTrails.push(f.trail);
      }
      f.trail.push(v3(f.pos), now, 1.5);
    }
    this.flarePoints.geometry.setDrawRange(0, fi);
    this.flarePoints.geometry.attributes.position.needsUpdate = true;
    this.flareTrails = this.flareTrails.filter((t) => {
      t.update(this.camera, now);
      if (t.pts.length === 0) { this.scene.remove(t.mesh); return false; }
      return true;
    });
    // effects
    this.effects = this.effects.filter((e) => {
      e.t += dt;
      const k = e.t / e.life;
      if (k >= 1) { this.scene.remove(e.obj); return false; }
      if (e.kind === 'fire') { e.obj.scale.setScalar(e.size * (0.4 + Math.sqrt(k))); e.obj.material.opacity = 1 - k * k; }
      else if (e.kind === 'smoke') { e.obj.scale.setScalar(e.size * (0.5 + k * 1.4)); e.obj.position.y += e.rise * dt; e.obj.material.opacity = 0.85 * (1 - k); }
      else if (e.kind === 'flash') { e.obj.scale.setScalar(e.size * (0.6 + k)); e.obj.material.opacity = 1 - k; }
      return true;
    });
    // wrecks fall and burn
    for (const w of this.wrecks) {
      w.t += dt;
      w.vel.y -= 9.81 * dt;
      w.vel.multiplyScalar(1 - 0.15 * dt);
      w.group.position.addScaledVector(w.vel, dt);
      w.group.rotation.x += w.spin.x * dt; w.group.rotation.z += w.spin.z * dt;
      if (w.group.position.y > 2) {
        w.smoke.push(w.group.position.clone(), now, 6);
        w.fire.push(w.group.position.clone(), now, 5);
      } else if (!w.splashed) { w.splashed = true; w.group.visible = false; this.spawnExplosion(w.group.position, false); }
      w.smoke.update(this.camera, now); w.fire.update(this.camera, now);
    }
    this.seaMat.uniforms.time.value = now;
  }

  /**
   * Camera. view: { mode: 'chase'|'look'|'kill'|'spectate', ac, target, killPos }
   */
  updateCamera(view, dt) {
    const cam = this.camera;
    const ac = view.ac;
    if (!ac) return;
    const pos = v3(ac.pos);
    const q = new THREE.Quaternion(ac.q.x, ac.q.y, ac.q.z, ac.q.w);
    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(q);
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(q);
    let wantPos, wantLook, wantUp;
    const k = 1 - Math.exp(-dt * 7);
    if (view.mode === 'kill' && view.killPos) {
      const kp = v3(view.killPos);
      if (!this.killCam) {
        const off = new THREE.Vector3().subVectors(cam.position, kp).normalize().multiplyScalar(320);
        off.y = Math.abs(off.y) + 40;
        this.killCam = kp.clone().add(off);
      }
      wantPos = this.killCam; wantLook = kp; wantUp = new THREE.Vector3(0, 1, 0);
      cam.position.lerp(wantPos, 1 - Math.exp(-dt * 2));
      cam.up.lerp(wantUp, k).normalize();
      cam.lookAt(wantLook);
    } else {
      this.killCam = null;
      if (view.mode === 'look' && view.target && view.target.alive) {
        const tp = v3(view.target.pos);
        const toT = new THREE.Vector3().subVectors(tp, pos);
        const dir = toT.clone().normalize();
        wantPos = pos.clone().addScaledVector(dir, -45).addScaledVector(new THREE.Vector3(0, 1, 0), 12);
        wantLook = pos.clone().addScaledVector(dir, Math.min(toT.length() * 0.5, 600));
        wantUp = new THREE.Vector3(0, 1, 0).lerp(up, 0.3).normalize();
      } else {
        const speedK = Math.min(1, ac.speed / 350);
        wantPos = pos.clone().addScaledVector(fwd, -34 - speedK * 6).addScaledVector(up, 9);
        wantLook = pos.clone().addScaledVector(fwd, 70).addScaledVector(up, 3);
        wantUp = up;
      }
      if (!this.camState) { cam.position.copy(wantPos); cam.up.copy(wantUp); }
      this.camState = true;
      // Responsive chase camera: do not add a second slow feeling on top of real jet inertia.
      cam.position.lerp(wantPos, 1 - Math.exp(-dt * 16));
      cam.up.lerp(wantUp, 1 - Math.exp(-dt * 9)).normalize();
      cam.lookAt(wantLook);
    }
    if (this.shake > 0) {
      this.shake = Math.max(0, this.shake - dt * 2.5);
      const s = this.shake * 1.8;
      cam.position.x += (Math.random() - 0.5) * s; cam.position.y += (Math.random() - 0.5) * s;
    }
    const fovTarget = this.baseFov + (ac.abCur || 0) * 7 + Math.min(8, Math.max(0, (ac.speed - 250) * 0.05));
    cam.fov += (fovTarget - cam.fov) * k;
    cam.updateProjectionMatrix();
    this.sky.position.copy(cam.position);
    this.sea.position.set(cam.position.x, 0, cam.position.z);
    this.seaMat.uniforms.camPos.value.copy(cam.position);
    this.cloudMat.uniforms.camPos.value.copy(cam.position);
  }

  render() { this.renderer.render(this.scene, this.camera); }

  /** World -> screen (CSS px). Returns {x, y, behind}. */
  project(p) {
    const v = new THREE.Vector3(p.x, p.y, p.z).project(this.camera);
    const w = window.innerWidth, h = window.innerHeight;
    const camDir = new THREE.Vector3(); this.camera.getWorldDirection(camDir);
    const behind = new THREE.Vector3(p.x, p.y, p.z).sub(this.camera.position).dot(camDir) < 0;
    return { x: (v.x * 0.5 + 0.5) * w, y: (-v.y * 0.5 + 0.5) * h, behind };
  }
}
