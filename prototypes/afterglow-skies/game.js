import * as THREE from './vendor/three.module.min.js';
const boot = window.__aceBoot;
boot.stage('正在建立場景…');
// 頂點焊接（取代 BufferGeometryUtils.mergeVertices）
function mergeVertices(geo) {
  const pos = geo.attributes.position, idx = geo.index, map = new Map(), P = [], I = [];
  const remap = new Int32Array(pos.count);
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), y = pos.getY(i), z = pos.getZ(i);
    const key = Math.round(x * 1000) + '_' + Math.round(y * 1000) + '_' + Math.round(z * 1000);
    let j = map.get(key); if (j === undefined) { j = P.length / 3; P.push(x, y, z); map.set(key, j); }
    remap[i] = j;
  }
  const n = idx ? idx.count : pos.count;
  for (let k = 0; k < n; k++) I.push(remap[idx ? idx.getX(k) : k]);
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); g.setIndex(I); return g;
}

/* =========================================================
   基本工具
   ========================================================= */
const $ = id => document.getElementById(id);
const rand = (a, b) => a + Math.random() * (b - a);
const clamp = (x, a, b) => x < a ? a : x > b ? b : x;
const V3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const UP = V3(0, 1, 0), AX_X = V3(1, 0, 0), AX_Y = V3(0, 1, 0), AX_Z = V3(0, 0, 1);

function hash3(x, y, z) {
  let h = (Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(z, 1440662683)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177); h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}
function noise3(x, y, z) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = x - xi, yf = y - yi, zf = z - zi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf), w = zf * zf * (3 - 2 * zf);
  const L = (a, b, t) => a + (b - a) * t;
  return L(
    L(L(hash3(xi, yi, zi), hash3(xi + 1, yi, zi), u), L(hash3(xi, yi + 1, zi), hash3(xi + 1, yi + 1, zi), u), v),
    L(L(hash3(xi, yi, zi + 1), hash3(xi + 1, yi, zi + 1), u), L(hash3(xi, yi + 1, zi + 1), hash3(xi + 1, yi + 1, zi + 1), u), v), w);
}
function fbm3(x, y, z) { let s = 0, a = .5; for (let i = 0; i < 4; i++) { s += a * noise3(x, y, z); x = x * 2.03 + 1.3; y = y * 2.03 + 7.1; z = z * 2.03 + 3.7; a *= .5; } return s; }

const NOISE = /* glsl */`
float h21(vec2 p){ p=fract(p*vec2(123.34,456.21)); p+=dot(p,p+45.32); return fract(p.x*p.y); }
float n2(vec2 p){ vec2 i=floor(p), f=fract(p); vec2 u=f*f*(3.-2.*f);
  return mix(mix(h21(i),h21(i+vec2(1,0)),u.x), mix(h21(i+vec2(0,1)),h21(i+vec2(1,1)),u.x), u.y); }
float fbm2(vec2 p){ float s=0., a=.5; for(int i=0;i<5;i++){ s+=a*n2(p); p=mat2(1.6,1.2,-1.2,1.6)*p+vec2(3.1,1.7); a*=.5; } return s; }
float h31(vec3 p){ p=fract(p*0.3183099+.1); p*=17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
float n3(vec3 x){ vec3 i=floor(x), f=fract(x); f=f*f*(3.-2.*f);
  return mix(mix(mix(h31(i),h31(i+vec3(1,0,0)),f.x), mix(h31(i+vec3(0,1,0)),h31(i+vec3(1,1,0)),f.x),f.y),
             mix(mix(h31(i+vec3(0,0,1)),h31(i+vec3(1,0,1)),f.x), mix(h31(i+vec3(0,1,1)),h31(i+vec3(1,1,1)),f.x),f.y), f.z); }
float fbm3(vec3 p){ float s=0., a=.5; for(int i=0;i<4;i++){ s+=a*n3(p); p=p*2.02+vec3(1.7,9.2,3.1); a*=.5; } return s; }
`;

/* =========================================================
   Renderer / Scene
   ========================================================= */
const isTouchDevice = matchMedia('(pointer: coarse)').matches || /iPhone|iPad|Android/i.test(navigator.userAgent);
const safeMode = new URLSearchParams(location.search).has('safe');
if (safeMode) boot.stage('安全模式：準備低負載場景…');
let mobileQuality = 'eco';
let mobileAB = false;
const mobileStick = { x: 0, y: 0, active: false };
const canvas = $('gl');
let renderer;
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' }); }
catch(err) { boot.fail(err); throw err; }
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
const DPR = isTouchDevice ? (safeMode ? 0.65 : 0.8) : Math.min(window.devicePixelRatio || 1, 1.5);
renderer.setPixelRatio(DPR);
renderer.setSize(innerWidth, innerHeight, false);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(64, innerWidth / innerHeight, 2, 42000);

const C = h => new THREE.Color(h);
const SUN_DIR = V3(0.42, 0.28, 0.86).normalize();
const PAL = {
  zen: C('#1652c0'), mid: C('#4c98ea'), hor: C('#d2e7fb'), sunCol: C('#ffcf92'), fog: C('#bed9f4'),
  cLit: C('#fffaf0'), cShade: C('#b2c1ec'), cDeep: C('#7682c0'), cRim: C('#ffd6a0'), sky: C('#8fc0f5'),
  seaDeep: C('#0a4688'), seaShallow: C('#1a68b4'),
};
const FOG_N = 2600, FOG_F = 24000;
scene.fog = new THREE.Fog(PAL.fog, FOG_N, FOG_F);

const sunLight = new THREE.DirectionalLight(0xfff0d8, 3.1);
sunLight.position.copy(SUN_DIR).multiplyScalar(1000);
scene.add(sunLight);
scene.add(new THREE.HemisphereLight(0xc4ddff, 0x3d5c8a, 1.0));

/* =========================================================
   天空（漸層＋地平線手繪雲帶＋太陽）
   ========================================================= */
const skyMat = new THREE.ShaderMaterial({
  uniforms: {
    uZen: { value: PAL.zen }, uMid: { value: PAL.mid }, uHor: { value: PAL.hor }, uSunCol: { value: PAL.sunCol },
    uSun: { value: SUN_DIR }, uLit: { value: PAL.cLit }, uShade: { value: PAL.cShade }
  },
  vertexShader: `varying vec3 vDir; void main(){ vDir=position; vec4 p=projectionMatrix*modelViewMatrix*vec4(position,1.); gl_Position=p.xyww; }`,
  fragmentShader: NOISE + `
  varying vec3 vDir; uniform vec3 uZen,uMid,uHor,uSunCol,uSun,uLit,uShade;
  void main(){
    vec3 d=normalize(vDir); float y=d.y; float s=max(dot(d,uSun),0.);
    vec3 c=mix(uHor,uMid,smoothstep(0.0,0.22,y));
    c=mix(c,uZen,smoothstep(0.18,0.92,y));
    c=mix(c,uSunCol*1.05,pow(1.-clamp(abs(y),0.,1.),10.)*(0.22+0.55*pow(s,3.)));
    c+=uSunCol*(pow(s,6.)*0.32+pow(s,48.)*0.75);
    // 地平線遠方積雲帶（手繪感）
    vec2 az=normalize(d.xz+1e-5);
    float hb=fbm3(vec3(az*3.2,1.7));
    float h2=fbm3(vec3(az*11.,y*30.+3.));
    float top=0.012+0.085*smoothstep(0.38,0.8,hb)+(h2-0.5)*0.02;
    float m=smoothstep(top+0.002,top-0.002,y)*step(-0.03,y);
    float tone=smoothstep(-0.1,0.25,(y/max(top,0.01))-0.45+(h2-0.5)*0.9+dot(az,normalize(uSun.xz))*0.35);
    vec3 cc=mix(uShade,uLit,tone);
    cc+=uSunCol*pow(s,5.)*0.8*smoothstep(top-0.012,top,y);
    cc=mix(cc,uHor,0.42);
    c=mix(c,cc,m);
    c=mix(c,uHor,smoothstep(0.0,-0.08,y));
    c+=vec3(7.,5.6,4.2)*smoothstep(0.99955,0.99982,s)*(1.-m);
    gl_FragColor=vec4(c,1.);
  }`,
  side: THREE.BackSide, depthWrite: false, fog: false
});
const sky = new THREE.Mesh(new THREE.SphereGeometry(1000, 48, 24), skyMat);
sky.renderOrder = -10; sky.frustumCulled = false;
scene.add(sky);

/* =========================================================
   海面（卡通水面＋閃光）
   ========================================================= */
const oceanMat = new THREE.ShaderMaterial({
  uniforms: {
    uCam: { value: V3() }, uSun: { value: SUN_DIR }, uDeep: { value: PAL.seaDeep }, uShallow: { value: PAL.seaShallow },
    uFog: { value: PAL.fog }, uSunCol: { value: PAL.sunCol }, uTime: { value: 0 }, uFogN: { value: FOG_N * 0.6 }, uFogF: { value: FOG_F }
  },
  vertexShader: `varying vec3 vW; void main(){ vec4 w=modelMatrix*vec4(position,1.); vW=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }`,
  fragmentShader: NOISE + `
  varying vec3 vW; uniform vec3 uCam,uSun,uDeep,uShallow,uFog,uSunCol; uniform float uTime,uFogN,uFogF;
  void main(){
    vec2 p=vW.xz;
    float w1=fbm2(p*0.0035+vec2(uTime*0.03,uTime*0.02));
    float w2=fbm2(p*0.018-vec2(uTime*0.09,0.03*uTime));
    vec3 n=normalize(vec3((w1-0.5)*0.5+(w2-0.5)*0.35,1.,(w2-0.5)*0.4-(w1-0.5)*0.3));
    vec3 v=normalize(uCam-vW);
    float fres=pow(1.-max(v.y,0.),4.);
    vec3 col=mix(uDeep,uShallow,smoothstep(0.48,0.56,w1));
    col=mix(col,uFog*0.95,fres*0.65);
    vec3 r=reflect(-v,n);
    float sp=pow(max(dot(r,uSun),0.),90.);
    col+=uSunCol*step(0.3,sp)*3.0;
    col+=vec3(0.9,0.95,1.)*smoothstep(0.74,0.76,w2)*0.22;
    float d=length(uCam-vW);
    col=mix(col,uFog,smoothstep(uFogN,uFogF,d));
    gl_FragColor=vec4(col,1.);
  }`, fog: false
});
const ocean = new THREE.Mesh(new THREE.PlaneGeometry(90000, 90000).rotateX(-Math.PI / 2), oceanMat);
ocean.renderOrder = -5;
scene.add(ocean);

/* =========================================================
   卡通材質 / 外框描線
   ========================================================= */
const gradTex = new THREE.DataTexture(new Uint8Array([88, 88, 88, 255, 168, 168, 168, 255, 255, 255, 255, 255]), 3, 1);
gradTex.minFilter = gradTex.magFilter = THREE.NearestFilter; gradTex.needsUpdate = true;
const toon = (c, extra = {}) => new THREE.MeshToonMaterial({ color: c, gradientMap: gradTex, ...extra });
const outlineMat = new THREE.ShaderMaterial({
  uniforms: { uT: { value: 0.055 }, uC: { value: C('#18203a') } },
  vertexShader: `uniform float uT; void main(){ vec3 p=position+normal*uT; gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.); }`,
  fragmentShader: `uniform vec3 uC; void main(){ gl_FragColor=vec4(uC,1.); }`,
  side: THREE.BackSide
});
function outlineGeo(geo) {
  let g = new THREE.BufferGeometry();
  g.setAttribute('position', geo.attributes.position.clone());
  if (geo.index) g.setIndex(geo.index.clone());
  g = mergeVertices(g); g.computeVertexNormals(); return g;
}
function part(parent, geo, mat, pos, outline = true, rot) {
  const m = new THREE.Mesh(geo, mat);
  if (pos) m.position.set(pos[0], pos[1], pos[2]);
  if (rot) m.rotation.set(rot[0], rot[1], rot[2]);
  parent.add(m);
  if (outline) m.add(new THREE.Mesh(outlineGeo(geo), outlineMat));
  return m;
}
function flatPoly(pts, th) { // 平面多邊形 (x,z)
  const s = new THREE.Shape(); s.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) s.lineTo(pts[i][0], pts[i][1]);
  const g = new THREE.ExtrudeGeometry(s, { depth: th, bevelEnabled: false });
  g.rotateX(Math.PI / 2); g.translate(0, th / 2, 0); return g;
}
function vertPoly(pts, th) { // 垂直多邊形 (z,y)
  const s = new THREE.Shape(); s.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) s.lineTo(pts[i][0], pts[i][1]);
  const g = new THREE.ExtrudeGeometry(s, { depth: th, bevelEnabled: false });
  g.rotateY(-Math.PI / 2); g.translate(th / 2, 0, 0); return g;
}
const lathe = (pts, seg = 28) => { if (pts[0][1] > pts[pts.length - 1][1]) pts = [...pts].reverse(); const g = new THREE.LatheGeometry(pts.map(p => new THREE.Vector2(p[0], p[1])), seg); g.rotateX(Math.PI / 2); return g; };
const mirrorX = pts => pts.map(p => [-p[0], p[1]]);

function makeAB(r, len) {
  const grp = new THREE.Group(); grp.name = 'ab';
  const mk = (rr, ll, col, op) => {
    const g = new THREE.ConeGeometry(rr, ll, 18, 1, true); g.rotateX(-Math.PI / 2); g.translate(0, 0, -ll / 2);
    return new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, fog: false }));
  };
  grp.add(mk(r, len, new THREE.Color(2.4, 0.9, 0.35), 0.55));
  grp.add(mk(r * 0.62, len * 0.62, new THREE.Color(3.2, 2.4, 1.4), 0.8));
  const core = new THREE.Mesh(new THREE.CircleGeometry(r * 0.95, 18).rotateY(Math.PI), new THREE.MeshBasicMaterial({ color: new THREE.Color(4, 2.6, 1.3), fog: false }));
  grp.add(core);
  return grp;
}

/* =========================================================
   F-16 VIPER（玩家）
   ========================================================= */
