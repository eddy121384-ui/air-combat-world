// XinyiLook look-dev preview renderer (WebGL2, headless Chromium).
//
// Not a product and not a second geometry path: it loads the same look GLBs
// the Unreal adapters import and runs the same shader source
// (tools/lookdev/shaders/xinyi_city.hlsl) through a GLSL macro prelude, with a
// lighting model approximating the Unreal rig (sun + sky + height fog +
// filmic tonemap). It exists so the look can be iterated where Unreal is not
// available.

const gl = document.getElementById('c').getContext('webgl2', {
  antialias: false, preserveDrawingBuffer: true, alpha: false,
});
if (!gl) throw new Error('no webgl2');
if (!gl.getExtension('EXT_color_buffer_float')) throw new Error('no float rt');
gl.getExtension('OES_texture_float_linear');

const PRELUDE = `#version 300 es
precision highp float;
precision highp int;
#define float2 vec2
#define float3 vec3
#define float4 vec4
#define frac fract
#define lerp mix
#define saturate(x) clamp((x), 0.0, 1.0)
`;

async function fetchText(u) { const r = await fetch(u); if (!r.ok) throw new Error(u); return r.text(); }
async function fetchBin(u) { const r = await fetch(u); if (!r.ok) throw new Error(u); return r.arrayBuffer(); }

// ---------------------------------------------------------------- GLB -------
function parseGLB(buf) {
  const dv = new DataView(buf);
  const jl = dv.getUint32(12, true);
  const json = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 20, jl)));
  const binOff = 20 + jl + 8;
  const TA = { 5126: Float32Array, 5121: Uint8Array, 5125: Uint32Array, 5123: Uint16Array };
  const NC = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 };
  const acc = (i) => {
    const a = json.accessors[i]; const v = json.bufferViews[a.bufferView];
    const T = TA[a.componentType];
    const off = binOff + (v.byteOffset || 0) + (a.byteOffset || 0);
    return { data: new T(buf, off, a.count * NC[a.type]), size: NC[a.type], type: a.componentType, norm: !!a.normalized, count: a.count };
  };
  const prims = [];
  for (const m of json.meshes) for (const p of m.primitives) {
    const at = {};
    for (const [k, v] of Object.entries(p.attributes)) at[k] = acc(v);
    prims.push({ attrs: at, indices: acc(p.indices), material: json.materials ? json.materials[p.material].name : '' });
  }
  return prims;
}

const LOC = { POSITION: 0, NORMAL: 1, TEXCOORD_0: 2, TEXCOORD_1: 3, TEXCOORD_2: 4, INST0: 5, INST1: 6 };
const DEFAULTS = { 1: [0, 1, 0, 0], 2: [0, 0, 0, 0], 3: [0, 3.2, 0, 0], 4: [0, 0, 0, 0] };

function upload(prim) {
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);
  for (const [name, loc] of Object.entries(LOC)) {
    if (loc >= 5) continue;
    const a = prim.attrs[name];
    if (!a) { gl.disableVertexAttribArray(loc); gl.vertexAttrib4f(loc, ...DEFAULTS[loc]); continue; }
    const b = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, b);
    gl.bufferData(gl.ARRAY_BUFFER, a.data, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, a.size, a.type, a.norm, 0, 0);
  }
  const ib = gl.createBuffer();
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, prim.indices.data, gl.STATIC_DRAW);
  gl.bindVertexArray(null);
  return { vao, count: prim.indices.count };
}

function addInstances(obj, inst) {
  const n = inst.length;
  const a = new Float32Array(n * 8);
  inst.forEach((t, i) => { a.set([t.e, t.n, t.z, t.yaw, t.sx ?? t.s, t.sy ?? t.s, t.sz ?? t.s, t.v], i * 8); });
  gl.bindVertexArray(obj.vao);
  const b = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, b);
  gl.bufferData(gl.ARRAY_BUFFER, a, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(5); gl.vertexAttribPointer(5, 4, gl.FLOAT, false, 32, 0); gl.vertexAttribDivisor(5, 1);
  gl.enableVertexAttribArray(6); gl.vertexAttribPointer(6, 4, gl.FLOAT, false, 32, 16); gl.vertexAttribDivisor(6, 1);
  gl.bindVertexArray(null);
  obj.instances = n;
}

