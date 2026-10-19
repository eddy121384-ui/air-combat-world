// Opus Sky renderer: R2 painted far sky + world-fixed NPR puff clouds + cloud-shadowed sea
// + camera-in-cloud fog and vapour streaks, all driven by one cloudscape.
import * as THREE from 'three';
import { PUFF_STRIDE } from './cloudscape.js';
import { PUFF_VS, PUFF_FS, SKY_VS, SKY_FS, SEA_VS, SEA_FS, STREAK_VS, STREAK_FS, SUNDEPTH_VS, SUNDEPTH_FS, MIST_VS, MIST_FS } from './sky-shaders.js';

// Golden-hour anime palette sampled by eye from the accepted R2 painting.
export const OPUS_PALETTE = Object.freeze({
  lit: [1.00, 0.96, 0.89], warm: [1.00, 0.83, 0.70], half: [0.90, 0.80, 0.86], skyShade: [0.77, 0.81, 0.95],
  shadow: [0.64, 0.68, 0.87], base: [0.50, 0.54, 0.74], deep: [0.46, 0.50, 0.72], silver: [1.0, 0.86, 0.62], glow: [0.98, 0.84, 0.74],
  horizon: [0.76, 0.82, 0.88], seaShade: [0.52, 0.62, 0.80], fog: [0.88, 0.89, 0.96], fogShade: [0.62, 0.66, 0.85], fogGlow: [0.16, 0.10, 0.03],
});

const DEFAULTS = Object.freeze({
  bands: [0.505, 0.565, 0.32, 0.46], normalMix: [0.12, 0.60, 0.28, 0.13],
  hazeDistance: 16000, nearFade: [8, 45], fogSigma: 0.03, lodPx: 2.2,
  bump: 1.0, sunDepthSize: [2048, 1024], sunSoft: [12, 460],
  streakRadius: 220, streakSpacing: 36, streakShutter: 0.07, streakWidth: 1.6, maxStreaks: 260, maxMist: 160,
});

