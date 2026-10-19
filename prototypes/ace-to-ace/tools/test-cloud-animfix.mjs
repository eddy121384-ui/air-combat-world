import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir,writeFile} from 'node:fs/promises';
import {performance} from 'node:perf_hooks';
import {createCloudField} from '../src/cloud/cloud-field.js';
import {buildCloudVolume,sampleCloudVolume,cloudRayIntervals} from '../src/cloud/cloud-volume.js';
import {CLOUD_ANIMATION_PATHS,cloudAnimationPose} from './cloud-animation-paths.js';
const reports=[];
for(const kind of ['cumulus','stratocumulus']){
 const f=createCloudField({kind}),start=performance.now(),v=buildCloudVolume(f),buildMs=performance.now()-start;
 const hash=data=>createHash('sha256').update(data).digest('hex'),same=buildCloudVolume(createCloudField({kind}));
 assert.equal(hash(v.data),hash(same.data));
 assert.notEqual(hash(v.data),hash(buildCloudVolume(createCloudField({kind,seed:74})).data));
 const errors=[];let advectionError=0;
 for(let i=0;i<5000;i++){
  const x=Math.sin(i*2.17)*3200,y=2300+(i*17%1600),z=Math.cos(i*1.97)*2800;
  const a=sampleCloudVolume(v,x,y,z);errors.push(Math.abs(a-f.sampleDensity(x,y,z)));
  advectionError=Math.max(advectionError,Math.abs(a-sampleCloudVolume(v,x+f.params.wind.x*73,y,z+f.params.wind.z*73,f.params.wind,73)));
 }
 errors.sort((a,b)=>a-b);assert.ok(errors.at(-1)<0.08,'cache density error < 0.08');assert.ok(advectionError<1e-9);
 for(const path of CLOUD_ANIMATION_PATHS.filter(p=>p.kind===kind))for(let i=0;i<=180;i++){
  const pose=cloudAnimationPose(f,path.id,i/180);assert.ok([...pose.eye,...pose.target].every(Number.isFinite));
 }
 reports.push({kind,buildMs,bytes:v.data.byteLength,grid:v.grid,sha256:hash(v.data),maxDensityError:errors.at(-1),p95DensityError:errors[4750],advectionError});
}
for(const end of [1,100,240,241,1000,1440,1441,8000]){
 const bands=cloudRayIntervals(0,end);assert.equal(bands.reduce((s,b)=>s+b.count,0),32);
 assert.equal(bands[0].start,0);assert.equal(bands.at(-1).end,end);
 assert.ok(bands.every((b,i)=>b.end>=b.start&&(i===0||b.start===bands[i-1].end)));
}
const out=new URL('../docs/cloud-engine-b1-animfix/',import.meta.url);await mkdir(out,{recursive:true});
await writeFile(new URL('volume-validation.json',out),JSON.stringify({passed:true,reports},null,2)+'\n');
console.log(JSON.stringify({passed:true,reports},null,2));