async function loadTexture(url) {
  const blob = await (await fetch(url)).blob();
  const bmp = await createImageBitmap(blob, { premultiplyAlpha: 'none', colorSpaceConversion: 'none' });
  const t = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, t);
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
  gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, bmp);
  gl.generateMipmap(gl.TEXTURE_2D);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  return t;
}
let groundTexture = null;

// ------------------------------------------------------------ shaders -------
function compile(type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(s);
    const lines = src.split('\n').map((l, i) => `${i + 1}: ${l}`);
    const m = /0:(\d+)/.exec(log);
    const ctx = m ? lines.slice(Math.max(0, +m[1] - 4), +m[1] + 2).join('\n') : '';
    throw new Error(log + '\n' + ctx);
  }
  return s;
}
function program(vs, fs) {
  const p = gl.createProgram();
  gl.attachShader(p, compile(gl.VERTEX_SHADER, vs));
  gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fs));
  for (const [n, l] of Object.entries(LOC)) gl.bindAttribLocation(p, l, 'a_' + n);
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const u = {};
  const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < n; i++) { const info = gl.getActiveUniform(p, i); u[info.name.replace('[0]', '')] = gl.getUniformLocation(p, info.name); }
  return { p, u };
}

const VS_WORLD = `
in vec3 a_POSITION; in vec3 a_NORMAL; in vec2 a_TEXCOORD_0; in vec2 a_TEXCOORD_1; in vec2 a_TEXCOORD_2;
uniform mat4 uViewProj; uniform vec3 uOffset;
out vec3 vW; out vec3 vN; out vec2 vUv0; out vec2 vUv1; out vec4 vCol;
void main() {
  vec3 w = vec3(a_POSITION.x, -a_POSITION.z, a_POSITION.y) + uOffset;   // game -> ENU
  vW = w; vN = vec3(a_NORMAL.x, -a_NORMAL.z, a_NORMAL.y);
  vUv0 = a_TEXCOORD_0; vUv1 = a_TEXCOORD_1; vCol = vec4(a_TEXCOORD_2, 0.0, 0.0);
  gl_Position = uViewProj * vec4(w, 1.0);
}`;

const VS_INST = `
in vec3 a_POSITION; in vec3 a_NORMAL; in vec2 a_TEXCOORD_2; in vec4 a_INST0; in vec4 a_INST1;
uniform mat4 uViewProj; uniform vec3 uOffset;
out vec3 vW; out vec3 vN; out vec2 vUv0; out vec2 vUv1; out vec4 vCol;
void main() {
  float c = cos(radians(a_INST0.w)), s = sin(radians(a_INST0.w));
  vec3 p = vec3(a_POSITION.x, -a_POSITION.z, a_POSITION.y) * a_INST1.xyz;
  vec3 n = normalize(vec3(a_NORMAL.x, -a_NORMAL.z, a_NORMAL.y) / a_INST1.xyz);
  p = vec3(c * p.x - s * p.y, s * p.x + c * p.y, p.z);
  n = vec3(c * n.x - s * n.y, s * n.x + c * n.y, n.z);
  vec3 w = p + a_INST0.xyz + uOffset;
  vW = w; vN = n; vUv0 = vec2(p.z, 0.0); vUv1 = vec2(0.0);
  vCol = vec4(a_TEXCOORD_2, (a_INST1.w + 0.5) / 4.0, 1.0);
  gl_Position = uViewProj * vec4(w, 1.0);
}`;
const VS_INST_SHADOW = `
in vec3 a_POSITION; in vec4 a_INST0; in vec4 a_INST1;
uniform mat4 uViewProj; uniform vec3 uOffset;
void main() {
  float c = cos(radians(a_INST0.w)), s = sin(radians(a_INST0.w));
  vec3 p = vec3(a_POSITION.x, -a_POSITION.z, a_POSITION.y) * a_INST1.xyz;
  p = vec3(c * p.x - s * p.y, s * p.x + c * p.y, p.z);
  gl_Position = uViewProj * vec4(p + a_INST0.xyz + uOffset, 1.0);
}`;

