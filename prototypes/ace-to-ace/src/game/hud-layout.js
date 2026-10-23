// Versioned, device-independent layout data. Coordinates are centres in the safe rect.
import {clamp} from '../sim/math.js';
export const HUD_KEY='ace2ace.hud.v1';
export const HUD_ITEMS=[
  ['stick','#stickZone','搖桿區'],['power','#powerControl','油門條（含未獨立配置的 AB／BRK）'],
  ['gun','[data-btn="gun"]','GUN'],['msl','[data-btn="msl"]','MSL'],
  ['flare','[data-btn="flare"]','FLR'],['look','[data-btn="look"]','LOOK'],
  ['yawLeft','[data-btn="yawLeft"]','◀ YAW'],['yawRight','[data-btn="yawRight"]','YAW ▶'],
  ['level','[data-btn="level"]','LVL'],['boost','[data-btn="boost"]','AB'],['brake','[data-btn="brake"]','BRK'],
  ['pause','#pauseBtn','暫停'],['calibrate','#tiltCalibrate','CAL（體感）']
];
export const emptyLayout=()=>({version:1,items:{}});
export function validLayout(value) {
  const clean=emptyLayout();
  if(value?.version!==1||!value.items||typeof value.items!=='object')return clean;
  for(const [key] of HUD_ITEMS) {
    const v=value.items[key];if(!v||!['x','y','scale','opacity'].every(k=>Number.isFinite(v[k])))continue;
    clean.items[key]={x:clamp(v.x,0,1),y:clamp(v.y,0,1),scale:clamp(v.scale,.65,1.6),opacity:clamp(v.opacity,.2,1)};
  }
  return clean;
}
export function loadLayout(store) {
  try{store??=globalThis.localStorage;return validLayout(JSON.parse(store.getItem(HUD_KEY)));}catch{return emptyLayout();}
}
export function saveLayout(layout,store) {
  try{store??=globalThis.localStorage;store.setItem(HUD_KEY,JSON.stringify(validLayout(layout)));return true;}catch{return false;}
}
export function safeBounds(width,height,insets={}) {
  const left=clamp(insets.left||0,0,width/3),right=clamp(insets.right||0,0,width/3);
  const top=clamp(insets.top||0,0,height/3),bottom=clamp(insets.bottom||0,0,height/3);
  return {x:left,y:top,width:Math.max(1,width-left-right),height:Math.max(1,height-top-bottom)};
}
export function layoutRect(entry,base,safe,key) {
  const min=key==='pause'?40:0;
  const width=Math.min(safe.width,Math.max(min,base.width*entry.scale));
  const height=Math.min(safe.height,Math.max(min,base.height*entry.scale));
  return {x:clamp(safe.x+entry.x*safe.width-width/2,safe.x,safe.x+safe.width-width),
    y:clamp(safe.y+entry.y*safe.height-height/2,safe.y,safe.y+safe.height-height),width,height};
}
export function relativeEntry(rect,safe,scale=1,opacity=1) {
  return {x:clamp((rect.x+rect.width/2-safe.x)/safe.width,0,1),y:clamp((rect.y+rect.height/2-safe.y)/safe.height,0,1),scale,opacity};
}
