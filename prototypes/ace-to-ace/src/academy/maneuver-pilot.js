// KITE demonstration intent. ONLY virtual stick/power -> normal PlayerController.
// The live trainee never uses this pilot. No aircraft state or physics writes.
import { clamp, DEG, toBody, norm, sub, forwardOf } from '../sim/math.js';
import { pitchForG } from '../sim/aircraft.js';
import { bankDeg, gammaDeg, hdgDeg, wrapDeg } from './runner.js';


export function pilotInput() {
  return { x:0, y:0, thr:.72, ab:false, brk:false,
    axes(){return {x:this.x,y:this.y,yaw:0};}, throttle(){return this.thr;},
    boost(){return this.ab;}, brake(){return this.brk;}, gun(){return false;}, consume(){return false;} };
}
const direction=(h,c=0)=>({x:Math.sin(h*DEG)*Math.cos(c*DEG),y:Math.sin(c*DEG),z:-Math.cos(h*DEG)*Math.cos(c*DEG)});
export class ManeuverPilot {
  constructor(ac,foe,id,control) {
    this.ac=ac;this.foe=foe;this.id=id;this.control=control;this.stage=0;this.t=0;
    this.input=pilotInput();
  }
  aim(dir,limit=1,push=.6) {
    const ac=this.ac,s=this.input;
    const b=toBody(ac.q,dir),ahead=Math.max(-b.z,.001);
    const ax=Math.atan2(b.x,ahead),ay=Math.atan2(b.y,ahead),off=Math.hypot(ax,ay);
    if(this.control==='expert') {
      if(off<12*DEG&&b.z<0){
        const v=Math.max(ac.speed,60),lat=clamp(ax*.9,-.2,.2)*v;
        const lift=clamp(ay*1.2,-.12,.12)*v+9.81*Math.cos(Math.asin(clamp(ac.vel.y/v,-1,1)));
        const want=clamp(Math.atan2(lat,lift),-75*DEG,75*DEG),bank=bankDeg(ac)*DEG;
        s.x=clamp((want-bank)*2.5-ac.rollRateCur*.08,-1,1);
        const n=Math.hypot(lat,lift)/9.81*Math.cos(clamp(want-bank,-1.5,1.5));
        s.y=-clamp(pitchForG(ac,n),-.6,limit);
      }else{
        const roll=Math.atan2(b.x,b.y);s.x=clamp(clamp(roll/(40*DEG),-1,1)-ac.rollRateCur*.06,-1,1);
        s.y=-(Math.abs(roll)<30*DEG?limit:.1);
      }
    }else{
      s.x=clamp(ax/(14*DEG),-1,1);s.y=-clamp(ay/(5*DEG),-push,limit);
      if(b.z>0){s.x=Math.sign(b.x||1);s.y=0;}
    }
  }
  speed(v) { const s=this.input,e=(v-this.ac.speed)*3.6;s.ab=e>60;s.brk=e< -60;s.thr=clamp(.55+e/250,0,1); }
  update(dt) {
    const ac=this.ac,foe=this.foe,s=this.input;
    s.thr=.72;s.ab=false;s.brk=false;
    if(this.id==='A01') {
      const f=forwardOf(ac.q);
      if(this.stage===0){s.x=0;s.y=-pitchForG(ac,5);if(f.z>.90&&f.y<.30)this.stage=1;}
      if(this.stage===1){s.y=0;s.x=clamp(wrapDeg(-bankDeg(ac))*DEG*2.5-ac.rollRateCur*.12,-1,1);if(Math.abs(bankDeg(ac))<8)this.stage=2;}
      if(this.stage===2)this.aim(direction(180),.5);
    } else if(this.id==='T01') {
      if(this.stage===0){s.x=0;s.y=-pitchForG(ac,3.2);if(gammaDeg(ac)>28)this.stage=1;}
      else if(this.stage===1){this.aim(direction(hdgDeg(foe)-15,28),.4);if(ac.pos.y>3400||this.closure()<5)this.stage=2;}
      else {this.aim(norm(sub(foe.pos,ac.pos)),this.control==='assisted'?.7:1,1);this.speed(foe.speed+clamp((this.range()-700)/14.4,-100/3.6,100/3.6));}
    } else {
      const ahead=this.ahead();
      if(this.stage===0){
        const side=Math.floor(this.t/3)%2===0?1:-1;
        if(this.control==='assisted'){s.x=side*.8;s.y=0;}
        else {s.x=clamp(wrapDeg(side*70-bankDeg(ac))*DEG*2.5-ac.rollRateCur*.12,-1,1);s.y=-pitchForG(ac,clamp(3.5-ac.vel.y/90,1,5));}
        s.thr=.1;s.brk=this.range()<900&&ac.speed>125;
        if(ahead>Math.cos(80*DEG))this.stage=1;
      } else {this.aim(norm(sub(foe.pos,ac.pos)));this.speed(foe.speed+clamp((this.range()-600)/14.4,-100/3.6,150/3.6));}
    }
    this.t+=dt;return s;
  }
  range(){return Math.hypot(this.foe.pos.x-this.ac.pos.x,this.foe.pos.y-this.ac.pos.y,this.foe.pos.z-this.ac.pos.z);}
  ahead(){const p=norm(sub(this.foe.pos,this.ac.pos)),f=forwardOf(this.ac.q);return p.x*f.x+p.y*f.y+p.z*f.z;}
  closure(){const p=norm(sub(this.foe.pos,this.ac.pos)),v=sub(this.ac.vel,this.foe.vel);return p.x*v.x+p.y*v.y+p.z*v.z;}
}
