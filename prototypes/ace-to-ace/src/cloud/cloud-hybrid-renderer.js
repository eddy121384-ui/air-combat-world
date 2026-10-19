// B2: one fixed painted hull draw + four-interval local density mist.
// No per-pixel volume marching, no observer-facing geometry, no distance LOD swap.
import * as THREE from 'three';
import {buildCloudHull} from './cloud-hull.js';
const FOG_ENDS=[60,180,400,900];
const PAINT=`
vec3 tilePaint(vec2 q){vec2 uv=1.-abs(mod(q/850.,2.)-1.);
 return texture2D(atlas,vec2(0.,0.5)+vec2(8./1024.)+uv*(496./1024.)).rgb;}
vec3 worldPaint(vec3 p){return (tilePaint(p.zy)+tilePaint(p.xz)+tilePaint(p.xy))/3.;}
`;
const VS=`uniform vec3 windOffset;varying vec3 localPoint,pWorld,nWorld;
void main(){localPoint=position;pWorld=position+windOffset;nWorld=normal;
 gl_Position=projectionMatrix*viewMatrix*vec4(pWorld,1.);}`;
const FS=`uniform sampler2D atlas;uniform vec3 sun,eye;uniform float wire;
varying vec3 localPoint,pWorld,nWorld;
${PAINT}
void main(){
 vec3 n=normalize(nWorld),weights=pow(abs(n),vec3(4.));weights/=weights.x+weights.y+weights.z;
 // Surface normal is stored in the fixed hull, not derived from eye direction.
 vec3 paint=tilePaint(localPoint.zy)*weights.x+tilePaint(localPoint.xz)*weights.y+tilePaint(localPoint.xy)*weights.z;
 float value=dot(paint,vec3(0.22,0.65,0.13));
 // Broad painted shadow masses, interrupted by anchored dry-brush values.
 float light=dot(n,sun)*0.5+0.5;
 float marks=smoothstep(0.26,0.64,value);
 float block=smoothstep(0.38,0.54,light+0.27*(marks-0.5));
 vec3 shade=mix(vec3(0.23,0.30,0.49),vec3(0.52,0.58,0.73),marks);
 vec3 lit=mix(vec3(0.76,0.72,0.66),vec3(1.00,0.91,0.74),marks);
 vec3 colour=mix(shade,lit,block);
 // Keep the painted marks stronger than smooth sphere-style Lambert shading.
 colour*=0.86+0.27*marks;
 float underside=smoothstep(-0.55,0.18,n.y);
 colour=mix(colour*vec3(0.69,0.77,0.95),colour,underside);
 float edgeLight=smoothstep(0.67,0.90,light)*(1.-smoothstep(0.48,0.70,marks));
 colour+=vec3(0.13,0.075,0.02)*edgeLight;
 float distance=length(pWorld-eye);
 colour=mix(colour,vec3(0.67,0.74,0.84),(1.-exp(-distance/14000.))*0.6);
 if(!gl_FrontFacing)colour=mix(colour,vec3(0.36,0.43,0.61),0.45);
 if(wire>0.5)colour=n*0.5+0.5;
 // Only the actual surface within 90m of the eye softens; never the whole cloud.
 gl_FragColor=vec4(colour,smoothstep(2.,90.,distance));
}`;
const FOG_VS=`varying vec2 screenUV;void main(){screenUV=uv;gl_Position=vec4(position.xy,0.,1.);}`;
const FOG_FS=`uniform sampler2D colorMap,depthMap,atlas;uniform mat4 inverseVP;
uniform vec3 eye,sun,windOffset;uniform vec4 fogColumns[9];uniform float enabled,diagnostic;
varying vec2 screenUV;
${PAINT}
float hash3(vec3 p){p=fract(p*0.1031);p+=dot(p,p.yzx+33.33);return fract((p.x+p.y)*p.z);}
float pigment(vec3 p){
 vec3 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
 return mix(mix(mix(hash3(i),hash3(i+vec3(1,0,0)),f.x),mix(hash3(i+vec3(0,1,0)),hash3(i+vec3(1,1,0)),f.x),f.y),
  mix(mix(hash3(i+vec3(0,0,1)),hash3(i+vec3(1,0,1)),f.x),mix(hash3(i+vec3(0,1,1)),hash3(i+vec3(1,1,1)),f.x),f.y),f.z);
}
vec4 column(int row,float x){int a=row*3;return x<1.?mix(fogColumns[a],fogColumns[a+1],x):mix(fogColumns[a+1],fogColumns[a+2],x-1.);}
void main(){
 vec4 p=inverseVP*vec4(screenUV*2.-1.,texture2D(depthMap,screenUV).r*2.-1.,1.);p.xyz/=p.w;
 vec3 ray=normalize(p.xyz-eye);float distance=min(length(p.xyz-eye),900.);vec2 t=screenUV*2.;
 vec4 rho=t.y<1.?mix(column(0,t.x),column(1,t.x),t.y):mix(column(1,t.x),column(2,t.x),t.y-1.);
 vec4 starts=vec4(0.,60.,180.,400.),ends=vec4(60.,180.,400.,900.);
 float T=1.;vec3 radiance=vec3(0.);
 for(int i=0;i<4;i++){
  float ds=clamp(distance-starts[i],0.,ends[i]-starts[i]);
  float alpha=1.-exp(-rho[i]*ds*0.012*enabled);
  vec3 q=eye-windOffset+ray*(starts[i]+ds*0.5);
  // Interior pigment must be a genuine 3D field. Equal-weight 2D projections
  // produce ruler-like streaks when viewed edge-on, even with fixed world UVs.
  float marks=smoothstep(0.25,0.75,0.7*pigment(q/200.)+0.3*pigment(q/65.));
  float sunward=pow(max(dot(ray,sun),0.),3.);
  vec3 mist=mix(vec3(0.36,0.44,0.63),vec3(0.88,0.80,0.69),0.28+0.30*sunward+0.27*marks);
  mist*=0.83+0.28*marks;
  radiance+=T*alpha*mist;T*=1.-alpha;
 }
 if(diagnostic>0.5){gl_FragColor=vec4(vec3(T),1.);return;}
 gl_FragColor=vec4(radiance+T*texture2D(colorMap,screenUV).rgb,1.);
 #include <tonemapping_fragment>
 #include <colorspace_fragment>
}`;
export function createCloudHybridRenderer(renderer,scene,camera,atlas){
 const target=new THREE.WebGLRenderTarget(1,1,{depthTexture:new THREE.DepthTexture(1,1),samples:4});
 // The cloud shell is a painted boundary, not an opaque obstruction to mist.
 // Keep real scene depth separately so shell near-plane crossings cannot reset T.
 const opaqueTarget=new THREE.WebGLRenderTarget(1,1,{depthTexture:new THREE.DepthTexture(1,1)});
 const depthMaterial=new THREE.MeshDepthMaterial({colorWrite:false});
 const uniforms={atlas:{value:atlas},sun:{value:new THREE.Vector3()},eye:{value:camera.position},windOffset:{value:new THREE.Vector3()},wire:{value:0}};
 const clouds=new THREE.Mesh(new THREE.BufferGeometry(),new THREE.ShaderMaterial({uniforms,vertexShader:VS,fragmentShader:FS,side:THREE.DoubleSide,alphaToCoverage:true}));
 clouds.visible=false;clouds.frustumCulled=false;scene.add(clouds);
 const fu={...uniforms,inverseVP:{value:new THREE.Matrix4()},colorMap:{value:target.texture},depthMap:{value:opaqueTarget.depthTexture},enabled:{value:1},diagnostic:{value:0},fogColumns:{value:Array.from({length:9},()=>new THREE.Vector4())}};
 const composite=new THREE.Scene(),flatCamera=new THREE.Camera();
 composite.add(new THREE.Mesh(new THREE.PlaneGeometry(2,2),new THREE.ShaderMaterial({uniforms:fu,vertexShader:FOG_VS,fragmentShader:FOG_FS,depthWrite:false,depthTest:false})));
 const directions=Array.from({length:9},()=>new THREE.Vector3());
 const gl=renderer.getContext(),timer=gl.getExtension('EXT_disjoint_timer_query_webgl2');
 let field,builds=0,hullStats={},query=null,gpuMs=null,gpuSample=0;
 function setField(next){
  const begin=performance.now(),hull=buildCloudHull(next);field=next;builds++;
  const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.BufferAttribute(hull.positions,3));
  geo.setAttribute('normal',new THREE.BufferAttribute(hull.normals,3));geo.setIndex(new THREE.BufferAttribute(hull.indices,1));
  clouds.geometry.dispose();clouds.geometry=geo;
  hullStats={grid:hull.grid,triangles:hull.triangles,vertices:hull.positions.length/3,bytes:hull.positions.byteLength+hull.normals.byteLength+hull.indices.byteLength,buildMs:performance.now()-begin};
 }
 function resize(w,h){target.setSize(w,h);opaqueTarget.setSize(w,h);}
 function render(time=0,{enabled=true,wire=false,diagnostic=false}={}){
  if(query&&gl.getQueryParameter(query,gl.QUERY_RESULT_AVAILABLE)){
   if(!gl.getParameter(timer.GPU_DISJOINT_EXT)){gpuMs=gl.getQueryParameter(query,gl.QUERY_RESULT)/1e6;gpuSample++;}gl.deleteQuery(query);query=null;
  }
  const begin=performance.now();camera.updateMatrixWorld();
  for(let y=0;y<3;y++)for(let x=0;x<3;x++)directions[y*3+x].set(x-1,y-1,0.5).unproject(camera).sub(camera.position).normalize();
  directions.forEach((d,i)=>fu.fogColumns.value[i].fromArray(FOG_ENDS.map((end,j)=>{
   const start=j?FOG_ENDS[j-1]:0;let rho=0;
   for(let k=0;k<3;k++){const s=start+(end-start)*(k+0.5)/3;rho+=field.sampleDensity(camera.position.x+d.x*s,camera.position.y+d.y*s,camera.position.z+d.z*s,time);}
   return rho/3;
  })));
  uniforms.windOffset.value.set(field.params.wind.x*time,0,field.params.wind.z*time);uniforms.wire.value=wire?1:0;
  fu.inverseVP.value.multiplyMatrices(camera.matrixWorld,camera.projectionMatrixInverse);fu.enabled.value=enabled?1:0;fu.diagnostic.value=diagnostic?1:0;
  const updateCpuMs=performance.now()-begin,measuring=!!timer&&!query;
  if(measuring){query=gl.createQuery();gl.beginQuery(timer.TIME_ELAPSED_EXT,query);}
  const submit=performance.now(),previousOverride=scene.overrideMaterial;
  clouds.visible=false;scene.overrideMaterial=depthMaterial;renderer.setRenderTarget(opaqueTarget);renderer.render(scene,camera);scene.overrideMaterial=previousOverride;
  let calls=renderer.info.render.calls,triangles=renderer.info.render.triangles;
  clouds.visible=enabled;renderer.setRenderTarget(target);renderer.render(scene,camera);
  calls+=renderer.info.render.calls;triangles+=renderer.info.render.triangles;
  renderer.setRenderTarget(null);renderer.render(composite,flatCamera);if(measuring)gl.endQuery(timer.TIME_ELAPSED_EXT);
  return {representation:'fixed-painted-hull',hull:hullStats,geometryBuilds:builds,cacheBuildMs:hullStats.buildMs,cacheBytes:hullStats.bytes,
   updateCpuMs,fogCpuMs:updateCpuMs,renderSubmitMs:performance.now()-submit,gpuMs,gpuSample,gpuTimerAvailable:!!timer,
   calls:calls+renderer.info.render.calls,triangles:triangles+renderer.info.render.triangles,width:target.width,height:target.height,
   transparentLayers:0,alphaCoverageShells:1,fogIntervals:4,densityQueries:108,textureBytes:1024*1024*4*4/3,renderTargetBytes:target.width*target.height*8*(2+target.samples),
   programsRunnable:renderer.info.programs.every(p=>p.diagnostics?.runnable!==false)};
 }
 return {uniforms,clouds,setField,resize,render,get ready(){return !!atlas.image&&!!field;}};
}