const VS_SHADOW = `
in vec3 a_POSITION;
uniform mat4 uViewProj; uniform vec3 uOffset;
void main() { gl_Position = uViewProj * vec4(vec3(a_POSITION.x, -a_POSITION.z, a_POSITION.y) + uOffset, 1.0); }`;
const FS_SHADOW = `out vec4 o; void main(){ o = vec4(1.0); }`;

const LIGHTING = `
uniform vec3 uCam; uniform vec3 uSunDir; uniform vec3 uSunRad; uniform vec3 uSkyZen; uniform vec3 uSkyHor;
uniform vec3 uGroundAmb; uniform vec3 uFogCol; uniform float uFogDen; uniform float uFogFall; uniform float uFogBase;
uniform float uNight; uniform float uLitFrac; uniform mat4 uShadowVP; uniform highp sampler2DShadow uShadow;
uniform int uKind; uniform float uNoShadow; uniform int uDebug;
const float PI = 3.14159265;

vec3 skyRad(vec3 d) {
  float h = clamp(d.z, -1.0, 1.0);
  vec3 c = mix(uSkyHor, uSkyZen, pow(clamp(h, 0.0, 1.0), 0.55));
  c = mix(c, uGroundAmb * 0.8, smoothstep(0.0, -0.15, h));
  float mu = max(dot(d, uSunDir), 0.0);
  c += uSunRad * (pow(mu, 8.0) * 0.05 + pow(mu, 64.0) * 0.15) * smoothstep(-0.1, 0.05, h);
  return c;
}

float shadowAt(vec3 w, vec3 n) {
  vec4 s = uShadowVP * vec4(w + n * 0.6, 1.0);
  vec3 c = s.xyz / s.w * 0.5 + 0.5;
  if (c.x < 0.0 || c.x > 1.0 || c.y < 0.0 || c.y > 1.0) return 1.0;
  if (uNoShadow > 0.5) return 1.0;
  float sum = 0.0;
  vec2 ts = 1.0 / vec2(textureSize(uShadow, 0));
  for (int y = -1; y <= 1; y++) for (int x = -1; x <= 1; x++)
    sum += texture(uShadow, vec3(c.xy + vec2(x, y) * ts * 1.2, c.z - 0.0004));
  return sum / 9.0;
}

vec3 applyFog(vec3 col, vec3 w) {
  vec3 d = w - uCam; float dist = length(d); vec3 v = d / max(dist, 1e-3);
  float dz = d.z;
  float k = uFogFall;
  float h0 = max(uCam.z - uFogBase, 0.0);
  // (1 - e^-x) / x, numerically stable near x = 0 (surfaces at camera altitude)
  float x = k * dz;
  float line = abs(x) > 0.02 ? (1.0 - exp(-x)) / x : 1.0 - x * 0.5 + x * x / 6.0;
  float od = uFogDen * exp(-k * h0) * dist * line;
  float f = 1.0 - exp(-od);
  float mu = max(dot(v, uSunDir), 0.0);
  vec3 fc = uFogCol + uSunRad * 0.06 * pow(mu, 6.0);
  return mix(col, fc, clamp(f, 0.0, 1.0));
}

vec3 shade(vec3 base, float rough, float metal, float spec, vec3 emis, vec3 N, vec3 w, float ao) {
  vec3 V = normalize(uCam - w);
  vec3 L = uSunDir;
  float NdL = max(dot(N, L), 0.0);
  float NdV = max(dot(N, V), 1e-3);
  vec3 H = normalize(L + V);
  float NdH = max(dot(N, H), 0.0);
  float a = max(rough * rough, 0.002);
  float d = a * a / (PI * pow(NdH * NdH * (a * a - 1.0) + 1.0, 2.0));
  vec3 F0 = mix(vec3(0.08 * spec), base, metal);
  vec3 F = F0 + (1.0 - F0) * pow(1.0 - max(dot(H, V), 0.0), 5.0);
  float k = a * 0.5;
  float G = NdL / (NdL * (1.0 - k) + k) * NdV / (NdV * (1.0 - k) + k);
  vec3 specSun = d * F * G / (4.0 * NdV * max(NdL, 1e-3)) * NdL;
  float sh = shadowAt(w, N);
  vec3 diff = base * (1.0 - metal) / PI;
  vec3 col = (diff * NdL + specSun) * uSunRad * sh;
  // sky irradiance (hemisphere) + ground bounce
  vec3 irr = mix(uGroundAmb, (uSkyZen + uSkyHor) * 0.5, N.z * 0.5 + 0.5);
  col += base * (1.0 - metal) * irr * ao;
  // environment reflection
  vec3 R = reflect(-V, N);
  vec3 env = skyRad(R);
  vec3 envBlur = (uSkyZen + uSkyHor) * 0.5;
  env = mix(env, envBlur, clamp(rough * 1.4, 0.0, 1.0));
  if (R.z < 0.0) env = mix(env, uGroundAmb * 0.6 + vec3(0.02), 0.85);
  vec3 Fr = F0 + (max(vec3(1.0 - rough), F0) - F0) * pow(1.0 - NdV, 5.0);
  col += env * Fr * ao * mix(1.0, 0.6, rough);
  col += emis;
  return col;
}
`;

