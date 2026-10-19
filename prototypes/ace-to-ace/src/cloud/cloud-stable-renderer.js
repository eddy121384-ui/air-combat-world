// B1 animation experiment: fixed 3D density + normals, world-anchored paint.
// One bounded 32-probe composite. No camera-facing geometry or sprite/fog handoff.
import * as THREE from 'three';
import {buildCloudVolume,VOLUME_STEPS} from './cloud-volume.js';
const VS=`varying vec2 screenUV;void main(){screenUV=uv;gl_Position=vec4(position.xy,0.,1.);}`;
const FS=`precision highp sampler3D;
varying vec2 screenUV;uniform sampler2D colorMap,depthMap,atlas;uniform sampler3D volume;
uniform mat4 inverseVP;uniform vec3 eye,sun,fieldMin,fieldSize,gridSize,windOffset;
uniform float enabled,wire,diagnostic,pixelScale;
vec3 worldAt(float d){vec4 p=inverseVP*vec4(screenUV*2.-1.,d*2.-1.,1.);return p.xyz/p.w;}
vec4 densityAt(vec3 p){
 vec3 t=(p-windOffset-fieldMin)/fieldSize;
 if(any(lessThan(t,vec3(0.)))||any(greaterThan(t,vec3(1.))))return vec4(0.,0.5,0.5,0.5);
 return textureLod(volume,(t*(gridSize-1.)+0.5)/gridSize,0.);
}
vec3 paintAt(vec2 p,vec2 cell,float lod){vec2 uv=1.-abs(mod(p/1100.,2.)-1.);
 return textureLod(atlas,cell+vec2(8./1024.)+uv*(496./1024.),lod).rgb;}
vec3 paintVolume(vec3 p,float lod){
 // Isotropic colour field. Interior density gradients have no reliable surface
 // normal, so they must not select/rotate whole top/side/base paintings.
 return (paintAt(p.zy,vec2(0.,0.5),lod)+paintAt(p.xz,vec2(0.,0.5),lod)+paintAt(p.xy,vec2(0.,0.5),lod))/3.;
}
void main(){
 vec3 background=texture2D(colorMap,screenUV).rgb;
 vec3 ray=normalize(worldAt(1.)-eye);float opaqueDistance=length(worldAt(texture2D(depthMap,screenUV).r)-eye);
 vec3 safeRay=mix(vec3(0.000001),ray,step(vec3(0.000001),abs(ray)));
 vec3 a=(fieldMin+windOffset-eye)/safeRay,b=(fieldMin+windOffset+fieldSize-eye)/safeRay;
 vec3 lo=min(a,b),hi=max(a,b);
 float start=max(0.,max(lo.x,max(lo.y,lo.z))),end=min(opaqueDistance,min(hi.x,min(hi.y,hi.z)));
 float T=1.;vec3 radiance=vec3(0.);
 if(enabled>0.5&&end>start){
  float nearEnd=min(end,start+240.),midEnd=min(end,start+1440.);
  for(int i=0;i<32;i++){
   float s,ds;
   if(i<8){ds=(nearEnd-start)/8.;s=start+(float(i)+0.5)*ds;}
   else if(i<20){ds=(midEnd-nearEnd)/12.;s=nearEnd+(float(i-8)+0.5)*ds;}
   else{ds=(end-midEnd)/12.;s=midEnd+(float(i-20)+0.5)*ds;}
   if(ds<=0.)continue;
   vec3 p=eye+ray*s;vec4 v=densityAt(p);if(v.r<0.00001)continue;
   vec3 n=normalize(v.gba*2.-1.+vec3(0.,0.00001,0.));
   float alpha=1.-exp(-0.012*v.r*ds),w=T*alpha;
   // World gradient/light, never the eye-to-cloud-centre direction.
   float light=0.38+0.46*max(dot(n,sun),0.)+0.12*max(n.y,0.);
   if(diagnostic<0.5){
    // Evaluate paint at EACH fixed world point, not a view-dependent centroid.
    // Explicit LOD is defined inside divergent ray loops; no implicit derivatives.
    vec3 paint=paintVolume(p-windOffset,log2(max(1.,s*pixelScale)));
    float height=clamp((p.y-fieldMin.y)/fieldSize.y,0.,1.);
    vec3 tint=mix(vec3(0.22,0.30,0.52),vec3(0.97,0.88,0.74),clamp(0.15+height*0.38+light*0.42,0.,1.));
    // Gentle brush variation belongs to the medium, not a high-contrast mural.
    vec3 colour=tint*(vec3(0.78)+paint*0.40);
    colour=mix(colour,vec3(0.67,0.74,0.84),(1.-exp(-s/14000.))*0.45);
    if(wire>0.5)colour=n*0.5+0.5;
    radiance+=w*colour;
   }T*=1.-alpha;
   if(T<0.008)break;
  }
 }
 if(diagnostic>0.5){gl_FragColor=vec4(vec3(T),1.);return;}
 gl_FragColor=vec4(radiance+T*background,1.);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;
export function createCloudStableRenderer(renderer,scene,camera,atlas){
 const target=new THREE.WebGLRenderTarget(1,1,{depthTexture:new THREE.DepthTexture(1,1)});
 const uniforms={colorMap:{value:target.texture},depthMap:{value:target.depthTexture},atlas:{value:atlas},volume:{value:null},
  inverseVP:{value:new THREE.Matrix4()},eye:{value:camera.position},sun:{value:new THREE.Vector3()},
  fieldMin:{value:new THREE.Vector3()},fieldSize:{value:new THREE.Vector3()},gridSize:{value:new THREE.Vector3()},
  windOffset:{value:new THREE.Vector3()},enabled:{value:1},wire:{value:0},diagnostic:{value:0},pixelScale:{value:1}};
 const composite=new THREE.Scene(),flatCamera=new THREE.Camera();
 composite.add(new THREE.Mesh(new THREE.PlaneGeometry(2,2),new THREE.ShaderMaterial({uniforms,vertexShader:VS,fragmentShader:FS,depthWrite:false,depthTest:false})));
 const gl=renderer.getContext(),timer=gl.getExtension('EXT_disjoint_timer_query_webgl2');
 let field,cacheStats={},builds=0,query=null,gpuMs=null,gpuSample=0,disjointSamples=0;
 function setField(next){
  const begin=performance.now(),cache=buildCloudVolume(next);field=next;builds++;
  uniforms.volume.value?.dispose();const texture=new THREE.Data3DTexture(cache.data,...cache.grid);
  texture.format=THREE.RGBAFormat;texture.type=THREE.UnsignedByteType;texture.minFilter=texture.magFilter=THREE.LinearFilter;
  texture.unpackAlignment=1;texture.needsUpdate=true;uniforms.volume.value=texture;
  uniforms.fieldMin.value.set(...Object.values(cache.min));uniforms.fieldSize.value.set(cache.max.x-cache.min.x,cache.max.y-cache.min.y,cache.max.z-cache.min.z);
  uniforms.gridSize.value.set(...cache.grid);
  cacheStats={grid:cache.grid,bytes:cache.data.byteLength,buildMs:performance.now()-begin,spacing:cache.spacing};
 }
 function resize(width,height){target.setSize(width,height);uniforms.pixelScale.value=2*Math.tan(camera.fov*Math.PI/360)/height*496/1100;}
 function render(time=0,{enabled=true,wire=false,diagnostic=false}={}){
  if(query&&gl.getQueryParameter(query,gl.QUERY_RESULT_AVAILABLE)){
   if(!gl.getParameter(timer.GPU_DISJOINT_EXT)){gpuMs=gl.getQueryParameter(query,gl.QUERY_RESULT)/1e6;gpuSample++;}
   else{gpuMs=null;disjointSamples++;}gl.deleteQuery(query);query=null;
  }
  const cpu=performance.now();camera.updateMatrixWorld();
  uniforms.inverseVP.value.multiplyMatrices(camera.matrixWorld,camera.projectionMatrixInverse);
  uniforms.windOffset.value.set(field.params.wind.x*time,0,field.params.wind.z*time);
  uniforms.enabled.value=enabled?1:0;uniforms.wire.value=wire?1:0;uniforms.diagnostic.value=diagnostic?1:0;
  const updateCpuMs=performance.now()-cpu,measuring=!!timer&&!query;
  if(measuring){query=gl.createQuery();gl.beginQuery(timer.TIME_ELAPSED_EXT,query);}
  const begin=performance.now();renderer.setRenderTarget(target);renderer.render(scene,camera);
  const calls=renderer.info.render.calls,triangles=renderer.info.render.triangles;
  renderer.setRenderTarget(null);renderer.render(composite,flatCamera);if(measuring)gl.endQuery(timer.TIME_ELAPSED_EXT);
  return {representation:'fixed-volume',renderSubmitMs:performance.now()-begin,updateCpuMs,fogCpuMs:0,gpuMs,gpuSample,gpuTimerAvailable:!!timer,disjointSamples,
   calls:calls+renderer.info.render.calls,triangles:triangles+renderer.info.render.triangles,width:target.width,height:target.height,
   volume:cacheStats,geometryBuilds:builds,cacheBuildMs:cacheStats.buildMs,cacheBytes:cacheStats.bytes,transparentLayers:0,volumeSteps:VOLUME_STEPS,
   textureBytes:1024*1024*4*4/3+cacheStats.bytes,textureWidth:atlas.image?.width??0,renderTargetBytes:target.width*target.height*8,
   renderer:gl.getExtension('WEBGL_debug_renderer_info')?gl.getParameter(gl.getExtension('WEBGL_debug_renderer_info').UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),
   programsRunnable:renderer.info.programs.every(p=>p.diagnostics?.runnable!==false)};
 }
 return {uniforms,setField,resize,render,get ready(){return !!atlas.image&&!!uniforms.volume.value;}};
}