export function createOpusSky({ renderer, scene, camera, skyTexture, cloudscape, palette = OPUS_PALETTE, options = {} }) {
  const o = { ...DEFAULTS, ...options };
  const sun = new THREE.Vector3(...cloudscape.sun);
  const v3 = a => new THREE.Vector3(...a);
  const wind = new THREE.Vector3();
  // Shared uniform objects: every material sees the same fog state in the same frame.
  const fog = { uFog: { value: new THREE.Vector4(...palette.fog, 0) }, uFogDir: { value: new THREE.Vector4(0, 1, 0, 0) },
    uFogGlow: { value: v3(palette.fogGlow) }, uFogRange: { value: 1e5 } };
  const shared = { skyMap: { value: skyTexture }, uSun: { value: sun }, uCam: { value: new THREE.Vector3() },
    uHorizon: { value: v3(palette.horizon) }, ...fog };

  // ---- far sky: the accepted R2 painting, untouched apart from in-cloud fog
  const sky = new THREE.Mesh(new THREE.SphereGeometry(50000, 32, 16), new THREE.ShaderMaterial({
    uniforms: { ...shared }, vertexShader: SKY_VS, fragmentShader: SKY_FS, side: THREE.BackSide, depthWrite: false }));
  sky.renderOrder = -10; sky.frustumCulled = false;
  scene.add(sky);

  // ---- sea with cloud shadows from the same puffs
  const raster = cloudscape.shadowRaster(256);
  blur(raster.data, raster.size, 2);
  const shadowTex = new THREE.DataTexture(raster.data, raster.size, raster.size, THREE.RedFormat, THREE.UnsignedByteType);
  shadowTex.magFilter = shadowTex.minFilter = THREE.LinearFilter; shadowTex.needsUpdate = true;
  const seaMat = new THREE.ShaderMaterial({ uniforms: { ...shared, uTime: { value: 0 }, uFogNear: { value: 4500 }, uFogFar: { value: 52000 },
    shadowMap: { value: shadowTex }, uShadow: { value: new THREE.Vector3(raster.extent, 0, 0) }, cSeaShade: { value: v3(palette.seaShade) } },
    vertexShader: SEA_VS, fragmentShader: SEA_FS });
  const sea = new THREE.Mesh(new THREE.PlaneGeometry(140000, 140000), seaMat);
  sea.rotation.x = -Math.PI / 2; sea.frustumCulled = false;
  scene.add(sea);

  // ---- puffs: one instanced draw of camera-facing quads ray-cast into exact spheres
  const geo = new THREE.InstancedBufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0], 3));
  geo.setIndex([0, 1, 2, 0, 2, 3]);
  const ib = new THREE.InstancedInterleavedBuffer(cloudscape.data, PUFF_STRIDE);
  ['iA', 'iB', 'iC', 'iD'].forEach((name, k) => geo.setAttribute(name, new THREE.InterleavedBufferAttribute(ib, 4, k * 4)));
  geo.instanceCount = cloudscape.count;
  const sunDepth = renderSunDepth(renderer, geo, cloudscape, sun, o.sunDepthSize);
  const noiseTex = makeNoiseTexture();
  const puffUniforms = { ...shared, uNoise: { value: noiseTex }, uWindF: { value: wind }, uSunDepth: { value: sunDepth.texture }, uSunMat: { value: sunDepth.matrix },
    uSunDepthInfo: { value: new THREE.Vector4(1 / sunDepth.width, sunDepth.range, ...o.sunSoft) }, uWind: { value: wind }, uTime: { value: 0 }, uPxScale: { value: 1 }, uPxAngle: { value: 0.001 },
    uLodPx: { value: o.lodPx }, uBump: { value: o.bump }, uProj: { value: camera.projectionMatrix }, uNearFade: { value: new THREE.Vector2(...o.nearFade) }, uHazeDist: { value: o.hazeDistance },
    uBands: { value: new THREE.Vector4(...o.bands) }, uMix: { value: new THREE.Vector4(...o.normalMix) },
    cLit: { value: v3(palette.lit) }, cWarm: { value: v3(palette.warm) }, cShadow: { value: v3(palette.shadow) },
    cDeep: { value: v3(palette.deep) }, cBase: { value: v3(palette.base) }, cSkyShade: { value: v3(palette.skyShade) },
    cHalf: { value: v3(palette.half) }, cGlow: { value: v3(palette.glow) }, cSilver: { value: v3(palette.silver) } };
  // Alpha drives MSAA coverage only; colour is written opaque and the target's alpha is kept,
  // so a host canvas created with alpha:true cannot show the page through billow fringes.
  const puffMat = new THREE.ShaderMaterial({ uniforms: puffUniforms, vertexShader: PUFF_VS, fragmentShader: PUFF_FS, alphaToCoverage: true,
    side: THREE.DoubleSide, blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.ZeroFactor,
    blendSrcAlpha: THREE.ZeroFactor, blendDstAlpha: THREE.OneFactor });
  const puffs = new THREE.Mesh(geo, puffMat);
  puffs.frustumCulled = false;
  scene.add(puffs);

  // ---- vapour streaks (only near/inside cloud)
  const streakData = new Float32Array(o.maxStreaks * 4);
  const sgeo = new THREE.InstancedBufferGeometry();
  sgeo.setAttribute('position', new THREE.Float32BufferAttribute([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0], 3));
  sgeo.setIndex([0, 1, 2, 0, 2, 3]);
  const sattr = new THREE.InstancedBufferAttribute(streakData, 4).setUsage(THREE.DynamicDrawUsage);
  sgeo.setAttribute('iP', sattr); sgeo.instanceCount = 0;
  const streakMat = new THREE.ShaderMaterial({ uniforms: { uCam: shared.uCam, uVel: { value: new THREE.Vector3() },
    uShutter: { value: o.streakShutter }, uWidth: { value: o.streakWidth }, uColor: { value: new THREE.Vector3(1, 0.98, 0.95) } },
    vertexShader: STREAK_VS, fragmentShader: STREAK_FS, transparent: true, depthWrite: false, side: THREE.DoubleSide });
  const streaks = new THREE.Mesh(sgeo, streakMat);
  streaks.frustumCulled = false; streaks.renderOrder = 5;
  scene.add(streaks);

  // ---- mist clumps on the same lattice
  const mistData = new Float32Array(o.maxMist * 4);
  const mgeo = new THREE.InstancedBufferGeometry();
  mgeo.setAttribute('position', sgeo.getAttribute('position')); mgeo.setIndex(sgeo.getIndex());
  const mattr = new THREE.InstancedBufferAttribute(mistData, 4).setUsage(THREE.DynamicDrawUsage);
  mgeo.setAttribute('iM', mattr); mgeo.instanceCount = 0;
  const mistMat = new THREE.ShaderMaterial({ uniforms: { uCam: shared.uCam, uSun: shared.uSun,
    uLight: { value: new THREE.Vector3(1.0, 0.97, 0.95) }, uShade: { value: v3(palette.shadow).multiplyScalar(1.12) } },
    vertexShader: MIST_VS, fragmentShader: MIST_FS, transparent: true, depthWrite: false, depthTest: false, side: THREE.DoubleSide });
  const mist = new THREE.Mesh(mgeo, mistMat);
  mist.frustumCulled = false; mist.renderOrder = 4;
  scene.add(mist);

  const state = { density: 0, fogSigma: 0, streaks: 0, mist: 0, cpuMs: 0 };
  const tmp = new THREE.Vector3(), fwd = new THREE.Vector3();

  /** Per-frame: camera-relative uniforms, in-cloud fog from the field, streak emission. */
  const fogLit = v3(palette.fog), fogShade = v3(palette.fogShade);
  const smoothed = { sigma: 0, sunVis: 1, primed: false };
  const MARCH = [15, 40, 80, 140, 220, 330, 480, 680, 950, 1300];

  /** Raw in-cloud fog at a world point: extinction and how much sun reaches it through the puffs. */
  function fogSample(x, y, z) {
    x -= wind.x; y -= wind.y; z -= wind.z;
    const d = cloudscape.density(x, y, z);
    if (d <= 0) return { sigma: 0, sunVis: 1, density: 0 };
    let od = 0, prev = 0;
    for (const t of MARCH) { od += cloudscape.density(x + sun.x * t, y + sun.y * t, z + sun.z * t) * (t - prev); prev = t; }
    return { sigma: o.fogSigma * smooth(d / 0.85), sunVis: Math.exp(-od / 260), density: d };
  }

  /**
   * Per-frame: camera-relative uniforms, in-cloud fog, streak emission. `fog` may be supplied
   * (already filtered) for deterministic captures; otherwise it is smoothed over `dt` here:
   * quick to close in (0.06 s), slower to clear (0.35 s), so leaving a cloud reads as a burst
   * through thinning mist instead of a one-frame cut.
   */
  function update({ time = 0, velocity = null, windOffset = null, viewportHeight = 720, dt = 1 / 60, fog: fogIn = null } = {}) {
    const t0 = performance.now();
    if (windOffset) wind.copy(windOffset);
    const cam = camera.position;
    shared.uCam.value.copy(cam);
    sky.position.copy(cam);
    puffUniforms.uTime.value = time; seaMat.uniforms.uTime.value = time;
    seaMat.uniforms.uShadow.value.set(raster.extent, wind.x, wind.z);
    const pxScale = viewportHeight / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
    puffUniforms.uPxScale.value = pxScale; puffUniforms.uPxAngle.value = 1 / pxScale;

    const cx = cam.x - wind.x, cy = cam.y - wind.y, cz = cam.z - wind.z;
    const raw = fogSample(cam.x, cam.y, cam.z), d = raw.density;
    if (fogIn) Object.assign(smoothed, fogIn, { primed: true });
    else if (!smoothed.primed) Object.assign(smoothed, raw, { primed: true });
    else filterFog(smoothed, raw, dt);
    const sigma = smoothed.sigma;
    fog.uFog.value.w = sigma;
    // Inside: real distance fog. Just out: the lingering mist is a thin veil, so the open sky
    // bursts through it instead of staying hidden behind kilometres of virtual fog.
    fog.uFogRange.value = d > 0.05 ? 1e5 : 160 + 900 * smooth(d / 0.05);
    // Mist is lit by whatever sun gets through: lavender in a cloud's shade, bright near its lit skin.
    fog.uFog.value.x = fogShade.x + (fogLit.x - fogShade.x) * smoothed.sunVis;
    fog.uFog.value.y = fogShade.y + (fogLit.y - fogShade.y) * smoothed.sunVis;
    fog.uFog.value.z = fogShade.z + (fogLit.z - fogShade.z) * smoothed.sunVis;
    fog.uFogGlow.value.fromArray(palette.fogGlow).multiplyScalar(smoothed.sunVis);
    // Inside cloud, nearby billow walls dissolve completely so only fog and wisps remain.
    const k = sigma / o.fogSigma;
    puffUniforms.uNearFade.value.set(o.nearFade[0] + 25 * k, o.nearFade[1] + 60 * k);
    if (d > 0) { const g = cloudscape.gradient(cx, cy, cz); fog.uFogDir.value.set(g[0], g[1], g[2], Math.max(0, 1 - d * 1.15)); }
    else fog.uFogDir.value.w = 0;

    // Stateless world lattice: the same wisps are found again when you fly back.
    let n = 0, nm = 0;
    camera.getWorldDirection(fwd);
    if (d > 0 || cloudscape.near(cx + fwd.x * 100, cz + fwd.z * 100)) {
      const s = o.streakSpacing, R = o.streakRadius;
      const ox = cam.x + fwd.x * R * 0.45, oy = cam.y + fwd.y * R * 0.45, oz = cam.z + fwd.z * R * 0.45;
      const i0 = Math.floor((ox - R * 0.6) / s), i1 = Math.floor((ox + R * 0.6) / s);
      const j0 = Math.floor((oy - R * 0.6) / s), j1 = Math.floor((oy + R * 0.6) / s);
      const k0 = Math.floor((oz - R * 0.6) / s), k1 = Math.floor((oz + R * 0.6) / s);
      for (let i = i0; i <= i1 && n < o.maxStreaks; i++) for (let j = j0; j <= j1 && n < o.maxStreaks; j++) for (let k = k0; k <= k1 && n < o.maxStreaks; k++) {
        const px = (i + hash3(i, j, k, 1)) * s, py = (j + hash3(i, j, k, 2)) * s, pz = (k + hash3(i, j, k, 3)) * s;
        tmp.set(px - cam.x, py - cam.y, pz - cam.z);
        const dist = tmp.length(), ahead = tmp.dot(fwd);
        if (ahead < 4 || dist > R) continue;
        const den = cloudscape.density(px - wind.x, py - wind.y, pz - wind.z);
        if (den < 0.08) continue;
        const fade = (1 - smooth((dist - R * 0.55) / (R * 0.45))) * smooth((dist - 4) / 18);
        const h = hash3(i, j, k, 4);
        if (h < 0.5 && nm < o.maxMist) {
          // Clumps: 18-60 m soft balls, lighter or shadier. Strongest at the cloud's skin (a veil
          // that softens the wall as you close in), present but thinner deep inside.
          const skin = 1 - 0.45 * smooth((den - 0.6) / 0.4);
          const radius = Math.floor(18 + 42 * hash3(i, j, k, 5)), ma = smooth((den - 0.08) / 0.35) * fade * 0.42 * skin;
          if (ma > 0.01) { mistData.set([px, py, pz, radius + Math.min(0.999, ma)], nm * 4); nm++; }
          continue;
        }
        const a = smooth((den - 0.12) / 0.5) * fade * 0.42;
        if (a < 0.01) continue;
        streakData.set([px, py, pz, a], n * 4); n++;
      }
    }
    sgeo.instanceCount = n; sattr.needsUpdate = n > 0;
    mgeo.instanceCount = nm; mattr.needsUpdate = nm > 0;
    if (velocity) streakMat.uniforms.uVel.value.copy(velocity);
    state.density = d; state.fogSigma = sigma; state.streaks = n; state.mist = nm; state.cpuMs = performance.now() - t0;
    return state;
  }

  function setPalette(p) {
    for (const [k, u] of [['lit', 'cLit'], ['warm', 'cWarm'], ['shadow', 'cShadow'], ['deep', 'cDeep'], ['base', 'cBase'], ['skyShade', 'cSkyShade'], ['half', 'cHalf'], ['glow', 'cGlow'], ['silver', 'cSilver']])
      if (p[k]) puffUniforms[u].value.set(...p[k]);
  }

  return { update, fogSample, setPalette, state, puffs, sky, sea, streaks, mist, uniforms: puffUniforms, fogUniforms: fog, shadowTexture: shadowTex,
    stats: () => ({ puffs: cloudscape.count, streaks: state.streaks }) };
}