let SHADER_SRC = '';
let progMain, progShadow, progSky, progPost, progBloom, progInst, progInstShadow;
const objects = [];

async function init(manifestUrl) {
  SHADER_SRC = await fetchText('/tools/lookdev/shaders/xinyi_city.hlsl');
  const FS_MAIN = PRELUDE + SHADER_SRC + LIGHTING + `
in vec3 vW; in vec3 vN; in vec2 vUv0; in vec2 vUv1; in vec4 vCol;
uniform sampler2D uGround;
out vec4 oColor;
vec4 groundTex(vec3 w) { return texture(uGround, vec2((w.x + 1500.0) / 2500.0, (1500.0 - w.y) / 2500.0)); }
void main() {
  vec3 N = normalize(vN);
  vec4 vc = xc_unpack(vCol.xy);
  if (vCol.w > 0.5) vc.z = vCol.z;   // instanced: variant from per-instance data
  if (uKind == 2) vc = vec4(vCol.xy, 0.5, 1.0);            // plain floats (not packed)
  if (uKind == 4) vc = vec4(vCol.xy, vCol.z, 1.0);
  vec3 base; float rough; float metal; float spec; vec3 emis;
  float ao = 1.0;
  float fwp = max(fwidth(vW.x), fwidth(vW.y));
  if (uKind == 0) {
    vec3 Np;
    xc_city(vW, N, vUv0, vUv1, vc, uNight, uLitFrac, base, rough, metal, spec, emis, Np);
    // street-canyon sky occlusion: lower floors see less sky
    float wallAO = mix(0.35, 1.0, smoothstep(0.0, 30.0, vUv0.y));
    ao = mix(wallAO, 1.0, smoothstep(0.55, 0.75, N.z));
    if (vc.w > 0.97) ao = mix(0.6, 1.0, smoothstep(0.0, 60.0, vUv0.y));
    N = Np;
  } else if (uKind == 1) {
    xc_ground(vW, N, groundTex(vW), uNight, fwp, base, rough, metal, spec, emis);
    ao = 0.85;
  } else if (uKind == 3) {
    xc_paint(vW, vc, groundTex(vW), uNight, fwp, base, rough, metal, spec, emis);
    ao = 0.85;
  } else if (uKind == 4) {
    xc_foliage(vW, N, vc, vc.x * 10.0, uNight, base, rough, metal, spec, emis);
    ao = mix(0.55, 1.0, clamp((vc.x * 10.0 - 3.0) / 5.0, 0.0, 1.0));
    N = normalize(mix(N, vec3(0.0, 0.0, 1.0), 0.35));
  } else if (uKind == 5) {
    xc_prop(vW, N, vc, vc.z, uNight, fwp, base, rough, metal, spec, emis);
  } else {
    xc_backdrop(vW, N, vc, uNight, fwp, base, rough, metal, spec, emis);
  }
  vec3 c = shade(base, rough, metal, spec, emis, N, vW, ao);
  if (uDebug == 1) { oColor = vec4(base, 1.0); return; }
  if (uDebug == 2) { oColor = vec4(N * 0.5 + 0.5, 1.0); return; }
  if (uDebug == 3) { oColor = vec4(c, 1.0); return; }
  oColor = vec4(applyFog(c, vW), 1.0);
}`;
  progMain = program(PRELUDE + VS_WORLD, FS_MAIN);
  progShadow = program(PRELUDE + VS_SHADOW, PRELUDE + FS_SHADOW);
  progInst = program(PRELUDE + VS_INST, FS_MAIN);
  progInstShadow = program(PRELUDE + VS_INST_SHADOW, PRELUDE + FS_SHADOW);
  progSky = program(PRELUDE + `
out vec2 vP; void main(){ vec2 p = vec2((gl_VertexID<<1)&2, gl_VertexID&2); vP = p*2.0-1.0; gl_Position = vec4(vP,0.9999,1.0);} `,
  PRELUDE + LIGHTING + `
in vec2 vP; uniform mat4 uInvVP; out vec4 o;
void main(){ vec4 a = uInvVP*vec4(vP,1.0,1.0); vec3 d = normalize(a.xyz/a.w - uCam);
  vec3 c = skyRad(d);
  float mu = dot(d, uSunDir); c += uSunRad * smoothstep(0.9995, 0.99985, mu) * 8.0;
  // horizon haze band matches the fog colour
  c = mix(c, uFogCol, exp(-max(d.z,0.0)*12.0)*0.7);
  o = vec4(c,1.0); }`);
  progBloom = program(PRELUDE + `
out vec2 vUv; void main(){ vec2 p = vec2((gl_VertexID<<1)&2, gl_VertexID&2); vUv=p; gl_Position=vec4(p*2.0-1.0,0.0,1.0);} `,
  PRELUDE + `
in vec2 vUv; uniform sampler2D uSrc; uniform vec2 uTexel; uniform float uThresh; out vec4 o;
void main(){ vec3 s = vec3(0.0);
  for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++){ vec3 c = texture(uSrc, vUv + vec2(x,y)*uTexel*1.5).rgb; s += max(c - uThresh, 0.0); }
  o = vec4(s/9.0,1.0);} `);
  progPost = program(PRELUDE + `
out vec2 vUv; void main(){ vec2 p = vec2((gl_VertexID<<1)&2, gl_VertexID&2); vUv=p; gl_Position=vec4(p*2.0-1.0,0.0,1.0);} `,
  PRELUDE + `
in vec2 vUv; uniform sampler2D uHdr; uniform sampler2D uB0; uniform sampler2D uB1; uniform sampler2D uB2;
uniform float uExposure; uniform float uBloom; uniform vec2 uHdrTexel; out vec4 o;
vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14),0.0,1.0); }
void main(){
  // 2x2 box resolve of the supersampled frame
  vec3 c = vec3(0.0);
  c += texture(uHdr, vUv + uHdrTexel*vec2(-0.5,-0.5)).rgb;
  c += texture(uHdr, vUv + uHdrTexel*vec2( 0.5,-0.5)).rgb;
  c += texture(uHdr, vUv + uHdrTexel*vec2(-0.5, 0.5)).rgb;
  c += texture(uHdr, vUv + uHdrTexel*vec2( 0.5, 0.5)).rgb;
  c *= 0.25;
  vec3 b = texture(uB0, vUv).rgb*0.5 + texture(uB1, vUv).rgb*0.3 + texture(uB2, vUv).rgb*0.2;
  c = (c + b*uBloom) * uExposure;
  c = aces(c);
  vec2 q = vUv - 0.5; c *= 1.0 - dot(q,q)*0.35;
  c = pow(c, vec3(1.0/2.2));
  o = vec4(c,1.0);} `);

  const manifest = await (await fetch(manifestUrl)).json();
  if (manifest.groundTexture) groundTexture = await loadTexture(manifest.groundTexture);
  for (const item of manifest.objects) {
    const prims = parseGLB(await fetchBin(item.url));
    for (const p of prims) {
      const g = upload(p);
      const o = { ...g, offset: item.offset, kind: item.kind, castShadow: item.castShadow !== false, name: item.url };
      if (item.instances) {
        const j = await (await fetch(item.instances)).json();
        const list = item.instanceKey ? j.types[item.instanceKey] : j.instances;
        if (!list.length) continue;
        addInstances(o, list);
      }
      objects.push(o);
    }
  }
  return { objects: objects.length, tris: objects.reduce((s, o) => s + o.count / 3, 0) };
}

