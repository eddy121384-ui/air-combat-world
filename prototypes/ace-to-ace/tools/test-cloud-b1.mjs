import assert from 'node:assert/strict';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {performance} from 'node:perf_hooks';
import {createCloudField} from '../src/cloud/cloud-field.js';
import {buildCloudLayers,sampleCloudFog,FOG_BREAKS} from '../src/cloud/cloud-layout.js';
const reports=[];
for(const kind of ['cumulus','stratocumulus']){
 const f=createCloudField({kind}),same=createCloudField({kind}),other=createCloudField({kind,seed:74});
 const layers=buildCloudLayers(f);assert.deepEqual(layers,buildCloudLayers(same));assert.notDeepEqual(layers,buildCloudLayers(other));
 assert.equal(layers.length,27);assert.equal(layers.filter(l=>l.detail===0).length,9);
 layers.forEach((l,i)=>{
  assert.deepEqual(l.center,[f.lobes[i].x,f.lobes[i].y,f.lobes[i].z]);
  assert.ok(l.size.every(v=>Number.isFinite(v)&&v>0));assert.ok(l.variant===0||l.variant===1);
 });
 const eye={x:120,y:3000,z:300},directions=[{x:1,y:0,z:0},{x:0,y:1,z:0},{x:0,y:0,z:-1}];
 const a=sampleCloudFog(f,eye,directions),time=60;
 const moved={x:eye.x+f.params.wind.x*time,y:eye.y,z:eye.z+f.params.wind.z*time};
 const b=sampleCloudFog(f,moved,directions,time);
 a.flat().forEach((v,i)=>{assert.ok(v>=0&&v<=1);assert.ok(Math.abs(v-b.flat()[i])<1e-9);});
 const clear=sampleCloudFog(f,{x:0,y:f.params.top+500,z:0},directions.filter(d=>d.y===0));
 assert.ok(clear.flat().every(d=>d===0));
 const constant=sampleCloudFog({sampleDensity:()=>0.5},eye,directions);
 assert.ok(constant.flat().every(d=>d===0.5));
 assert.equal(FOG_BREAKS.length,5);
 const repeated=Array.from({length:9},(_,i)=>directions[i%3]);
 const times=[];for(let j=0;j<7;j++){
  const start=performance.now();for(let i=0;i<1000;i++)sampleCloudFog(f,eye,repeated);
  times.push((performance.now()-start)/1000);
 }
 reports.push({kind,layers:layers.length,triangles:layers.length*2,fogQueriesPerFrame:108,fogCpuMs:times.sort((a,b)=>a-b)});
}
const outArg=process.argv.indexOf('--out');
const output=new URL('../'+(outArg>=0?process.argv[outArg+1]:'docs/cloud-engine-b1')+'/',import.meta.url);await mkdir(output,{recursive:true});
await writeFile(new URL('layout-validation.json',output),JSON.stringify({passed:true,reports},null,2)+'\n');
console.log(JSON.stringify({passed:true,reports},null,2));
