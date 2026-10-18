// B1 display layers use unchanged B0 lobe anchors. No camera or mutable RNG.
export function buildCloudLayers(field){
 return field.lobes.map((l,i)=>Object.freeze({center:Object.freeze([l.x,l.y,l.z]),
  size:Object.freeze([l.rx*2.4,l.ry*2.6,l.rz*2.4]),variant:((Math.floor(i/3)+field.params.seed)%2+2)%2,
  detail:i%3===0?0:1}));
}
export const FOG_BREAKS=Object.freeze([0,80,250,700,1800]);
// 9 frustum directions × 4 intervals × 3 midpoint probes = 108 CPU queries.
export function sampleCloudFog(field,eye,directions,time=0){
 return directions.map(d=>FOG_BREAKS.slice(1).map((end,j)=>{
  const start=FOG_BREAKS[j];let density=0;
  for(let k=0;k<3;k++){const s=start+(end-start)*(k+0.5)/3;
   density+=field.sampleDensity(eye.x+d.x*s,eye.y+d.y*s,eye.z+d.z*s,time);
  }return density/3;
 }));
}