// ------------------------------------------------------------- math ---------
function persp(fovy, aspect, n, f) {
  const t = 1 / Math.tan(fovy / 2);
  return [t / aspect, 0, 0, 0, 0, t, 0, 0, 0, 0, (f + n) / (n - f), -1, 0, 0, 2 * f * n / (n - f), 0];
}
function ortho(l, r, b, t, n, f) {
  return [2 / (r - l), 0, 0, 0, 0, 2 / (t - b), 0, 0, 0, 0, -2 / (f - n), 0, -(r + l) / (r - l), -(t + b) / (t - b), -(f + n) / (f - n), 1];
}
function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
function cross(a, b) { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
function norm(a) { const l = Math.hypot(...a); return [a[0] / l, a[1] / l, a[2] / l]; }
function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
function lookAt(eye, at, up) {
  const z = norm(sub(eye, at)); const x = norm(cross(up, z)); const y = cross(z, x);
  return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -dot(x, eye), -dot(y, eye), -dot(z, eye), 1];
}
function mul(a, b) {
  const o = new Array(16).fill(0);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) for (let k = 0; k < 4; k++) o[c * 4 + r] += a[k * 4 + r] * b[c * 4 + k];
  return o;
}
function inv(m) {
  const a = m, o = new Array(16);
  const b00 = a[0] * a[5] - a[1] * a[4], b01 = a[0] * a[6] - a[2] * a[4], b02 = a[0] * a[7] - a[3] * a[4];
  const b03 = a[1] * a[6] - a[2] * a[5], b04 = a[1] * a[7] - a[3] * a[5], b05 = a[2] * a[7] - a[3] * a[6];
  const b06 = a[8] * a[13] - a[9] * a[12], b07 = a[8] * a[14] - a[10] * a[12], b08 = a[8] * a[15] - a[11] * a[12];
  const b09 = a[9] * a[14] - a[10] * a[13], b10 = a[9] * a[15] - a[11] * a[13], b11 = a[10] * a[15] - a[11] * a[14];
  const det = 1 / (b00 * b11 - b01 * b10 + b02 * b09 + b03 * b08 - b04 * b07 + b05 * b06);
  o[0] = (a[5] * b11 - a[6] * b10 + a[7] * b09) * det; o[1] = (a[2] * b10 - a[1] * b11 - a[3] * b09) * det;
  o[2] = (a[13] * b05 - a[14] * b04 + a[15] * b03) * det; o[3] = (a[10] * b04 - a[9] * b05 - a[11] * b03) * det;
  o[4] = (a[6] * b08 - a[4] * b11 - a[7] * b07) * det; o[5] = (a[0] * b11 - a[2] * b08 + a[3] * b07) * det;
  o[6] = (a[14] * b02 - a[12] * b05 - a[15] * b01) * det; o[7] = (a[8] * b05 - a[10] * b02 + a[11] * b01) * det;
  o[8] = (a[4] * b10 - a[5] * b08 + a[7] * b06) * det; o[9] = (a[1] * b08 - a[0] * b10 - a[3] * b06) * det;
  o[10] = (a[12] * b04 - a[13] * b02 + a[15] * b00) * det; o[11] = (a[9] * b02 - a[8] * b04 - a[11] * b00) * det;
  o[12] = (a[5] * b07 - a[4] * b09 - a[6] * b06) * det; o[13] = (a[0] * b09 - a[1] * b07 + a[2] * b06) * det;
  o[14] = (a[13] * b01 - a[12] * b03 - a[14] * b00) * det; o[15] = (a[8] * b03 - a[9] * b01 + a[10] * b00) * det;
  return o;
}

