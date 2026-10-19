// One external timer query per frame; polling never submits more draw work.
import http from 'node:http';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {resolve,sep,extname} from 'node:path';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const root=fileURLToPath(new URL('../',import.meta.url)),out=new URL('../docs/cloud-engine-b2/performance/',import.meta.url);
await mkdir(out,{recursive:true});
const server=http.createServer(async(req,res)=>{try{
 const p=resolve(root,'.'+new URL(req.url,'http://local').pathname);assert.ok(p.startsWith(root.slice(0,-1)+sep));
 const data=await readFile(p);res.writeHead(200,{'Content-Type':{'.html':'text/html','.js':'text/javascript','.webp':'image/webp','.jpg':'image/jpeg'}[extname(p)]||'application/octet-stream'});res.end(data);
}catch{res.writeHead(404);res.end('not found');}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const report={capturedAt:new Date().toISOString(),runtime:'Chromium ANGLE SwiftShader; no iPhone hardware claim',method:'external timer, internal timer disabled, no redraw while waiting',errors:[],perf:{},sha256:{}};
for(const p of ['src/cloud/cloud-field.js','src/cloud/cloud-anime-renderer.js','src/cloud/cloud-stable-renderer.js','src/cloud/cloud-volume.js','src/cloud/cloud-hull.js','src/cloud/cloud-hybrid-renderer.js','tools/cloud-lab.js','tools/cloud-animation-paths.js'])report.sha256[p]=createHash('sha256').update(await readFile(resolve(root,p))).digest('hex');
let browser;
try{
 browser=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});report.browser=browser.version();
 const page=await browser.newPage({viewport:{width:1280,height:720},deviceScaleFactor:1});
 await page.addInitScript(()=>{
  const native=WebGL2RenderingContext.prototype.getExtension;
  window.__nativeTimer=gl=>native.call(gl,'EXT_disjoint_timer_query_webgl2');
  WebGL2RenderingContext.prototype.getExtension=function(name){return name==='EXT_disjoint_timer_query_webgl2'?null:native.call(this,name);};
 });
 page.on('pageerror',e=>report.errors.push(e.message));page.on('console',m=>{if(m.type()==='error')report.errors.push(m.text());});
 await page.goto(`http://127.0.0.1:${server.address().port}/tools/cloud-lab.html`);await page.waitForFunction(()=>window.__cloudLab?.snapshot().ready);
 await page.evaluate(()=>window.__cloudLab.setAnimation(false));
 for(const pose of ['approach','inside'])for(const quality of ['0.5','1'])for(const mode of ['anime','stable','hybrid']){
  await page.evaluate(({pose,quality,mode})=>{
   const q=document.querySelector('#quality');q.value=quality;q.dispatchEvent(new Event('change'));
   const l=window.__cloudLab;l.setScenario(pose);l.setProgress(0.5);l.setRenderer(mode);l.frame();document.querySelector('canvas').getContext('webgl2').finish();
  },{pose,quality,mode});
  const samples=[];
  for(let i=0;i<3;i++)samples.push(await page.evaluate(async()=>{
   const gl=document.querySelector('canvas').getContext('webgl2'),ext=window.__nativeTimer(gl),q=ext?gl.createQuery():null;
   if(q)gl.beginQuery(ext.TIME_ELAPSED_EXT,q);const begin=performance.now(),s=window.__cloudLab.frame();
   if(q)gl.endQuery(ext.TIME_ELAPSED_EXT);gl.finish();const finishWallMs=performance.now()-begin;
   let gpuMs=null,disjoint=false;
   if(q){
    const deadline=performance.now()+10000;
    while(!gl.getQueryParameter(q,gl.QUERY_RESULT_AVAILABLE)&&performance.now()<deadline)await new Promise(r=>setTimeout(r,30));
    disjoint=gl.getParameter(ext.GPU_DISJOINT_EXT);
    if(gl.getQueryParameter(q,gl.QUERY_RESULT_AVAILABLE)&&!disjoint)gpuMs=gl.getQueryParameter(q,gl.QUERY_RESULT)/1e6;
    gl.deleteQuery(q);
   }
   delete s.layers?.anchors;return {...s,gpuMs,gpuTimerAvailable:!!ext,disjoint,finishWallMs};
  }));
  assert.ok(samples.every(s=>s.programsRunnable));report.perf[`${pose}-${quality}-${mode}`]=samples;
  console.log(`${pose} ${quality} ${mode}: ${samples.map(s=>s.gpuMs?.toFixed(2)??'N/A').join(', ')} ms`);
 }
 report.boundary=await page.evaluate(()=>{
  const l=window.__cloudLab,q=document.querySelector('#quality');q.value='0.25';q.dispatchEvent(new Event('change'));
  l.setScenario('entry');l.setRenderer('hybrid');const build=l.snapshot().geometryBuilds,gl=document.querySelector('canvas').getContext('webgl2'),pixels=new Uint8Array(32*18*4),means=[];
  for(let i=0;i<120;i++){
   l.setProgress(0.35+i*220/60/1100);l.frame();gl.readPixels(gl.drawingBufferWidth/2-16,gl.drawingBufferHeight/2-9,32,18,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
   let m=0;for(let j=0;j<pixels.length;j+=4)m+=pixels[j]+pixels[j+1]+pixels[j+2];means.push(m/(32*18*3*255));
  }return {frames:120,width:gl.drawingBufferWidth,height:gl.drawingBufferHeight,buildsBefore:build,buildsAfter:l.snapshot().geometryBuilds,maxCentreRgbDelta:Math.max(...means.slice(1).map((m,i)=>Math.abs(m-means[i])))};
 });
 assert.equal(report.boundary.buildsBefore,report.boundary.buildsAfter);assert.ok(report.boundary.maxCentreRgbDelta<0.06);
 // Numerical limit of sparse local mist, measured from actual GPU output.
 // This is not an exact full-field volume renderer; retain errors, don't hide them.
 report.mistRays=await page.evaluate(()=>{
  const l=window.__cloudLab,gl=document.querySelector('canvas').getContext('webgl2'),results=[];
  l.setDensityView(true);l.setRenderer('hybrid');
  for(const id of ['approach','side-pass','climb','sea-wall','entry','inside','exit','turn180']){
   l.setScenario(id);l.setProgress(0.5);const s=l.frame(),target=l.camera.getWorldDirection(l.camera.position.clone()).multiplyScalar(1000).add(l.camera.position);
   l.setPose(s.position,target.toArray(),{aircraft:false});l.frame();
   const camera=l.camera,w=gl.drawingBufferWidth,h=gl.drawingBufferHeight,pixels=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
   for(const u of [0.2,0.5,0.8])for(const v of [0.2,0.5,0.8]){
    const x=Math.floor(w*u),y=Math.floor(h*v),ray=camera.position.clone().set((x+0.5)/w*2-1,(y+0.5)/h*2-1,0.5).unproject(camera).sub(camera.position).normalize();
    const end=camera.position.clone().addScaledVector(ray,900),reference=l.field.integrateSightline(camera.position,end,{step:10}).transmittance,actual=pixels[(x+y*w)*4]/255;
    results.push({id,u,v,reference,actual,error:Math.abs(reference-actual)});
   }
  }l.setDensityView(false);return results;
 });
 report.mistMaxError=Math.max(...report.mistRays.map(r=>r.error));
 report.mistMeanError=report.mistRays.reduce((s,r)=>s+r.error,0)/report.mistRays.length;
 assert.ok(report.mistRays.every(r=>Number.isFinite(r.actual)&&r.actual>=0&&r.actual<=1));
 assert.deepEqual(report.errors,[]);report.passed=true;
}finally{await browser?.close();server.close();await writeFile(new URL('report.json',out),JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({passed:report.passed,errors:report.errors}));