function buildF16() {
  const g = new THREE.Group();
  const body = toon('#aab4c0'), dark = toon('#7f8a99'), accent = toon('#ff8a3d'), white = toon('#eef2f6'), metal = toon('#4d5460');
  const glass = new THREE.MeshPhongMaterial({ color: '#1a2a4a', specular: '#ffffff', shininess: 160, emissive: '#0a1630' });
  part(g, lathe([[0, 7.7], [0.2, 7.2], [0.42, 6.4], [0.62, 5.4], [0.76, 4.3], [0.86, 3.0], [0.9, 1.2], [0.9, -2.6], [0.84, -4.6], [0.68, -6.3], [0.56, -7.1]]).scale(1, 0.88, 1), body);
  part(g, lathe([[0, 7.75], [0.2, 7.2], [0.38, 6.55], [0.42, 6.35]]).scale(1.02, 0.9, 1), dark, [0, 0, 0.02]);
  const sp = new THREE.CapsuleGeometry(0.42, 6.4, 6, 14); sp.rotateX(Math.PI / 2); sp.scale(1.12, 0.72, 1);
  part(g, sp, body, [0, 0.5, -1.7]);
  const it = new THREE.CylinderGeometry(0.56, 0.62, 4.2, 18); it.rotateX(Math.PI / 2); it.scale(1.15, 0.72, 1);
  part(g, it, body, [0, -0.74, 1.0]);
  const mouth = new THREE.Mesh(new THREE.CircleGeometry(0.5, 18), new THREE.MeshBasicMaterial({ color: '#0d1220' }));
  mouth.position.set(0, -0.74, 3.12); mouth.scale.set(1.12, 0.66, 1); g.add(mouth);
  const cn = new THREE.SphereGeometry(0.5, 22, 14); cn.scale(1.05, 0.98, 3.1);
  part(g, cn, glass, [0, 0.74, 3.7]);
  const wR = [[0.6, 4.9], [1.05, 2.6], [4.7, -1.6], [4.7, -2.6], [0.6, -3.4]];
  part(g, flatPoly(wR, 0.16), body, [0, -0.05, 0]);
  part(g, flatPoly(mirrorX(wR), 0.16), body, [0, -0.05, 0]);
  const hs = [[0.45, -4.7], [3.3, -6.3], [3.3, -7.1], [0.45, -7.25]];
  part(g, flatPoly(hs, 0.12), dark, [0, -0.08, 0], true, [0, 0, -0.1]);
  part(g, flatPoly(mirrorX(hs), 0.12), dark, [0, -0.08, 0], true, [0, 0, 0.1]);
  part(g, vertPoly([[-2.9, 0.5], [-6.0, 4.6], [-6.95, 4.6], [-7.15, 0.5]], 0.14), body, [0, 0.35, 0]);
  part(g, vertPoly([[-5.25, 3.5], [-5.95, 4.45], [-6.9, 4.45], [-6.95, 3.5]], 0.18), accent, [0, 0.35, 0], false);
  part(g, vertPoly([[-4.6, 2.5], [-5.2, 3.25], [-6.98, 3.25], [-7.02, 2.5]], 0.17), dark, [0, 0.35, 0], false);
  const vf = vertPoly([[-3.6, 0], [-4.5, -0.75], [-5.2, -0.75], [-5.0, 0]], 0.08);
  part(g, vf, dark, [0.55, -0.58, 0], true, [0, 0, 0.45]);
  part(g, vf, dark, [-0.55, -0.58, 0], true, [0, 0, -0.45]);
  const nz = new THREE.CylinderGeometry(0.53, 0.46, 1.3, 18, 1, true); nz.rotateX(Math.PI / 2);
  part(g, nz, metal, [0, 0, -7.55], true).material.side = THREE.DoubleSide;
  const ab = makeAB(0.44, 5.5); ab.position.set(0, 0, -8.1); g.add(ab);
  const ms = new THREE.CylinderGeometry(0.075, 0.075, 2.9, 8); ms.rotateX(Math.PI / 2);
  for (const sx of [4.78, -4.78]) part(g, ms, white, [sx, 0, -1.9]);
  for (const sx of [3.0, -3.0]) { part(g, ms, white, [sx, -0.38, -0.6]); }
  const tank = new THREE.CapsuleGeometry(0.32, 3.2, 6, 12); tank.rotateX(Math.PI / 2);
  for (const sx of [2.1, -2.1]) part(g, tank, body, [sx, -0.62, -0.4]);
  g.scale.setScalar(1.0);
  return g;
}

/* =========================================================
   J-16（敵機）
   ========================================================= */
function buildJ16() {
  const g = new THREE.Group();
  const body = toon('#6d7887'), dark = toon('#525c6b'), radome = toon('#8a939e'), red = toon('#d84a3e'), metal = toon('#3d434d');
  const glass = new THREE.MeshPhongMaterial({ color: '#2a2238', specular: '#ffffff', shininess: 140, emissive: '#120a1a' });
  part(g, lathe([[0, 11.2], [0.24, 10.6], [0.55, 9.6], [0.8, 8.3], [0.95, 6.9], [1.02, 5.0], [1.0, 2.0], [0.88, -2], [0.6, -6.2], [0.38, -10], [0.18, -11.6]]).scale(1, 0.95, 1), body);
  part(g, lathe([[0, 11.25], [0.24, 10.6], [0.5, 9.75], [0.56, 9.5]]), radome, [0, 0, 0.02]);
  const lb = new THREE.SphereGeometry(1, 28, 16); lb.scale(2.15, 0.48, 6.6);
  part(g, lb, body, [0, 0.05, -1.4]);
  const nac = new THREE.CylinderGeometry(0.62, 0.66, 9.2, 18); nac.rotateX(Math.PI / 2);
  for (const sx of [1.28, -1.28]) part(g, nac, dark, [sx, -0.48, -3.4]);
  const intk = new THREE.BoxGeometry(1.15, 1.05, 3.0);
  for (const sx of [1.28, -1.28]) {
    part(g, intk, dark, [sx, -0.62, 2.1]);
    const mo = new THREE.Mesh(new THREE.PlaneGeometry(0.95, 0.85), new THREE.MeshBasicMaterial({ color: '#0b0e18' }));
    mo.position.set(sx, -0.62, 3.62); g.add(mo);
  }
  const cn = new THREE.SphereGeometry(0.55, 22, 14); cn.scale(1.0, 0.95, 3.6);
  part(g, cn, glass, [0, 0.9, 6.6]);
  const wR = [[0.9, 7.2], [1.9, 2.6], [7.4, -4.0], [7.4, -5.2], [2.2, -5.7], [0.9, -5.7]];
  part(g, flatPoly(wR, 0.2), body, [0, -0.05, 0]);
  part(g, flatPoly(mirrorX(wR), 0.2), body, [0, -0.05, 0]);
  const hs = [[1.8, -6.6], [4.7, -8.7], [4.7, -9.5], [1.8, -9.2]];
  part(g, flatPoly(hs, 0.14), dark, [0, -0.2, 0]);
  part(g, flatPoly(mirrorX(hs), 0.14), dark, [0, -0.2, 0]);
  const vt = vertPoly([[-3.8, 0.4], [-6.9, 4.1], [-7.9, 4.1], [-8.1, 0.4]], 0.16);
  const vtTip = vertPoly([[-6.45, 3.55], [-6.9, 4.1], [-7.9, 4.1], [-7.95, 3.55]], 0.2);
  for (const sx of [2.1, -2.1]) { part(g, vt, body, [sx, 0.1, 0]); part(g, vtTip, red, [sx, 0.1, 0], false); }
  const vf = vertPoly([[-4.5, 0], [-5.4, -0.9], [-6.2, -0.9], [-6.1, 0]], 0.1);
  for (const sx of [1.9, -1.9]) part(g, vf, dark, [sx, -0.9, 0]);
  const nz = new THREE.CylinderGeometry(0.6, 0.52, 1.4, 18, 1, true); nz.rotateX(Math.PI / 2);
  for (const sx of [1.28, -1.28]) {
    part(g, nz, metal, [sx, -0.48, -8.6], true).material.side = THREE.DoubleSide;
    const ab = makeAB(0.5, 6.0); ab.position.set(sx, -0.48, -9.2); g.add(ab);
  }
  const ms = new THREE.CylinderGeometry(0.1, 0.1, 3.8, 8); ms.rotateX(Math.PI / 2);
  for (const sx of [3.4, -3.4, 5.3, -5.3]) part(g, ms, toon('#e6e8ec'), [sx, -0.42, -2.6]);
  for (const sx of [7.45, -7.45]) part(g, ms, toon('#e6e8ec'), [sx, 0, -4.4]);
  return g;
}

function buildMissile() {
  const g = new THREE.Group(); const w = toon('#f2f4f7'), d = toon('#5b6370');
  const b = new THREE.CylinderGeometry(0.13, 0.13, 3.0, 10); b.rotateX(Math.PI / 2); part(g, b, w);
  const n = new THREE.ConeGeometry(0.13, 0.5, 10); n.rotateX(Math.PI / 2); part(g, n, d, [0, 0, 1.75]);
  const f = new THREE.BoxGeometry(0.8, 0.04, 0.4);
  part(g, f, d, [0, 0, -1.3], false); part(g, f, d, [0, 0, -1.3], false, [0, 0, Math.PI / 2]);
  g.scale.setScalar(1.6);
  return g;
}
const J16_TPL = buildJ16();
const MSL_TPL = buildMissile();
function collectAB(g) { const a = []; g.traverse(o => { if (o.name === 'ab') a.push(o); }); return a; }

/* =========================================================
   島嶼
   ========================================================= */
const islands = [];
function buildIsland(x, z, R, H) {
  const g = new THREE.CylinderGeometry(R * 0.12, R, H, 56, 10);
  const p = g.attributes.position; const cols = [];
  const cSand = C('#ead9ab'), cGrass = C('#63a95b'), cForest = C('#3f7f4a'), cRock = C('#8d8f86');
  for (let i = 0; i < p.count; i++) {
    let vx = p.getX(i), vy = p.getY(i), vz = p.getZ(i);
    const t = (vy + H / 2) / H;
    const n = fbm3(vx * 0.004 + x * 0.001, vy * 0.01, vz * 0.004);
    const k = 1 + (n - 0.5) * 0.55;
    vx *= k; vz *= k; vy = (vy + H / 2) * (0.75 + n * 0.5);
    p.setXYZ(i, vx, vy, vz);
    const c = t < 0.07 ? cSand : t < 0.45 ? cGrass : t < 0.8 ? cForest : cRock;
    cols.push(c.r, c.g, c.b);
  }
  g.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, toon('#ffffff', { vertexColors: true }));
  m.position.set(x, -4, z); scene.add(m);
  islands.push({ x, z, R: R * 1.1, H: H * 1.2 });
}
[[3200, 5200, 1500, 520], [-6800, 2400, 1100, 380], [9000, -3000, 900, 300], [-2500, 11000, 1700, 640], [-11000, -7000, 1300, 420], [12500, 9000, 1000, 360], [600, -14000, 800, 240]]
  .forEach(a => buildIsland(...a));
function groundH(x, z) {
  let h = 0;
  for (const s of islands) { const d = Math.hypot(x - s.x, z - s.z); if (d < s.R) h = Math.max(h, s.H * (1 - d / s.R)); }
  return h;
}

/* =========================================================
   雲：積雲（手繪 cel 陰影）＋ 雲邊柔絮 ＋ 雲海 ＋ 卷雲
   ========================================================= */
const cloudUniforms = {
  uSun: { value: SUN_DIR }, uCam: { value: V3() }, uLit: { value: PAL.cLit }, uShade: { value: PAL.cShade }, uDeep: { value: PAL.cDeep },
  uRim: { value: PAL.cRim }, uFogC: { value: PAL.fog }, uSky: { value: PAL.sky }, uFogN: { value: FOG_N }, uFogF: { value: FOG_F }, uTime: { value: 0 }
};
const cloudMat = new THREE.ShaderMaterial({
  uniforms: cloudUniforms,
  vertexShader: `attribute float aH; varying vec3 vN; varying vec3 vW; varying float vH;
    void main(){ vec4 w=modelMatrix*vec4(position,1.); vW=w.xyz; vN=normalize(mat3(modelMatrix)*normal); vH=aH; gl_Position=projectionMatrix*viewMatrix*w; }`,
  fragmentShader: NOISE + `
  uniform vec3 uSun,uCam,uLit,uShade,uDeep,uRim,uFogC,uSky; uniform float uFogN,uFogF;
  varying vec3 vN; varying vec3 vW; varying float vH;
  void main(){
    vec3 n=normalize(vN); vec3 v=normalize(uCam-vW);
    float br=fbm3(vW*0.011)-0.5; float br2=n3(vW*0.05)-0.5;
    float ndl=dot(n,uSun)+br*0.6+br2*0.2;
    float t1=smoothstep(0.13,0.2,ndl);
    float t2=smoothstep(-0.3,-0.23,ndl);
    vec3 col=mix(uDeep,uShade,t2); col=mix(col,uLit,t1);
    col+=uSky*0.16*clamp(n.y,0.,1.)*(1.-t1);
    col*=mix(vec3(0.80,0.84,0.97),vec3(1.),smoothstep(0.02,0.3,vH));
    float fr=pow(1.-clamp(dot(n,v),0.,1.),2.6);
    float back=pow(clamp(dot(-v,uSun),0.,1.),3.);
    col+=uRim*fr*(0.22+1.9*back)*smoothstep(-0.3,0.25,ndl+0.25);
    float d=length(uCam-vW);
    col=mix(col,uFogC,smoothstep(uFogN,uFogF,d)*0.94);
    gl_FragColor=vec4(col,1.);
  }`
});

const clouds = []; // 用於穿雲白霧＆太陽遮蔽
const fluffPos = [], fluffN = [], fluffSize = [], fluffSeed = [];
const START = V3(0, 2200, -9000);

function buildCloud(x, y, z, R, tower) {
  const P = [], N = [], H = [], I = []; let off = 0, maxY = 1;
  const puffs = [];
  const n = tower ? (isTouchDevice ? (safeMode ? 11 : 16) : 24) : Math.floor(rand(isTouchDevice ? 7 : 9, isTouchDevice ? (safeMode ? 9 : 11) : 15));
  for (let i = 0; i < n; i++) {
    let r, px, py, pz;
    if (tower) {
      const t = i / n;
      if (i > n - 6) { r = R * rand(0.42, 0.58); px = rand(-R * 1.4, R * 1.4); pz = rand(-R * 1.0, R * 1.0); py = R * 3.1 + rand(-R * 0.15, R * 0.25); }
      else { r = R * (0.62 - t * 0.22 + rand(-0.08, 0.08)); const sp = R * (0.62 - t * 0.35); px = rand(-sp, sp); pz = rand(-sp, sp); py = t * R * 3.0 + r * 0.25; }
    } else {
      const a = Math.random() * 6.283, d = Math.pow(Math.random(), 0.75);
      px = Math.cos(a) * d * R * 1.35; pz = Math.sin(a) * d * R * 0.95;
      r = R * (0.62 - d * 0.3) * rand(0.8, 1.15);
      py = r * 0.22 + (1 - d) * R * 0.55 * rand(0.6, 1.25);
    }
    puffs.push([px, py, pz, r]);
    let g = new THREE.IcosahedronGeometry(r, isTouchDevice ? (safeMode ? 2 : 3) : (r > 260 ? 7 : 5));
    g.deleteAttribute('normal'); g.deleteAttribute('uv'); g = mergeVertices(g);
    const p = g.attributes.position;
    for (let k = 0; k < p.count; k++) {
      const vx = p.getX(k), vy = p.getY(k), vz = p.getZ(k);
      const nx = vx / r, ny = vy / r, nz = vz / r;
      const s = 2.4 / R;
      const nn = fbm3((vx + px + x) * s, (vy + py) * s, (vz + pz + z) * s) - 0.5;
      const disp = 1 + nn * 0.6;
      let fx = px + nx * r * disp, fy = py + ny * r * disp, fz = pz + nz * r * disp;
      if (fy < 0) fy *= 0.06;
      p.setXYZ(k, fx, fy, fz); if (fy > maxY) maxY = fy;
    }
    g.computeVertexNormals();
    const pa = g.attributes.position.array, na = g.attributes.normal.array, ia = g.index.array;
    for (let k = 0; k < pa.length; k++) { P.push(pa[k]); N.push(na[k]); }
    for (let k = 0; k < ia.length; k++) I.push(ia[k] + off);
    off += p.count;
    g.dispose();
  }
  for (let k = 1; k < P.length; k += 3) H.push(P[k] / maxY);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(P, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(N, 3));
  geo.setAttribute('aH', new THREE.Float32BufferAttribute(H, 1));
  geo.setIndex(I);
  geo.computeBoundingSphere();
  const mesh = new THREE.Mesh(geo, cloudMat);
  mesh.position.set(x, y, z); scene.add(mesh);
  // 雲邊柔絮
  const nf = tower ? (isTouchDevice ? 19 : 34) : (isTouchDevice ? 11 : 14);
  for (let i = 0; i < nf; i++) {
    const pf = puffs[Math.floor(Math.random() * puffs.length)];
    const dir = V3(rand(-1, 1), rand(-0.25, 1), rand(-1, 1)).normalize();
    fluffPos.push(x + pf[0] + dir.x * pf[3] * 0.92, y + Math.max(pf[1] + dir.y * pf[3] * 0.92, pf[3] * 0.1), z + pf[2] + dir.z * pf[3] * 0.92);
    fluffN.push(dir.x, dir.y, dir.z); fluffSize.push(pf[3] * rand(0.9, 1.5)); fluffSeed.push(Math.random());
  }
  if (tower) clouds.push({ c: V3(x, y + R * 1.7, z), rx: R * 1.5, ry: R * 2.0, rz: R * 1.5 });
  else clouds.push({ c: V3(x, y + R * 0.32, z), rx: R * 1.5, ry: R * 0.62, rz: R * 1.25 });
}