// ----------------------------------------------------------- targets --------
function makeTarget(w, h, depth, fmt = gl.RGBA16F) {
  const fb = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texStorage2D(gl.TEXTURE_2D, 1, fmt, w, h);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
  if (depth) {
    const rb = gl.createRenderbuffer();
    gl.bindRenderbuffer(gl.RENDERBUFFER, rb);
    gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT32F, w, h);
    gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, rb);
  }
  return { fb, tex, w, h };
}
function makeShadow(size) {
  const fb = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texStorage2D(gl.TEXTURE_2D, 1, gl.DEPTH_COMPONENT32F, size, size);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_COMPARE_MODE, gl.COMPARE_REF_TO_TEXTURE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_COMPARE_FUNC, gl.LEQUAL);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.TEXTURE_2D, tex, 0);
  const col = gl.createRenderbuffer();
  gl.bindRenderbuffer(gl.RENDERBUFFER, col);
  gl.renderbufferStorage(gl.RENDERBUFFER, gl.RGBA8, size, size);
  gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.RENDERBUFFER, col);
  return { fb, tex, size };
}

function sunDir(azDeg, elDeg) {
  const az = azDeg * Math.PI / 180, el = elDeg * Math.PI / 180;
  // azimuth clockwise from north; ENU x=east y=north
  return [Math.sin(az) * Math.cos(el), Math.cos(az) * Math.cos(el), Math.sin(el)];
}

