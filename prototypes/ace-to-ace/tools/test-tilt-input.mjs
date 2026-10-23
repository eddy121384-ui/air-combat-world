import assert from 'node:assert/strict';
import {TiltInput,tiltSettings,screenAngles} from '../src/game/tilt-input.js';
import {PlayerController} from '../src/game/input.js';
import {createAircraft} from '../src/sim/aircraft.js';
import {controlText} from '../src/academy/control-text.js';
import {DEG} from '../src/sim/math.js';
function fixture() {
  let t=0;const listeners=new Map(), orientation=new EventTarget();orientation.angle=90;
  const host={isSecureContext:true,document:{hidden:false},screen:{orientation},DeviceOrientationEvent:{},
    addEventListener:(k,f)=>{if(!listeners.has(k))listeners.set(k,new Set());listeners.get(k).add(f);},
    removeEventListener:(k,f)=>listeners.get(k)?.delete(f)};
  const tilt=new TiltInput({host,now:()=>t});
  return {host,tilt,orientation,listeners,advance:(n=16)=>{t+=n;tilt.tick();},sample:(beta,gamma)=>{
    for(const f of listeners.get('deviceorientation')||[])f({beta,gamma});
  }};
}
assert.deepEqual(tiltSettings({sensitivity:Infinity,deadzone:99,smoothing:-5,invertX:'true'}),
  {sensitivity:1,deadzone:6,smoothing:0,invertX:false,invertY:false});
for(const angle of [0,90,180,270]) {
  const a=screenAngles(0,0,angle);assert.ok(Math.abs(a.roll)<1e-10&&Math.abs(a.pitch)<1e-10);
}
for(const angle of [90,270]) {
  const f=fixture(),{tilt,host}=f;host.screen.orientation.angle=angle;
  await tilt.enable();assert.equal(tilt.state,'waiting');assert.equal(tilt.axes(),null);
  f.sample(0,angle===90?-40:40);f.advance();assert.deepEqual(tilt.axes(),{x:0,y:0},'comfortable tilted grip is neutral');
  const sign=angle===90?1:-1;
  f.sample(12*sign,-40*sign);for(let i=0;i<15;i++)f.advance();assert.ok(tilt.axes().x>.35&&Math.abs(tilt.axes().y)<1e-8,'landscape right roll, no pitch coupling');
  f.sample(0,-52*sign);for(let i=0;i<15;i++)f.advance();assert.ok(tilt.axes().y>.35&&Math.abs(tilt.axes().x)<1e-8,'landscape pitch sign');
  f.sample(.5,-40*sign);f.advance();assert.deepEqual(tilt.axes(),{x:0,y:0},'deadzone rejects sensor noise immediately');
  tilt.configure({sensitivity:2,deadzone:1,smoothing:0,invertX:true,invertY:true});
  f.sample(30*sign,-70*sign);f.advance();assert.deepEqual(tilt.axes(),{x:-1,y:-1},'inversions and saturation');
  tilt.calibrate();assert.deepEqual(tilt.axes(),{x:0,y:0});f.sample(30*sign,-70*sign);f.advance();assert.deepEqual(tilt.axes(),{x:0,y:0});
  host.screen.orientation.angle=angle===90?270:90;f.orientation.dispatchEvent(new Event('change'));
  assert.equal(tilt.axes(),null,'rotation drops stale coordinate reference');f.sample(-10,20);f.advance();assert.deepEqual(tilt.axes(),{x:0,y:0});
  f.advance(1501);assert.equal(tilt.state,'stale');assert.equal(tilt.axes(),null);assert.equal(f.listeners.get('deviceorientation').size,0,'watchdog removes high-rate listener');
}
{
  const f=fixture();f.tilt.configure({smoothing:50});await f.tilt.enable();f.sample(0,-40);f.sample(12,-40);f.advance(16);
  assert.ok(f.tilt.axes().x>0&&f.tilt.axes().x<.5,'smoothing prevents a step');
  for(let i=0;i<9;i++)f.advance(16);assert.ok(f.tilt.axes().x>f.tilt.target.x*.95,'50ms option reaches >95% in 160ms');
  f.sample(20,-40);f.advance(16);assert.equal(f.tilt.axes().x,1,'full throw never waits for the smoothing filter');
  f.sample(null,null);assert.equal(f.tilt.axes(),null,'invalid data neutralizes immediately');
}
for(const failure of ['insecure','unavailable','denied','reject','pending']) {
  const f=fixture();let calls=0,resolve;
  if(failure==='insecure')f.host.isSecureContext=false;
  else if(failure==='unavailable')delete f.host.DeviceOrientationEvent;
  else f.host.DeviceOrientationEvent.requestPermission=()=>{calls++;return failure==='pending'?new Promise(r=>resolve=r):failure==='reject'?Promise.reject(Error('denied')):Promise.resolve('denied');};
  const promise=f.tilt.enable();if(failure==='pending'){assert.equal(calls,1,'request called synchronously within user gesture');f.tilt.stop();resolve('granted');}
  assert.equal(await promise,false);assert.equal(f.tilt.axes(),null);assert.equal(f.tilt.active,false);
}
{
  const f=fixture();await f.tilt.enable();f.advance(2401);assert.equal(f.tilt.state,'stale','no initial sample safely falls back');
}
// Same shaped axes produce identical flight commands in all four combinations.
for(const flight of ['arcade','tactical'])for(const assist of [false,true]) {
  const f=fixture();f.tilt.configure({smoothing:0});await f.tilt.enable();f.sample(0,-40);f.sample(10,-50);f.advance();
  const axes=f.tilt.axes();const ac=createAircraft('F16V','blue',{x:0,y:3000,z:0},{x:0,y:0,z:-1},250,flight);ac.flightFeel=flight;
  const base={throttle:()=>.42,boost:()=>true,brake:()=>false,gun:()=>false,consume:()=>false};
  const stick=new PlayerController(ac,{...base,axes:()=>({...axes,yaw:.5})},{assist,invert:false});
  const sensor=new PlayerController(ac,{...base,axes:()=>({...f.tilt.axes(),yaw:.5})},{assist,invert:false});
  assert.deepEqual(sensor.update(),stick.update(),'input devices share exactly the same controller');
  f.tilt.stop();assert.equal(f.tilt.axes(),null);assert.equal(f.listeners.get('deviceorientation').size,0);
}
assert.match(controlText('放手，搖桿回中；放手不會改平','tilt'),/回到校準握姿，體感回中/);
assert.equal(controlText('放手，搖桿回中','stick'),'放手，搖桿回中');
console.log('TILT PASS: secure gesture permission, both landscapes, grip calibration, inversion/deadzone/saturation, bounded smoothing, dropout/lifecycle and four-mode command equality');