function placeClouds() {
  boot.stage('正在建立雲層…');
  let placed = 0, guard = 0;
  const cloudCount = isTouchDevice ? (safeMode ? 12 : 28) : 50;
  while (placed < cloudCount && guard++ < 600) {
    const a = Math.random() * 6.283, d = Math.sqrt(Math.random()) * 17000;
    const x = Math.cos(a) * d, z = Math.sin(a) * d, R = rand(230, 540), y = rand(1100, 2700);
    if (Math.hypot(x - START.x, z - START.z) < 2600) continue;
    buildCloud(x, y, z, R, false); placed++;
  }
  const towers = [[5200, 7000], [-8200, 9500], [11000, -2500], [-12000, -4000], [1500, 15500], [-3500, -12500]];
  for (const [x, z] of (isTouchDevice ? towers.slice(0, safeMode ? 2 : 4) : towers)) buildCloud(x, 650, z, rand(760, 960), true);
}
placeClouds();
boot.stage('正在準備戰機與戰鬥場景…');

const fluffGeo = new THREE.BufferGeometry();
fluffGeo.setAttribute('position', new THREE.Float32BufferAttribute(fluffPos, 3));
fluffGeo.setAttribute('aN', new THREE.Float32BufferAttribute(fluffN, 3));
fluffGeo.setAttribute('aSize', new THREE.Float32BufferAttribute(fluffSize, 1));
fluffGeo.setAttribute('aSeed', new THREE.Float32BufferAttribute(fluffSeed, 1));
const fluffMat = new THREE.ShaderMaterial({
  uniforms: { ...cloudUniforms, uScale: { value: 500 } },
  vertexShader: `attribute vec3 aN; attribute float aSize; attribute float aSeed; uniform float uScale,uFogN,uFogF;
    varying vec3 vN; varying float vSeed; varying float vFog; varying float vNear;
    void main(){ vec4 mv=modelViewMatrix*vec4(position,1.); gl_Position=projectionMatrix*mv; float d=-mv.z;
      gl_PointSize=clamp(aSize*uScale/max(d,1.),1.,1600.); vN=aN; vSeed=aSeed; vFog=smoothstep(uFogN,uFogF,d); vNear=smoothstep(300.,1100.,d); }`,
  fragmentShader: `uniform vec3 uSun,uLit,uShade,uDeep,uRim,uFogC; varying vec3 vN; varying float vSeed; varying float vFog; varying float vNear;
    void main(){ vec2 p=gl_PointCoord*2.-1.; p.y=-p.y; float r=length(p); float ang=atan(p.y,p.x);
      float edge=0.72+0.13*sin(ang*4.+vSeed*20.)+0.08*sin(ang*9.+vSeed*7.);
      float a=smoothstep(edge,edge-0.4,r)*0.9*vNear; if(a<0.02) discard;
      float ndl=dot(normalize(vN),uSun)+p.y*0.25+(vSeed-0.5)*0.2;
      vec3 col=mix(uShade,uLit,smoothstep(0.0,0.1,ndl)); col=mix(uDeep,col,smoothstep(-0.45,-0.35,ndl));
      col+=uRim*smoothstep(0.4,0.75,r)*0.35;
      col=mix(col,uFogC,vFog*0.94); gl_FragColor=vec4(col,a); }`,
  transparent: true, depthWrite: false
});
const fluff = new THREE.Points(fluffGeo, fluffMat); fluff.renderOrder = 2; fluff.frustumCulled = false;
scene.add(fluff);

// 雲海（低空層積雲）
const CLOUDSEA_Y = 430;
const seaCloudMat = new THREE.ShaderMaterial({
  uniforms: { ...cloudUniforms, uCov: { value: 0.585 } },
  vertexShader: `varying vec3 vW; void main(){ vec4 w=modelMatrix*vec4(position,1.); vW=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }`,
  fragmentShader: NOISE + `
  uniform vec3 uSun,uCam,uLit,uShade,uDeep,uRim,uFogC; uniform float uFogN,uFogF,uTime,uCov; varying vec3 vW;
  float field(vec2 p){ return fbm2(p*0.00030+vec2(uTime*0.004,uTime*0.002))*0.85+fbm2(p*0.0013+vec2(7.3,1.1))*0.36; }
  void main(){
    vec2 p=vW.xz; float f=field(p); float d=f-uCov;
    float a=smoothstep(0.0,0.045,d); if(a<0.01) discard;
    float e=55.; float fx=field(p+vec2(e,0.))-f; float fz=field(p+vec2(0.,e))-f;
    vec3 n=normalize(vec3(-fx*60.,1.,-fz*60.));
    float br=fbm2(p*0.007)-0.5;
    float ndl=dot(n,uSun)+br*0.22;
    vec3 col=mix(uShade,uLit,smoothstep(0.26,0.33,ndl));
    col=mix(uDeep,col,smoothstep(0.0,0.06,ndl+0.05));
    col+=uRim*(1.-smoothstep(0.0,0.07,d))*0.45;
    if(uCam.y<vW.y) col=mix(uShade*0.95,uDeep*0.78,smoothstep(0.0,0.25,d));
    float dist=length(uCam-vW);
    col=mix(col,uFogC,smoothstep(uFogN,uFogF,dist)*0.95);
    gl_FragColor=vec4(col,a*0.97);
  }`,
  transparent: true, depthWrite: false, side: THREE.DoubleSide
});
const cloudSea = new THREE.Mesh(new THREE.PlaneGeometry(70000, 70000).rotateX(-Math.PI / 2), seaCloudMat);
cloudSea.position.y = CLOUDSEA_Y; cloudSea.renderOrder = 1; scene.add(cloudSea);

// 高空卷雲
const cirrusMat = new THREE.ShaderMaterial({
  uniforms: { ...cloudUniforms },
  vertexShader: `varying vec3 vW; void main(){ vec4 w=modelMatrix*vec4(position,1.); vW=w.xyz; gl_Position=projectionMatrix*viewMatrix*w; }`,
  fragmentShader: NOISE + `
  uniform vec3 uSun,uCam,uRim; uniform float uTime; varying vec3 vW;
  void main(){ vec2 p=vW.xz; vec2 q=mat2(0.8,-0.6,0.6,0.8)*p;
    float c=fbm2(vec2(q.x*0.00007,q.y*0.0003)+uTime*0.002);
    float s=fbm2(vec2(q.x*0.00025,q.y*0.0045));
    float a=smoothstep(0.5,0.78,c)*smoothstep(0.32,0.72,s)*0.8;
    float d=length(uCam-vW); a*=1.-smoothstep(15000.,32000.,d);
    vec3 v=normalize(vW-uCam); float sn=pow(max(dot(v,uSun),0.),4.);
    vec3 col=mix(vec3(1.),uRim*1.5,sn*0.75+0.08);
    gl_FragColor=vec4(col,a); }`,
  transparent: true, depthWrite: false, side: THREE.DoubleSide, fog: false
});
const cirrus = new THREE.Mesh(new THREE.PlaneGeometry(80000, 80000).rotateX(-Math.PI / 2), cirrusMat);
cirrus.position.y = 8200; cirrus.renderOrder = 0; scene.add(cirrus);

/* =========================================================
   粒子系統（卡通煙 / 發光）
   ========================================================= */
const PVS = `attribute float aSize; attribute vec3 aColor; attribute float aAlpha; attribute float aSeed;
  uniform float uScale,uFogN,uFogF; varying vec3 vC; varying float vA; varying float vSeed; varying float vFog;
  void main(){ vec4 mv=modelViewMatrix*vec4(position,1.); gl_Position=projectionMatrix*mv;
    gl_PointSize=clamp(aSize*uScale/max(-mv.z,0.5),1.,1400.); vC=aColor; vA=aAlpha; vSeed=aSeed; vFog=smoothstep(uFogN,uFogF,-mv.z); }`;
const SMOKE_FS = `uniform vec3 uFogC; uniform vec2 uL; varying vec3 vC; varying float vA; varying float vSeed; varying float vFog;
  void main(){ vec2 p=gl_PointCoord*2.-1.; p.y=-p.y; float r=length(p); float ang=atan(p.y,p.x);
    float edge=0.84+0.07*sin(ang*5.+vSeed*40.)+0.05*sin(ang*11.+vSeed*17.); if(r>edge) discard;
    vec3 n=vec3(p,sqrt(max(0.,1.-r*r))); float l=dot(n,normalize(vec3(uL,0.65)));
    vec3 col=l>0.2?vC:vC*vec3(0.62,0.67,0.82); col=mix(col,vC*1.12,step(0.82,l)*0.7);
    float a=vA*smoothstep(edge,edge-0.1,r); col=mix(col,uFogC,vFog); gl_FragColor=vec4(col,a); }`;
const GLOW_FS = `varying vec3 vC; varying float vA; varying float vSeed; varying float vFog;
  void main(){ vec2 p=gl_PointCoord*2.-1.; float r=dot(p,p); float k=(1.-vFog)*vA;
    vec3 col=vC*exp(-r*4.5)*k+vec3(1.)*exp(-r*28.)*k*0.7; gl_FragColor=vec4(col,1.); }`;

class PSys {
  constructor(max, additive, fadeMode) {
    this.max = max; this.cur = 0; this.fade = fadeMode;
    const f = n => new Float32Array(n);
    Object.assign(this, { p: f(max * 3), v: f(max * 3), c: f(max * 3), life: f(max), ml: f(max), s0: f(max), s1: f(max), a0: f(max), drag: f(max), grav: f(max), seed: f(max) });
    this.gp = f(max * 3); this.gs = f(max); this.gc = f(max * 3); this.ga = f(max); this.gd = f(max);
    const g = new THREE.BufferGeometry();
    const at = (arr, n) => new THREE.BufferAttribute(arr, n).setUsage(THREE.DynamicDrawUsage);
    g.setAttribute('position', at(this.gp, 3)); g.setAttribute('aSize', at(this.gs, 1)); g.setAttribute('aColor', at(this.gc, 3));
    g.setAttribute('aAlpha', at(this.ga, 1)); g.setAttribute('aSeed', at(this.gd, 1));
    this.geo = g;
    this.mat = new THREE.ShaderMaterial({
      uniforms: { uScale: { value: 500 }, uFogC: { value: PAL.fog }, uFogN: { value: FOG_N }, uFogF: { value: FOG_F }, uL: { value: new THREE.Vector2(0.4, 0.7) } },
      vertexShader: PVS, fragmentShader: additive ? GLOW_FS : SMOKE_FS, transparent: true, depthWrite: false,
      blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending
    });
    this.pts = new THREE.Points(g, this.mat); this.pts.frustumCulled = false; this.pts.renderOrder = additive ? 6 : 5;
    scene.add(this.pts);
  }
  emit(x, y, z, vx, vy, vz, life, s0, s1, r, g, b, a = 1, drag = 0, grav = 0) {
    const i = this.cur; this.cur = (this.cur + 1) % this.max; const j = i * 3;
    this.p[j] = x; this.p[j + 1] = y; this.p[j + 2] = z; this.v[j] = vx; this.v[j + 1] = vy; this.v[j + 2] = vz;
    this.c[j] = r; this.c[j + 1] = g; this.c[j + 2] = b;
    this.life[i] = life; this.ml[i] = life; this.s0[i] = s0; this.s1[i] = s1; this.a0[i] = a; this.drag[i] = drag; this.grav[i] = grav; this.seed[i] = Math.random();
  }
  update(dt) {
    let n = 0; const { p, v, life, ml, gp, gs, gc, ga, gd } = this;
    for (let i = 0; i < this.max; i++) {
      if (life[i] <= 0) continue;
      life[i] -= dt; if (life[i] <= 0) continue;
      const j = i * 3, k = 1 - life[i] / ml[i];
      const dr = Math.exp(-this.drag[i] * dt);
      v[j] *= dr; v[j + 1] = v[j + 1] * dr - this.grav[i] * dt; v[j + 2] *= dr;
      p[j] += v[j] * dt; p[j + 1] += v[j + 1] * dt; p[j + 2] += v[j + 2] * dt;
      const m = n * 3;
      gp[m] = p[j]; gp[m + 1] = p[j + 1]; gp[m + 2] = p[j + 2];
      gc[m] = this.c[j]; gc[m + 1] = this.c[j + 1]; gc[m + 2] = this.c[j + 2];
      const e = 1 - (1 - k) * (1 - k);
      gs[n] = this.s0[i] + (this.s1[i] - this.s0[i]) * e;
      ga[n] = this.fade ? this.a0[i] * Math.pow(1 - k, 1.4) : this.a0[i] * clamp((1 - k) / 0.4, 0, 1);
      gd[n] = this.seed[i]; n++;
    }
    for (const key of ['position', 'aSize', 'aColor', 'aAlpha', 'aSeed']) this.geo.attributes[key].needsUpdate = true;
    this.geo.setDrawRange(0, n);
  }
}
const smoke = new PSys(9000, false, false);
const glow = new PSys(5000, true, true);

