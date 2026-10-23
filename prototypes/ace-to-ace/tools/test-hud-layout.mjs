import assert from 'node:assert/strict';
import {emptyLayout,validLayout,loadLayout,saveLayout,layoutRect,relativeEntry,safeBounds,HUD_KEY} from '../src/game/hud-layout.js';
for(const value of [null,[],{version:99,items:{}},{version:1,items:{gun:{x:NaN,y:0,scale:1,opacity:1}}}])assert.deepEqual(validLayout(value),emptyLayout());
const clean=validLayout({version:1,items:{gun:{x:-3,y:9,scale:99,opacity:-1},hack:{x:1,y:1,scale:1,opacity:1}}});
assert.deepEqual(clean,{version:1,items:{gun:{x:0,y:1,scale:1.6,opacity:.2}}});
const mem=new Map(),store={getItem:k=>mem.get(k),setItem:(k,v)=>mem.set(k,v)};
assert.equal(saveLayout(clean,store),true);assert.deepEqual(loadLayout(store),clean);
mem.set(HUD_KEY,'{broken');assert.deepEqual(loadLayout(store),emptyLayout());
const denied={getItem(){throw Error('blocked');},setItem(){throw Error('blocked');}};
assert.deepEqual(loadLayout(denied),emptyLayout());assert.equal(saveLayout(clean,denied),false);
{
  const prior=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
  Object.defineProperty(globalThis,'localStorage',{configurable:true,get(){throw Error('private storage');}});
  assert.deepEqual(loadLayout(),emptyLayout());assert.equal(saveLayout(clean),false);
  if(prior)Object.defineProperty(globalThis,'localStorage',prior);else delete globalThis.localStorage;
}
for(const width of [667,812,1280])for(const height of [375,720])for(const side of [0,34]) {
  const safe=safeBounds(width,height,{left:side,right:side,top:8,bottom:21});
  for(const key of ['gun','pause','stick','power'])for(const scale of [.65,1,1.6])for(const x of [0,.5,1])for(const y of [0,.5,1]) {
    const base=key==='stick'?{width:width*.48,height}:key==='power'?{width:62,height:225}:key==='pause'?{width:40,height:34}:{width:84,height:84};
    const r=layoutRect({x,y,scale,opacity:.2},base,safe,key);
    assert.ok(r.x>=safe.x&&r.y>=safe.y&&r.x+r.width<=safe.x+safe.width+.000001&&r.y+r.height<=safe.y+safe.height+.000001);
    if(key==='pause')assert.ok(r.width>=40&&r.height>=40,'custom menu remains usable even at 65%');
    const again=layoutRect(relativeEntry(r,safe,scale),base,safe,key);
    for(const k of ['x','y','width','height'])assert.ok(Math.abs(r[k]-again[k])<1e-8,'normalized safe-space round trip');
  }
}
console.log('HUD layout PASS: version/data validation, storage failure, safe-area bounds, resize/relative-coordinate round trips, protected menu');
