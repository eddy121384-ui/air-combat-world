// Automated students: only normal stick/power/buttons. Judges never read this state.
import {stickToward,dirFor,speedControl} from './academy-student.mjs';
import {pitchForG} from '../src/sim/aircraft.js';
import {hdgDeg,gammaDeg,bankDeg,wrapDeg} from '../src/academy/runner.js';
import {norm,sub,forwardOf,toBody,clamp,DEG} from '../src/sim/math.js';
import {relativeFlight} from '../src/academy/advanced.js';
export function advancedStudent(r,s,c,{mistake=null}={}) {
  const id=r.lesson.id,ac=r.me,foe=r.foe;
  if(!r.__student||r.__student.phase!==r.phaseIdx)r.__student={phase:r.phaseIdx,stage:0};
  const p=r.__student,g=relativeFlight(ac,foe);s.ab=false;s.brk=false;s.thr=.72;s.gunOn=false;
  if(r.phase.id==='demonstration')return;
  if(mistake==='flat'){
    Object.assign(s.stick,stickToward(ac,dirFor(hdgDeg(ac)+60,0),c));return;
  }
  if(mistake==='noSpeed'){
    s.thr=0;s.brk=true;s.stick.x=0;s.stick.y=-1;return;
  }
  if(mistake==='gOnly'){
    if(c==='assisted'){s.stick.x=1;s.stick.y=1;}
    else {s.stick.x=clamp(wrapDeg(75-bankDeg(ac))*DEG*2.5-ac.rollRateCur*.12,-1,1);s.stick.y=-1;}
    return;
  }
  if(mistake==='noReverse'){
    if(c==='assisted'){s.stick.x=.8;s.stick.y=0;}
    else {s.stick.x=clamp(wrapDeg(70-bankDeg(ac))*DEG*2.5-ac.rollRateCur*.12,-1,1);s.stick.y=-pitchForG(ac,3.5);}
    s.thr=.1;s.brk=ac.speed>125;return;
  }
  if(mistake==='shoot'){
    s.gunOn=true;Object.assign(s.stick,stickToward(ac,norm(sub(foe.pos,ac.pos)),c));s.ab=true;s.thr=1;return;
  }
  if(id==='A01') {
    const f=forwardOf(ac.q);
    if(p.stage===0){s.stick.x=0;s.stick.y=-pitchForG(ac,5);if(f.z>.90&&f.y<.30)p.stage=1;}
    if(p.stage===1){s.stick.y=0;s.stick.x=mistake==='noRoll'?0:clamp(wrapDeg(-bankDeg(ac))*DEG*2.5-ac.rollRateCur*.12,-1,1);if(Math.abs(bankDeg(ac))<8)p.stage=2;}
    if(p.stage===2)Object.assign(s.stick,stickToward(ac,dirFor(180,mistake==='lowExit'&&ac.pos.y>3200?-50:0),c,{pullLimit:.5}));
  } else if(id==='T01'){
    if(p.stage===0){s.stick.x=0;s.stick.y=-pitchForG(ac,3.2);if(gammaDeg(ac)>28)p.stage=1;}
    else if(p.stage===1){Object.assign(s.stick,stickToward(ac,dirFor(hdgDeg(foe)-15,28),c,{pullLimit:.4}));if(ac.pos.y>3400||g.closure<5)p.stage=2;}
    else {Object.assign(s.stick,stickToward(ac,norm(sub(foe.pos,ac.pos)),c));if(c==='assisted'){const aim=toBody(ac.q,norm(sub(foe.pos,ac.pos)));s.stick.y=-clamp(Math.atan2(aim.y,Math.max(-aim.z,.001))/(5*DEG),-1,.7);}speedControl(s,ac,foe.speed*3.6+clamp((g.range-700)/4,-100,100));}
  } else {
    if(p.stage===0){const side=Math.floor(r.phaseT/3)%2===0?1:-1;
      if(c==='assisted'){s.stick.x=side*.8;s.stick.y=0;}
      else{s.stick.x=clamp(wrapDeg(side*70-bankDeg(ac))*DEG*2.5-ac.rollRateCur*.12,-1,1);s.stick.y=-pitchForG(ac,clamp(3.5-ac.vel.y/90,1,5));}
      s.thr=.1;s.brk=g.range<900&&ac.speed>125;if(g.ata<80)p.stage=1;
    } else {Object.assign(s.stick,stickToward(ac,norm(sub(foe.pos,ac.pos)),c));speedControl(s,ac,foe.speed*3.6+clamp((g.range-600)/4,-100,150));}
  }
}
