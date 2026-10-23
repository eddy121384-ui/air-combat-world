import assert from 'node:assert/strict';
import { createAircraft, stepAircraft, bankAngle, pitchAngle } from '../src/sim/aircraft.js';
import { PlayerController } from '../src/game/input.js';
import { LevelAssist } from '../src/game/level-assist.js';
import { placeJet } from '../src/academy/runner.js';
import { DEG } from '../src/sim/math.js';

const results=[];
for(const flight of ['arcade','tactical'])for(const assist of [false,true]) {
  for(const [bank,pitch] of [[60,0],[-60,20],[45,-20],[170,5],[-170,-5]]) {
    const ac=createAircraft('F16V','blue',{x:0,y:3500,z:0},{x:0,y:0,z:-1},250,flight);
    ac.flightFeel=flight;placeJet(ac,{bank,pitch,speed:250});
    const level=new LevelAssist(), axes={x:0,y:0,yaw:0};
    const input={levelAssist:level,axes:()=>axes,throttle:()=>.52,boost:()=>false,brake:()=>false,gun:()=>false,consume:()=>false};
    const ctl=new PlayerController(ac,input,{assist,invert:false});level.toggle();
    const initial=JSON.stringify([ac.pos,ac.q,ac.vel,ac.speed]);
    ctl.update(1/60);
    assert.equal(JSON.stringify([ac.pos,ac.q,ac.vel,ac.speed]),initial,'controller must not teleport or mutate the aircraft');
    let peakWrongBank=0,peakWrongGamma=0,time=0, completed=false;
    for(let i=0;i<1200;i++) {
      ac.controls=ctl.update(1/60);
      assert.equal(ac.controls.throttle,.52);assert.equal(ac.controls.boost,false);assert.equal(ac.controls.brake,false);
      assert.ok(Math.abs(ac.controls.roll)<=1&&Math.abs(ac.controls.pitch)<=1);
      stepAircraft(ac,1/60);time+=1/60;
      if(pitch)peakWrongGamma=Math.max(peakWrongGamma,-Math.sign(pitch)*Math.asin(ac.vel.y/ac.speed)/DEG);
      peakWrongBank=Math.max(peakWrongBank,Math.max(0,-Math.sign(bank)*bankAngle(ac)/DEG));
      if(!level.active){completed=true;break;}
    }
    const gamma=Math.asin(ac.vel.y/ac.speed)/DEG;
    assert.ok(completed&&time<20,`${flight}/${assist}/${bank}/${pitch}: recovery terminates`);
    assert.match(level.message,/完成/);
    assert.ok(Math.abs(bankAngle(ac)/DEG)<3.5&&Math.abs(gamma)<1.7,JSON.stringify({bank,pitch,gamma,b:bankAngle(ac)/DEG}));
    assert.ok(peakWrongBank<4,'no repeated roll overshoot or hunting');
    assert.ok(peakWrongGamma<2,'no pitch oscillation across the horizon');
    const pitchAtEnd=pitchAngle(ac);
    for(let i=0;i<60;i++){ac.controls=ctl.update();stepAircraft(ac,1/60);}
    assert.ok(Math.abs(pitchAngle(ac)-pitchAtEnd)<1*DEG,'no post-release runaway pitch');
    level.toggle();axes.x=.3;
    const manual=ctl.update();assert.equal(level.active,false,'manual override on this very update');
    if(!assist)assert.equal(manual.roll,.3);
    axes.x=0;level.toggle();level.toggle();assert.equal(level.active,false,'second tap cancels');
    results.push({flight,assist,bank,pitch,time:+time.toFixed(2),gamma:+gamma.toFixed(2),overshoot:+peakWrongBank.toFixed(2)});
  }
}
const ac=createAircraft('F16V','blue',{x:0,y:120,z:0},{x:0,y:0,z:-1},80);
ac.flightFeel='tactical';const level=new LevelAssist();level.toggle();
const power={throttle:.25,boost:false,brake:true,yaw:0,pitch:0,roll:0};
const cmd=level.update(ac,{x:0,y:0},power);
assert.ok(level.warning&&/不是救援/.test(level.message));
assert.equal(cmd.throttle,.25);assert.equal(cmd.boost,false);assert.equal(cmd.brake,true);
level.cancel();assert.equal(level.update(ac,{x:0,y:0},power),power);
console.table(results);console.log('LEVEL PASS: four modes, climbs/dives/inverted, no state edits or power override, damping, completion and immediate handover');
