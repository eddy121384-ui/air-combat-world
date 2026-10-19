// B1 painted layers + depth-corrected relief + bounded CPU-driven local fog.
// All 27 anchors/sizes stay in world space. Only the impostor orientation faces
// the observer; no cloud position, seed or texture regenerates with view.
import * as THREE from 'three';
import {buildCloudLayers,sampleCloudFog} from './cloud-layout.js';

const VS=`attribute vec3 aCenter,aSize;attribute float aVariant,aDetail;
uniform vec3 eye,windOffset;varying vec2 paintUV;varying vec3 pWorld,pCenter;
varying float elevation,variant,thickness,lod;
void main(){
 pCenter=aCenter+windOffset;vec3 toEye=normalize(eye-pCenter);
 vec3 right=cross(vec3(0,1,0),toEye);
 if(length(right)<0.02)right=vec3(viewMatrix[0][0],viewMatrix[1][0],viewMatrix[2][0]);
 right=normalize(right);vec3 up=normalize(cross(toEye,right));
 float h=mix(aSize.y,aSize.z,smoothstep(0.25,0.85,abs(toEye.y)));
 pWorld=pCenter+right*position.x*aSize.x+up*position.y*h;
 paintUV=uv;elevation=toEye.y;variant=aVariant;thickness=aSize.z;
 lod=1.-aDetail*smoothstep(4500.,7500.,length(eye-pCenter));
 gl_Position=projectionMatrix*viewMatrix*vec4(pWorld,1.);
}`;
const FS=`uniform mat4 projectionMatrix;uniform sampler2D silhouettes;uniform vec3 eye,sun,windOffset,fieldMin,fieldMax;uniform float wire;
varying vec2 paintUV;varying vec3 pWorld,pCenter;varying float elevation,variant,thickness,lod;
vec4 tile(vec2 uv,vec2 cell){return texture2D(silhouettes,cell+vec2(8./1024.)+uv*(496./1024.));}
void main(){
 if(lod<0.01)discard;
 vec2 uv=paintUV;uv.x=variant>0.5?1.-uv.x:uv.x;
 vec4 side=tile(uv,variant>0.5?vec2(0.5,0.):vec2(0.,0.5));
 vec4 vertical=tile(uv,elevation>0.?vec2(0.5,0.5):vec2(0.,0.));
 float tilt=smoothstep(0.25,0.85,abs(elevation));
 float alpha=mix(side.a,vertical.a,tilt)*lod;
 vec3 paint=mix(side.rgb*side.a,vertical.rgb*vertical.a,tilt)/max(mix(side.a,vertical.a,tilt),0.001);
 vec3 toEye=normalize(eye-pCenter),ray=normalize(pWorld-eye);
 float bulge=max(0.,1.-dot((paintUV-0.5)*1.4,(paintUV-0.5)*1.4));
 float relief=min((0.10+0.12*dot(paint,vec3(0.22,0.65,0.13)))*bulge*thickness,length(pWorld-eye)*0.6);
 vec3 surface=pWorld-ray*relief;
 vec3 local=surface-windOffset;
 alpha*=smoothstep(fieldMin.y,fieldMin.y+70.,local.y)*(1.-smoothstep(fieldMax.y-100.,fieldMax.y,local.y));
 alpha*=smoothstep(fieldMin.x,fieldMin.x+150.,local.x)*(1.-smoothstep(fieldMax.x-150.,fieldMax.x,local.x));
 alpha*=smoothstep(fieldMin.z,fieldMin.z+150.,local.z)*(1.-smoothstep(fieldMax.z-150.,fieldMax.z,local.z));
 // Local mist takes over before the eye crosses a near sprite plane.
 alpha*=smoothstep(100.,650.,length(eye-pCenter))*smoothstep(15.,110.,length(eye-surface));
 if(alpha<0.025)discard;
 float facing=dot(toEye,sun),back=pow(max(-facing,0.),2.);
 vec3 tint=mix(vec3(0.78,0.84,1.04),vec3(1.07,1.01,0.90),smoothstep(-0.6,0.8,facing));
 vec3 col=paint*tint;
 float edge=1.-smoothstep(0.12,0.80,alpha);
 col+=vec3(0.28,0.14,0.035)*back*edge;
 col*=mix(0.78,1.,smoothstep(-0.9,0.1,elevation));
 col=mix(col,vec3(0.67,0.74,0.84),(1.-exp(-length(eye-surface)/14000.))*0.6);
 if(wire>0.5){float line=step(0.97,fract(paintUV.x*10.))+step(0.97,fract(paintUV.y*10.));col=mix(col,vec3(0.1,0.9,0.7),min(1.,line));}
 vec4 depth=projectionMatrix*viewMatrix*vec4(surface,1.);
 gl_FragDepth=depth.z/depth.w*0.5+0.5;
 gl_FragColor=vec4(col,alpha);
}`;
const FOG_VS=`varying vec2 screenUV;void main(){screenUV=uv;gl_Position=vec4(position.xy,0.,1.);}`;
const FOG_FS=`uniform sampler2D atlas,colorMap,depthMap;uniform mat4 inverseVP;
uniform vec3 eye,sun,windOffset;uniform float enabled;uniform vec4 fogColumns[9];varying vec2 screenUV;
vec4 column(int row,float x){int a=row*3;return x<1.?mix(fogColumns[a],fogColumns[a+1],x):mix(fogColumns[a+1],fogColumns[a+2],x-1.);}
vec3 fogPaint(vec2 p){vec2 uv=1.-abs(mod(p/1300.,2.)-1.);return texture2D(atlas,vec2(0.5)+vec2(8./1024.)+uv*(496./1024.)).rgb;}
void main(){
 vec4 p=inverseVP*vec4(screenUV*2.-1.,texture2D(depthMap,screenUV).r*2.-1.,1.);p.xyz/=p.w;
 vec3 ray=normalize(p.xyz-eye);float d=min(length(p.xyz-eye),1800.);vec2 t=screenUV*2.;
 vec4 rho=t.y<1.?mix(column(0,t.x),column(1,t.x),t.y):mix(column(1,t.x),column(2,t.x),t.y-1.);
 vec4 lengths=clamp(vec4(d)-vec4(0.,80.,250.,700.),vec4(0.),vec4(80.,170.,450.,1100.));
 float T=exp(-dot(rho,lengths)*0.012*enabled);
 // Triplanar fog paint avoids stretching an XZ texture edge-on into vertical bands.
 vec3 q=eye-windOffset+ray*350.,w=pow(abs(ray),vec3(4.));w/=w.x+w.y+w.z;
 vec3 paint=fogPaint(q.zy)*w.x+fogPaint(q.xz)*w.y+fogPaint(q.xy)*w.z;
 float sunlight=pow(max(dot(ray,sun),0.),3.);
 vec3 mist=mix(vec3(0.60,0.67,0.82),vec3(0.96,0.87,0.73),0.30+sunlight*0.50+max(ray.y,0.)*0.14);
 float value=smoothstep(0.28,0.9,dot(paint,vec3(0.22,0.65,0.13)));
 mist=mix(mist*vec3(0.76,0.80,0.91),mist*1.04,value);
 gl_FragColor=vec4(mix(mist,texture2D(colorMap,screenUV).rgb,T),1.);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;

export function createCloudAnimeRenderer(renderer,scene,camera){
 const target=new THREE.WebGLRenderTarget(1,1,{depthTexture:new THREE.DepthTexture(1,1),samples:4});
 const load=name=>{const t=new THREE.TextureLoader().load(new URL('../../assets/cloud-b1/'+name,import.meta.url).href);
  t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=Math.min(4,renderer.capabilities.getMaxAnisotropy());return t;};
 const atlas=load('cloud-materials-b1.webp'),silhouettes=load('cloud-silhouettes-b1.webp');
 const uniforms={silhouettes:{value:silhouettes},sun:{value:new THREE.Vector3(-0.64,0.3,-0.69).normalize()},eye:{value:camera.position},
  windOffset:{value:new THREE.Vector3()},fieldMin:{value:new THREE.Vector3()},fieldMax:{value:new THREE.Vector3()},wire:{value:0}};
 const material=new THREE.ShaderMaterial({uniforms,vertexShader:VS,fragmentShader:FS,alphaToCoverage:true,side:THREE.DoubleSide});
 const clouds=new THREE.Mesh(new THREE.BufferGeometry(),material);clouds.visible=false;clouds.frustumCulled=false;scene.add(clouds);
 const fu={atlas:{value:atlas},sun:uniforms.sun,eye:uniforms.eye,windOffset:uniforms.windOffset,enabled:{value:1},
  inverseVP:{value:new THREE.Matrix4()},colorMap:{value:target.texture},depthMap:{value:target.depthTexture},
  fogColumns:{value:Array.from({length:9},()=>new THREE.Vector4())}};
 const composite=new THREE.Scene();composite.add(new THREE.Mesh(new THREE.PlaneGeometry(2,2),new THREE.ShaderMaterial({
  uniforms:fu,vertexShader:FOG_VS,fragmentShader:FOG_FS,depthWrite:false,depthTest:false})));
 const gl=renderer.getContext(),timer=gl.getExtension('EXT_disjoint_timer_query_webgl2');
 let field,buildStats={},query=null,gpuMs=null,gpuSample=0,disjointSamples=0,builds=0;
 const flatCamera=new THREE.Camera(),ray=new THREE.Vector3(),directions=Array.from({length:9},()=>new THREE.Vector3());
 function setField(next){
  const begin=performance.now();field=next;const layers=buildCloudLayers(field),geo=new THREE.InstancedBufferGeometry(),plane=new THREE.PlaneGeometry(1,1);
  geo.index=plane.index;geo.attributes.position=plane.attributes.position;geo.attributes.uv=plane.attributes.uv;
  geo.setAttribute('aCenter',new THREE.InstancedBufferAttribute(new Float32Array(layers.flatMap(l=>l.center)),3));
  geo.setAttribute('aSize',new THREE.InstancedBufferAttribute(new Float32Array(layers.flatMap(l=>l.size)),3));
  geo.setAttribute('aVariant',new THREE.InstancedBufferAttribute(new Float32Array(layers.map(l=>l.variant)),1));
  geo.setAttribute('aDetail',new THREE.InstancedBufferAttribute(new Float32Array(layers.map(l=>l.detail)),1));
  geo.instanceCount=layers.length;clouds.geometry.dispose();clouds.geometry=geo;builds++;
  uniforms.fieldMin.value.set(...Object.values(field.bounds.min));uniforms.fieldMax.value.set(...Object.values(field.bounds.max));
  buildStats={triangles:layers.length*2,count:layers.length,buildMs:performance.now()-begin,bytes:layers.length*8*4,anchors:layers.map(l=>l.center)};
 }
 function resize(width,height){target.setSize(width,height);}
 function render(time=0,{enabled=true,wire=false,fogEnabled=true}={}){
  if(query&&gl.getQueryParameter(query,gl.QUERY_RESULT_AVAILABLE)){
   if(!gl.getParameter(timer.GPU_DISJOINT_EXT)){gpuMs=gl.getQueryParameter(query,gl.QUERY_RESULT)/1e6;gpuSample++;}else{gpuMs=null;disjointSamples++;}
   gl.deleteQuery(query);query=null;
  }
  const cpuStart=performance.now();camera.updateMatrixWorld();
  for(let y=0;y<3;y++)for(let x=0;x<3;x++)directions[y*3+x].copy(ray.set(x-1,y-1,0.5).unproject(camera).sub(camera.position).normalize());
  sampleCloudFog(field,camera.position,directions,time).forEach((c,i)=>fu.fogColumns.value[i].fromArray(c));
  const fogCpuMs=performance.now()-cpuStart;
  uniforms.windOffset.value.set(field.params.wind.x*time,0,field.params.wind.z*time);uniforms.wire.value=wire?1:0;
  fu.enabled.value=enabled&&fogEnabled?1:0;fu.inverseVP.value.multiplyMatrices(camera.matrixWorld,camera.projectionMatrixInverse);clouds.visible=enabled;
  const measuring=!!timer&&!query;if(measuring){query=gl.createQuery();gl.beginQuery(timer.TIME_ELAPSED_EXT,query);}
  const begin=performance.now();renderer.setRenderTarget(target);renderer.render(scene,camera);
  const calls=renderer.info.render.calls,triangles=renderer.info.render.triangles;
  renderer.setRenderTarget(null);renderer.render(composite,flatCamera);if(measuring)gl.endQuery(timer.TIME_ELAPSED_EXT);
  return {renderSubmitMs:performance.now()-begin,fogCpuMs,gpuMs,gpuSample,gpuTimerAvailable:!!timer,disjointSamples,
   calls:calls+renderer.info.render.calls,triangles:triangles+renderer.info.render.triangles,width:target.width,height:target.height,
   layers:buildStats,geometryBuilds:builds,cacheBuildMs:0,cacheBytes:0,textureBytes:2*1024*1024*4*4/3,
   textureWidth:silhouettes.image?.width??0,renderTargetBytes:target.width*target.height*8*(1+target.samples),
   renderer:gl.getExtension('WEBGL_debug_renderer_info')?gl.getParameter(gl.getExtension('WEBGL_debug_renderer_info').UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),
   programsRunnable:renderer.info.programs.every(p=>p.diagnostics?.runnable!==false)};
 }
 return {uniforms,clouds,setField,resize,render,atlas,get ready(){return !!atlas.image&&!!silhouettes.image;},get builds(){return builds;}};
}
