// Research evidence only. Offline exact-time frames are not device frame rate.
import http from 'node:http';
import assert from 'node:assert/strict';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {resolve,extname,sep,join} from 'node:path';
import {ONE_CLOUD_PATHS} from '../src/cloud/one-cloud.js';
const {chromium}=createRequire(import.meta.url)('playwright');
const args=process.argv.slice(2),quick=args.includes('--stills'),perf=args.includes('--perf');
const root=fileURLToPath(new URL('../',import.meta.url)),out=join(root,'docs/cloud-commercial-npr',perf?'performance':quick?'stills':'motion'),raw=join(root,'tools/out/one-cloud');
await mkdir(out,{recursive:true});await mkdir(raw,{recursive:true});
const server=http.createServer(async(req,res)=>{try{
  const p=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://local').pathname));assert.ok(p.startsWith(resolve(root)+sep));
  const data=await readFile(p);res.writeHead(200,{'Content-Type':{'.html':'text/html','.js':'text/javascript','.webp':'image/webp','.jpg':'image/jpeg'}[extname(p)]||'application/octet-stream'});res.end(data);
}catch{res.writeHead(404);res.end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const modes=['anime','hybrid','prelit'],report={seed:73,sourceBase:'75db0dc3189cc9501210b4580521815d57b7a9cb',errors:[],sha256:{},scenes:{},perf:{},
  runtime:'Chromium ANGLE SwiftShader; software relative test only; no iPhone Safari data',video:'12 fps offline exact-time runtime frames; not measured FPS',capturedAt:new Date().toISOString()};
for(const name of ['src/cloud/one-cloud.js','src/cloud/cloud-prelit-renderer.js','src/cloud/cloud-anime-renderer.js','src/cloud/cloud-hybrid-renderer.js','tools/cloud-lab.js'])
  report.sha256[name]=createHash('sha256').update(await readFile(join(root,name))).digest('hex');
let browser;
try{
  browser=await chromium.launch({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']});
  report.browser=browser.version();
  const page=await browser.newPage({viewport:{width:1280,height:720},deviceScaleFactor:1});
  await page.addInitScript(()=>{
    const native=WebGL2RenderingContext.prototype.getExtension;
    window.__nativeTimer=gl=>native.call(gl,'EXT_disjoint_timer_query_webgl2');
    WebGL2RenderingContext.prototype.getExtension=function(n){return n==='EXT_disjoint_timer_query_webgl2'?null:native.call(this,n);};
  });
  page.on('pageerror',e=>report.errors.push(e.message));page.on('console',m=>{if(m.type()==='error')report.errors.push(m.text());});
  page.on('response',r=>{if(r.status()>=400)report.errors.push(`HTTP ${r.status()} ${r.url()}`);});
  await page.goto(`http://127.0.0.1:${server.address().port}/tools/cloud-lab.html?oneCloud=1`);
  await page.waitForFunction(()=>window.__cloudLab?.snapshot().ready,null,{timeout:120000});
  await page.evaluate(()=>{window.__cloudLab.setAnimation(false);document.querySelector('aside').hidden=true;document.querySelector('#reticle').hidden=true;});
  report.renderer=await page.evaluate(()=>{const gl=document.querySelector('canvas').getContext('webgl2'),e=gl.getExtension('WEBGL_debug_renderer_info');return e?gl.getParameter(e.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER);});
  if(!perf)for(const path of ONE_CLOUD_PATHS){
    report.scenes[path.id]={};
    for(const mode of modes){
      const frames=quick?3:path.seconds*12+1,dir=join(raw,`${path.id}-${mode}`),states=[];await mkdir(dir,{recursive:true});
      await page.evaluate(({id,mode})=>{const l=window.__cloudLab;l.setScenario(id);l.setRenderer(mode);},{id:path.id,mode});
      for(let i=0;i<frames;i++){
        const state=await page.evaluate(p=>{const l=window.__cloudLab;l.setProgress(p);const s=l.frame();return {position:s.position,direction:s.direction,density:s.density,T500:s.transmittance500,builds:s.geometryBuilds,calls:s.calls,triangles:s.triangles,width:s.width,height:s.height,programsRunnable:s.programsRunnable};},i/(frames-1));
        assert.ok(state.programsRunnable);states.push(state);
        await page.screenshot({path:join(dir,`frame-${String(i).padStart(4,'0')}.jpg`),type:'jpeg',quality:88});
      }
      assert.ok(states.every(s=>s.builds===states[0].builds),'no camera-dependent bake');
      report.scenes[path.id][mode]={frames,states};
      const sample=[0,Math.floor((frames-1)/2),frames-1];
      execFileSync('ffmpeg',['-v','error','-y','-framerate','12','-i',join(dir,'frame-%04d.jpg'),'-vf',`select='${sample.map(n=>`eq(n,${n})`).join('+')}',scale=640:360,tile=3x1`,'-frames:v','1',join(out,`${path.id}-${mode}.jpg`)],{stdio:'pipe'});
      if(!quick)execFileSync('ffmpeg',['-v','error','-y','-framerate','12','-i',join(dir,'frame-%04d.jpg'),'-frames:v',String(frames),'-vf','scale=960:540','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',join(out,`${path.id}-${mode}.mp4`)],{stdio:'pipe'});
      console.log(`${path.id} ${mode}: ${frames} frames`);
    }
    for(const mode of modes.slice(1))report.scenes[path.id].anime.states.forEach((s,i)=>{
      const b=report.scenes[path.id][mode].states[i];for(const key of ['position','direction','density','T500','width','height'])assert.deepEqual(s[key],b[key]);
    });
    await writeFile(join(out,'report.json'),JSON.stringify(report,null,2));
  }
  if(perf)for(const route of ['approach-skim','entry'])for(const mode of modes)for(const enabled of [false,true]){
    await page.evaluate(({route,mode,enabled})=>{const l=window.__cloudLab;l.setScenario(route);l.setProgress(route==='entry'?0.9:0.15);document.querySelector('#clouds').checked=enabled;l.setRenderer(mode);for(let i=0;i<3;i++)l.frame();document.querySelector('canvas').getContext('webgl2').finish();},{route,mode,enabled});
    const samples=[];
    for(let i=0;i<7;i++)samples.push(await page.evaluate(async()=>{
      const gl=document.querySelector('canvas').getContext('webgl2'),e=window.__nativeTimer(gl),q=e?gl.createQuery():null;
      if(q)gl.beginQuery(e.TIME_ELAPSED_EXT,q);const begin=performance.now(),s=window.__cloudLab.frame();if(q)gl.endQuery(e.TIME_ELAPSED_EXT);gl.finish();
      // Chrome can return from finish before the software backend's work is
      // observable. A readback forces the measured draw to produce its pixel.
      gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array(4));
      const finishWallMs=performance.now()-begin;let elapsedMs=null;
      if(q){const deadline=performance.now()+15000;while(!gl.getQueryParameter(q,gl.QUERY_RESULT_AVAILABLE)&&performance.now()<deadline)await new Promise(r=>setTimeout(r,20));
        if(gl.getQueryParameter(q,gl.QUERY_RESULT_AVAILABLE)&&!gl.getParameter(e.GPU_DISJOINT_EXT))elapsedMs=gl.getQueryParameter(q,gl.QUERY_RESULT)/1e6;gl.deleteQuery(q);}
      return {elapsedMs,finishWallMs,submitMs:s.renderSubmitMs,updateCpuMs:s.updateCpuMs??s.fogCpuMs,calls:s.calls,triangles:s.triangles,cacheBytes:s.cacheBytes,textureBytes:s.textureBytes,renderTargetBytes:s.renderTargetBytes,cacheBuildMs:s.cacheBuildMs,width:s.width,height:s.height};
    }));
    report.perf[`${route}-${mode}-${enabled?'on':'off'}`]=samples;
    console.log(`${route} ${mode} ${enabled}: ${samples.map(s=>s.elapsedMs?.toFixed(1)??'N/A').join(', ')} ms`);
  }
  if(perf){
    report.transmittance=await page.evaluate(()=>{
      const l=window.__cloudLab,gl=document.querySelector('canvas').getContext('webgl2'),pixel=new Uint8Array(4),samples=[];
      document.querySelector('#clouds').checked=true;l.setRenderer('prelit');l.setDensityView(true);
      const builds=l.snapshot().geometryBuilds;
      for(const id of ['entry','exit'])for(let i=0;i<=48;i++){
        l.setScenario(id);l.setProgress(i/48);l.frame();
        const x=Math.floor(gl.drawingBufferWidth/2),y=Math.floor(gl.drawingBufferHeight/2),c=l.camera;
        gl.readPixels(x,y,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);
        const ray=c.position.clone().set(2*(x+0.5)/gl.drawingBufferWidth-1,2*(y+0.5)/gl.drawingBufferHeight-1,0.5).unproject(c).sub(c.position).normalize();
        const end=c.position.clone().addScaledVector(ray,4000),reference=l.field.integrateSightline(c.position,end,{step:2}).transmittance;
        samples.push({id,t:i/48,reference,actual:pixel[0]/255,error:Math.abs(reference-pixel[0]/255)});
      }
      l.setDensityView(false);return {samples,buildsBefore:builds,buildsAfter:l.snapshot().geometryBuilds};
    });
    assert.equal(report.transmittance.buildsBefore,report.transmittance.buildsAfter);
    assert.ok(report.transmittance.samples.every(s=>Number.isFinite(s.actual)&&s.actual>=0&&s.actual<=1));
    // Smoke the unchanged default Lab independently of the one-cloud input.
    await page.goto(`http://127.0.0.1:${server.address().port}/tools/cloud-lab.html`);
    await page.waitForFunction(()=>window.__cloudLab?.snapshot().ready);
    report.defaultLab=await page.evaluate(()=>{window.__cloudLab.setAnimation(false);return window.__cloudLab.frame();});
    assert.equal(report.defaultLab.oneCloud,false);assert.equal(report.defaultLab.rendererMode,'hybrid');assert.ok(report.defaultLab.programsRunnable);
  }
  assert.deepEqual(report.errors,[]);report.passed=true;
}finally{await browser?.close();server.close();await writeFile(join(out,'report.json'),JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify({passed:report.passed,errors:report.errors}));