// 衝擊波環
const rings = [];
for (let i = 0; i < 10; i++) {
  const m = new THREE.Mesh(new THREE.RingGeometry(0.95, 1, 64), new THREE.MeshBasicMaterial({ color: new THREE.Color(1.3, 1.2, 1.1), transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, fog: false }));
  m.visible = false; m.renderOrder = 7; scene.add(m); rings.push({ m, t: 1, s: 1 });
}
let ringIdx = 0;

/* =========================================================
   音效（WebAudio 合成）
   ========================================================= */
const AU = { ctx: null };
function auInit() {
  if (AU.ctx) { AU.ctx.resume(); return; }
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)(); AU.ctx = ctx;
    AU.master = ctx.createGain(); AU.master.gain.value = 0.45; AU.master.connect(ctx.destination);
    const len = ctx.sampleRate * 2, buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    AU.noise = buf;
    const src = ctx.createBufferSource(); src.buffer = buf; src.loop = true;
    const f = ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = 380;
    const g = ctx.createGain(); g.gain.value = 0.0;
    src.connect(f).connect(g).connect(AU.master); src.start(); AU.eng = { f, g };
  } catch (e) { AU.ctx = null; }
}
function sNoise(dur, type, f0, f1, vol, q = 1) {
  const ctx = AU.ctx; if (!ctx || vol < 0.003) return; const t = ctx.currentTime;
  const s = ctx.createBufferSource(); s.buffer = AU.noise;
  const f = ctx.createBiquadFilter(); f.type = type; f.Q.value = q; f.frequency.setValueAtTime(f0, t); f.frequency.exponentialRampToValueAtTime(Math.max(f1, 20), t + dur);
  const g = ctx.createGain(); g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0008, t + dur);
  s.connect(f).connect(g).connect(AU.master); s.start(t, Math.random() * 1.5); s.stop(t + dur + 0.05);
}
function sTone(freq, dur, vol, type = 'sine', f1) {
  const ctx = AU.ctx; if (!ctx) return; const t = ctx.currentTime;
  const o = ctx.createOscillator(); o.type = type; o.frequency.setValueAtTime(freq, t); if (f1) o.frequency.exponentialRampToValueAtTime(f1, t + dur);
  const g = ctx.createGain(); g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0008, t + dur);
  o.connect(g).connect(AU.master); o.start(t); o.stop(t + dur + 0.02);
}
const SFX = {
  gun: () => sNoise(0.07, 'highpass', 1800, 900, 0.16),
  missile: () => { sNoise(0.9, 'bandpass', 500, 2200, 0.35, 0.8); sNoise(0.25, 'lowpass', 900, 200, 0.3); },
  boom: (d) => { const v = clamp(1 - d / 6000, 0.05, 1); sNoise(1.6, 'lowpass', 900, 60, 0.7 * v); sTone(70, 0.9, 0.5 * v, 'sine', 30); },
  hit: () => sTone(1400, 0.05, 0.06, 'square'),
  lock: () => sTone(1250, 0.06, 0.07, 'square'),
  locked: () => sTone(1650, 0.05, 0.08, 'square'),
  alert: () => sTone(980, 0.11, 0.1, 'square'),
  flare: () => sNoise(0.35, 'bandpass', 3000, 800, 0.18, 2),
  dmg: () => { sNoise(0.5, 'lowpass', 1500, 200, 0.6); sTone(180, 0.3, 0.2, 'sawtooth', 60); },
};

/* =========================================================
   玩家 / 敵機 / 武器資料
   ========================================================= */
const playerMesh = buildF16(); scene.add(playerMesh);
const player = {
  mesh: playerMesh, pos: playerMesh.position, q: playerMesh.quaternion, ab: collectAB(playerMesh), vel: V3(), up: V3(0, 1, 0),
  speed: 260, hp: 100, alive: true, msl: 96, flares: 36, thr: 0.5, pi: 0, ri: 0, yi: 0, inv: 0, ai: false, lastDmg: -10
};
const enemies = [], missiles = [], decoys = [];
const bullets = []; for (let i = 0; i < 600; i++) bullets.push({ on: false, pos: V3(), prev: V3(), vel: V3(), life: 0, owner: '' });
const bulletMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(0.28, 0.28, 13), new THREE.MeshBasicMaterial({ color: new THREE.Color(3, 2.2, 1.1), fog: false }), 600);
bulletMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage); bulletMesh.frustumCulled = false; bulletMesh.count = 0;
bulletMesh.setColorAt(0, new THREE.Color(1, 1, 1)); scene.add(bulletMesh);
const BCOL_P = new THREE.Color(1, 0.9, 0.55), BCOL_E = new THREE.Color(1, 0.35, 0.4);

let state = 'loading', gTime = 0, score = 0, kills = 0, wave = 0, combo = 0, comboT = 0, waveTimer = 0;
let target = null, lockT = 0, locked = false, lockBeepT = 0, mslCd = 0, gunCd = 0, flareCd = 0, side = 1, alertT = 0, shake = 0, dmgFlash = 0, flash = 0, deadT = 0;
let invertPitch = false, hitPopT = 0, clearSaid = false;
const keys = {};
const camQ = new THREE.Quaternion();
const Q_FLIP = new THREE.Quaternion().setFromAxisAngle(AX_Y, Math.PI);
const Q_TILT = new THREE.Quaternion().setFromAxisAngle(AX_X, -0.05);
const popups = [], radioQ = []; let radioCur = null, banner = null;
const deathCam = V3();

const _f = V3(), _r = V3(), _u = V3(), _o = V3(), _t = V3(), _t2 = V3(), _ax = V3(), _lat = V3(), _upT = V3(), _aim = V3(), _sa = V3(), _sb = V3(), _sc = V3();
const _q = new THREE.Quaternion(), _m = new THREE.Matrix4(), _dummy = new THREE.Object3D();

const fwdOf = (q, out = V3()) => out.set(0, 0, 1).applyQuaternion(q);
function segDist(a, b, p) {
  _sa.subVectors(b, a); const L = Math.max(_sa.lengthSq(), 1e-6);
  const t = clamp(_sb.subVectors(p, a).dot(_sa) / L, 0, 1);
  return _sc.copy(a).addScaledVector(_sa, t).distanceTo(p);
}
function steer(o, desired, rate, dt) {
  fwdOf(o.q, _f);
  const d = clamp(_f.dot(desired), -1, 1), ang = Math.acos(d);
  _lat.copy(desired).addScaledVector(_f, -d); _lat.y *= 0.35;
  const latL = _lat.length(); if (latL > 1e-4) _lat.multiplyScalar(1 / latL);
  if (ang > 1e-4) { _ax.crossVectors(_f, desired); if (_ax.lengthSq() < 1e-8) _ax.copy(o.up); _ax.normalize(); _f.applyAxisAngle(_ax, Math.min(ang, rate * dt)); }
  const bank = clamp(ang * 2.4, 0, 1.3);
  _upT.copy(UP).multiplyScalar(Math.cos(bank)); if (latL > 1e-4) _upT.addScaledVector(_lat, Math.sin(bank));
  o.up.lerp(_upT, 1 - Math.exp(-dt * 3.5));
  o.up.addScaledVector(_f, -o.up.dot(_f)).normalize();
  _r.crossVectors(o.up, _f).normalize(); o.up.crossVectors(_f, _r).normalize();
  _m.makeBasis(_r, o.up, _f); o.q.setFromRotationMatrix(_m);
}
function setOrient(o, fwd) {
  o.up.set(0, 1, 0); _r.crossVectors(o.up, fwd).normalize(); o.up.crossVectors(fwd, _r).normalize();
  _m.makeBasis(_r, o.up, fwd); o.q.setFromRotationMatrix(_m);
}

/* ---------- 無線電 / 提示 ---------- */
function radio(who, text) { radioQ.push({ who, text }); if (radioQ.length > 3) radioQ.shift(); }
function popup(text, col = '#9ff5d0') { popups.push({ text, col, t: 0 }); if (popups.length > 3) popups.shift(); }
const pick = a => a[Math.floor(Math.random() * a.length)];
const KILL_LINES = ['擊落確認！漂亮～', 'Splash one！敵機墜落。', '目標消滅，下一個！', 'J-16 冒煙墜海——好球。', '命中！這片天空是你的。', '乾淨俐落，連雲都替你鼓掌。'];

/* ---------- 爆炸 ---------- */
function explode(p, s = 1, big = true) {
  glow.emit(p.x, p.y, p.z, 0, 0, 0, 0.26, 22 * s, 65 * s, 2.0, 1.5, 1.0, 1);
  for (let i = 0; i < 20 * s; i++) {
    const v = V3(rand(-1, 1), rand(-1, 1), rand(-1, 1)).normalize().multiplyScalar(rand(20, 70) * s);
    smoke.emit(p.x, p.y, p.z, v.x, v.y, v.z, rand(0.5, 1.0), rand(10, 18) * s, rand(26, 42) * s, rand(1.6, 2.2), rand(0.9, 1.25), 0.3, 1, 2.2, -4);
  }
  for (let i = 0; i < 14 * s; i++) {
    const v = V3(rand(-1, 1), rand(-1, 1), rand(-1, 1)).normalize().multiplyScalar(rand(10, 45) * s);
    smoke.emit(p.x + v.x * 0.3, p.y + v.y * 0.3, p.z + v.z * 0.3, v.x, v.y + 6, v.z, rand(2.5, 4.5), rand(16, 26) * s, rand(50, 80) * s, rand(0.3, 0.42), 0.32, 0.38, 0.95, 1.4, -3);
  }
  for (let i = 0; i < 26 * s; i++) {
    const v = V3(rand(-1, 1), rand(-0.6, 1), rand(-1, 1)).normalize().multiplyScalar(rand(80, 220) * s);
    glow.emit(p.x, p.y, p.z, v.x, v.y, v.z, rand(0.6, 1.3), 4 * s, 2 * s, 2.6, 1.4, 0.5, 1, 1.0, 60);
  }
  if (big) {
    const R = rings[ringIdx++ % rings.length]; R.t = 0; R.s = 85 * s; R.m.position.copy(p); R.m.visible = true;
  }
  const d = p.distanceTo(camera.position);
  shake = Math.max(shake, clamp(1.4 - d / 1500, 0, 1.4) * s);
  flash = Math.max(flash, clamp(1 - d / 2500, 0, 0.5));
  SFX.boom(d);
}

/* ---------- 子彈 ---------- */
function fireBullet(pos, dir, baseVel, owner, spread) {
  for (const b of bullets) {
    if (b.on) continue;
    b.on = true; b.owner = owner; b.life = 1.5; b.pos.copy(pos); b.prev.copy(pos);
    _t.set(rand(-spread, spread), rand(-spread, spread), rand(-spread, spread));
    b.vel.copy(dir).add(_t).normalize().multiplyScalar(1150).add(baseVel);
    return;
  }
}

/* ---------- 飛彈 ---------- */
function spawnMissile(pos, dir, speed, tgt, owner) {
  const mesh = MSL_TPL.clone(); mesh.position.copy(pos); scene.add(mesh);
  const P = owner === 'p';
  missiles.push({ mesh, pos: mesh.position, dir: dir.clone(), speed, target: tgt, owner, life: P ? 8 : 9, max: P ? 790 : 640, turn: P ? 3.7 : 2.05, fov: P ? 1.3 : 0.95, prev: V3().copy(pos), armT: 0.25, hadTarget: !!tgt, hit: false, evTrig: false, dead: false });
}
function makeDecoy(p, v) {
  const d = { pos: p.clone(), vel: v.clone(), alive: true, isDecoy: true, life: 3.2 }; decoys.push(d); return d;
}

/* ---------- 敵機 ---------- */
function makeEnemy(pos, lookAt) {
  const mesh = J16_TPL.clone(); scene.add(mesh); mesh.position.copy(pos);
  const e = { mesh, pos: mesh.position, q: mesh.quaternion, up: V3(0, 1, 0), ab: collectAB(mesh), vel: V3(), speed: rand(235, 285), hp: 100, alive: true, dying: false, dieT: 0, spin: 0,
    fireCd: rand(5, 10), gunCd: 0, burst: 0, evadeT: 0, evadeDir: V3(), jink: rand(0, 10), ai: true, dead: false, smokeT: 0 };
  setOrient(e, _t.subVectors(lookAt, pos).normalize());
  enemies.push(e); return e;
}
function spawnWave() {
  wave++;
  const n = [0, 3, 5, 6, 8, 9, 10][Math.min(wave, 6)] + Math.max(0, wave - 6);
  const f = fwdOf(player.q, V3()); const hdg = Math.atan2(f.x, f.z);
  for (let i = 0; i < n; i++) {
    const a = hdg + rand(-0.9, 0.9), d = rand(5200, 7800);
    const p = V3(player.pos.x + Math.sin(a) * d, clamp(player.pos.y + rand(-500, 1300), 1300, 5200), player.pos.z + Math.cos(a) * d);
    makeEnemy(p, player.pos);
  }
  banner = { title: `WAVE ${wave}`, sub: `J-16 × ${n}　接近中`, t: 0 };
  if (wave === 1) radio('AWACS Shiori', '這裡是空中預警機 Shiori。Aurora 1，雷達上出現 J-16 編隊，交戰許可已下達——讓他們見識一下這片天空的主人吧。');
  else radio('AWACS Shiori', `新的 J-16 編隊，數量 ${n}。風向不錯，去吧，Aurora 1。`);
}
function enemyEvade(e, m) {
  e.evadeT = rand(2, 3.2);
  const s = Math.random() < .5 ? -1 : 1;
  e.evadeDir.crossVectors(m.dir, UP).normalize().multiplyScalar(s).addScaledVector(UP, rand(-0.25, 0.45)).normalize();
  if (Math.random() < 0.6) {
    for (let i = 0; i < 6; i++) { const v = V3(rand(-40, 40), rand(-60, -10), rand(-40, 40)).addScaledVector(e.vel, 0.4); makeDecoy(e.pos, v); }
    if (Math.random() < 0.3 + Math.min(wave, 8) * 0.025) { m.target = decoys[decoys.length - 1]; m.lost = true; }
  }
}
function killEnemy(e) {
  e.alive = false; e.dying = true; e.dieT = rand(2.0, 3.4); e.spin = rand(2.5, 5) * (Math.random() < .5 ? -1 : 1);
  combo = comboT > 0 ? combo + 1 : 1; comboT = 7;
  score += 1000 + (combo - 1) * 300; kills++;
  popup(combo > 1 ? `DESTROYED  ×${combo}` : 'DESTROYED', '#ffd27a');
  if (Math.random() < 0.75) radio('AWACS Shiori', pick(KILL_LINES));
  explode(e.pos, 0.8, true);
  if (target === e) { target = null; lockT = 0; locked = false; }
}
function damagePlayer(dmg, heavy) {
  if (!player.alive || gTime - player.inv < 0) return;
  player.hp -= dmg; player.lastDmg = gTime;
  dmgFlash = Math.min(1, dmgFlash + (heavy ? 1 : 0.25)); shake = Math.max(shake, heavy ? 1.6 : 0.4);
  if (heavy) { SFX.dmg(); radio('AWACS Shiori', player.hp > 40 ? '被擊中了！還能飛嗎？穩住機頭！' : '機體損傷嚴重……別逞強，求你了。'); }
  if (player.hp <= 0) playerDie();
}
function playerDie() {
  player.alive = false; player.hp = 0; explode(player.pos, 1.6, true);
  player.mesh.visible = false; deathCam.copy(camera.position); state = 'dead'; deadT = 0;
  radio('AWACS Shiori', 'Aurora 1！……Aurora 1，請回答！');
}

