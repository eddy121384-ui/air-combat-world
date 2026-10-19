// B2 display geometry only. B0 density/physics are never modified.
// A closed, connected iso-hull, with fixed oblique contour cuts instead of spheres.
export const HULL_GRID = Object.freeze([60, 26, 50]);
export function hullValue(field,x,y,z){
 const density=field.sampleDensity(x,y,z,0);if(density===0)return -0.2;
 const height=field.params.top-field.params.base;
 // Three unequal, oblique tower roofs, plus a comparatively level base.
 // These are carved out of B0 occupancy: no extra spheres, no noise displacement.
 let roof=-Infinity;
 field.lobes.forEach((l,i)=>{
  const u=(x-l.x)/l.rx,v=(z-l.z)/l.rz;
  if(Math.abs(u)>2||Math.abs(v)>2)return;
  const cap=field.params.base+height*([0.96,0.72,0.84][i%3]-0.39*(Math.abs(u+0.18*v)**1.6+Math.abs(v)**1.6));
  roof=Math.max(roof,cap);
 });
 const seed=field.params.seed*0.173;
 // Broad shoulders and smaller cutbacks have different directions/scales.
 // They subtract from the envelope, never invent occupancy outside B0 cloud.
 const shoulder=Math.sin((x+0.47*z)/210+Math.sin(y/310)+seed);
 const cut=Math.sin((z-0.31*x)/170+Math.sin(y/250+seed));
 const shelf=Math.sin(y/150+Math.sin(x/360+z/480));
 const floor=field.params.base+height*0.17+18*Math.sin((x+0.4*z)/360+seed);
 return Math.max(-0.2,Math.min(density-Math.max(0.055,0.19+0.10*shoulder+0.045*cut+0.055*shelf),(roof-y)/150,(y-floor)/100));
}
export function buildCloudHull(field,grid=HULL_GRID){
 const [nx,ny,nz]=grid,min=field.bounds.min,max=field.bounds.max;
 const step=[(max.x-min.x)/(nx-1),(max.y-min.y)/(ny-1),(max.z-min.z)/(nz-1)];
 const idx=(x,y,z)=>x+nx*(y+ny*z),count=nx*ny*nz;
 const values=new Float32Array(count),points=new Float32Array(count*3),grad=new Float32Array(count*3);
 for(let z=0;z<nz;z++)for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){
  const i=idx(x,y,z),p=[min.x+x*step[0],min.y+y*step[1],min.z+z*step[2]];
  points.set(p,i*3);const v=hullValue(field,...p);
  // Avoid sub-millimetre triangles near an exact grid corner. Keep its sign,
  // so neighbouring tetrahedra share topology; never delete isolated faces.
  values[i]=Math.abs(v)<0.0005?(v>0?0.0005:-0.0005):v;
 }
 for(let z=0;z<nz;z++)for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){
  const i=idx(x,y,z);grad.set([
   (values[idx(Math.max(0,x-1),y,z)]-values[idx(Math.min(nx-1,x+1),y,z)])/step[0],
   (values[idx(x,Math.max(0,y-1),z)]-values[idx(x,Math.min(ny-1,y+1),z)])/step[1],
   (values[idx(x,y,Math.max(0,z-1))]-values[idx(x,y,Math.min(nz-1,z+1))])/step[2]],i*3);
 }
 const positions=[],normals=[],indices=[],edges=new Map();
 function vertex(a,b){
  const key=a<b?a*count+b:b*count+a;if(edges.has(key))return edges.get(key);
  const t=values[a]/(values[a]-values[b]),i=positions.length/3,n=[];
  for(let k=0;k<3;k++){positions.push(points[a*3+k]+t*(points[b*3+k]-points[a*3+k]));n.push(grad[a*3+k]+t*(grad[b*3+k]-grad[a*3+k]));}
  const length=Math.hypot(...n)||1;normals.push(...n.map(v=>v/length));edges.set(key,i);return i;
 }
 function triangle(a,b,c,outward){
  const u=[0,1,2].map(k=>positions[b*3+k]-positions[a*3+k]),v=[0,1,2].map(k=>positions[c*3+k]-positions[a*3+k]);
  const cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];
  const dot=cross.reduce((s,n,k)=>s+n*outward[k],0);
  indices.push(a,...(dot>=0?[b,c]:[c,b]));
 }
 const tetra=[[0,1,3,7],[0,3,2,7],[0,2,6,7],[0,6,4,7],[0,4,5,7],[0,5,1,7]];
 for(let z=0;z<nz-1;z++)for(let y=0;y<ny-1;y++)for(let x=0;x<nx-1;x++){
  const cube=[idx(x,y,z),idx(x+1,y,z),idx(x,y+1,z),idx(x+1,y+1,z),idx(x,y,z+1),idx(x+1,y,z+1),idx(x,y+1,z+1),idx(x+1,y+1,z+1)];
  for(const tet of tetra){
   const inside=tet.map(i=>cube[i]).filter(i=>values[i]>0),outside=tet.map(i=>cube[i]).filter(i=>values[i]<=0);
   if(!inside.length||!outside.length)continue;
   const outward=[0,1,2].map(k=>outside.reduce((s,i)=>s+points[i*3+k],0)/outside.length-inside.reduce((s,i)=>s+points[i*3+k],0)/inside.length);
   if(inside.length===1)triangle(...outside.map(b=>vertex(inside[0],b)),outward);
   else if(outside.length===1)triangle(...inside.map(a=>vertex(a,outside[0])),outward);
   else{const [a,b]=inside,[c,d]=outside,ac=vertex(a,c),ad=vertex(a,d),bc=vertex(b,c),bd=vertex(b,d);triangle(ac,ad,bc,outward);triangle(ad,bd,bc,outward);}
  }
 }
 return {positions:new Float32Array(positions),normals:new Float32Array(normals),indices:new Uint32Array(indices),grid:[...grid],triangles:indices.length/3};
}