/**
 * Render the puffs once from the sun into a depth texture (orthographic, cloud-local, no wind).
 * Returns the texture and the world→shadow-clip matrix used for lookups.
 */
function renderSunDepth(renderer, puffGeometry, scape, sun, [width, height]) {
  const dir = sun.clone().negate();                     // view direction: from the sun into the field
  const [mn, mx] = [scape.bounds.min, scape.bounds.max];
  const centre = new THREE.Vector3((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2);
  const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 2);
  cam.position.copy(centre).addScaledVector(sun, 40000); cam.up.set(0, 1, 0); cam.lookAt(centre);
  cam.updateMatrixWorld();
  // Fit the frustum to the field's corners in light space.
  const box = new THREE.Box3();
  for (const x of [mn[0], mx[0]]) for (const y of [mn[1], mx[1] + 200]) for (const z of [mn[2], mx[2]])
    box.expandByPoint(new THREE.Vector3(x, y, z).applyMatrix4(cam.matrixWorldInverse));
  cam.left = box.min.x - 300; cam.right = box.max.x + 300; cam.bottom = box.min.y - 300; cam.top = box.max.y + 300;
  cam.near = -box.max.z - 2000; cam.far = -box.min.z + 2000; cam.updateProjectionMatrix();
  const target = new THREE.WebGLRenderTarget(width, height, { depthBuffer: true });
  target.depthTexture = new THREE.DepthTexture(width, height);
  target.depthTexture.type = THREE.UnsignedIntType;
  const mat = new THREE.ShaderMaterial({ vertexShader: SUNDEPTH_VS, fragmentShader: SUNDEPTH_FS, side: THREE.DoubleSide,
    uniforms: { uViewDir: { value: dir }, uProj: { value: cam.projectionMatrix } } });
  const scene = new THREE.Scene(), mesh = new THREE.Mesh(puffGeometry, mat);
  mesh.frustumCulled = false; scene.add(mesh);
  const prev = renderer.getRenderTarget(), clear = renderer.getClearColor(new THREE.Color()), clearAlpha = renderer.getClearAlpha();
  renderer.setRenderTarget(target); renderer.setClearColor(0x000000, 1); renderer.clear(); renderer.render(scene, cam);
  renderer.setRenderTarget(prev); renderer.setClearColor(clear, clearAlpha);
  mat.dispose();
  const matrix = new THREE.Matrix4().multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
  return { texture: target.depthTexture, matrix, width, range: cam.far - cam.near, target };
}

