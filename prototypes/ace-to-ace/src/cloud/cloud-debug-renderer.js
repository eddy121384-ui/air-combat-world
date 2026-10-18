// Lab-only bounded volume preview. One composite pass, no alpha-sorted cloud meshes.
// The CPU field is authoritative; the 8-bit cache is only a display approximation.
import * as THREE from 'three';

const VS = `varying vec2 uvScreen;
void main(){uvScreen=uv;gl_Position=vec4(position.xy,0.,1.);}`;
const FS = `precision highp sampler3D;
varying vec2 uvScreen;
uniform sampler2D sceneColor, sceneDepth;
uniform sampler3D volume;
uniform mat4 inverseVP;
uniform vec3 eye, fieldMin, fieldSize, gridSize, windOffset, sun;
uniform float enabled;
vec3 worldAt(float depth){vec4 p=inverseVP*vec4(uvScreen*2.-1.,depth*2.-1.,1.);return p.xyz/p.w;}
float rho(vec3 p){
 vec3 t=(p-windOffset-fieldMin)/fieldSize;
 if(any(lessThan(t,vec3(0.)))||any(greaterThan(t,vec3(1.))))return 0.;
 return texture(volume,(t*(gridSize-1.)+0.5)/gridSize).r;
}
void main(){
 vec3 background=texture2D(sceneColor,uvScreen).rgb;
 vec3 ray=normalize(worldAt(1.)-eye);
 float opaqueDistance=length(worldAt(texture2D(sceneDepth,uvScreen).r)-eye);
 // Slab interval: sign-safe inverse also handles horizontal / vertical cameras.
 vec3 safeRay=mix(vec3(0.000001),ray,step(vec3(0.000001),abs(ray)));
 vec3 a=(fieldMin+windOffset-eye)/safeRay,b=(fieldMin+windOffset+fieldSize-eye)/safeRay;
 vec3 lo=min(a,b),hi=max(a,b);
 float start=max(0.,max(lo.x,max(lo.y,lo.z)));
 float end=min(opaqueDistance,min(hi.x,min(hi.y,hi.z)));
 float T=1.;vec3 light=vec3(0.);
 if(enabled>0.5&&end>start){
  float ds=(end-start)/96.;
  for(int i=0;i<96;i++){
   vec3 p=eye+ray*(start+(float(i)+0.5)*ds);
   float d=rho(p);
   float alpha=1.-exp(-0.012*d*ds);
   // Two local probes: inexpensive sun-facing gradient, not multiple scattering.
   float facing=clamp((d-rho(p+sun*100.))*2.+0.5,0.,1.);
   float height=clamp((p.y-fieldMin.y)/fieldSize.y,0.,1.);
   vec3 tint=mix(vec3(0.46,0.53,0.63),vec3(1.,0.96,0.86),0.23+0.48*facing+0.22*height);
   light+=T*alpha*tint;T*=1.-alpha;
  }
 }
 gl_FragColor=vec4(light+T*background,1.);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;

export function createCloudDebugRenderer(canvas, scene, camera) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false });
  renderer.setPixelRatio(1);
  renderer.autoClear = true;
  const target = new THREE.WebGLRenderTarget(1, 1, { depthTexture: new THREE.DepthTexture(1, 1) });
  const uniforms = {
    sceneColor: { value: target.texture }, sceneDepth: { value: target.depthTexture }, volume: { value: null },
    inverseVP: { value: new THREE.Matrix4() }, eye: { value: camera.position },
    fieldMin: { value: new THREE.Vector3() }, fieldSize: { value: new THREE.Vector3() },
    gridSize: { value: new THREE.Vector3(96, 48, 80) }, windOffset: { value: new THREE.Vector3() },
    sun: { value: new THREE.Vector3(-0.64, 0.6, -0.5).normalize() }, enabled: { value: 1 },
  };
  const material = new THREE.ShaderMaterial({ uniforms, vertexShader: VS, fragmentShader: FS, depthTest: false, depthWrite: false });
  const composite = new THREE.Scene();
  composite.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material));
  const flatCamera = new THREE.Camera();
  const gl = renderer.getContext(), timer = gl.getExtension('EXT_disjoint_timer_query_webgl2');
  let query = null, gpuMs = null, gpuSample = 0, disjointSamples = 0, field;
  let cacheBuildMs = 0;

  function setField(next) {
    field = next;
    const begin = performance.now(), [nx, ny, nz] = uniforms.gridSize.value.toArray();
    const min = next.bounds.min, max = next.bounds.max;
    uniforms.fieldMin.value.set(min.x, min.y, min.z);
    uniforms.fieldSize.value.set(max.x - min.x, max.y - min.y, max.z - min.z);
    const bytes = new Uint8Array(nx * ny * nz);
    for (let z = 0; z < nz; z++) for (let y = 0; y < ny; y++) for (let x = 0; x < nx; x++) {
      bytes[x + nx * (y + ny * z)] = Math.round(255 * next.sampleDensity(
        min.x + (max.x - min.x) * x / (nx - 1), min.y + (max.y - min.y) * y / (ny - 1),
        min.z + (max.z - min.z) * z / (nz - 1), 0));
    }
    uniforms.volume.value?.dispose();
    const texture = new THREE.Data3DTexture(bytes, nx, ny, nz);
    texture.format = THREE.RedFormat; texture.type = THREE.UnsignedByteType;
    texture.minFilter = texture.magFilter = THREE.LinearFilter;
    texture.unpackAlignment = 1; texture.needsUpdate = true;
    uniforms.volume.value = texture;
    cacheBuildMs = performance.now() - begin;
  }
  function resize(width, height, quality = 0.5) {
    renderer.setSize(Math.max(1, Math.round(width * quality)), Math.max(1, Math.round(height * quality)), false);
    const size = renderer.getDrawingBufferSize(new THREE.Vector2());
    target.setSize(size.x, size.y);
    camera.aspect = width / height; camera.updateProjectionMatrix();
  }
  function render(time = 0) {
    if (query && gl.getQueryParameter(query, gl.QUERY_RESULT_AVAILABLE)) {
      if (!gl.getParameter(timer.GPU_DISJOINT_EXT)) { gpuMs = gl.getQueryParameter(query, gl.QUERY_RESULT) / 1e6; gpuSample++; }
      else { gpuMs = null; disjointSamples++; }
      gl.deleteQuery(query); query = null;
    }
    const measuring = !!timer && !query;
    if (measuring) { query = gl.createQuery(); gl.beginQuery(timer.TIME_ELAPSED_EXT, query); }
    const begin = performance.now();
    uniforms.windOffset.value.set(field.params.wind.x * time, 0, field.params.wind.z * time);
    camera.updateMatrixWorld();
    uniforms.inverseVP.value.multiplyMatrices(camera.matrixWorld, camera.projectionMatrixInverse);
    renderer.setRenderTarget(target); renderer.render(scene, camera);
    const sceneCalls = renderer.info.render.calls, sceneTriangles = renderer.info.render.triangles;
    renderer.setRenderTarget(null); renderer.render(composite, flatCamera);
    if (measuring) gl.endQuery(timer.TIME_ELAPSED_EXT);
    return { renderSubmitMs: performance.now() - begin, gpuMs, gpuSample, gpuTimerAvailable: !!timer, disjointSamples,
      calls: sceneCalls + renderer.info.render.calls, triangles: sceneTriangles + renderer.info.render.triangles,
      width: target.width, height: target.height, cacheBuildMs, cacheBytes: 96 * 48 * 80,
      renderer: gl.getExtension('WEBGL_debug_renderer_info') ? gl.getParameter(gl.getExtension('WEBGL_debug_renderer_info').UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
      programsRunnable: renderer.info.programs.every(p => p.diagnostics?.runnable !== false) };
  }
  return { renderer, uniforms, setField, resize, render };
}