/* =========================================================
   玩家更新
   ========================================================= */
function updatePlayer(dt) {
  const P = player; if (!P.alive) return;
  const play = state === 'play';
  fwdOf(P.q, _f); _r.set(-1, 0, 0).applyQuaternion(P.q);
  let pi = 0, ri = 0, yi = 0;
  const boost = play && (keys.ShiftLeft || keys.ShiftRight), brake = play && keys.KeyC;
  if (play) {
    pi = isTouchDevice ? mobileStick.y : ((keys.KeyS || keys.ArrowDown) ? 1 : 0) - ((keys.KeyW || keys.ArrowUp) ? 1 : 0);
    if (invertPitch) pi = -pi;
    ri = isTouchDevice ? mobileStick.x : ((keys.KeyD || keys.ArrowRight) ? 1 : 0) - ((keys.KeyA || keys.ArrowLeft) ? 1 : 0);
    yi = (keys.KeyE ? 1 : 0) - (keys.KeyQ ? 1 : 0);
  } else {
    ri = clamp((_r.y + 0.3) * 3, -1, 1);
    pi = clamp(-_f.y * 6 + (2200 - P.pos.y) / 3000, -0.6, 0.6);
  }
  const k = 1 - Math.exp(-dt * 7);
  P.pi += (pi - P.pi) * k; P.ri += (ri - P.ri) * k; P.yi += (yi - P.yi) * k;
  const spdF = clamp((P.speed - 70) / 170, 0.3, 1.1);
  const pitchRate = 1.3 * spdF * (brake ? 1.4 : 1), rollRate = 2.9, yawRate = 0.42;
  _q.setFromAxisAngle(AX_X, -P.pi * pitchRate * dt); P.q.multiply(_q);
  _q.setFromAxisAngle(AX_Z, P.ri * rollRate * dt); P.q.multiply(_q);
  _q.setFromAxisAngle(AX_Y, -P.yi * yawRate * dt); P.q.multiply(_q);
  _r.set(-1, 0, 0).applyQuaternion(P.q);
  _q.setFromAxisAngle(UP, _r.y * 0.5 * spdF * dt); P.q.premultiply(_q);
  P.q.normalize();
  fwdOf(P.q, _f);
  const tgt = boost ? 410 : brake ? 140 : 258;
  const acc = tgt > P.speed ? (boost ? 60 : 32) : (brake ? 85 : 26);
  P.speed += clamp(tgt - P.speed, -acc * dt, acc * dt);
  P.speed -= _f.y * 9.8 * dt * 0.9 + Math.abs(P.pi) * spdF * 10 * dt;
  P.speed = clamp(P.speed, 85, 470);
  P.thr += ((boost ? 1 : brake ? 0.08 : 0.45) - P.thr) * (1 - Math.exp(-dt * 5));
  P.vel.copy(_f).multiplyScalar(P.speed);
  P.pos.addScaledVector(P.vel, dt);
  if (P.speed < 125) P.pos.y -= (125 - P.speed) * 0.3 * dt;
  if (P.pos.y > 9600) P.pos.y = 9600;
  // 翼尖凝結尾流
  if (Math.abs(P.pi) > 0.55 && P.speed > 190) {
    for (const sx of [4.8, -4.8]) {
      _o.set(sx, 0, -2.2).applyQuaternion(P.q).add(P.pos);
      smoke.emit(_o.x, _o.y, _o.z, 0, 0, 0, 0.55, 0.9, 2.6, 1, 1, 1, 0.55, 0);
    }
  }
  if (P.hp < 50 && Math.random() < dt * 30) {
    _o.set(0, 0.5, -6).applyQuaternion(P.q).add(P.pos);
    smoke.emit(_o.x, _o.y, _o.z, rand(-3, 3), rand(0, 3), rand(-3, 3), 1.6, 2, 9, 0.42, 0.42, 0.48, 0.8, 0.5);
  }
  if (P.hp < 100 && gTime - P.lastDmg > 8) P.hp = Math.min(100, P.hp + dt * 1.2);
  for (const a of P.ab) { a.scale.set(1, 1, 0.25 + P.thr * 1.1 + Math.random() * 0.12); a.children[0].material.opacity = 0.2 + P.thr * 0.5; }
  if (play && P.pos.y < groundH(P.pos.x, P.pos.z) + 3) { P.pos.y = groundH(P.pos.x, P.pos.z) + 3; playerDie(); return; }
  if (play) weapons(dt);
  if (AU.eng) { AU.eng.f.frequency.value = 260 + P.thr * 900; AU.eng.g.gain.value = play ? 0.08 + P.thr * 0.12 : 0.05; }
}

function weapons(dt) {
  const P = player;
  mslCd -= dt; gunCd -= dt; flareCd -= dt;
  fwdOf(P.q, _f);
  if (!target || !target.alive) { target = pickTarget(); lockT = 0; }
  let ang = 9, dist = 1e9;
  if (target) { _t.subVectors(target.pos, P.pos); dist = _t.length(); ang = Math.acos(clamp(_f.dot(_t.normalize()), -1, 1)); }
  const inCone = target && ang < 0.6 && dist < 4000;
  lockT = inCone ? lockT + dt : Math.max(0, lockT - dt * 2);
  const was = locked; locked = lockT >= 0.5;
  lockBeepT -= dt;
  if (inCone && !locked && lockBeepT <= 0) { SFX.lock(); lockBeepT = 0.12; }
  if (locked && !was) SFX.locked();
  if (keys.Space || keys.Mouse2) {
    if (mslCd <= 0 && P.msl > 0) {
      mslCd = 0.34; P.msl--; side = -side;
      _o.set(side * 3.1, -0.6, 0).applyQuaternion(P.q).add(P.pos);
      const tg = target && (locked || ang < 0.45) ? target : null;
      spawnMissile(_o, _f, P.speed + 25, tg, 'p'); SFX.missile();
      if (Math.random() < 0.25) radio('Aurora 1', 'Fox Two！');
    }
  }
  if ((keys.KeyJ || keys.Mouse0) && gunCd <= 0) {
    gunCd = 0.034;
    _o.set(0.75, 0.35, 5.2).applyQuaternion(P.q).add(P.pos);
    fireBullet(_o, _f, P.vel, 'p', 0.006);
    glow.emit(_o.x, _o.y, _o.z, P.vel.x, P.vel.y, P.vel.z, 0.05, 3.5, 2, 3, 2.2, 1, 1);
    if (Math.random() < 0.6) SFX.gun();
  }
  if (keys.KeyX && flareCd <= 0 && P.flares > 0) {
    flareCd = 2.4; P.flares -= 2; SFX.flare();
    const list = [];
    for (let i = 0; i < 8; i++) {
      _r.set(-1, 0, 0).applyQuaternion(P.q); _u.set(0, 1, 0).applyQuaternion(P.q);
      const s = i % 2 ? 1 : -1;
      const v = V3().copy(P.vel).multiplyScalar(0.35).addScaledVector(_r, s * rand(30, 70)).addScaledVector(_u, rand(-40, 5));
      list.push(makeDecoy(P.pos, v));
    }
    for (const m of missiles) if (m.owner === 'e' && m.target === player && m.pos.distanceTo(P.pos) < 3200 && Math.random() < 0.8) m.target = pick(list);
  }
}
function pickTarget() {
  let best = null, bs = 1e9; fwdOf(player.q, _f);
  for (const e of enemies) {
    if (!e.alive) continue;
    _t.subVectors(e.pos, player.pos); const d = _t.length(); const a = Math.acos(clamp(_f.dot(_t.normalize()), -1, 1));
    const s = a * 3 + d / 4000; if (s < bs) { bs = s; best = e; }
  }
  return best;
}
function cycleTarget() {
  const list = enemies.filter(e => e.alive).sort((a, b) => a.pos.distanceTo(player.pos) - b.pos.distanceTo(player.pos));
  if (!list.length) return; const i = list.indexOf(target); target = list[(i + 1) % list.length]; lockT = 0;
}

/* =========================================================
   敵機 AI
   ========================================================= */
function updateEnemies(dt) {
  const P = player;
  const turn = Math.min(0.88 + wave * 0.06, 1.4);
  let activeEM = 0; for (const m of missiles) if (m.owner === 'e') activeEM++;
  for (const e of enemies) {
    fwdOf(e.q, _f);
    if (e.dying) {
      e.dieT -= dt;
      _q.setFromAxisAngle(AX_Z, e.spin * dt); e.q.multiply(_q);
      _q.setFromAxisAngle(AX_X, 0.45 * dt); e.q.multiply(_q);
      e.speed = Math.max(170, e.speed - 25 * dt);
      e.vel.copy(_f).multiplyScalar(e.speed); e.vel.y -= 40;
      e.pos.addScaledVector(e.vel, dt);
      smoke.emit(e.pos.x, e.pos.y, e.pos.z, rand(-4, 4), rand(0, 5), rand(-4, 4), 3.0, 6, 26, 0.3, 0.3, 0.36, 0.9, 0.6, -2);
      smoke.emit(e.pos.x, e.pos.y, e.pos.z, rand(-6, 6), rand(-6, 6), rand(-6, 6), 0.45, 7, 13, 2.2, 1.1, 0.35, 1, 1);
      if (e.dieT <= 0 || e.pos.y < groundH(e.pos.x, e.pos.z) + 5) { explode(e.pos, 1.3, true); e.dead = true; scene.remove(e.mesh); }
      continue;
    }
    _t.subVectors(P.pos, e.pos); const dist = _t.length(); const toP = _t.clone().normalize();
    let desired;
    if (e.evadeT > 0) { e.evadeT -= dt; desired = e.evadeDir.clone(); }
    else if (!P.alive || state !== 'play') { desired = _f.clone(); desired.y = 0; desired.normalize(); }
    else {
      const lead = _t2.copy(P.pos).addScaledVector(P.vel, Math.min(dist / 700, 2));
      desired = lead.sub(e.pos).normalize();
      e.jink += dt;
      desired.x += Math.sin(e.jink * 0.7) * 0.18; desired.y += Math.cos(e.jink * 0.5) * 0.08;
      if (dist < 280) desired.addScaledVector(_r.set(-1, 0, 0).applyQuaternion(e.q), 1.0).addScaledVector(UP, 0.3);
      desired.normalize();
    }
    const gh = groundH(e.pos.x, e.pos.z);
    if (e.pos.y < gh + 600) { desired.y = Math.max(desired.y, 0.55); desired.normalize(); }
    if (e.pos.y > 7500) { desired.y = Math.min(desired.y, -0.25); desired.normalize(); }
    const hr = Math.hypot(e.pos.x, e.pos.z);
    if (hr > 16000) { desired.lerp(_t2.set(-e.pos.x, 0, -e.pos.z).normalize(), 0.6).normalize(); }
    steer(e, desired, e.evadeT > 0 ? turn * 1.25 : turn, dt);
    fwdOf(e.q, _f);
    const want = e.evadeT > 0 ? 330 : dist > 2500 ? 300 : 245;
    e.speed += clamp(want - e.speed, -30 * dt, 30 * dt);
    e.vel.copy(_f).multiplyScalar(e.speed);
    e.pos.addScaledVector(e.vel, dt);
    const thr = e.evadeT > 0 || e.speed > 280 ? 1 : 0.4;
    for (const a of e.ab) a.scale.set(1, 1, 0.25 + thr + Math.random() * 0.12);
    if (e.hp < 60 && Math.random() < dt * 25) smoke.emit(e.pos.x, e.pos.y, e.pos.z, 0, 2, 0, 1.4, 3, 12, 0.45, 0.45, 0.5, 0.8, 0.5);
    // 開火
    if (state === 'play' && P.alive) {
      const ang = Math.acos(clamp(_f.dot(toP), -1, 1));
      e.fireCd -= dt;
      if (e.fireCd <= 0 && dist < 3300 && dist > 500 && ang < 0.45 && activeEM < 2 + Math.floor(wave / 3)) {
        e.fireCd = rand(7, 12) / Math.min(1 + wave * 0.08, 1.6);
        spawnMissile(e.pos.clone().addScaledVector(_f, 6), _f, e.speed + 20, P, 'e'); activeEM++;
        radio('AWACS Shiori', pick(['飛彈接近！快規避——拉桿、投熱焰彈！', '敵飛彈發射！Break, break！', '被鎖定了！別發呆，動起來！']));
      }
      e.gunCd -= dt;
      if (dist < 900 && ang < 0.09 && e.gunCd <= 0) { e.gunCd = 1.6; e.burst = 14; }
      if (e.burst > 0 && Math.random() < 0.7) { e.burst--; fireBullet(_t2.copy(e.pos).addScaledVector(_f, 11), _f, e.vel, 'e', 0.018); }
    }
  }
  for (let i = enemies.length - 1; i >= 0; i--) if (enemies[i].dead) enemies.splice(i, 1);
}

/* =========================================================
   飛彈 / 子彈 / 誘餌 更新
   ========================================================= */
