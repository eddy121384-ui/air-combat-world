// Temporary pilot assistance; never writes aircraft state, power or sim rules.
import { clamp, DEG, G } from '../sim/math.js';
import { bankAngle, pitchAngle, pitchForG, neutralG, availableG } from '../sim/aircraft.js';

export class LevelAssist {
  constructor() { this.active=false; this.version=0; this.message=''; this.warning=false; }
  toggle() {
    if(this.active) { this.cancel('LVL 已取消'); return; }
    this.active=true; this.elapsed=0; this.settled=0; this.warned=false;
    this.notify('LVL 改平中；推桿即交還操控');
  }
  notify(message, warning=false) { this.message=message;this.warning=warning;this.version++; }
  cancel(message='') {
    if(!this.active)return;
    this.active=false;this.settled=0;this.notify(message);
  }
  update(ac, axes, commands, dt=1/60) {
    if(!this.active)return commands;
    if(Math.hypot(axes.x,axes.y)>.12) {
      this.cancel('LVL 已交還操控');return commands;
    }
    this.elapsed+=dt;
    if(!ac.alive || this.elapsed>20) {
      this.cancel(ac.alive?'LVL 未完成：檢查速度與高度':'');return commands;
    }
    if(!this.warned && (ac.speed<110 || ac.pos.y<500 || availableG(ac)<1.3)) {
      this.warned=true;this.notify('LVL 不是救援；留意速度與離地高度',true);
    }
    const bank=bankAngle(ac), pitch=pitchAngle(ac);
    const gamma=Math.asin(clamp(ac.vel.y/Math.max(1,ac.speed),-1,1));
    const error=Math.atan2(Math.sin(-bank),Math.cos(-bank));
    const roll=clamp(error*2.2-ac.rollRateCur*.22,-1,1);
    // Nose/path lag feedback damps the approach instead of freezing pitch.
    const rate=clamp(-.65*pitch-.8*(pitch-gamma),-.25,.25);
    const upright=Math.cos(bank);
    const n=Math.abs(bank)>65*DEG ? neutralG(ac)
      : clamp((Math.cos(pitch)+rate*ac.speed/G)/Math.max(.4,upright),-.5,Math.min(3,availableG(ac)));
    const level=Math.abs(bank)<3*DEG && Math.abs(gamma)<1.5*DEG
      && Math.abs(pitch)<2*DEG && Math.abs(ac.rollRateCur)<.08;
    this.settled=level?this.settled+dt:0;
    if(this.settled>=.45) {this.cancel('LVL 平飛完成');return commands;}
    return {...commands,roll,pitch:pitchForG(ac,n)};
  }
}
