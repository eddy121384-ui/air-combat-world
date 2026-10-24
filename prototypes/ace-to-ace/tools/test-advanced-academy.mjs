import assert from 'node:assert/strict';
import {ADVANCED_LESSONS,advancedSupport} from '../src/academy/advanced.js';
import {createLessonSession} from '../src/academy/session.js';
import {makeStudentInput} from './academy-student.mjs';
import {advancedStudent} from './advanced-student.mjs';
import {loadProgress,recordAttempt,saveProgress} from '../src/academy/progress.js';
import {TiltInput} from '../src/game/tilt-input.js';
import {writeFile} from 'node:fs/promises';
export function flyAdvanced(lesson,mode,{mistake=null,mistakeStage='guided',seed=52031,device='stick',gunHeld=false}={}) {
 const [flight,control]=mode.split(':'),input=makeStudentInput();
 let now=0,tilt=null;
 if(device==='tilt'){
  const host=new EventTarget();Object.assign(host,{isSecureContext:true,DeviceOrientationEvent:{},screen:{orientation:{angle:90}}});
  tilt=new TiltInput({host,now:()=>now});tilt.allowed=true;tilt.start();tilt.receive({beta:0,gamma:-40});
  input.axes=()=>({...tilt.axes(),yaw:0});input.inputDevice='tilt';
 }
 const {match,runner:r}=createLessonSession(lesson,{flight,control,input,seed});
 assert.equal(r.view().timer,lesson.attemptLimit,'the per-attempt time limit is visible before flying');
 const ctl=match.controllers.get(match.blue),update=ctl.update;
 r.onSay=text=>{
  if(text.includes('已倒飛反向'))assert.ok(r.d.m.inverted,'inversion hint has observed evidence');
  if(text.includes('高度存好了'))assert.ok(r.d.m.maxHeight>250&&r.d.m.unload>=.5,'energy hint matches the flown climb');
  if(text.includes('追兵已穿過前方'))assert.ok(r.d.m.overshoot,'overshoot hint has actual crossing evidence');
 };
 ctl.update=(dt,m)=>{
  advancedStudent(r,input,control,{mistake:r.phase?.id===mistakeStage?mistake:null});
  if(gunHeld)input.gunOn=true;
  if(tilt){
   const degrees=v=>Math.abs(v)<1e-9?0:Math.sign(v)*(2+18*(-.35+Math.sqrt(.35*.35+2.6*Math.min(1,Math.abs(v))))/1.3);
   now+=dt*1000;tilt.receive({beta:degrees(input.stick.x),gamma:-40-degrees(input.stick.y)});tilt.tick();
  }
  const before=JSON.stringify([r.me.q,r.me.pos,r.me.vel,r.me.speed,r.me.nCur]);
  const out=update(dt,m);
  assert.equal(JSON.stringify([r.me.q,r.me.pos,r.me.vel,r.me.speed,r.me.nCur]),before,'student and instructor controllers only produce commands');
  assert.ok(Math.abs(out.pitch)<=1&&Math.abs(out.roll)<=1&&out.throttle>=0&&out.throttle<=1);
  return out;
 };
 for(let i=0;i<35000&&!r.result;i++){
  if(r.waiting)r.requestAdvance();
  match.step(1/60);r.step(1/60);
 }
 assert.doesNotThrow(()=>r.view(),'HUD remains valid between flight completion and debrief');
 assert.equal(r.view().weapons,false,'position training never advertises a combat SHOOT cue');
 tilt?.stop();return r;
}
if(import.meta.url===`file://${process.argv[1]}`){
 const rows=[];let failed=0;
 for(const l of ADVANCED_LESSONS)for(const f of ['arcade','tactical'])for(const c of ['assisted','expert']){
  const mode=`${f}:${c}`;
  if(advancedSupport(l,c)){assert.throws(()=>createLessonSession(l,{flight:f,control:c,input:makeStudentInput()}),/Expert/);rows.push({id:l.id,mode,status:'blocked: Expert required'});continue;}
  for(const mistake of [null,...(l.id==='A01'?['flat','noRoll','noSpeed','lowExit']:l.id==='T01'?['gOnly','noSpeed','shoot']:['gOnly','noReverse','noSpeed','shoot'])]){
   const r=flyAdvanced(l,mode,{mistake}),m=r.notes.challenge||r.d.m;
   const expected={flat:/平面轉彎/,noRoll:/半滾轉/,noSpeed:/低能量/,lowExit:/末端.*高度收益/,gOnly:/低能量|沒有把多餘速度換成高度|穩定射擊窗口|有效反轉/,noReverse:/有效反轉/,shoot:/尚未改善位置就開火/};
   const ok=mistake?r.result&&!r.result.success&&r.phase?.id==='guided'&&expected[mistake].test(r.result.reason):r.result?.success;
   assert.ok(r.notes.demonstration,`${l.id}/${mode}: instructor actually completed the maneuver`);
   if(!mistake){assert.ok(r.notes.guided&&r.notes.challenge);assert.ok(m.trace.length>=20&&m.trace.length<=400);assert.ok(m.maxG<=10.51);}
   rows.push({id:l.id,mode,mistake:mistake||'correct',ok,t:+r.t.toFixed(2),phase:r.phase?.id,why:r.result?.reason||'',maxHeight:Math.round(m.maxHeight),minV:Math.round(m.minSpeed*3.6),rev:m.reversals,overshoot:m.overshoot,window:+m.bestWindow.toFixed(2),challengeTime:mistake?null:+m.duration.toFixed(2),maxG:+m.maxG.toFixed(2),energyDelta:Math.round(m.end.energy-m.entryEnergy),endRange:Math.round(m.end.range),endClosure:+m.end.closure.toFixed(2)});
   if(!ok)failed++;
  }
 }
 // Fixed-seed repeated run must reproduce exact result/telemetry; no retry-until-green.
 for(const l of ADVANCED_LESSONS)for(const mode of ['arcade:expert','tactical:expert']){
  const a=flyAdvanced(l,mode),b=flyAdvanced(l,mode);
  assert.deepEqual(a.result,b.result);assert.deepEqual(a.notes.challenge,b.notes.challenge);
 }
 // Synthetic sensor events exercise the actual TiltInput shaping + PlayerController.
 for(const l of ADVANCED_LESSONS)for(const mode of ['arcade:assisted','arcade:expert','tactical:assisted','tactical:expert']){
  if(advancedSupport(l,mode.split(':')[1]))continue;
  const r=flyAdvanced(l,mode,{device:'tilt'});
  assert.ok(r.result?.success,`${l.id}/${mode}: synthetic TILT input can complete the same challenge`);
 }
 // The same incorrect inputs must also fail without guided hints in Challenge.
 for(const mode of ['arcade:expert','tactical:expert']){
  const r=flyAdvanced(ADVANCED_LESSONS[0],mode,{gunHeld:true});
  assert.ok(r.result.success,'incidental weapon contact cannot fail an aerobatics-only lesson');
  assert.equal(r.me.stats.roundsFired,0,'A01 filters weapon commands rather than judging firing discipline');
 }
 for(const l of ADVANCED_LESSONS)for(const mode of ['arcade:assisted','arcade:expert','tactical:assisted','tactical:expert']){
  if(advancedSupport(l,mode.split(':')[1]))continue;
  const mistake=l.id==='A01'?'noRoll':l.id==='T01'?'shoot':'noReverse';
  const r=flyAdvanced(l,mode,{mistake,mistakeStage:'challenge'});
  assert.ok(r.result&&!r.result.success&&r.phase.id==='challenge',`${l.id}/${mode}: wrong challenge fails after valid guided practice`);
 }
 const values=new Map(),store={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)};
 const progress={lessons:{L01:{best:'S',cleared:true,attempts:2}}};saveProgress(progress,store);
 const p=loadProgress(store);recordAttempt(p,'A01',{success:true,grade:'A',time:71,mode:'arcade:expert'});saveProgress(p,store);
 assert.deepEqual(loadProgress(store).lessons.L01,progress.lessons.L01);
 console.table(rows);if(process.env.ACE_ADVANCED_REPORT)await writeFile(process.env.ACE_ADVANCED_REPORT,JSON.stringify(rows,null,2)+'\n');
 assert.equal(failed,0,`${failed} advanced checks failed`);
 console.log('Advanced Academy PASS');
}
