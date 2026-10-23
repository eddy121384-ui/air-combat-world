// Synthetic orientation stream, not a shortcut around PlayerController.
import assert from 'node:assert/strict';
import {TiltInput} from '../src/game/tilt-input.js';
import {LESSONS} from '../src/academy/lessons.js';
import {createLessonSession} from '../src/academy/session.js';
import {makeStudentInput,PLANS} from './academy-student.mjs';
const table=[];
function fly(lesson,flight,control,seed) {
  let now=0;const host=new EventTarget();host.isSecureContext=true;host.DeviceOrientationEvent={};host.screen={orientation:{angle:90}};
  const tilt=new TiltInput({host,now:()=>now});tilt.allowed=true;tilt.start();tilt.receive({beta:0,gamma:-40});
  const s=makeStudentInput();s.inputDevice='tilt';s.axes=()=>({...tilt.axes(),yaw:0});
  const {match,runner:r}=createLessonSession(lesson,{flight,control,input:s,...(seed==null?{}:{seed})});
  const ctl=match.controllers.get(match.blue),update=ctl.update;
  // Ignore numerical epsilon around intended zero, not real control corrections.
  // Translate the unmodified student's desired shaped stick into physical degrees.
  const degrees=v=>Math.abs(v)<1e-9?0:Math.sign(v)*(2+18*(-.35+Math.sqrt(.35*.35+2.6*Math.min(1,Math.abs(v))))/1.3);
  ctl.update=(dt,m)=>{PLANS[lesson.id](r,s,control);now+=dt*1000;
    tilt.receive({beta:degrees(s.stick.x),gamma:-40-degrees(s.stick.y)});tilt.tick();return update(dt,m);};
  while(!r.result&&r.t<600){match.step(1/60);r.step(1/60);}
  tilt.stop();return r;
}
for(const flight of ['arcade','tactical'])for(const control of ['assisted','expert']) {
  for(const l of LESSONS) {
    const r=fly(l,flight,control);
    assert.ok(r.result,`${l.id}/${flight}/${control}: finishes`);
    if(!l.final)assert.ok(r.result.success,`${l.id}/${flight}/${control}: ${r.result.reason}`);
    table.push({id:l.id,flight,control,success:r.result.success,time:+r.t.toFixed(2)});
  }
  let wins=0;
  for(let k=0;k<12;k++)if(fly(LESSONS.at(-1),flight,control,52031+k).result?.success)wins++;
  assert.ok(wins>=4,`${flight}/${control}: ${wins}/12 checkrides, same existing standard`);
  table.push({id:'L10 x12',flight,control,success:true,wins});
}
console.table(table);console.log('TILT academy PASS: unchanged plans, seeds and grading; default zero additional delay (deadzone + Expo); L01–09 x4 and L10 >=4/12 wins x4');
