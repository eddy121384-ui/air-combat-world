// Identical continuous world paths for baseline B1 and the animation experiment.
export const CLOUD_ANIMATION_PATHS=Object.freeze([
 {id:'approach',label:'接近單一前緣雲團',kind:'cumulus'},
 {id:'side-pass',label:'側面掠過',kind:'cumulus'},
 {id:'climb',label:'雲底爬升至雲頂',kind:'cumulus'},
 {id:'sea-wall',label:'雲海上方看雲牆',kind:'stratocumulus'},
 {id:'entry',label:'進入雲層',kind:'cumulus'},
 {id:'inside',label:'雲內前飛',kind:'cumulus'},
 {id:'exit',label:'穿出雲層',kind:'cumulus'},
 {id:'turn90',label:'繞同一雲團轉向 90°',kind:'cumulus'},
 {id:'turn180',label:'繞同一雲團轉向 180°',kind:'cumulus'},
]);
export function cloudAnimationPose(field,id,t){
 const p=field.params,mid=(p.base+p.top)/2,l=field.lobes.slice(24,27);
 const c=[l.reduce((s,v)=>s+v.x,0)/3,mid,l.reduce((s,v)=>s+v.z,0)/3];
 const mix=(a,b)=>a+(b-a)*t;let eye,target;
 if(id==='approach'){eye=[c[0],mid+100,c[2]+mix(2500,420)];target=c;}
 else if(id==='side-pass'){eye=[c[0]+820,mid+30,c[2]+mix(1700,-1700)];target=[c[0]-100,mid,c[2]+mix(700,-2700)];}
 else if(id==='climb'){eye=[c[0]+300,mix(p.base-500,p.top+650),c[2]+250];target=[eye[0]-100,eye[1]+180,eye[2]-800];}
 else if(id==='sea-wall'){eye=[mix(2300,-900),p.top+850,mix(3400,600)];target=[0,mid,-1500];}
 else if(id==='entry'){eye=[c[0],mid+12,c[2]+mix(1250,150)];target=[c[0],mid,c[2]-800];}
 else if(id==='inside'){eye=[0,mid+12,mix(1100,-1000)];target=[0,mid,eye[2]-800];}
 else if(id==='exit'){eye=[0,mid+12,mix(-1700,-3450)];target=[0,mid,eye[2]-800];}
 else if(id==='turn90'||id==='turn180'){
  const a=t*Math.PI*(id==='turn90'?0.5:1),r=1450;
  eye=[c[0]+Math.sin(a)*r,mid+100,c[2]+Math.cos(a)*r];target=c;
 }else throw new RangeError('unknown cloud animation path');
 return {eye,target};
}
