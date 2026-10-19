import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir,writeFile} from 'node:fs/promises';
import {createCloudField} from '../src/cloud/cloud-field.js';
import {buildCloudHull,hullValue} from '../src/cloud/cloud-hull.js';
import {CLOUD_ANIMATION_PATHS,cloudAnimationPose} from './cloud-animation-paths.js';
const digest=h=>createHash('sha256').update(h.positions).update(h.normals).update(h.indices).digest('hex');
const reports=[];
for(const kind of ['cumulus','stratocumulus']){
 const field=createCloudField({kind}),begin=performance.now(),h=buildCloudHull(field),buildMs=performance.now()-begin;
 assert.equal(digest(h),digest(buildCloudHull(createCloudField({kind}))));
 assert.notEqual(digest(h),digest(buildCloudHull(createCloudField({kind,seed:74}))));
 assert.ok(h.triangles>1000&&h.triangles<120000,'bounded whole-field mesh');
 const edges=new Map();let volume=0,minArea=Infinity,maxResidual=0,minRho=1,minCentreRho=1;
 for(let i=0;i<h.positions.length;i+=3){
  const p=Array.from(h.positions.slice(i,i+3)),n=Array.from(h.normals.slice(i,i+3));
  assert.ok(p.every(Number.isFinite)&&n.every(Number.isFinite));assert.ok(Math.abs(Math.hypot(...n)-1)<1e-5);
  const {min,max}=field.bounds;assert.ok(p.every((v,a)=>v>=Object.values(min)[a]-0.001&&v<=Object.values(max)[a]+0.001));
  maxResidual=Math.max(maxResidual,Math.abs(hullValue(field,...p)));minRho=Math.min(minRho,field.sampleDensity(...p));
 }
 for(let i=0;i<h.indices.length;i+=3){
  const ids=Array.from(h.indices.slice(i,i+3)),[a,b,c]=ids.map(j=>Array.from(h.positions.slice(j*3,j*3+3)));
  const u=b.map((v,k)=>v-a[k]),v=c.map((v,k)=>v-a[k]),cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];
  minArea=Math.min(minArea,Math.hypot(...cross)/2);
  minCentreRho=Math.min(minCentreRho,field.sampleDensity(...a.map((v,k)=>(v+b[k]+c[k])/3)));
  volume+=(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6;
  for(let k=0;k<3;k++){const a=ids[k],b=ids[(k+1)%3],key=a<b?`${a}:${b}`:`${b}:${a}`,e=edges.get(key)||{count:0,balance:0};e.count++;e.balance+=a<b?1:-1;edges.set(key,e);}
 }
 const openEdges=[...edges.values()].filter(e=>e.count!==2).length,badWinding=[...edges.values()].filter(e=>e.balance!==0).length;
 assert.equal(openEdges,0,'closed two-manifold hull');assert.equal(badWinding,0,'consistent winding');assert.ok(volume>0);assert.ok(minArea>0);
 assert.ok(minRho>0,'display shell remains in B0 occupancy');
 assert.ok(minCentreRho>0,'triangle centres remain in B0 occupancy');
 reports.push({kind,passed:true,hash:digest(h),triangles:h.triangles,vertices:h.positions.length/3,bytes:h.positions.byteLength+h.normals.byteLength+h.indices.byteLength,buildMs,openEdges,badWinding,volume,minArea,minRho,minCentreRho,maxResidual});
}
for(const path of CLOUD_ANIMATION_PATHS)for(let i=0;i<=100;i++){
 const field=createCloudField({kind:path.kind}),p=cloudAnimationPose(field,path.id,i/100);assert.ok([...p.eye,...p.target].every(Number.isFinite));
}
const out=new URL('../docs/cloud-engine-b2/',import.meta.url);await mkdir(out,{recursive:true});
await writeFile(new URL('hull-validation.json',out),JSON.stringify({reports,paths:CLOUD_ANIMATION_PATHS.length},null,2)+'\n');console.log(JSON.stringify(reports,null,2));