/** Tiling value noise (period 32) baked at 2 texels per lattice cell with smoothstep weights. */
function makeNoiseTexture() {
  const P = 32, N = 64, lat = new Float32Array(P * P * P);
  for (let z = 0; z < P; z++) for (let y = 0; y < P; y++) for (let x = 0; x < P; x++) lat[(z * P + y) * P + x] = hash3(x, y, z, 7);
  const at = (x, y, z) => lat[(((z + P) % P) * P + ((y + P) % P)) * P + ((x + P) % P)];
  const data = new Uint8Array(N * N * N);
  for (let z = 0; z < N; z++) for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const fx = x / 2, fy = y / 2, fz = z / 2, ix = Math.floor(fx), iy = Math.floor(fy), iz = Math.floor(fz);
    const u = smooth(fx - ix), v = smooth(fy - iy), w = smooth(fz - iz);
    const l = (a, b, t) => a + (b - a) * t;
    const val = l(l(l(at(ix, iy, iz), at(ix + 1, iy, iz), u), l(at(ix, iy + 1, iz), at(ix + 1, iy + 1, iz), u), v),
      l(l(at(ix, iy, iz + 1), at(ix + 1, iy, iz + 1), u), l(at(ix, iy + 1, iz + 1), at(ix + 1, iy + 1, iz + 1), u), v), w);
    data[(z * N + y) * N + x] = Math.round(val * 255);
  }
  const tex = new THREE.Data3DTexture(data, N, N, N);
  tex.format = THREE.RedFormat; tex.type = THREE.UnsignedByteType;
  tex.minFilter = tex.magFilter = THREE.LinearFilter;
  tex.wrapS = tex.wrapT = tex.wrapR = THREE.RepeatWrapping; tex.unpackAlignment = 1; tex.needsUpdate = true;
  return tex;
}