function updateMissiles(dt) {
  for (const m of missiles) {
    m.prev.copy(m.pos); m.life -= dt; m.armT -= dt;
    m.speed = Math.min(m.max, m.speed + 430 * dt);
    const t = m.target;
    if (t && !t.alive) m.target = null;
    if (m.target) {
      _t.subVectors(m.target.pos, m.pos); const dist = _t.length();
      _aim.copy(m.target.pos).addScaledVector(m.target.vel, dist / Math.max(m.speed, 1) * 0.85).sub(m.pos).normalize();
      const ang = Math.acos(clamp(m.dir.dot(_aim), -1, 1));
      if (ang > m.fov) { m.target = null; m.lost = true; }
      else if (ang > 1e-4) { _ax.crossVectors(m.dir, _aim).normalize(); m.dir.applyAxisAngle(_ax, Math.min(ang, m.turn * dt)).normalize(); }
      if (m.owner === 'p' && m.target && m.target.ai && !m.evTrig && dist < 1500) { m.evTrig = true; enemyEvade(m.target, m); }
    }
    m.pos.addScaledVector(m.dir, m.speed * dt);
    if (m.armT <= 0) {
      if (m.owner === 'p') {
        for (const e of enemies) if (e.alive && segDist(m.prev, m.pos, e.pos) < 17) { m.hit = true; m.dead = true; killEnemy(e); break; }
      } else if (player.alive && segDist(m.prev, m.pos, player.pos) < 13) {
        m.dead = true; m.hit = true; explode(m.pos, 0.7, true); damagePlayer(34, true);
      }
      if (!m.dead && m.target && m.target.isDecoy && segDist(m.prev, m.pos, m.target.pos) < 25) { m.dead = true; explode(m.pos, 0.45, false); }
    }
    if (m.pos.y < groundH(m.pos.x, m.pos.z)) { m.dead = true; explode(m.pos, 0.5, false); }    if (m.life <= 0 && !m.dead) { m.dead = true; explode(m.pos, 0.35, false); }
    // 尾煙＋火焰
    const step = m.prev.distanceTo(m.pos), n = Math.min(6, Math.ceil(step / 5));
    for (let i = 0; i < n; i++) {
      _t.lerpVectors(m.prev, m.pos, i / n).addScaledVector(m.dir, -2.6);
      smoke.emit(_t.x, _t.y, _t.z, rand(-2, 2), rand(-1, 2), rand(-2, 2), rand(2.0, 3.0), 1.8, rand(6, 9.5), 0.97, 0.97, 1.0, 0.9, 0.6, -1.5);
    }
    _t.copy(m.pos).addScaledVector(m.dir, -2.8);
    glow.emit(_t.x, _t.y, _t.z, 0, 0, 0, 0.06, 7, 4, 3, 1.9, 0.9, 1);
    m.mesh.lookAt(_t2.copy(m.pos).add(m.dir));
    if (m.dead) {
      scene.remove(m.mesh);
      if (m.owner === 'p' && m.lost && !m.hit) popup('MISSED', '#b8c7e0');
    }
  }
  for (let i = missiles.length - 1; i >= 0; i--) if (missiles[i].dead) missiles.splice(i, 1);

  for (const d of decoys) {
    d.life -= dt; d.vel.multiplyScalar(Math.exp(-dt * 0.8)); d.vel.y -= 25 * dt; d.pos.addScaledVector(d.vel, dt);
    glow.emit(d.pos.x, d.pos.y, d.pos.z, 0, 0, 0, 0.12, 9, 5, 3.4, 2.4, 1.3, 1);
    smoke.emit(d.pos.x, d.pos.y, d.pos.z, 0, 1, 0, 1.4, 2, 7, 0.95, 0.95, 0.98, 0.7, 0.4);
    if (d.life <= 0) d.alive = false;
  }
  for (let i = decoys.length - 1; i >= 0; i--) if (!decoys[i].alive) decoys.splice(i, 1);
}
function updateBullets(dt) {
  let n = 0;
  for (const b of bullets) {
    if (!b.on) continue;
    b.prev.copy(b.pos); b.pos.addScaledVector(b.vel, dt); b.life -= dt;
    if (b.life <= 0 || b.pos.y < 0) { b.on = false; continue; }
    if (b.owner === 'p') {
      for (const e of enemies) {
        if (!e.alive) continue;
        if (segDist(b.prev, b.pos, e.pos) < 9) {
          b.on = false; e.hp -= 5.5;
          for (let i = 0; i < 3; i++) glow.emit(b.pos.x, b.pos.y, b.pos.z, rand(-40, 40), rand(-40, 40), rand(-40, 40), 0.25, 3, 1, 3, 2, 0.8, 1, 2);
          if (hitPopT <= 0) { popup('HIT'); hitPopT = 0.35; SFX.hit(); }
          if (e.hp <= 0) killEnemy(e);
          break;
        }
      }
    } else if (player.alive && segDist(b.prev, b.pos, player.pos) < 7) { b.on = false; damagePlayer(2.2, false); }
    if (!b.on) continue;
    _dummy.position.copy(b.pos); _dummy.lookAt(_t.copy(b.pos).add(b.vel)); _dummy.updateMatrix();
    bulletMesh.setMatrixAt(n, _dummy.matrix); bulletMesh.setColorAt(n, b.owner === 'p' ? BCOL_P : BCOL_E); n++;
  }
  bulletMesh.count = n; bulletMesh.instanceMatrix.needsUpdate = true; if (bulletMesh.instanceColor) bulletMesh.instanceColor.needsUpdate = true;
}

/* =========================================================
   後製：Bloom + 鏡頭光暈 + 動畫調色
   ========================================================= */
const FSV = `varying vec2 vUv; void main(){ vUv=uv; gl_Position=vec4(position.xy,0.,1.); }`;
const brightMat = new THREE.ShaderMaterial({
  uniforms: { t: { value: null }, uTexel: { value: new THREE.Vector2() } }, vertexShader: FSV,
  fragmentShader: `uniform sampler2D t; uniform vec2 uTexel; varying vec2 vUv;
    void main(){ vec3 c=(texture2D(t,vUv+uTexel*vec2(-1,-1)).rgb+texture2D(t,vUv+uTexel*vec2(1,-1)).rgb+texture2D(t,vUv+uTexel*vec2(-1,1)).rgb+texture2D(t,vUv+uTexel*vec2(1,1)).rgb)*0.25;
      float l=max(c.r,max(c.g,c.b)); gl_FragColor=vec4(c*smoothstep(0.92,1.5,l),1.); }`, depthTest: false, depthWrite: false
});
const blurMat = new THREE.ShaderMaterial({
  uniforms: { t: { value: null }, uDir: { value: new THREE.Vector2() } }, vertexShader: FSV,
  fragmentShader: `uniform sampler2D t; uniform vec2 uDir; varying vec2 vUv;
    void main(){ vec3 c=texture2D(t,vUv).rgb*0.227; c+=texture2D(t,vUv+uDir*1.385).rgb*0.316; c+=texture2D(t,vUv-uDir*1.385).rgb*0.316;
      c+=texture2D(t,vUv+uDir*3.231).rgb*0.07; c+=texture2D(t,vUv-uDir*3.231).rgb*0.07; gl_FragColor=vec4(c,1.); }`, depthTest: false, depthWrite: false
});
const compMat = new THREE.ShaderMaterial({
  uniforms: {
    tS: { value: null }, tB: { value: null }, uSunUV: { value: new THREE.Vector2(-9, -9) }, uSunVis: { value: 0 }, uWhite: { value: 0 }, uDmg: { value: 0 },
    uFlash: { value: 0 }, uBoost: { value: 0 }, uTime: { value: 0 }, uAspect: { value: 1 }, uRes: { value: new THREE.Vector2(1, 1) }
  }, vertexShader: FSV,
  fragmentShader: NOISE + `
  uniform sampler2D tS,tB; uniform vec2 uSunUV,uRes; uniform float uSunVis,uWhite,uDmg,uFlash,uBoost,uTime,uAspect; varying vec2 vUv;
  vec3 ghost(vec2 uv,vec2 c,float r,vec3 col){ vec2 d=(uv-c)*vec2(uAspect,1.); vec2 a=abs(d); float hx=max(a.x*0.866+a.y*0.5,a.y);
    float m=smoothstep(r,r*0.88,hx); float ring=smoothstep(r*0.78,r,hx)*m; return col*(m*0.1+ring*0.28); }
  void main(){
    vec2 uv=vUv; vec3 c;
    if(uBoost>0.01){ vec2 dc=uv-0.5; float w=dot(dc,dc)*4.; c=vec3(0.);
      for(int i=0;i<7;i++){ float k=float(i)/6.; c+=texture2D(tS,uv-dc*k*0.045*uBoost*w).rgb; } c/=7.; }
    else c=texture2D(tS,uv).rgb;
    c+=texture2D(tB,uv).rgb*0.9;
    if(uSunVis>0.001){
      vec2 sv=uSunUV; vec2 ax=vec2(0.5)-sv; vec3 fl=vec3(0.);
      fl+=ghost(uv,sv+ax*0.38,0.016,vec3(1.,1.,0.95));
      fl+=ghost(uv,sv+ax*0.66,0.036,vec3(0.45,0.9,1.0));
      fl+=ghost(uv,sv+ax*1.18,0.062,vec3(1.0,0.55,0.82));
      fl+=ghost(uv,sv+ax*1.5,0.022,vec3(1.0,0.9,0.5));
      fl+=ghost(uv,sv+ax*2.05,0.095,vec3(0.5,1.0,0.72));
      vec2 dd=(uv-sv)*vec2(uAspect,1.); float dl=length(dd);
      fl+=vec3(1.0,0.82,0.58)*0.32/(1.+dl*dl*80.);
      fl+=vec3(1.0,0.86,0.62)*exp(-abs(dd.y)*150.)*exp(-abs(dd.x)*2.6)*0.75;
      float ang=atan(dd.y,dd.x); float rn=n2(vec2(cos(ang),sin(ang))*5.+uTime*0.06);
      fl+=vec3(1.0,0.9,0.7)*pow(rn,4.)*exp(-dl*3.2)*0.9;
      fl+=vec3(0.6,0.8,1.0)*smoothstep(0.018,0.0,abs(dl-0.3))*0.10;
      c+=fl*uSunVis;
    }
    c=mix(c,vec3(0.93,0.95,1.0),uWhite);
    c=c/(1.+max(c-0.86,0.)*0.9);
    c=pow(max(c,0.),vec3(1./2.2));
    float l=dot(c,vec3(.299,.587,.114));
    c=mix(vec3(l),c,1.12);
    c=mix(c,c*vec3(0.95,1.0,1.07),(1.-l)*0.8);
    vec2 q=uv-0.5; q.x*=uAspect; c*=1.-dot(q,q)*0.32;
    float dv=smoothstep(0.25,0.95,length(q)); c=mix(c,vec3(0.85,0.08,0.1),dv*uDmg*0.65);
    c+=vec3(1.,0.92,0.82)*uFlash*0.22;
    c+=(h21(uv*uRes+fract(uTime*7.)*91.)-0.5)*0.022;
    gl_FragColor=vec4(c,1.);
  }`, depthTest: false, depthWrite: false
});
const fsScene = new THREE.Scene(), fsCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
const fsQuad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), compMat); fsQuad.frustumCulled = false; fsScene.add(fsQuad);
function pass(mat, tgt) { fsQuad.material = mat; renderer.setRenderTarget(tgt); renderer.render(fsScene, fsCam); }
let rtMain, rtA, rtB; const dbs = new THREE.Vector2(), blurTexel = new THREE.Vector2();
function makeRTs() {
  renderer.getDrawingBufferSize(dbs);
  [rtMain, rtA, rtB].forEach(r => r && r.dispose());
  // Multisample half-float targets have poor availability on mobile Safari.
  rtMain = new THREE.WebGLRenderTarget(dbs.x, dbs.y, { type: isTouchDevice ? THREE.UnsignedByteType : THREE.HalfFloatType, samples: isTouchDevice ? 0 : 4 });
  const bw = Math.max(1, dbs.x >> 2), bh = Math.max(1, dbs.y >> 2);
  // The original half-float postprocess targets can fail framebuffer completeness on some iOS GPUs.
  const postType = isTouchDevice ? THREE.UnsignedByteType : THREE.HalfFloatType;
  rtA = new THREE.WebGLRenderTarget(bw, bh, { type: postType });
  rtB = new THREE.WebGLRenderTarget(bw, bh, { type: postType });
  brightMat.uniforms.uTexel.value.set(1 / dbs.x, 1 / dbs.y);
  blurTexel.set(1 / bw, 1 / bh);
  compMat.uniforms.uRes.value.copy(dbs);
}

/* =========================================================
   HUD
   ========================================================= */