// ---------------------------------------------------------- render ----------
async function render(shot, light, W, H, SS) {
  const cvs = document.getElementById('c');
  cvs.width = W; cvs.height = H;
  const hdr = makeTarget(W * SS, H * SS, true);
  const shadow = makeShadow(4096);
  const L = sunDir(light.sunAz, light.sunEl);

  // shadow camera around the shot focus
  const R = shot.shadowRadius || 1400;
  const f = shot.shadowCenter || shot.target;
  const sEye = [f[0] + L[0] * 3000, f[1] + L[1] * 3000, f[2] + L[2] * 3000];
  const sVP = mul(ortho(-R, R, -R, R, 10, 7000), lookAt(sEye, f, [0, 0, 1]));
  gl.bindFramebuffer(gl.FRAMEBUFFER, shadow.fb);
  gl.viewport(0, 0, shadow.size, shadow.size);
  gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS);
  gl.clear(gl.DEPTH_BUFFER_BIT | gl.COLOR_BUFFER_BIT);
  gl.enable(gl.POLYGON_OFFSET_FILL); gl.polygonOffset(2.0, 4.0);
  gl.useProgram(progShadow.p);
  gl.uniformMatrix4fv(progShadow.u.uViewProj, false, sVP);
  for (const o of objects) {
    if (!o.castShadow) continue;
    const pr = o.instances ? progInstShadow : progShadow;
    gl.useProgram(pr.p);
    gl.uniformMatrix4fv(pr.u.uViewProj, false, sVP);
    gl.uniform3fv(pr.u.uOffset, o.offset);
    gl.bindVertexArray(o.vao);
    if (o.instances) gl.drawElementsInstanced(gl.TRIANGLES, o.count, gl.UNSIGNED_INT, 0, o.instances);
    else gl.drawElements(gl.TRIANGLES, o.count, gl.UNSIGNED_INT, 0);
  }
  gl.disable(gl.POLYGON_OFFSET_FILL);

  // main
  const aspect = W / H;
  const proj = persp(shot.fov * Math.PI / 180, aspect, 2.0, 80000.0);
  const view = lookAt(shot.eye, shot.target, [0, 0, 1]);
  const VP = mul(proj, view);
  gl.bindFramebuffer(gl.FRAMEBUFFER, hdr.fb);
  gl.viewport(0, 0, hdr.w, hdr.h);
  gl.clearColor(0, 0, 0, 1);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

  const setLight = (pr) => {
    const u = pr.u;
    gl.uniform3fv(u.uCam, shot.eye);
    gl.uniform3fv(u.uSunDir, L);
    gl.uniform3fv(u.uSunRad, light.sunRad);
    gl.uniform3fv(u.uSkyZen, light.skyZen);
    gl.uniform3fv(u.uSkyHor, light.skyHor);
    gl.uniform3fv(u.uGroundAmb, light.groundAmb);
    gl.uniform3fv(u.uFogCol, light.fogCol);
    if (u.uFogDen) gl.uniform1f(u.uFogDen, light.fogDen);
    if (u.uFogFall) gl.uniform1f(u.uFogFall, light.fogFall);
    if (u.uFogBase) gl.uniform1f(u.uFogBase, light.fogBase || 0);
    if (u.uNight) gl.uniform1f(u.uNight, light.night);
    if (u.uLitFrac) gl.uniform1f(u.uLitFrac, light.litFrac);
    if (u.uNoShadow) gl.uniform1f(u.uNoShadow, light.noShadow ? 1.0 : 0.0);
    if (u.uDebug) gl.uniform1i(u.uDebug, light.debug || 0);
  };

  // sky
  gl.disable(gl.DEPTH_TEST);
  gl.useProgram(progSky.p);
  setLight(progSky);
  gl.uniformMatrix4fv(progSky.u.uInvVP, false, inv(VP));
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  gl.enable(gl.DEPTH_TEST);

  const prep = (pr) => {
    gl.useProgram(pr.p);
    setLight(pr);
    gl.uniformMatrix4fv(pr.u.uViewProj, false, VP);
    gl.uniformMatrix4fv(pr.u.uShadowVP, false, sVP);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, shadow.tex);
    gl.uniform1i(pr.u.uShadow, 0);
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, groundTexture);
    if (pr.u.uGround) gl.uniform1i(pr.u.uGround, 1);
  };
  gl.cullFace(gl.BACK);
  for (const o of objects) {
    const pr = o.instances ? progInst : progMain;
    prep(pr);
    gl.uniform3fv(pr.u.uOffset, o.offset);
    gl.uniform1i(pr.u.uKind, o.kind);
    if (o.kind === 0) gl.enable(gl.CULL_FACE); else gl.disable(gl.CULL_FACE);
    gl.bindVertexArray(o.vao);
    if (o.kind === 3) { gl.enable(gl.POLYGON_OFFSET_FILL); gl.polygonOffset(-2.0, -8.0); }
    if (o.instances) gl.drawElementsInstanced(gl.TRIANGLES, o.count, gl.UNSIGNED_INT, 0, o.instances);
    else gl.drawElements(gl.TRIANGLES, o.count, gl.UNSIGNED_INT, 0);
    gl.disable(gl.POLYGON_OFFSET_FILL);
  }
  gl.disable(gl.CULL_FACE);
  gl.disable(gl.DEPTH_TEST);

  // bloom chain
  const blooms = [];
  let src = hdr;
  for (let i = 0; i < 3; i++) {
    const t = makeTarget(Math.max(1, src.w >> 2), Math.max(1, src.h >> 2), false);
    gl.bindFramebuffer(gl.FRAMEBUFFER, t.fb);
    gl.viewport(0, 0, t.w, t.h);
    gl.useProgram(progBloom.p);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, src.tex);
    gl.uniform1i(progBloom.u.uSrc, 0);
    gl.uniform2f(progBloom.u.uTexel, 1 / src.w, 1 / src.h);
    gl.uniform1f(progBloom.u.uThresh, i === 0 ? light.bloomThresh : 0.0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    blooms.push(t); src = t;
  }

  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.viewport(0, 0, W, H);
  gl.useProgram(progPost.p);
  const bind = (unit, tex, name) => { gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, tex); gl.uniform1i(progPost.u[name], unit); };
  bind(0, hdr.tex, 'uHdr'); bind(1, blooms[0].tex, 'uB0'); bind(2, blooms[1].tex, 'uB1'); bind(3, blooms[2].tex, 'uB2');
  gl.uniform1f(progPost.u.uExposure, light.exposure);
  gl.uniform1f(progPost.u.uBloom, light.bloom);
  gl.uniform2f(progPost.u.uHdrTexel, 1 / hdr.w, 1 / hdr.h);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  gl.finish();
  const url = cvs.toDataURL('image/png');
  // free
  for (const t of [hdr, ...blooms]) { gl.deleteTexture(t.tex); gl.deleteFramebuffer(t.fb); }
  gl.deleteTexture(shadow.tex); gl.deleteFramebuffer(shadow.fb);
  return url;
}

window.XL = { init, render };
window.__ready = true;
