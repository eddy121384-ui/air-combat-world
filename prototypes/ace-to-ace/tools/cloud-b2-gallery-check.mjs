import {createRequire} from 'node:module';
import {writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const server=await chromium.launchServer({args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']}),browser=await chromium.connect(server.wsEndpoint()),page=await browser.newPage({viewport:{width:1280,height:760}});
page.setDefaultTimeout(15000);
const report={errors:[],videos:{},passed:false,cleanup:'Kill owned headless BrowserServer after assertions; graceful media-browser close stalled on this Windows host'};
page.on('pageerror',e=>report.errors.push(e.message));page.on('console',m=>{if(m.type()==='error')report.errors.push(m.text());});
page.on('response',r=>{if(r.status()>=400)report.errors.push(`HTTP ${r.status()} ${r.url()}`);});
try{
 await page.goto('http://127.0.0.1:8096/docs/cloud-engine-b2/gallery.html');
 await page.locator('video').evaluateAll(vs=>vs.forEach(v=>{v.preload='auto';v.load();}));
 const choices=await page.locator('#scene option').evaluateAll(xs=>xs.map(x=>x.value));
 for(const scene of choices){
  await page.locator('#scene').selectOption(scene);
  await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>Number.isFinite(v.duration)&&v.readyState>=1),null,{timeout:15000});
  report.videos[scene]=await page.locator('video').evaluateAll(vs=>vs.map(v=>v.duration));
  assert.ok(Math.max(...report.videos[scene])-Math.min(...report.videos[scene])<0.01);
  console.log('metadata',scene,report.videos[scene]);
 }
 await page.locator('#scene').selectOption('side-clear');
 await page.waitForFunction(()=>[...document.querySelectorAll('video')].every(v=>v.readyState>=1),null,{timeout:15000});
 await page.locator('#play').click();await page.waitForTimeout(1200);await page.locator('#play').click();
 console.log('playback',await page.locator('video').evaluateAll(vs=>vs.map(v=>({time:v.currentTime,ready:v.readyState,error:v.error?.message}))));
 assert.ok(await page.locator('video').first().evaluate(v=>v.currentTime)>0.2);
 const before=await page.locator('video').first().evaluate(v=>v.currentTime);await page.locator('#next').click();
 const after=await page.locator('video').first().evaluate(v=>v.currentTime);assert.ok(Math.abs(after-before-1/15)<0.01);
 await page.screenshot({path:'docs/cloud-engine-b2/gallery-runtime.jpg'});
 assert.deepEqual(report.errors,[]);report.passed=true;
}finally{await writeFile('docs/cloud-engine-b2/gallery-smoke.json',JSON.stringify(report,null,2)+'\n');await server.kill();}
console.log(report);