const hud = $('hud'), ctx = hud.getContext('2d');
let HD = isTouchDevice ? 1 : Math.min(window.devicePixelRatio || 1, 2);
const speedLines = Array.from({ length: 46 }, () => ({ a: Math.random() * 6.283, r: Math.random(), l: rand(0.08, 0.25), w: rand(0.5, 2) }));
function resize() {
  renderer.setSize(innerWidth, innerHeight, false);
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  hud.width = innerWidth * HD; hud.height = innerHeight * HD;
  compMat.uniforms.uAspect.value = camera.aspect;
  makeRTs();
}
const _pv = V3();
function proj(p) {
  _pv.copy(p).applyMatrix4(camera.matrixWorldInverse); const behind = _pv.z > 0;
  _pv.copy(p).project(camera);
  return { x: (_pv.x * 0.5 + 0.5) * hud.width, y: (-_pv.y * 0.5 + 0.5) * hud.height, behind };
}
const HUDC = '#a6f7d6', HUDW = 'rgba(166,247,214,', RED = '#ff4f6a';
function txt(s, x, y, size, col = HUDC, align = 'center', font = 'Consolas,"SF Mono",monospace') {
  ctx.font = `600 ${size}px ${font}`; ctx.textAlign = align; ctx.fillStyle = col; ctx.fillText(s, x, y);
}
function drawHUD(dt) {
  const W = hud.width, H = hud.height, s = isTouchDevice ? Math.max(H / 1000, 0.72 * HD) : H / 1000, cx = W / 2, cy = H / 2;
  ctx.clearRect(0, 0, W, H);
  const P = player;
  // 速度線
  const sl = clamp((P.speed - 300) / 100, 0, 1) * (state === 'play' ? 1 : 0);
  if (sl > 0.01) {
    ctx.save(); ctx.strokeStyle = `rgba(255,255,255,${0.32 * sl})`;
    for (const L of speedLines) {
      L.r += dt * 1.8; if (L.r > 1.1) { L.r = rand(0.3, 0.6); L.a = Math.random() * 6.283; L.l = rand(0.08, 0.25); }
      const r1 = L.r * Math.hypot(cx, cy), r2 = r1 + L.l * H;
      ctx.lineWidth = L.w * s * 2; ctx.beginPath();
      ctx.moveTo(cx + Math.cos(L.a) * r1, cy + Math.sin(L.a) * r1); ctx.lineTo(cx + Math.cos(L.a) * r2, cy + Math.sin(L.a) * r2); ctx.stroke();
    }
    ctx.restore();
  }
  if (state === 'title' || state === 'loading') return;
  ctx.save();
  ctx.lineCap = 'round'; ctx.shadowColor = 'rgba(40,120,110,.65)'; ctx.shadowBlur = 5 * s;
  ctx.strokeStyle = HUDC; ctx.fillStyle = HUDC; ctx.lineWidth = 2 * s;
  if (P.alive) {
    fwdOf(P.q, _f);
    // 準星
    const bs = proj(_t.copy(P.pos).addScaledVector(_f, 2000));
    const bx = bs.x, by = bs.y;
    ctx.beginPath(); ctx.moveTo(bx - 26 * s, by); ctx.lineTo(bx - 9 * s, by); ctx.moveTo(bx + 9 * s, by); ctx.lineTo(bx + 26 * s, by);
    ctx.moveTo(bx, by - 9 * s); ctx.lineTo(bx, by - 20 * s); ctx.stroke();
    ctx.beginPath(); ctx.arc(bx, by, 3 * s, 0, 6.283); ctx.fill();
    // 俯仰梯
    const hdg = Math.atan2(_f.x, _f.z); const hF = V3(Math.sin(hdg), 0, Math.cos(hdg)); const hR = V3(-hF.z, 0, hF.x);
    ctx.lineWidth = 1.4 * s; ctx.font = `600 ${13 * s}px Consolas,monospace`;
    for (let a = -80; a <= 80; a += 10) {
      const r = a * Math.PI / 180;
      const dir = V3().copy(hF).multiplyScalar(Math.cos(r)).addScaledVector(UP, Math.sin(r));
      const c0 = V3().copy(camera.position).addScaledVector(dir, 1000);
      const p1 = proj(V3().copy(c0).addScaledVector(hR, -70)), p2 = proj(V3().copy(c0).addScaledVector(hR, 70));
      if (p1.behind || p2.behind) continue;
      const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2;
      if (Math.hypot(mx - cx, my - cy) > 0.3 * H) continue;
      const dx = p2.x - p1.x, dy = p2.y - p1.y;
      ctx.globalAlpha = a === 0 ? 0.85 : 0.55;
      ctx.setLineDash(a < 0 ? [6 * s, 5 * s] : []);
      ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(mx - dx * 0.18, my - dy * 0.18); ctx.moveTo(mx + dx * 0.18, my + dy * 0.18); ctx.lineTo(p2.x, p2.y); ctx.stroke();
      if (a !== 0) { ctx.fillText(String(a), p2.x + 8 * s, p2.y + 4 * s); }
    }
    ctx.setLineDash([]); ctx.globalAlpha = 1;
    // 速度 / 高度
    ctx.lineWidth = 1.6 * s;
    const bxL = cx - 330 * s, bxR = cx + 330 * s;
    ctx.strokeRect(bxL - 64 * s, cy - 18 * s, 78 * s, 34 * s); ctx.strokeRect(bxR - 14 * s, cy - 18 * s, 84 * s, 34 * s);
    txt(String(Math.round(P.speed * 3.6)), bxL - 25 * s, cy + 8 * s, 22 * s);
    txt(String(Math.round(P.pos.y * 3.281)), bxR + 28 * s, cy + 8 * s, 22 * s);
    txt('SPEED km/h', bxL - 25 * s, cy - 26 * s, 11 * s); txt('ALT ft', bxR + 28 * s, cy - 26 * s, 11 * s);
    txt(`THR ${Math.round(P.thr * 100)}%`, bxL - 25 * s, cy + 38 * s, 11 * s, P.thr > 0.8 ? '#ffd27a' : HUDC);
    // 航向
    const hdgDeg = ((-hdg * 180 / Math.PI) + 720) % 360;
    ctx.save(); ctx.beginPath(); ctx.rect(cx - 160 * s, 40 * s, 320 * s, 40 * s); ctx.clip();
    for (let d = -40; d <= 40; d += 5) {
      const val = Math.round(hdgDeg / 5) * 5 + d, x = cx + (val - hdgDeg) * 4 * s;
      ctx.beginPath(); ctx.moveTo(x, 62 * s); ctx.lineTo(x, (val % 10 === 0 ? 52 : 57) * s); ctx.stroke();
      if (val % 10 === 0) txt(String(((val % 360) + 360) % 360).padStart(3, '0'), x, 76 * s, 11 * s);
    }
    ctx.restore();
    ctx.beginPath(); ctx.moveTo(cx, 46 * s); ctx.lineTo(cx - 5 * s, 38 * s); ctx.lineTo(cx + 5 * s, 38 * s); ctx.closePath(); ctx.fill();

    // 敵機標記
    for (const e of enemies) {
      if (!e.alive) continue;
      const p = proj(e.pos); if (p.behind || p.x < 0 || p.x > W || p.y < 0 || p.y > H) continue;
      const d = e.pos.distanceTo(P.pos), isT = e === target;
      const sz = clamp(1800 / d, 9, 26) * s;
      ctx.strokeStyle = isT ? (locked ? RED : '#ffb0ba') : '#ff8a9a'; ctx.fillStyle = ctx.strokeStyle; ctx.lineWidth = (isT ? 2.2 : 1.6) * s;
      const b = sz * 0.45;
      ctx.beginPath();
      ctx.moveTo(p.x - sz, p.y - sz + b); ctx.lineTo(p.x - sz, p.y - sz); ctx.lineTo(p.x - sz + b, p.y - sz);
      ctx.moveTo(p.x + sz - b, p.y - sz); ctx.lineTo(p.x + sz, p.y - sz); ctx.lineTo(p.x + sz, p.y - sz + b);
      ctx.moveTo(p.x + sz, p.y + sz - b); ctx.lineTo(p.x + sz, p.y + sz); ctx.lineTo(p.x + sz - b, p.y + sz);
      ctx.moveTo(p.x - sz + b, p.y + sz); ctx.lineTo(p.x - sz, p.y + sz); ctx.lineTo(p.x - sz, p.y + sz - b);
      ctx.stroke();
      txt('J-16', p.x + sz + 6 * s, p.y - sz + 10 * s, 11 * s, ctx.strokeStyle, 'left');
      if (isT) {
        txt(`${(d / 1000).toFixed(1)}km`, p.x + sz + 6 * s, p.y - sz + 24 * s, 11 * s, ctx.strokeStyle, 'left');
        if (!locked && lockT > 0) {
          const k = lockT / 0.5, rr = (70 - 48 * k) * s;
          ctx.beginPath(); ctx.arc(p.x, p.y, rr, 0, 6.283); ctx.stroke();
        }
        if (locked) {
          ctx.beginPath(); const r2 = sz + 8 * s; ctx.moveTo(p.x, p.y - r2); ctx.lineTo(p.x + r2, p.y); ctx.lineTo(p.x, p.y + r2); ctx.lineTo(p.x - r2, p.y); ctx.closePath(); ctx.stroke();
          txt('LOCK', p.x, p.y + r2 + 16 * s, 12 * s, RED);
        }
        if (d < 1500) {
          const lp = proj(_t.copy(e.pos).addScaledVector(e.vel, d / 1150).addScaledVector(P.vel, -d / 1150 * 0.0));
          if (!lp.behind) { ctx.strokeStyle = HUDC; ctx.lineWidth = 1.6 * s; ctx.beginPath(); ctx.arc(lp.x, lp.y, 12 * s, 0, 6.283); ctx.stroke(); ctx.beginPath(); ctx.arc(lp.x, lp.y, 2 * s, 0, 6.283); ctx.fillStyle = HUDC; ctx.fill(); }
        }
      }
    }
    // 畫面外目標箭頭
    if (target && target.alive) {
      const p = proj(target.pos);
      if (p.behind || p.x < 0 || p.x > W || p.y < 0 || p.y > H) {
        _t.copy(target.pos).applyMatrix4(camera.matrixWorldInverse);
        const a = Math.atan2(-_t.y, _t.x), R = 0.3 * H;
        const ax = cx + Math.cos(a) * R, ay = cy + Math.sin(a) * R;
        ctx.save(); ctx.translate(ax, ay); ctx.rotate(a); ctx.fillStyle = '#ffb0ba';
        ctx.beginPath(); ctx.moveTo(18 * s, 0); ctx.lineTo(-8 * s, -11 * s); ctx.lineTo(-3 * s, 0); ctx.lineTo(-8 * s, 11 * s); ctx.closePath(); ctx.fill(); ctx.restore();
        txt(`${(target.pos.distanceTo(P.pos) / 1000).toFixed(1)}km`, ax, ay + 26 * s, 11 * s, '#ffb0ba');
      }
    }
    // 來襲飛彈
    let threat = false;
    for (const m of missiles) {
      if (m.owner !== 'e' || m.target !== player) continue; threat = true;
      const p = proj(m.pos); if (p.behind) continue;
      ctx.strokeStyle = RED; ctx.lineWidth = 2 * s; ctx.beginPath(); ctx.arc(p.x, p.y, 9 * s, 0, 6.283); ctx.stroke(); txt('MSL', p.x, p.y - 14 * s, 10 * s, RED);
    }
    alertT -= dt;
    if (threat && alertT <= 0) { SFX.alert(); alertT = 0.24; }
    // 警告
    const blink = Math.floor(gTime * 5) % 2 === 0;
    let wy = cy + 0.24 * H;
    const warn = (t, c = RED) => { if (blink) txt(t, cx, wy, 26 * s, c); wy += 32 * s; };
    if (threat) warn('MISSILE ALERT');
    const gh = groundH(P.pos.x, P.pos.z);
    if (P.pos.y - gh < 450 && _f.y < -0.05) warn('PULL UP');
    if (P.speed < 120) warn('STALL', '#ffd27a');
    if (Math.hypot(P.pos.x, P.pos.z) > 17500) warn('RETURN TO COMBAT AREA', '#ffd27a');

    // 雷達
    const rx = W - 130 * s, ry = H - 140 * s, RR = 100 * s, RANGE = 9000;
    ctx.fillStyle = 'rgba(10,35,45,.35)'; ctx.strokeStyle = HUDC; ctx.lineWidth = 1.4 * s;
    ctx.beginPath(); ctx.arc(rx, ry, RR, 0, 6.283); ctx.fill(); ctx.stroke();
    ctx.globalAlpha = 0.4; ctx.beginPath(); ctx.arc(rx, ry, RR / 2, 0, 6.283); ctx.moveTo(rx - RR, ry); ctx.lineTo(rx + RR, ry); ctx.moveTo(rx, ry - RR); ctx.lineTo(rx, ry + RR); ctx.stroke(); ctx.globalAlpha = 1;
    const rp = (p) => { const dx = p.x - P.pos.x, dz = p.z - P.pos.z; let X = dx * hR.x + dz * hR.z, Y = dx * hF.x + dz * hF.z; const L = Math.hypot(X, Y), k = Math.min(L, RANGE) / Math.max(L, 1e-3); return [rx + X * k / RANGE * RR, ry - Y * k / RANGE * RR]; };
    for (const e of enemies) {
      if (!e.alive) continue; const [x, y] = rp(e.pos); ctx.fillStyle = e === target ? RED : '#ff8a9a';
      if (e === target) { ctx.beginPath(); ctx.moveTo(x, y - 6 * s); ctx.lineTo(x + 6 * s, y); ctx.lineTo(x, y + 6 * s); ctx.lineTo(x - 6 * s, y); ctx.fill(); }
      else { ctx.beginPath(); ctx.arc(x, y, 3.5 * s, 0, 6.283); ctx.fill(); }
    }
    for (const m of missiles) { const [x, y] = rp(m.pos); ctx.fillStyle = m.owner === 'e' ? RED : '#fff'; ctx.fillRect(x - 1.5 * s, y - 1.5 * s, 3 * s, 3 * s); }
    ctx.fillStyle = HUDC; ctx.beginPath(); ctx.moveTo(rx, ry - 8 * s); ctx.lineTo(rx + 6 * s, ry + 6 * s); ctx.lineTo(rx - 6 * s, ry + 6 * s); ctx.closePath(); ctx.fill();
    txt(`${RANGE / 1000}km`, rx + RR - 6 * s, ry + RR + 4 * s, 10 * s, HUDC, 'right');

    // 狀態
    const lx = 46 * s, ly = H - 150 * s;
    txt('AURORA 1 · F-16C', lx, ly, 13 * s, HUDC, 'left');
    txt('DMG', lx, ly + 28 * s, 12 * s, HUDC, 'left');
    const dmg = 100 - P.hp; ctx.strokeStyle = HUDC; ctx.strokeRect(lx + 40 * s, ly + 17 * s, 160 * s, 12 * s);
    ctx.fillStyle = dmg > 60 ? RED : dmg > 30 ? '#ffd27a' : HUDC; ctx.fillRect(lx + 40 * s, ly + 17 * s, 160 * s * dmg / 100, 12 * s);
    txt(`${Math.round(dmg)}%`, lx + 210 * s, ly + 28 * s, 12 * s, ctx.fillStyle, 'left');
    txt(`MSL  ${String(P.msl).padStart(3, ' ')}`, lx, ly + 56 * s, 16 * s, P.msl > 10 ? HUDC : RED, 'left');
    txt(`FLR  ${String(P.flares).padStart(3, ' ')}`, lx, ly + 80 * s, 16 * s, HUDC, 'left');
    txt('GUN   ∞', lx, ly + 104 * s, 16 * s, HUDC, 'left');
  }
  // 分數
  txt(`SCORE ${String(score).padStart(7, '0')}`, W - 40 * s, 52 * s, 18 * s, '#ffffff', 'right');
  txt(`WAVE ${wave}   TARGET ${enemies.filter(e => e.alive).length}   KILLS ${kills}`, W - 40 * s, 76 * s, 12 * s, HUDC, 'right');
  if (comboT > 0 && combo > 1) txt(`COMBO ×${combo}`, W - 40 * s, 98 * s, 14 * s, '#ffd27a', 'right');

  // 彈出字
  let py = cy - 0.17 * H;
  for (const p of popups) {
    p.t += dt; const a = clamp(1.6 - p.t, 0, 1), sc = 1 + Math.max(0, 0.25 - p.t) * 2;
    ctx.globalAlpha = a; txt(p.text, cx, py, 22 * s * sc, p.col); py -= 30 * s;
  }
  ctx.globalAlpha = 1;
  for (let i = popups.length - 1; i >= 0; i--) if (popups[i].t > 1.6) popups.splice(i, 1);

  // 波次橫幅
  if (banner) {
    banner.t += dt; const a = clamp(Math.min(banner.t * 2, 3.2 - banner.t), 0, 1);
    ctx.globalAlpha = a; ctx.shadowColor = 'rgba(255,190,120,.8)'; ctx.shadowBlur = 18 * s;
    txt(banner.title, cx, cy - 0.28 * H, 44 * s, '#ffffff', 'center', '"Noto Serif JP","Yu Mincho",serif');
    ctx.shadowBlur = 6 * s; txt(banner.sub, cx, cy - 0.28 * H + 34 * s, 16 * s, '#ffe2b8', 'center', '"Noto Sans TC","Microsoft JhengHei",sans-serif');
    ctx.globalAlpha = 1; if (banner.t > 3.2) banner = null;
  }
  // 無線電字幕
  if (!radioCur && radioQ.length) radioCur = { ...radioQ.shift(), t: 0 };
  if (radioCur) {
    radioCur.t += dt; const dur = 2.2 + radioCur.text.length * 0.07;
    const shown = radioCur.text.slice(0, Math.floor(radioCur.t * 30));
    const a = clamp(Math.min(radioCur.t * 4, dur - radioCur.t), 0, 1);
    ctx.globalAlpha = a; ctx.shadowColor = 'rgba(0,10,30,.9)'; ctx.shadowBlur = 8 * s;
    const yy = H - 70 * s;
    txt(`【${radioCur.who}】`, cx, yy - 26 * s, 14 * s, '#ffd9a0', 'center', '"Noto Sans TC","Microsoft JhengHei",sans-serif');
    txt(shown, cx, yy, 18 * s, '#ffffff', 'center', '"Noto Sans TC","Microsoft JhengHei",sans-serif');
    ctx.globalAlpha = 1; if (radioCur.t > dur) radioCur = null;
  }
  ctx.restore();
}

/* =========================================================
   相機 / 雲霧 / 太陽遮蔽
   ========================================================= */
