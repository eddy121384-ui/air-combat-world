// Display cache only. B0 remains authoritative; positions/normals never use the eye.
export const VOLUME_GRID = Object.freeze([96, 32, 80]);
export const VOLUME_STEPS = Object.freeze([8, 12, 12]);
export function buildCloudVolume(field, grid = VOLUME_GRID) {
  const [nx, ny, nz] = grid, min = field.bounds.min, max = field.bounds.max;
  const spacing = [(max.x-min.x)/(nx-1), (max.y-min.y)/(ny-1), (max.z-min.z)/(nz-1)];
  const rho = new Float32Array(nx*ny*nz), data = new Uint8Array(rho.length*4);
  const index = (x,y,z) => x+nx*(y+ny*z);
  for (let z=0;z<nz;z++) for (let y=0;y<ny;y++) for (let x=0;x<nx;x++)
    rho[index(x,y,z)] = field.sampleDensity(min.x+x*spacing[0],min.y+y*spacing[1],min.z+z*spacing[2],0);
  for (let z=0;z<nz;z++) for (let y=0;y<ny;y++) for (let x=0;x<nx;x++) {
    const i=index(x,y,z), n=[
      (rho[index(Math.max(x-1,0),y,z)]-rho[index(Math.min(x+1,nx-1),y,z)])/spacing[0],
      (rho[index(x,Math.max(y-1,0),z)]-rho[index(x,Math.min(y+1,ny-1),z)])/spacing[1],
      (rho[index(x,y,Math.max(z-1,0))]-rho[index(x,y,Math.min(z+1,nz-1))])/spacing[2]];
    const length=Math.hypot(...n)||1;
    data[i*4]=Math.round(rho[i]*255);
    for(let a=0;a<3;a++)data[i*4+1+a]=Math.round((n[a]/length*0.5+0.5)*255);
  }
  return {data, grid:[...grid], min:{...min}, max:{...max}, spacing};
}
// Mirrors GPU texel-centre reconstruction for numerical validation.
export function sampleCloudVolume(cache, x, y, z, wind={x:0,z:0}, time=0) {
  const p=[x-wind.x*time,y,z-wind.z*time], lo=Object.values(cache.min), hi=Object.values(cache.max);
  if(p.some((v,a)=>v<lo[a]||v>hi[a]))return 0;
  const t=p.map((v,a)=>(v-lo[a])/(hi[a]-lo[a])*(cache.grid[a]-1));
  const base=t.map(Math.floor), f=t.map((v,a)=>v-base[a]);let rho=0;
  for(let z=0;z<2;z++)for(let y=0;y<2;y++)for(let x=0;x<2;x++){
    const q=[x,y,z].map((v,a)=>Math.min(base[a]+v,cache.grid[a]-1));
    rho+=cache.data[(q[0]+cache.grid[0]*(q[1]+cache.grid[1]*q[2]))*4]/255
      *(x?f[0]:1-f[0])*(y?f[1]:1-f[1])*(z?f[2]:1-f[2]);
  }return rho;
}
// 240 m boundary/near detail, next 1200 m middle, remainder distant volume.
// Each region shrinks continuously to zero; there is no geometry/alpha LOD swap.
export function cloudRayIntervals(start,end) {
  const breaks=[start,Math.min(end,start+240),Math.min(end,start+1440),end];
  return VOLUME_STEPS.map((count,i)=>({start:breaks[i],end:breaks[i+1],count}));
}
