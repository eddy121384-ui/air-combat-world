// Lab asset only. Authored support and prelit colour; never used by game physics.
const clamp = x => Math.max(0, Math.min(1, x));
const smooth = x => { x = clamp(x); return x*x*(3-2*x); };
const mix = (a,b,t) => a+(b-a)*t;
function hash(x,y,z,seed) {
  let h = Math.imul(x,374761393)^Math.imul(y,668265263)^Math.imul(z,2147483647)^seed;
  h = Math.imul(h^(h>>>13),1274126177);
  return ((h^(h>>>16))>>>0)/4294967295;
}
function noise(x,y,z,seed) {
  const i=Math.floor(x),j=Math.floor(y),k=Math.floor(z),u=smooth(x-i),v=smooth(y-j),w=smooth(z-k);
  const row=(dy,dz)=>mix(hash(i,j+dy,k+dz,seed),hash(i+1,j+dy,k+dz,seed),u);
  return mix(mix(row(0,0),row(1,0),v),mix(row(0,1),row(1,1),v),w);
}
export const ONE_CLOUD_SUN = Object.freeze([-0.6040227736,0.3420201433,-0.7198463104]);
export const ONE_CLOUD_GRID = Object.freeze([64,64,64]);
export const ONE_CLOUD_STEPS = 24;
export const ONE_CLOUD_EXTINCTION = 0.012;

export function createOneCloud(seed=73) {
  const params=Object.freeze({kind:'cumulus',seed,base:2450,top:3850,width:2300,depth:1900,cellSize:1400,density:0.9,wind:Object.freeze({x:0,z:0})});
  const bounds=Object.freeze({min:Object.freeze({x:-1150,y:2450,z:-950}),max:Object.freeze({x:1150,y:3850,z:950})});
  // Asymmetric base, leaning crown and offset shoulder; no camera/RNG state.
  const shapes=[[-380,2670,20,550,240,490],[150,2690,-30,650,250,530],
    [-160,2950,0,600,430,550],[-240,3270,-90,420,430,400],
    [-330,3530,-100,290,245,300],[320,3120,60,390,335,390],
    [610,3000,10,230,230,270],[-650,2930,0,235,265,310],
    [-440,3360,180,255,235,270],[100,3320,-280,260,245,260],
    [330,2890,400,350,270,230],[-270,2930,-430,320,260,235]];
  const lobes=Object.freeze(shapes.map(v=>Object.freeze(Object.fromEntries(['x','y','z','rx','ry','rz'].map((k,i)=>[k,v[i]])))));
  function sampleDensity(x,y,z) {
    if(x<=bounds.min.x||x>=bounds.max.x||y<=params.base||y>=params.top||z<=bounds.min.z||z>=bounds.max.z)return 0;
    let support=-1;
    for(const l of lobes) {
      const q=Math.hypot((x-l.x)/l.rx,(y-l.y)/l.ry,(z-l.z)/l.rz);
      support=Math.max(support,1-q);
    }
    // Subtractive, fixed-world erosion changes the contour, unlike B0's
    // small density multiplier. Broad shape remains the authored union.
    const erosion=0.10*(noise(x/140,y/100,z/130,seed)-0.35)
      +0.045*(noise(x/43,y/39,z/47,seed+1)-0.4);
    return 0.9*smooth((support-erosion)/0.18)*smooth((y-params.base)/85);
  }
  function integrateSightline(a,b,{step=12,extinction=ONE_CLOUD_EXTINCTION}={}) {
    if(!(step>0)||!Number.isFinite(step)||!(extinction>=0)||!Number.isFinite(extinction))throw new RangeError('invalid integration');
    const delta=['x','y','z'].map(k=>b[k]-a[k]),distance=Math.hypot(...delta),samples=Math.max(1,Math.ceil(distance/step));
    let columnDensity=0;
    for(let i=0;i<samples;i++)columnDensity+=sampleDensity(...delta.map((d,k)=>a[['x','y','z'][k]]+d*(i+0.5)/samples));
    columnDensity*=distance/samples;
    return {distance,samples,columnDensity,opticalDepth:extinction*columnDensity,transmittance:Math.exp(-extinction*columnDensity)};
  }
  return Object.freeze({params,bounds,lobes,sampleDensity,integrateSightline});
}