function cloudWhite(p) {
  let w = 0;
  for (const c of clouds) {
    const dx = (p.x - c.c.x) / c.rx, dy = (p.y - c.c.y) / c.ry, dz = (p.z - c.c.z) / c.rz;
    const d = Math.sqrt(dx * dx + dy * dy + dz * dz); if (d < 1.05) w = Math.max(w, clamp((1.05 - d) / 0.45, 0, 1));
  }
  if (Math.abs(p.y - CLOUDSEA_Y) < 30) w = Math.max(w, 0.35 * (1 - Math.abs(p.y - CLOUDSEA_Y) / 30));
  return w * 0.88;
}
function sunOccluded(o) {
  for (const c of clouds) {
    const ox = (o.x - c.c.x) / c.rx, oy = (o.y - c.c.y) / c.ry, oz = (o.z - c.c.z) / c.rz;
    const dx = SUN_DIR.x / c.rx, dy = SUN_DIR.y / c.ry, dz = SUN_DIR.z / c.rz;
    const A = dx * dx + dy * dy + dz * dz, B = 2 * (ox * dx + oy * dy + oz * dz), Cc = ox * ox + oy * oy + oz * oz - 0.75;
    const disc = B * B - 4 * A * Cc; if (disc > 0 && (-B + Math.sqrt(disc)) > 0) return true;
  }
  return false;
}
let sunVis = 0, whiteNow = 0, titleAng = 0;
function updateCamera(dt) {
  const P = player;
  if (state === 'title' || state === 'loading') {
    titleAng += dt * 0.09;
    camera.position.set(P.pos.x + Math.sin(titleAng) * 46, P.pos.y + 9 + Math.sin(titleAng * 2.3) * 5, P.pos.z + Math.cos(titleAng) * 46);
    camera.up.set(0, 1, 0); camera.lookAt(P.pos);
    camera.fov = 52;
  } else if (state === 'dead') {
    deathCam.lerp(_t.copy(P.pos).add(V3(60, 30, -60)), 1 - Math.exp(-dt * 0.5));
    camera.position.copy(deathCam); camera.lookAt(P.pos);
  } else {
    camQ.slerp(P.q, 1 - Math.exp(-dt * 6.5));
    const boost = P.thr > 0.8 ? 1 : 0;
    _o.set(0, 5.4, -23 - boost * 3).applyQuaternion(camQ);
    camera.position.copy(P.pos).add(_o);
    camera.quaternion.copy(camQ).multiply(Q_FLIP).multiply(Q_TILT);
    camera.fov += (62 + clamp((P.speed - 258) / 150, -0.4, 1) * 14 - camera.fov) * (1 - Math.exp(-dt * 3));
  }
  if (shake > 0.001) { camera.position.x += rand(-1, 1) * shake * 1.6; camera.position.y += rand(-1, 1) * shake * 1.6; camera.position.z += rand(-1, 1) * shake * 1.6; shake *= Math.exp(-dt * 4); }
  camera.updateProjectionMatrix(); camera.updateMatrixWorld();
}

/* =========================================================
   主迴圈
   ========================================================= */
let last = performance.now();
function frame(now) {
  requestAnimationFrame(frame);
  now = performance.now(); let dt = clamp((now - last) / 1000, 0, 0.05); last = now;
  if (state === 'paused') dt = 0;
  gTime += dt;
  if (state !== 'paused') {
    hitPopT -= dt; comboT -= dt; dmgFlash *= Math.exp(-dt * 2.2); flash *= Math.exp(-dt * 6);
    updatePlayer(dt);
    updateEnemies(dt);
    updateMissiles(dt);
    updateBullets(dt);
    smoke.update(dt); glow.update(dt);
    for (const R of rings) {
      if (!R.m.visible) continue; R.t += dt * 1.6; if (R.t >= 1) { R.m.visible = false; continue; }
      R.m.scale.setScalar(R.s * (1 - Math.pow(1 - R.t, 3))); R.m.material.opacity = (1 - R.t) * 0.55; R.m.lookAt(camera.position);
    }
    if (state === 'play') {
      if (enemies.length === 0) {
        if (wave > 0 && !clearSaid) { clearSaid = true; radio('AWACS Shiori', '空域淨空！呼……等等，又有新的訊號進來了。'); banner = { title: 'AREA CLEAR', sub: `目前分數 ${score}`, t: 0 }; }
        waveTimer -= dt;
        if (waveTimer <= 0) { spawnWave(); clearSaid = false; waveTimer = 4.5; }
      } else waveTimer = 4.5;
    }
    if (state === 'dead') {
      deadT += dt;
      if (deadT > 2.8 && $('over').classList.contains('hidden')) {
        $('overS').innerHTML = `SCORE　${score}<br>KILLS　${kills}　／　WAVE　${wave}<br><span style="opacity:.7;font-size:13px">按 Enter 或點擊重新出擊</span>`;
        $('over').classList.remove('hidden');
      }
    }
  }
  updateCamera(dt);
  updateTouchUI();

  // 跟隨相機的大型平面
  sky.position.copy(camera.position);
  ocean.position.set(Math.round(camera.position.x / 100) * 100, 0, Math.round(camera.position.z / 100) * 100);
  cloudSea.position.set(ocean.position.x, CLOUDSEA_Y, ocean.position.z);
  cirrus.position.set(ocean.position.x, 8200, ocean.position.z);

  // uniforms
  renderer.getDrawingBufferSize(dbs);
  const pScale = dbs.y / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
  smoke.mat.uniforms.uScale.value = glow.mat.uniforms.uScale.value = fluffMat.uniforms.uScale.value = pScale;
  cloudUniforms.uCam.value.copy(camera.position); cloudUniforms.uTime.value = gTime;
  oceanMat.uniforms.uCam.value.copy(camera.position); oceanMat.uniforms.uTime.value = gTime;

  const sp = V3().copy(camera.position).addScaledVector(SUN_DIR, 10000).project(camera);
  const camF = V3(0, 0, -1).applyQuaternion(camera.quaternion);
  const onScr = camF.dot(SUN_DIR) > 0 && Math.abs(sp.x) < 1.25 && Math.abs(sp.y) < 1.25;
  const occ = onScr && sunOccluded(camera.position);
  sunVis += ((onScr && !occ ? 1 : 0) - sunVis) * (1 - Math.exp(-dt * 6));
  whiteNow += (cloudWhite(camera.position) - whiteNow) * (1 - Math.exp(-dt * 8));
  smoke.mat.uniforms.uL.value.set(sp.x, sp.y).normalize();
  const cu = compMat.uniforms;
  cu.uSunUV.value.set(sp.x * 0.5 + 0.5, sp.y * 0.5 + 0.5); cu.uSunVis.value = sunVis * (1 - whiteNow);
  cu.uWhite.value = whiteNow; cu.uDmg.value = Math.max(dmgFlash, player.alive && state === 'play' ? clamp((50 - player.hp) / 50, 0, 1) * (0.35 + 0.15 * Math.sin(gTime * 6)) : 0);
  cu.uFlash.value = flash; cu.uBoost.value = state === 'play' ? clamp((player.speed - 300) / 100, 0, 1) : 0; cu.uTime.value = gTime;

  // render
  renderer.setRenderTarget(rtMain); renderer.render(scene, camera);
  brightMat.uniforms.t.value = rtMain.texture; pass(brightMat, rtA);
  const tx = blurTexel;
  for (const k of (isTouchDevice && mobileQuality === 'eco' ? [1] : [1, 2])) {
    blurMat.uniforms.t.value = rtA.texture; blurMat.uniforms.uDir.value.set(tx.x * k, 0); pass(blurMat, rtB);
    blurMat.uniforms.t.value = rtB.texture; blurMat.uniforms.uDir.value.set(0, tx.y * k); pass(blurMat, rtA);
  }
  cu.tS.value = rtMain.texture; cu.tB.value = rtA.texture; pass(compMat, null);
  drawHUD(dt);
  boot.ready();
}

/* =========================================================
   流程控制 / 輸入
   ========================================================= */
function resetGame() {
  for (const e of enemies) scene.remove(e.mesh); enemies.length = 0;
  for (const m of missiles) scene.remove(m.mesh); missiles.length = 0; decoys.length = 0;
  for (const b of bullets) b.on = false;
  Object.assign(player, { speed: 260, hp: 100, alive: true, msl: 96, flares: 36, thr: 0.5, pi: 0, ri: 0, yi: 0, lastDmg: -10 });
  player.pos.copy(START); player.q.identity(); player.mesh.visible = true; camQ.copy(player.q);
  score = 0; kills = 0; wave = 0; combo = 0; clearSaid = false; target = null; lockT = 0; locked = false; waveTimer = 2.5; dmgFlash = 0;
  player.inv = gTime + 3; popups.length = 0; radioQ.length = 0; radioCur = null; banner = null;
}
function startGame() {
  auInit(); resetGame(); state = 'play';
  $('title').classList.add('hidden'); $('over').classList.add('hidden'); $('pause').classList.add('hidden');
  mobileStick.x=mobileStick.y=0; mobileAB=false;keys.ShiftLeft=false; $('abBtn').classList.remove('on'); placeStick(); updateTouchUI();
  radio('AWACS Shiori', 'Aurora 1，起飛確認。今天的雲很美——但別看太久喔。');
}

/* =========================================================
   Mobile inputs.  No visual/cloud/AI/weapon model changes.
   ========================================================= */
const touchLayer = $('touchControls');
function updateTouchUI() {
  if (!isTouchDevice) return;
  touchLayer.classList.toggle('active', state === 'play' || state === 'paused');
  $('pauseBtn').textContent = state === 'paused' ? 'RESUME' : 'PAUSE';
}
function placeStick() {
  const knob = $('stickCap');
  const pad = $('flightStick');
  const range = (pad.clientWidth - knob.clientWidth) / 2 - 4;
  knob.style.transform = `translate(calc(-50% + ${mobileStick.x*range}px),calc(-50% + ${mobileStick.y*range}px))`;
}
function setStickFromEvent(ev) {
  const bounds = $('flightStick').getBoundingClientRect();
  const dx = (ev.clientX - (bounds.left + bounds.width/2)) / (bounds.width*.38);
  const dy = (ev.clientY - (bounds.top + bounds.height/2)) / (bounds.height*.38);
  const len = Math.hypot(dx,dy); const n = Math.max(1,len);
  mobileStick.x = dx / n; mobileStick.y = dy / n;
  placeStick();
}
if (isTouchDevice) {
  const stick = $('flightStick');let stickPointer = null;
  stick.addEventListener('pointerdown', ev => {
    if (ev.target.closest('button')) return;
    ev.preventDefault();stickPointer = ev.pointerId;mobileStick.active = true;
    stick.setPointerCapture(ev.pointerId);setStickFromEvent(ev);
  });
  stick.addEventListener('pointermove', ev => { if (stickPointer === ev.pointerId) { ev.preventDefault();setStickFromEvent(ev); }});
  const releaseStick = ev => { if (stickPointer === ev.pointerId) { stickPointer = null; mobileStick.active = false; /* retain last deflection */ }};
  stick.addEventListener('pointerup',releaseStick);stick.addEventListener('pointercancel',releaseStick);
  $('stickZero').addEventListener('pointerdown', ev => ev.stopPropagation());
  $('stickZero').addEventListener('click', () => {mobileStick.x = mobileStick.y = 0;placeStick();});
  function tap(id,fn) { const el=$(id);el.addEventListener('pointerdown', ev=>{ev.preventDefault();ev.stopPropagation();fn();el.classList.add('pressed');});el.addEventListener('pointerup',()=>el.classList.remove('pressed'));el.addEventListener('pointercancel',()=>el.classList.remove('pressed')); }
  function hold(id,key) {
    const el=$(id);
    el.addEventListener('pointerdown',ev=>{ev.preventDefault();el.setPointerCapture(ev.pointerId);keys[key]=true;el.classList.add('pressed');});
    const stop=()=>{keys[key]=false;el.classList.remove('pressed');};
    el.addEventListener('pointerup',stop);el.addEventListener('pointercancel',stop);el.addEventListener('lostpointercapture',stop);
  }
  function pulse(id,key,duration=170) {let timer;tap(id,()=>{keys[key]=true;clearTimeout(timer);timer=setTimeout(()=>{keys[key]=false;$(id).classList.remove('pressed')},duration);});}
  pulse('missileBtn','Space',190);hold('gunBtn','KeyJ');pulse('flareBtn','KeyX',150);hold('brkBtn','KeyC');
  tap('abBtn',()=>{mobileAB=!mobileAB;keys.ShiftLeft=mobileAB;$('abBtn').classList.toggle('on',mobileAB);});
  tap('targetBtn',()=>{if(state==='play')cycleTarget();});
  tap('pitchBtn',()=>{invertPitch=!invertPitch;popup(invertPitch?'PITCH INVERTED':'PITCH NORMAL');});
  tap('pauseBtn',()=>{if(state==='play'){state='paused';$('pause').classList.remove('hidden');}
                       else if(state==='paused'){state='play';$('pause').classList.add('hidden');}updateTouchUI();});
  tap('qualityBtn',()=>{ mobileQuality = mobileQuality === 'eco' ? 'hd' : 'eco';
    const ratio=mobileQuality==='eco'?(safeMode?0.65:0.8):1.1;
    renderer.setPixelRatio(ratio);$('qualityBtn').textContent=mobileQuality.toUpperCase();resize();
    popup(mobileQuality==='eco'?'ECO · 更順暢':'HD · 更清晰'); });
  document.addEventListener('touchmove', ev => { if(ev.cancelable) ev.preventDefault(); }, {passive:false});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){keys.KeyJ=false;keys.KeyC=false;keys.Space=false;keys.KeyX=false;}});
  // Interactive title buttons may be behind the mobile keyboard on tiny screens.
  $('startBtn').textContent='TAP TO TAKE OFF';
  $('overS').style.maxWidth='90vw';
}

$('startBtn').onclick = startGame;
$('retryBtn').onclick = startGame;
addEventListener('keydown', e => {
  if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code)) e.preventDefault();
  keys[e.code] = true;
  if (e.repeat) return;
  if (e.code === 'KeyR' && state === 'play') cycleTarget();
  if (e.code === 'KeyI') { invertPitch = !invertPitch; popup(invertPitch ? 'PITCH: W = 拉升' : 'PITCH: S = 拉升'); }
  if (e.code === 'KeyP' || e.code === 'Escape') {
    if (state === 'play') { state = 'paused'; $('pause').classList.remove('hidden'); }
    else if (state === 'paused') { state = 'play'; $('pause').classList.add('hidden'); }
  }
  if (e.code === 'Enter' && (state === 'title' || (state === 'dead' && deadT > 2.8))) startGame();
});
addEventListener('keyup', e => { keys[e.code] = false; });
canvas.addEventListener('mousedown', e => { keys['Mouse' + e.button] = true; });
addEventListener('mouseup', e => { keys['Mouse' + e.button] = false; });
addEventListener('contextmenu', e => e.preventDefault());
addEventListener('blur', () => { for (const k in keys) keys[k] = false; });
addEventListener('resize', resize);

boot.stage('正在繪製第一幀…');
resize();
resetGame();
state = 'title';
$('title').classList.remove('hidden');
requestAnimationFrame(frame);
