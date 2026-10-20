// One-cloud proof: bounded low-resolution volume, no visible shell, fixed light.
import * as THREE from 'three';
import {buildOneCloudBrick,ONE_CLOUD_STEPS,ONE_CLOUD_EXTINCTION} from './one-cloud.js';
const VS=`varying vec2 screenUV;void main(){screenUV=uv;gl_Position=vec4(position.xy,0.,1.);}`;
const FS=`precision highp sampler3D;
varying vec2 screenUV;uniform sampler2D colorMap,depthMap;uniform sampler3D volume;
uniform mat4 inverseVP;uniform vec3 eye,fieldMin,fieldSize,gridSize;uniform float enabled,diagnostic;
vec3 worldAt(float d){vec4 p=inverseVP*vec4(screenUV*2.-1.,d*2.-1.,1.);return p.xyz/p.w;}
void main(){
 vec3 background=texture2D(colorMap,screenUV).rgb,farPoint=worldAt(1.);
 vec3 ray=normalize(farPoint-eye);
 float depth=texture2D(depthMap,screenUV).r;
 float opaqueDistance=length(worldAt(depth)-eye);
 // Preserve sign even for almost-parallel rays. Camera-inside starts at zero.
 vec3 signRay=step(vec3(0.),ray)*2.-1.;vec3 safeRay=signRay*max(abs(ray),vec3(1.e-6));
 vec3 a=(fieldMin-eye)/safeRay,b=(fieldMin+fieldSize-eye)/safeRay,lo=min(a,b),hi=max(a,b);
 float start=max(0.,max(lo.x,max(lo.y,lo.z))),end=min(opaqueDistance,min(hi.x,min(hi.y,hi.z)));
 float T=1.;vec3 radiance=vec3(0.);
 if(enabled>0.5&&end>start){
  float ds=(end-start)/float(${ONE_CLOUD_STEPS});
  for(int i=0;i<${ONE_CLOUD_STEPS};i++){
   float s=start+(float(i)+0.5)*ds;
   vec3 p=eye+ray*s,t=(p-fieldMin)/fieldSize;
   vec4 v=textureLod(volume,(t*(gridSize-1.)+0.5)/gridSize,0.);
   if(v.a<=0.001)continue;
   float alpha=1.-exp(-${ONE_CLOUD_EXTINCTION}*v.a*ds);
   vec3 colour=v.rgb/max(v.a,0.001);
   colour=mix(colour,vec3(0.67,0.74,0.84),(1.-exp(-s/14000.))*0.6);
   radiance+=T*alpha*colour;T*=1.-alpha;
   if(T<0.008)break;
  }
 }
 if(diagnostic>0.5){gl_FragColor=vec4(vec3(T),1.);return;}
 gl_FragColor=vec4(radiance+T*background,1.);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;
export function createCloudPrelitRenderer(renderer,scene,camera) {
  const target=new THREE.WebGLRenderTarget(1,1,{depthTexture:new THREE.DepthTexture(1,1)});
  const uniforms={colorMap:{value:target.texture},depthMap:{value:target.depthTexture},volume:{value:null},inverseVP:{value:new THREE.Matrix4()},
    eye:{value:camera.position},fieldMin:{value:new THREE.Vector3()},fieldSize:{value:new THREE.Vector3()},gridSize:{value:new THREE.Vector3()},enabled:{value:1},diagnostic:{value:0}};
  const composite=new THREE.Scene(),flatCamera=new THREE.Camera();
  composite.add(new THREE.Mesh(new THREE.PlaneGeometry(2,2),new THREE.ShaderMaterial({uniforms,vertexShader:VS,fragmentShader:FS,depthWrite:false,depthTest:false})));
  let builds=0,cacheStats;
  function setField(field) {
    const cache=buildOneCloudBrick(field),texture=new THREE.Data3DTexture(cache.data,...cache.grid);
    texture.format=THREE.RGBAFormat;texture.type=THREE.UnsignedByteType;texture.minFilter=texture.magFilter=THREE.LinearFilter;
    texture.unpackAlignment=1;texture.needsUpdate=true;uniforms.volume.value?.dispose();uniforms.volume.value=texture;
    uniforms.fieldMin.value.set(...Object.values(cache.min));uniforms.fieldSize.value.set(...['x','y','z'].map(k=>cache.max[k]-cache.min[k]));
    uniforms.gridSize.value.set(...cache.grid);builds++;
    cacheStats={grid:cache.grid,bytes:cache.bytes,buildMs:cache.buildMs,occupied:cache.occupied};
  }
  function render(time=0,{enabled=true,diagnostic=false}={}) {
    const cpu=performance.now();camera.updateMatrixWorld();uniforms.inverseVP.value.multiplyMatrices(camera.matrixWorld,camera.projectionMatrixInverse);
    uniforms.enabled.value=enabled?1:0;uniforms.diagnostic.value=diagnostic?1:0;
    const updateCpuMs=performance.now()-cpu,begin=performance.now();renderer.setRenderTarget(target);renderer.render(scene,camera);
    const calls=renderer.info.render.calls,triangles=renderer.info.render.triangles;
    renderer.setRenderTarget(null);renderer.render(composite,flatCamera);
    return {representation:'one-cloud-prelit',renderSubmitMs:performance.now()-begin,updateCpuMs,fogCpuMs:0,gpuMs:null,
      calls:calls+renderer.info.render.calls,triangles:triangles+renderer.info.render.triangles,width:target.width,height:target.height,
      volume:cacheStats,volumeSteps:ONE_CLOUD_STEPS,geometryBuilds:builds,cacheBuildMs:cacheStats.buildMs,cacheBytes:cacheStats.bytes,
      textureBytes:cacheStats.bytes,renderTargetBytes:target.width*target.height*8,
      renderer:renderer.getContext().getParameter(renderer.getContext().RENDERER),programsRunnable:renderer.info.programs.every(p=>p.diagnostics?.runnable!==false)};
  }
  return {uniforms,setField,render,resize:(w,h)=>target.setSize(w,h),get ready(){return !!uniforms.volume.value;}};
}