/** Asymmetric first-order filter shared by the renderer and deterministic captures. */
export function filterFog(state, target, dt) {
  const tau = target.sigma > state.sigma ? 0.06 : 0.28;
  const a = 1 - Math.exp(-dt / tau);
  state.sigma += (target.sigma - state.sigma) * a;
  state.sunVis += (target.sunVis - state.sunVis) * (1 - Math.exp(-dt / 0.2));
  return state;
}

function hash3(i, j, k, s) {
  let h = Math.imul(i, 374761393) ^ Math.imul(j, 668265263) ^ Math.imul(k, 2147483647) ^ Math.imul(s, 1274126177);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
function smooth(x) { x = x < 0 ? 0 : x > 1 ? 1 : x; return x * x * (3 - 2 * x); }
function blur(data, size, passes) {
  const tmp = new Float32Array(data.length);
  for (let p = 0; p < passes; p++) for (const axis of [0, 1]) {
    for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
      let sum = 0, cnt = 0;
      for (let k = -2; k <= 2; k++) {
        const xx = axis ? x : x + k, yy = axis ? y + k : y;
        if (xx < 0 || yy < 0 || xx >= size || yy >= size) continue;
        sum += data[yy * size + xx]; cnt++;
      }
      tmp[y * size + x] = sum / cnt;
    }
    for (let i = 0; i < data.length; i++) data[i] = Math.round(tmp[i]);
  }
}
