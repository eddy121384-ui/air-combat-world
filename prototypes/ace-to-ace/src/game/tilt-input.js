// Device input only: screen-relative gravity -> the existing stick axes.
// No aircraft/physics dependencies. Permission is session-local, never persisted.
import { clamp, DEG } from '../sim/math.js';
export const TILT_DEFAULTS = Object.freeze({ sensitivity:1, deadzone:2, smoothing:0, invertX:false, invertY:false });
export function tiltSettings(value={}) {
  const number=(k,lo,hi)=>Number.isFinite(value?.[k])?clamp(value[k],lo,hi):TILT_DEFAULTS[k];
  return {sensitivity:number('sensitivity',.5,2),deadzone:number('deadzone',0,6),
    smoothing:number('smoothing',0,60),invertX:value?.invertX===true,invertY:value?.invertY===true};
}
const wrap=a=>Math.atan2(Math.sin(a),Math.cos(a));
export function screenAngles(beta,gamma,angle) {
  // W3C intrinsic Z-X'-Y'': -R^T * world-up. Alpha cancels, avoiding compass drift.
  const b=beta*DEG,g=gamma*DEG,t=angle*DEG;
  const x=Math.sin(g)*Math.cos(b),y=-Math.sin(b),z=-Math.cos(g)*Math.cos(b);
  const sx=Math.cos(t)*x-Math.sin(t)*y,sy=Math.sin(t)*x+Math.cos(t)*y;
  return {roll:Math.asin(clamp(sx,-1,1)),pitch:Math.atan2(-sy,-z)};
}
export class TiltInput {
  constructor({host=globalThis.window,now=()=>performance.now(),onChange=()=>{}}={}) {
    this.host=host;this.now=now;this.onChange=onChange;this.options=tiltSettings();
    this.state='idle';this.allowed=false;this.active=false;this.epoch=0;this.zero();
    this.listener=e=>this.receive(e);
    this.rotation=()=>{this.latest=null;this.calibrate();};
  }
  zero() {this.value={x:0,y:0};this.target={x:0,y:0};this.reference=null;}
  setState(state) {this.state=state;this.onChange(state);}
  configure(options) {this.options=tiltSettings(options);this.value={x:0,y:0};this.target={x:0,y:0};}
  async enable() {
    this.stop();const token=++this.epoch;
    if(!this.host.isSecureContext){this.setState('insecure');return false;}
    const api=this.host.DeviceOrientationEvent;
    if(!api){this.setState('unavailable');return false;}
    this.setState('requesting');
    try {
      // Called in the button's click stack, BEFORE awaiting anything (Safari).
      const result=typeof api.requestPermission==='function'?await api.requestPermission():'granted';
      if(token!==this.epoch)return false; // menu/blur cancelled a pending prompt
      if(result!=='granted'){this.allowed=false;this.setState('denied');return false;}
      this.allowed=true;return this.start();
    } catch {
      if(token===this.epoch){this.allowed=false;this.setState('denied');}
      return false;
    }
  }
  start() {
    if(!this.allowed || this.host.document?.hidden)return false;
    this.stop();this.active=true;this.latest=null;this.lastAt=this.lastTick=this.now();
    this.host.addEventListener('deviceorientation',this.listener);
    this.host.addEventListener('orientationchange',this.rotation);
    this.host.screen?.orientation?.addEventListener?.('change',this.rotation);
    this.setState('waiting');return true;
  }
  stop(state='idle') {
    this.epoch++;this.active=false;
    this.host.removeEventListener('deviceorientation',this.listener);
    this.host.removeEventListener('orientationchange',this.rotation);
    this.host.screen?.orientation?.removeEventListener?.('change',this.rotation);
    this.latest=null;this.zero();this.setState(state);
  }
  fail(state) {this.allowed=false;this.stop(state);}
  angle() {return this.host.screen?.orientation?.angle ?? this.host.orientation ?? 0;}
  calibrate() {
    this.zero();this.lastAt=this.lastTick=this.now();
    if(this.latest && this.now()-this.latest.at<400) {
      this.reference={...this.latest.angles};this.setState('ready');
    } else {this.latest=null;this.setState('waiting');}
  }
  receive(e) {
    if(!this.active)return;
    if(!Number.isFinite(e.beta)||!Number.isFinite(e.gamma)||Math.abs(e.beta)>180||Math.abs(e.gamma)>90) {
      if(this.state==='ready')this.fail('unavailable');return;
    }
    const now=this.now(), angles=screenAngles(e.beta,e.gamma,this.angle());
    this.latest={angles,at:now};this.lastAt=now;
    if(!this.reference){this.reference={...angles};this.setState('ready');}
    const o=this.options, shape=delta=>{
      const a=clamp((Math.abs(delta)/DEG-o.deadzone)/(20/o.sensitivity-o.deadzone),0,1);
      return Math.sign(delta)*(.35*a+.65*a*a);
    };
    this.target={x:shape(wrap(angles.roll-this.reference.roll))*(o.invertX?-1:1),
      y:shape(wrap(angles.pitch-this.reference.pitch))*(o.invertY?-1:1)};
  }
  tick() {
    if(!this.active)return;
    const now=this.now(),dt=clamp((now-this.lastTick)/1000,0,.1);this.lastTick=now;
    // No endless nonzero command if a stream stops. Explicit enable retries it.
    if(now-this.lastAt>(this.state==='waiting'?2400:1500)){this.fail('stale');return;}
    const a=this.options.smoothing?1-Math.exp(-dt/(this.options.smoothing/1000)):1;
    // Deadzone neutral and deliberate full authority bypass smoothing: small
    // corrections stay quiet, emergency full throw has no filter-induced delay.
    for(const key of ['x','y']) {
      const target=this.target[key];
      this.value[key]=target===0?0:Math.abs(target)>=.98?target:this.value[key]+(target-this.value[key])*a;
    }
  }
  axes() {return this.active&&this.state==='ready'?{...this.value}:null;}
}
