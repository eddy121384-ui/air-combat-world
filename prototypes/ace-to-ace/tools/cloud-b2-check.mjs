// Actual WebGL sequences for all three representations, same field/pose/time.
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
const args=process.argv.slice(2),arg=(k,d)=>args.includes(k)?args[args.indexOf(k)+1]:d;
const quick=args.includes('--quick'),round=arg('--round',quick?'iteration-1':'final'),frames=+arg('--frames',quick?'7':'90');
const modes=arg('--modes','anime,stable,hybrid').split(','),paths=args.includes('--traverse')?[{id:'traverse',kind:'cumulus'}]:CLOUD_ANIMATION_PATHS.filter(p=>!args.includes('--scene')||p.id===arg('--scene'));
const clearSide=args.includes('--clear-side');assert.ok(!clearSide||paths.length===1&&paths[0].id==='side-pass');
const root=fileURLToPath(new URL('../',import.meta.url)),out=join(root,'docs/cloud-engine-b2',round),raw=join(root,'tools/out/cloud-b2',round);
await mkdir(out,{recursive:true});await mkdir(raw,{recursive:true});
const server=http.createServer(async(req,res)=>{try{
 const p=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://local').pathname));assert.ok(p.startsWith(resolve(root)+sep));
 const data=await readFile(p);res.writeHead(200,{'Content-Type':{'.html':'text/html','.js':'text/javascript','.webp':'image/webp','.jpg':'image/jpeg','.png':'image/png'}[extname(p)]||'application/octet-stream'});res.end(data);
}catch{res.writeHead(404);res.end('not found');}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const report={baseline:'996329258379383f6ed1d8bdb4ea992589be6c14',animfix:'abab83a84212c20406494784e7a3ea5ab4342630',round,frames,modes,clearSide,capturedAt:new Date().toISOString(),errors:[],scenes:{},sha256:{},
 video:'15fps offline encoding of actual runtime frames, no interpolation; not device FPS',runtime:'Chromium ANGLE SwiftShader, no iPhone claim'};
for(const p of ['src/cloud/cloud-field.js','src/cloud/cloud-layout.js','src/cloud/cloud-anime-renderer.js','src/cloud/cloud-stable-renderer.js','src/cloud/cloud-volume.js','src/cloud/cloud-hull.js','src/cloud/cloud-hybrid-renderer.js','tools/cloud-lab.js','tools/cloud-animation-paths.js'])report.sha256[p]=createHash('sha256').update(await readFile(join(root,p))).digest('hex');
let browser;
try{
 browser=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});report.browser=browser.version();
 const page=await browser.newPage({viewport:{width:1280,height:720},deviceScaleFactor:1});
 // Avoid nested internal timer queries in capture; profiling has its own harness.
 await page.addInitScript(()=>{const native=WebGL2RenderingContext.prototype.getExtension;WebGL2RenderingContext.prototype.getExtension=function(n){return n==='EXT_disjoint_timer_query_webgl2'?null:native.call(this,n);};});
 page.on('pageerror',e=>report.errors.push(e.message));page.on('console',m=>{if(m.type()==='error')report.errors.push(m.text());});
 page.on('response',r=>{if(r.status()>=400)report.errors.push(`HTTP ${r.status()} ${r.url()}`);});
 page.on('requestfailed',r=>report.errors.push(r.url()));
 await page.goto(`http://127.0.0.1:${server.address().port}/tools/cloud-lab.html`);
 await page.waitForFunction(()=>window.__cloudLab?.snapshot().ready,null,{timeout:60000});
 await page.evaluate(()=>{window.__cloudLab.setAnimation(false);document.querySelector('aside').style.display='none';document.querySelector('#reticle').style.display='none';});
 for(const path of paths){
  report.scenes[path.id]={};
  for(const mode of modes){
   const dir=join(raw,`${path.id}-${mode}`),states=[];await mkdir(dir,{recursive:true});
   await page.evaluate(({id,mode})=>{const l=window.__cloudLab;if(id==='traverse')l.setRoute('traverse');else l.setScenario(id);l.setRenderer(mode);l.setTime(0);},{id:path.id,mode});
   for(let i=0;i<frames;i++){
    const state=await page.evaluate(({p,clearSide})=>{
     const l=window.__cloudLab;l.setProgress(p);
     if(clearSide){const lobes=l.field.lobes.slice(24,27),cx=lobes.reduce((s,v)=>s+v.x,0)/3,cz=lobes.reduce((s,v)=>s+v.z,0)/3,mid=(l.field.params.base+l.field.params.top)/2;
      l.setPose([Math.max(cx+Math.max(...lobes.map(v=>v.rx))+300,l.field.bounds.max.x+180),mid+30,cz+1700-3400*p],[cx,mid,cz],{aircraft:true});}
     const s=l.frame();
     return {position:s.position,direction:s.direction,density:s.density,field:s.field,T500:s.transmittance500,builds:s.geometryBuilds,calls:s.calls,triangles:s.triangles,width:s.width,height:s.height,programsRunnable:s.programsRunnable};
    },{p:i/(frames-1),clearSide});
    assert.ok(state.programsRunnable);assert.ok(state.calls<20);states.push(state);
    await page.screenshot({path:join(dir,`frame-${String(i).padStart(4,'0')}.jpg`),type:'jpeg',quality:87});
   }
   assert.ok(states.every(s=>s.builds===states[0].builds),'camera does not rebuild geometry');
   if(clearSide)assert.ok(states.every(s=>s.density===0),'clear-side eye remains outside B0 clouds');
   if(path.id==='traverse'){
    assert.equal(states[0].density,0);assert.equal(states.at(-1).density,0);assert.ok(states.some(s=>s.density>0.5));
    const expected=Math.hypot(...states[0].position.map((v,k)=>v-states.at(-1).position[k]))/(frames-1);
    for(let i=1;i<states.length;i++)assert.ok(Math.abs(Math.hypot(...states[i].position.map((v,k)=>v-states[i-1].position[k]))-expected)<1e-6,'continuous path without cuts or teleports');
   }
   const samples=Array.from({length:6},(_,i)=>Math.round((frames-1)*i/5));
   execFileSync('ffmpeg',['-v','error','-y','-framerate','15','-i',join(dir,'frame-%04d.jpg'),'-vf',`select='${samples.map(n=>`eq(n,${n})`).join('+')}',scale=426:240,tile=3x2`,'-frames:v','1',join(out,`${path.id}-${mode}.jpg`)],{stdio:'pipe'});
   if(!quick)execFileSync('ffmpeg',['-v','error','-y','-framerate','15','-i',join(dir,'frame-%04d.jpg'),'-frames:v',String(frames),'-vf','scale=960:540','-c:v','libvpx','-crf','10','-b:v','1100k','-deadline','realtime','-cpu-used','6',join(out,`${path.id}-${mode}.webm`)],{stdio:'pipe'});
   report.scenes[path.id][mode]={states};console.log(`${round} ${path.id} ${mode}: ${frames} WebGL frames`);
  }
  const reference=report.scenes[path.id][modes[0]].states;
  for(const mode of modes.slice(1))reference.forEach((s,i)=>{const b=report.scenes[path.id][mode].states[i];assert.deepEqual(s.position,b.position);assert.deepEqual(s.direction,b.direction);assert.equal(s.density,b.density);assert.deepEqual(s.field,b.field);});
  await writeFile(join(out,'report.json'),JSON.stringify(report,null,2)+'\n');
 }
 if(!quick&&paths.length>1)for(const mode of modes){
  const list=join(raw,`concat-${mode}.txt`);await writeFile(list,paths.map(p=>`file '${join(out,`${p.id}-${mode}.webm`).replaceAll('\\','/')}'`).join('\n'));
  execFileSync('ffmpeg',['-v','error','-y','-f','concat','-safe','0','-i',list,'-c','copy',join(out,`overview-${mode}.webm`)],{stdio:'pipe'});
 }
 assert.deepEqual(report.errors,[]);report.passed=true;
}finally{await browser?.close();server.close();await writeFile(join(out,'report.json'),JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({passed:report.passed,round,scenes:Object.keys(report.scenes).length,errors:report.errors}));
