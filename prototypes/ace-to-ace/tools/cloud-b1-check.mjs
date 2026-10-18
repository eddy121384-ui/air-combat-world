// Real fixed-camera B0/B1 comparisons and traversal sequences. Requires Playwright.
import http from 'node:http';
import assert from 'node:assert/strict';
import { readFile,mkdir,writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve,extname,sep } from 'node:path';
import {createHash} from 'node:crypto';
const {chromium}=createRequire(import.meta.url)('playwright');
const root=fileURLToPath(new URL('../',import.meta.url));
const args=process.argv.slice(2), round=args[args.indexOf('--round')+1]||'final';
const quick=args.includes('--quick');
const out=new URL(`../docs/cloud-engine-b1/${round}/`,import.meta.url);await mkdir(out,{recursive:true});
const mime={'.html':'text/html','.js':'text/javascript','.webp':'image/webp','.png':'image/png','.jpg':'image/jpeg'};
const server=http.createServer(async(req,res)=>{try{
 const path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://local').pathname));assert.ok(path.startsWith(resolve(root)+sep));
 const data=await readFile(path);res.writeHead(200,{'Content-Type':mime[extname(path)]||'application/octet-stream'});res.end(data);
}catch{res.writeHead(404);res.end('not found');}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const views=[
 ['01-wall',[0,3200,5100],[0,3100,0]],
 ['02-side',[4500,3150,800],[0,3050,0]],
 ['03-cloud-sea',[1800,4600,2000],[0,3150,-600]],
 ['04-base',[1400,1700,2100],[0,2800,-200]],
 ['05-skim',[2600,3150,1300],[1700,3050,-1200]],
 ['06-entry',[0,3062,2470],[0,3050,1000]],
 ['07-interior',[0,3062,60],[0,3050,-800]],
 ['08-exit',[0,3062,-2750],[1200,3080,-4100]],
 ['09-turn90',[0,3062,-2750],[1500,3050,-2750]],
 ['10-turn180',[0,3062,-2750],[0,3050,0]],
];
const report={round,errors:[],views:{},sequence:[],runtime:'Chromium ANGLE SwiftShader, not iPhone hardware'};
report.provenance={baseline:'a75ea74fcadcf73464c9aea42164dcb96b57509a',capturedAt:new Date().toISOString(),sha256:{}};
for(const path of ['src/cloud/cloud-field.js','src/cloud/cloud-layout.js','src/cloud/cloud-anime-renderer.js','tools/cloud-lab.js',
 'assets/cloud-b1/cloud-materials-b1.webp','assets/cloud-b1/cloud-silhouettes-b1.webp'])
 report.provenance.sha256[path]=createHash('sha256').update(await readFile(resolve(root,path))).digest('hex');
let browser;
try{
 browser=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
 report.browser=browser.version();const page=await browser.newPage({viewport:{width:1280,height:720},deviceScaleFactor:1});
 page.on('pageerror',e=>report.errors.push(e.message));page.on('console',m=>{if(m.type()==='error')report.errors.push(m.text());});
 page.on('response',r=>{if(r.status()>=400)report.errors.push(`HTTP ${r.status()}: ${r.url()}`);});
 page.on('requestfailed',r=>report.errors.push(`request failed ${r.url()}`));
 await page.goto(`http://127.0.0.1:${server.address().port}/tools/cloud-lab.html`);
 await page.waitForFunction(()=>window.__cloudLab?.snapshot().ready,null,{timeout:60000});
 await page.evaluate(()=>{window.__cloudLab.setAnimation(false);document.querySelector('aside').style.display='none';document.querySelector('#reticle').style.display='none';});
 if(args.includes('--no-fog'))await page.evaluate(()=>{document.querySelector('#fog').checked=false;});
 for(const[name,eye,target]of views){
  await page.evaluate(name=>{
    const kind=document.querySelector('#kind'),value=name==='03-cloud-sea'?'stratocumulus':'cumulus';
    if(kind.value!==value){kind.value=value;kind.dispatchEvent(new Event('change'));}
  },name);
  report.views[name]={};
  for(const mode of quick?['anime']:['debug','anime']){
   const state=await page.evaluate(({mode,eye,target})=>{const l=window.__cloudLab;l.setPose(eye,target,{aircraft:true});l.setRenderer(mode);return l.frame();},{mode,eye,target});
   assert.ok(state.programsRunnable);assert.ok(state.calls<24);
   if(mode==='anime'){assert.equal(state.textureWidth,1024);assert.equal(state.layers.count,27);assert.equal(state.layers.triangles,54);assert.ok(state.triangles<10000);}
   await page.screenshot({path:fileURLToPath(new URL(`${name}-${mode}.jpg`,out)),type:'jpeg',quality:90});report.views[name][mode]=state;
  }
  if(!quick){assert.deepEqual(report.views[name].anime.position,report.views[name].debug.position);assert.equal(report.views[name].anime.density,report.views[name].debug.density);assert.deepEqual(report.views[name].anime.field,report.views[name].debug.field);}
 }
 const sequence=quick?[0.14,0.19,0.24,0.5,0.76,0.84,0.9]:Array.from({length:25},(_,i)=>0.10+i*0.8/24);
 for(const[i,progress]of sequence.entries()){
  const state=await page.evaluate(p=>{const l=window.__cloudLab;l.setRenderer('anime');l.setRoute('traverse');l.setProgress(p);return l.frame();},progress);
  await page.screenshot({path:fileURLToPath(new URL(`flight-${String(i).padStart(2,'0')}.jpg`,out)),type:'jpeg',quality:88});report.sequence.push(state);
 }
 if(!quick){
  const pixelHash=()=>page.evaluate(()=>{
   window.__cloudLab.frame();const gl=document.querySelector('canvas').getContext('webgl2');
   const pixels=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4);gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
   let h=2166136261;for(const p of pixels)h=Math.imul(h^p,16777619);return h>>>0;
  });
  const pose=target=>page.evaluate(target=>{const l=window.__cloudLab;l.setPose([1800,3200,2600],target,{aircraft:true});l.frame();},target);
  await pose([0,3050,0]);const first=await pixelHash();await pose([3600,3200,5200]);await pose([0,3050,0]);
  assert.equal(first,await pixelHash(),'world artwork returns to identical framebuffer after turning away/back');
  report.returnToPosePixelsIdentical=true;
  report.boundarySweep=await page.evaluate(()=>{
   const l=window.__cloudLab,gl=document.querySelector('canvas').getContext('webgl2'),pixels=new Uint8Array(16*16*4),means=[];
   const before=l.snapshot().geometryBuilds;
   for(let i=0;i<120;i++){
    const z=2700-i*220/60;l.setPose([0,3062,z],[0,3050,z-800]);l.frame();
    gl.readPixels(gl.drawingBufferWidth/2-8,gl.drawingBufferHeight/2-8,16,16,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
    let mean=0;for(let j=0;j<pixels.length;j+=4)mean+=pixels[j]+pixels[j+1]+pixels[j+2];means.push(mean/(256*3*255));
   }
   return {frames:means.length,maxMeanRgbDelta:Math.max(...means.slice(1).map((v,i)=>Math.abs(v-means[i]))),geometryBuildsBefore:before,geometryBuildsAfter:l.snapshot().geometryBuilds};
  });
  assert.ok(report.boundarySweep.maxMeanRgbDelta<0.08,'smooth entry pixels');
  assert.equal(report.boundarySweep.geometryBuildsBefore,report.boundarySweep.geometryBuildsAfter,'no frame-driven geometry/cache rebuild');
  // Controlled manual frames keep GPU timing bounded, independent of queued rAF work.
  report.perf={};
  for(const quality of ['0.5','1'])for(const mode of ['anime','debug']){
   await page.evaluate(({quality,mode})=>{
    const q=document.querySelector('#quality');q.value=quality;q.dispatchEvent(new Event('change'));
    const l=window.__cloudLab;l.setPose([0,3062,60],[0,3050,-800],{aircraft:true});l.setRenderer(mode);l.frame();
    document.querySelector('canvas').getContext('webgl2').finish();
   },{quality,mode});
   const samples=[];let previous=-1,discard=2;
   for(let i=0;i<160&&samples.length<6;i++){
    await page.waitForTimeout(80);
    const s=await page.evaluate(()=>{const s=window.__cloudLab.frame();document.querySelector('canvas').getContext('webgl2').finish();return s;});
    if(!s.gpuTimerAvailable||s.gpuSample!==previous){previous=s.gpuSample;if(discard>0)discard--;else samples.push(s);}
   }
   // Software drivers can leave a timer pending; retain the actual fresh count.
   report.perf[`${mode}-${quality}`]=samples;
   assert.ok(samples.length>=3,`at least three fresh GPU timer samples for ${mode} ${quality}`);
   console.log(`B1 compare ${mode} ${quality}: ${samples.length} fresh samples (target 6)`);
  }
  // Real WebGL video, continuous animation, with a fixed simulation step per real frame.
  const vc=await browser.newContext({viewport:{width:1280,height:720},recordVideo:{dir:fileURLToPath(out),size:{width:960,height:540}}});
  const vp=await vc.newPage();vp.on('pageerror',e=>report.errors.push(`video: ${e.message}`));
  await vp.goto(page.url());await vp.waitForFunction(()=>window.__cloudLab?.snapshot().ready);
  await vp.evaluate(()=>{
   const l=window.__cloudLab;l.setAnimation(false);document.querySelector('aside').style.display='none';document.querySelector('#reticle').style.display='none';
   l.setRoute('traverse');l.setProgress(0.08);
   let steps=0;function fly(){l.frame(0.12);steps++;if(steps<250)requestAnimationFrame(fly);else window.__flightVideoDone=true;}
   document.querySelector('#play').click();requestAnimationFrame(fly);
  });
  await vp.waitForFunction(()=>window.__flightVideoDone,null,{timeout:60000});
  report.videoEnd=await vp.evaluate(()=>window.__cloudLab.snapshot());
  assert.ok(report.videoEnd.progress>0.9&&report.videoEnd.density===0);
  const video=vp.video();await vc.close();await video.saveAs(fileURLToPath(new URL('traversal.webm',out)));
 }
 assert.deepEqual(report.errors,[]);report.passed=true;
}finally{await browser?.close();server.close();await writeFile(new URL('report.json',out),JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({passed:report.passed,round,errors:report.errors,views:Object.keys(report.views).length,sequence:report.sequence.length}));
