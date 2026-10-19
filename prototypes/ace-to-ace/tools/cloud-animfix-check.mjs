// Deterministic real WebGL frame sequences -> videos. FFmpeg never invents frames.
import http from 'node:http';
import assert from 'node:assert/strict';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {resolve,extname,sep,join} from 'node:path';
import {CLOUD_ANIMATION_PATHS} from './cloud-animation-paths.js';
const {chromium}=createRequire(import.meta.url)('playwright');
const args=process.argv.slice(2),arg=(key,fallback)=>args.includes(key)?args[args.indexOf(key)+1]:fallback;
const quick=args.includes('--quick'),round=arg('--round',quick?'r1':'final'),frames=Number(arg('--frames',quick?'7':'180'));
const paths=CLOUD_ANIMATION_PATHS.filter(p=>!args.includes('--scene')||p.id===arg('--scene'));
assert.ok(paths.length);const elevated=args.includes('--elevated');
const root=fileURLToPath(new URL('../',import.meta.url));
const out=join(root,'docs/cloud-engine-b1-animfix',round),raw=join(root,'tools/out/cloud-animfix',round);
await mkdir(out,{recursive:true});await mkdir(raw,{recursive:true});
const mime={'.html':'text/html','.js':'text/javascript','.jpg':'image/jpeg','.png':'image/png','.webp':'image/webp'};
const server=http.createServer(async(req,res)=>{try{
 const path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://local').pathname));assert.ok(path.startsWith(resolve(root)+sep));
 const data=await readFile(path);res.writeHead(200,{'Content-Type':mime[extname(path)]||'application/octet-stream'});res.end(data);
}catch{res.writeHead(404);res.end('not found');}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const report={baseline:'996329258379383f6ed1d8bdb4ea992589be6c14',round,frames,elevatedOrbit:elevated,capturedAt:new Date().toISOString(),errors:[],scenes:{},sha256:{},
 runtime:'Chromium ANGLE SwiftShader, not iPhone hardware',video:'15 fps, deterministic path samples; offline replay is not runtime FPS'};
for(const path of ['src/cloud/cloud-field.js','src/cloud/cloud-anime-renderer.js','src/cloud/cloud-stable-renderer.js','src/cloud/cloud-volume.js','tools/cloud-lab.js','tools/cloud-animation-paths.js'])
 report.sha256[path]=createHash('sha256').update(await readFile(join(root,path))).digest('hex');
const reference=args.includes('--baseline-report')?JSON.parse(await readFile(resolve(root,arg('--baseline-report')),'utf8')):null;
if(reference){
 for(const path of ['src/cloud/cloud-field.js','src/cloud/cloud-anime-renderer.js','tools/cloud-lab.js','tools/cloud-animation-paths.js'])
  assert.equal(reference.sha256[path],report.sha256[path],`unchanged baseline input ${path}`);
 report.baselineCapturedAt=reference.capturedAt;report.baselineProvenance=reference.sha256;
}
const encode=(input,output)=>execFileSync('ffmpeg',['-v','error','-y','-framerate','15','-i',input,'-frames:v',String(frames),'-vf','scale=960:540','-c:v','libvpx','-crf','12','-b:v','800k','-deadline','realtime','-cpu-used','6',output],{stdio:'pipe'});
let browser;
try{
 browser=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});report.browser=browser.version();
 const page=await browser.newPage({viewport:{width:1280,height:720},deviceScaleFactor:1});
 page.on('pageerror',e=>report.errors.push(e.message));page.on('console',m=>{if(m.type()==='error')report.errors.push(m.text());});
 page.on('response',r=>{if(r.status()>=400)report.errors.push(`HTTP ${r.status()} ${r.url()}`);});page.on('requestfailed',r=>report.errors.push(r.url()));
 await page.goto(`http://127.0.0.1:${server.address().port}/tools/cloud-lab.html`);
 await page.waitForFunction(()=>window.__cloudLab?.snapshot().ready,null,{timeout:60000});
 await page.evaluate(()=>{window.__cloudLab.setAnimation(false);document.querySelector('aside').style.display='none';document.querySelector('#reticle').style.display='none';});
 for(const path of paths){
  report.scenes[path.id]=reference?{anime:reference.scenes[path.id].anime}:{};
  for(const mode of reference?['stable']:['anime','stable']){
   const dir=join(raw,`${path.id}-${mode}`);await mkdir(dir,{recursive:true});const states=[];
   await page.evaluate(({id,mode})=>{const l=window.__cloudLab;l.setScenario(id);l.setRenderer(mode);l.setTime(0);},{id:path.id,mode});
   for(let i=0;i<frames;i++){
    const state=await page.evaluate(({p,elevated,id})=>{
     const l=window.__cloudLab;
     if(elevated){
      l.setScenario(id);l.setProgress(p);const s=l.frame(),eye=s.position;
      eye[1]=l.field.params.top+350;const group=l.field.lobes.slice(24,27);
      const target=[group.reduce((a,b)=>a+b.x,0)/3,(l.field.params.base+l.field.params.top)/2,group.reduce((a,b)=>a+b.z,0)/3];
      l.setPose(eye,target,{aircraft:true});
     }else l.setProgress(p);
     const s=l.frame(),gl=document.querySelector('canvas').getContext('webgl2');
     const pixels=new Uint8Array(32*18*4);gl.readPixels(Math.floor(gl.drawingBufferWidth/2)-16,Math.floor(gl.drawingBufferHeight/2)-9,32,18,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
     let mean=0;for(let j=0;j<pixels.length;j+=4)mean+=pixels[j]+pixels[j+1]+pixels[j+2];
     return {position:s.position,direction:s.direction,progress:s.progress,density:s.density,T500:s.transmittance500,builds:s.geometryBuilds,
      meanRgb:mean/(32*18*3*255),calls:s.calls,triangles:s.triangles,programsRunnable:s.programsRunnable,field:s.field};
    },{p:i/(frames-1),elevated,id:path.id});
    assert.ok(state.programsRunnable);assert.ok(state.calls<20);states.push(state);
    await page.screenshot({path:join(dir,`frame-${String(i).padStart(4,'0')}.jpg`),type:'jpeg',quality:86});
   }
   assert.ok(states.every(s=>s.builds===states[0].builds),'no camera-driven volume/geometry builds');
   const samples=Array.from({length:6},(_,i)=>Math.round((frames-1)*i/5));
   execFileSync('ffmpeg',['-v','error','-y','-framerate','15','-i',join(dir,'frame-%04d.jpg'),'-vf',`select='${samples.map(n=>`eq(n,${n})`).join('+')}',scale=426:240,tile=3x2`,'-frames:v','1',join(out,`${path.id}-${mode}.jpg`)],{stdio:'pipe'});
   if(!quick)encode(join(dir,'frame-%04d.jpg'),join(out,`${path.id}-${mode}.webm`));
   report.scenes[path.id][mode]={states,maxCentreRgbDelta:Math.max(...states.slice(1).map((s,i)=>Math.abs(s.meanRgb-states[i].meanRgb)))};
   console.log(`${round} ${path.id} ${mode}: ${frames} real frames`);
  }
  const {anime,stable}=report.scenes[path.id];
  anime.states.forEach((s,i)=>{assert.deepEqual(s.position,stable.states[i].position);assert.deepEqual(s.direction,stable.states[i].direction);assert.equal(s.density,stable.states[i].density);assert.deepEqual(s.field,stable.states[i].field);});
 }
 report.rays=await page.evaluate(()=>{
  const l=window.__cloudLab,results=[],gl=document.querySelector('canvas').getContext('webgl2');l.setRenderer('stable');l.setDensityView(true);
  for(const id of ['approach','climb','sea-wall','entry','inside','exit','turn90','turn180']){
   l.setScenario(id);l.setProgress(0.5);const s=l.frame(),target=l.camera.getWorldDirection(l.camera.position.clone()).multiplyScalar(1000).add(l.camera.position);
   l.setPose(s.position,target.toArray(),{aircraft:false});l.frame();const camera=l.camera,w=gl.drawingBufferWidth,h=gl.drawingBufferHeight;
   const pixels=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
   for(const u of [0.2,0.5,0.8])for(const v of [0.2,0.5,0.8]){
    const x=Math.floor(w*u),y=Math.floor(h*v),ray=camera.position.clone().set((x+0.5)/w*2-1,(y+0.5)/h*2-1,0.5).unproject(camera).sub(camera.position).normalize();
    const distance=ray.y<0?Math.min(24000,-camera.position.y/ray.y):24000;
    const end=camera.position.clone().addScaledVector(ray,distance),ref=l.field.integrateSightline(camera.position,end,{step:15}).transmittance;
    const actual=pixels[(x+y*w)*4]/255;results.push({id,u,v,referenceT:ref,renderedT:actual,error:Math.abs(ref-actual)});
   }
  }l.setDensityView(false);return results;
 });
 report.maxRayError=Math.max(...report.rays.map(r=>r.error));
 assert.ok(report.maxRayError<0.20,'bounded display integral stays near the original B0 sightline');
 if(!quick&&paths.length>1){
  for(const mode of ['anime','stable']){
   const list=join(raw,`concat-${mode}.txt`);await writeFile(list,paths.map(p=>`file '${join(out,`${p.id}-${mode}.webm`).replaceAll('\\','/')}'`).join('\n'));
   execFileSync('ffmpeg',['-v','error','-y','-f','concat','-safe','0','-i',list,'-c','copy',join(out,`overview-${mode}.webm`)],{stdio:'pipe'});
  }
 }
 if(!quick&&!args.includes('--clips-only')){
  // Slow translation at 220 m/s and 60 Hz around entry, no frame-wide transition.
  report.boundary=await page.evaluate(()=>{
   const quality=document.querySelector('#quality');quality.value='0.5';quality.dispatchEvent(new Event('change'));
   const l=window.__cloudLab;l.setScenario('entry');l.setRenderer('stable');const means=[],builds=l.snapshot().geometryBuilds;
   const gl=document.querySelector('canvas').getContext('webgl2'),pixels=new Uint8Array(32*18*4);
   for(let i=0;i<120;i++){
    l.setProgress(0.35+i*220/60/1100);l.frame();gl.readPixels(gl.drawingBufferWidth/2-16,gl.drawingBufferHeight/2-9,32,18,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
    let mean=0;for(let j=0;j<pixels.length;j+=4)mean+=pixels[j]+pixels[j+1]+pixels[j+2];means.push(mean/(32*18*3*255));
   }return {frames:means.length,width:gl.drawingBufferWidth,height:gl.drawingBufferHeight,maxCentreRgbDelta:Math.max(...means.slice(1).map((m,i)=>Math.abs(m-means[i]))),buildsBefore:builds,buildsAfter:l.snapshot().geometryBuilds};
  });
  assert.ok(report.boundary.maxCentreRgbDelta<0.06);assert.equal(report.boundary.buildsBefore,report.boundary.buildsAfter);
 }
 assert.deepEqual(report.errors,[]);report.passed=true;
}finally{await browser?.close();server.close();await writeFile(join(out,'report.json'),JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({passed:report.passed,round,scenes:Object.keys(report.scenes).length,errors:report.errors}));
