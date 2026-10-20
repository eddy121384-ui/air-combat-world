import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createOneCloud,buildOneCloudBrick,sampleBrick,oneCloudPose,ONE_CLOUD_PATHS} from '../src/cloud/one-cloud.js';
const field=createOneCloud(),a=buildOneCloudBrick(field),b=buildOneCloudBrick(createOneCloud());
const sha=data=>createHash('sha256').update(data).digest('hex');
assert.equal(sha(a.data),sha(b.data),'fixed seed reproduces density and light');
assert.equal(a.bytes,1048576);assert.ok(a.occupied>0&&a.occupied<64**3);
assert.equal(field.sampleDensity(2000,3000,0),0);assert.ok(field.sampleDensity(-80,3060,0)>0.5);
let maxError=0;
for(let i=0;i<2000;i++){
  const x=-1100+(i*137%2200),y=2450+(i*89%1400),z=-900+(i*97%1800);
  maxError=Math.max(maxError,Math.abs(sampleBrick(a,x,y,z)-field.sampleDensity(x,y,z)));
}
assert.ok(maxError<0.25,`64³ cache approximation error ${maxError}`);
// Independently check trilinear reconstruction of a linear scalar field.
const linear={data:new Uint8Array(2*2*2*4),grid:[2,2,2],min:{x:0,y:0,z:0},max:{x:1,y:1,z:1}};
for(let i=0;i<8;i++)linear.data[i*4+3]=(i%2)*255;
assert.ok(Math.abs(sampleBrick(linear,0.37,0.61,0.2)-0.37)<1e-9);
const entryEnd=oneCloudPose('entry',1),exitStart=oneCloudPose('exit',0);
assert.deepEqual(entryEnd,exitStart,'entry and exit form one continuous traversal');
for(const path of ONE_CLOUD_PATHS){
  const poses=Array.from({length:121},(_,i)=>oneCloudPose(path.id,i/120));
  assert.ok(poses.every(p=>[...p.eye,...p.target,p.roll].every(Number.isFinite)));
  for(let i=1;i<poses.length;i++)assert.ok(Math.hypot(...poses[i].eye.map((v,k)=>v-poses[i-1].eye[k]))<60,'no camera teleport');
}
const sky={x:-80,y:3060,z:1450},inside={x:-80,y:3060,z:-50},exit={x:-80,y:3060,z:-1550};
assert.equal(field.sampleDensity(...Object.values(sky)),0);assert.equal(field.sampleDensity(...Object.values(exit)),0);
const fine=field.integrateSightline(sky,exit,{step:2}),coarse=field.integrateSightline(sky,exit,{step:12});
assert.ok(Math.abs(fine.opticalDepth-coarse.opticalDepth)<0.03);
const first=field.integrateSightline(sky,inside,{step:2}),last=field.integrateSightline(inside,exit,{step:2});
assert.ok(Math.abs(fine.opticalDepth-first.opticalDepth-last.opticalDepth)<0.01,'path-length extinction composes');
assert.ok(fine.transmittance<0.01);
assert.throws(()=>field.integrateSightline(sky,exit,{step:0}));
console.log(JSON.stringify({passed:true,brickSha256:sha(a.data),bytes:a.bytes,maxDensityError:maxError,buildMs:a.buildMs,opticalDepth:fine.opticalDepth}));
