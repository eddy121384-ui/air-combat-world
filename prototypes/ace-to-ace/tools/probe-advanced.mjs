// Feasibility only: real PlayerController + existing physical drones, no pose writes after setup.
import {Match} from '../src/sim/world.js';
import {PlayerController} from '../src/game/input.js';
import {placeJet,hdgDeg,gammaDeg,bankDeg,wrapDeg} from '../src/academy/runner.js';
import {pitchForG,specificEnergy} from '../src/sim/aircraft.js';
import {TurnDrone} from '../src/academy/drones.js';
import {PilotAI} from '../src/ai/pilot.js';
import {makeStudentInput,stickToward,dirFor,speedControl} from './academy-student.mjs';
import {clamp,forwardOf,sub,norm,len,dot,angleBetween,DEG,toBody} from '../src/sim/math.js';
function geo(a,b){const p=sub(b.pos,a.pos),R=len(p),los=norm(p);return{R,ata:angleBetween(forwardOf(a.q),los)/DEG,aot:angleBetween(forwardOf(b.q),los)/DEG,closure:-dot(sub(b.vel,a.vel),los),along:dot(p,forwardOf(a.q))};}
for(const id of ['A01','T01','T02'])for(const flight of ['arcade','tactical'])for(const control of ['expert','assisted']){
 const m=new Match({seed:52031,flightFeel:flight,blue:{type:'F16V'},red:{type:'J16'}}),a=m.blue,b=m.red,s=makeStudentInput();
 placeJet(a,{pos:{x:0,y:3000,z:0},speed:id==='A01'?280:id==='T01'?270:190,heading:0});
 placeJet(b,{pos:{x:0,y:3000,z:id==='T02'?650:-1000},speed:id==='T02'?250:180,heading:0});
 if(id==='A01')b.dormant=true;
 if(id==='T01')m.setController(b,new TurnDrone(b,{speed:180,rate:7,reverseEvery:0}));
 if(id==='T02'){b.missiles=0;const ai=new PilotAI(b,{skill:'rookie',seed:91});m.setController(b,{update(dt,match){const c=ai.update(dt,match);c.fireGun=false;c.fireMissile=false;return c;}});}
 const pc=new PlayerController(a,s,{assist:control==='assisted'});m.setController(a,pc);
 let stage=0,maxAlt=3000,minV=a.speed,maxG=1,vertical=false,inverted=false,rev=0,oldSign=0,held=0,overshot=false;const path=[];
 for(let t=0;t<65;t+=1/60){
 const g=geo(a,b),f=forwardOf(a.q);s.ab=false;s.brk=false;s.thr=.72;
 if(id==='A01'){
  if(stage===0){s.stick.x=0;s.stick.y=-pitchForG(a,5);if(f.z>.90&&f.y<.30){stage=1;}}
  if(stage===1){s.stick.y=0;s.stick.x=clamp(wrapDeg(-bankDeg(a))*DEG*2.5-a.rollRateCur*.12,-1,1);if(Math.abs(bankDeg(a))<8){stage=2;}}
  if(stage===2)Object.assign(s.stick,stickToward(a,dirFor(180,0),control,{pullLimit:.5}));
  vertical ||= f.y>.95;inverted ||= f.z>.7&&Math.abs(bankDeg(a))>150;
  if(stage===2&&Math.abs(gammaDeg(a))<5&&Math.abs(bankDeg(a))<10){held+=1/60;if(held>.6)break;}
 }else if(id==='T01'){
  if(stage===0){s.stick.x=0;s.stick.y=-pitchForG(a,3.2);if(gammaDeg(a)>28)stage=1;}
  else if(stage===1){Object.assign(s.stick,stickToward(a,dirFor(hdgDeg(b)-15,28),control,{pullLimit:.4}));if(a.pos.y>3400||g.closure<5)stage=2;}
  else {Object.assign(s.stick,stickToward(a,norm(sub(b.pos,a.pos)),control));if(control==='assisted'){const aim=toBody(a.q,norm(sub(b.pos,a.pos)));s.stick.y=-clamp(Math.atan2(aim.y,Math.max(-aim.z,.001))/(5*DEG),-1,.7);}speedControl(s,a,b.speed*3.6+clamp((g.R-700)/4,-100,100));}
  if(stage===2&&g.R>300&&g.R<1600&&g.aot<45&&g.ata<18&&Math.abs(g.closure)<35){held+=1/60;if(held>.8)break;}
 }else{
  if(stage===0){let side=Math.floor(t/3)%2===0?1:-1;const bank=bankDeg(a);if(control==='assisted'){s.stick.x=side*.8;s.stick.y=0;}else{const want=side*70;s.stick.x=clamp(wrapDeg(want-bank)*DEG*2.5-a.rollRateCur*.12,-1,1);s.stick.y=-pitchForG(a,clamp(3.5-a.vel.y/90,1,5));}s.thr=.1;s.brk=g.R<900&&a.speed>125;
  if(g.ata<80){stage=1;overshot=true;}}
  else{Object.assign(s.stick,stickToward(a,norm(sub(b.pos,a.pos)),control));speedControl(s,a,b.speed*3.6+clamp((g.R-600)/4,-100,150));}
  const sg=Math.abs(bankDeg(a))>25?Math.sign(bankDeg(a)):0;if(sg&&oldSign&&sg!==oldSign)rev++;if(sg)oldSign=sg;
  if(stage===1&&g.R<1500&&g.ata<30&&g.aot<50){held+=1/60;if(held>.8)break;}
 }
 m.step(1/60);maxAlt=Math.max(maxAlt,a.pos.y);minV=Math.min(minV,a.speed);maxG=Math.max(maxG,a.nCur);
 if(Math.round(t*60)%120===0)path.push({t:+t.toFixed(1),stage,v:Math.round(a.speed*3.6),alt:Math.round(a.pos.y),bank:Math.round(bankDeg(a)),hdg:Math.round(hdgDeg(a)),...Object.fromEntries(Object.entries(g).map(([k,v])=>[k,v]))});
 if(!a.alive)break;
 }
 console.log(JSON.stringify({id,flight,control,time:+m.time.toFixed(2),stage,held,vertical,inverted,maxAlt:Math.round(maxAlt),minV:Math.round(minV*3.6),maxG:+maxG.toFixed(2),rev,overshot,end:geo(a,b),path}));
}