export function sampleBrick(cache,x,y,z,channel=3) {
  const p=[x,y,z],lo=Object.values(cache.min),hi=Object.values(cache.max);
  if(p.some((v,a)=>v<lo[a]||v>hi[a]))return 0;
  const t=p.map((v,a)=>(v-lo[a])/(hi[a]-lo[a])*(cache.grid[a]-1)),base=t.map(Math.floor),f=t.map((v,a)=>v-base[a]);
  let value=0;
  for(let z=0;z<2;z++)for(let y=0;y<2;y++)for(let x=0;x<2;x++) {
    const q=[x,y,z].map((v,a)=>Math.min(base[a]+v,cache.grid[a]-1));
    value+=cache.data[(q[0]+cache.grid[0]*(q[1]+cache.grid[1]*q[2]))*4+channel]/255
      *(x?f[0]:1-f[0])*(y?f[1]:1-f[1])*(z?f[2]:1-f[2]);
  }
  return value;
}

export function buildOneCloudBrick(field,grid=ONE_CLOUD_GRID) {
  const start=performance.now(),[nx,ny,nz]=grid,min=field.bounds.min,max=field.bounds.max;
  const data=new Uint8Array(nx*ny*nz*4),cache={data,grid:[...grid],min,max};
  const pos=(x,y,z)=>[min.x+(max.x-min.x)*x/(nx-1),min.y+(max.y-min.y)*y/(ny-1),min.z+(max.z-min.z)*z/(nz-1)];
  for(let z=0;z<nz;z++)for(let y=0;y<ny;y++)for(let x=0;x<nx;x++)
    data[(x+nx*(y+ny*z))*4+3]=Math.round(field.sampleDensity(...pos(x,y,z))*255);
  // Fixed sun: eight coarse self-shadow probes in cached density, once per
  // voxel on apply. No nested light march, gradient or atlas reads at runtime.
  let occupied=0;
  for(let z=0;z<nz;z++)for(let y=0;y<ny;y++)for(let x=0;x<nx;x++) {
    const i=(x+nx*(y+ny*z))*4,rho=data[i+3]/255;if(!rho)continue;
    occupied++;
    const p=pos(x,y,z);let column=0;
    for(let j=0;j<8;j++)column+=sampleBrick(cache,...p.map((v,a)=>v+ONE_CLOUD_SUN[a]*(j+0.5)*90))*90;
    const marks=noise(p[0]/105,p[1]/70,p[2]/120,field.params.seed+7);
    const light=Math.exp(-column*0.008),tone=smooth((light+0.14*(marks-0.5)-0.28)/0.17);
    const half=smooth((light-0.10)/0.23),colour=[0,1,2].map(a=>mix(mix([0.28,0.35,0.55][a],[0.56,0.58,0.73][a],half),[1.0,0.87,0.67][a],tone));
    const brush=0.93+0.12*marks;
    for(let a=0;a<3;a++)data[i+a]=Math.round(clamp(colour[a]*brush)*rho*255);
  }
  return {...cache,bytes:data.byteLength,occupied,buildMs:performance.now()-start};
}

// Four routes, elapsed simulation seconds -> exact pose; orbit includes roll.
export const ONE_CLOUD_PATHS=Object.freeze([{id:'approach-skim',seconds:10},{id:'orbit',seconds:12},{id:'entry',seconds:6},{id:'exit',seconds:6}]);
export function oneCloudPose(id,t) {
  const c=[-80,3090,0];let eye,target,roll=0;
  if(id==='approach-skim') {
    eye=[900*smooth(t*2),3100,mix(2600,-2200,t)];
    target=[mix(c[0],900,smooth((t-0.5)*2)),3090,mix(0,-3200,smooth((t-0.5)*2))];
  } else if(id==='orbit') {
    const a=t*Math.PI;eye=[c[0]+Math.sin(a)*2000,3250+Math.sin(a*2)*250,Math.cos(a)*2000];target=c;roll=Math.sin(a*2)*0.35;
  } else if(id==='entry') {eye=[-80,3060,mix(1450,-50,t)];target=[-80,3060,eye[2]-900];}
  else if(id==='exit') {eye=[-80,3060,mix(-50,-1550,t)];target=[-80,3060,eye[2]-900];}
  else throw new RangeError('unknown one-cloud route');
  return {eye,target,roll};
}
