import assert from 'node:assert/strict';
import {ADVANCED_LESSONS,advancedSupport} from '../src/academy/advanced.js';
import {flyAdvanced} from './test-advanced-academy.mjs';

export async function checkAdvanced({page,iphone,shot,report,quick=false}) {
 report.perf.advanced=[];
 for(const width of (quick?[667]:[812,667]))for(const flight of (quick?['arcade']:['arcade','tactical']))for(const control of (quick?['expert']:['assisted','expert'])){
  const {ctx,p}=await page({...iphone,viewport:{width,height:375}},`?mode=${flight}&control=${control}${width===812?'&debug=1':''}`,'advanced');
  await p.waitForFunction(()=>window.__game?.mode==='title');
  await p.evaluate(()=>{
   for(const [k,v] of Object.entries({'--sal':'34px','--sar':'34px','--sab':'21px'}))document.documentElement.style.setProperty(k,v);
   window.__game.hud.resize();
   localStorage.setItem('ace2ace.academy.v1',JSON.stringify({lessons:{L01:{attempts:2,cleared:true,best:'S',bestTime:55,modes:['arcade:expert']}}}));
  });
  await p.reload();await p.waitForFunction(()=>window.__game?.mode==='title');
  await p.evaluate(async()=>{
   for(const [k,v] of Object.entries({'--sal':'34px','--sar':'34px','--sab':'21px'}))document.documentElement.style.setProperty(k,v);
   const g=window.__game;g.hud.resize();
   const {makeStudentInput}=await import('/tools/academy-student.mjs');
   const {advancedStudent}=await import('/tools/advanced-student.mjs');
   g.onLessonStart=()=>{
    const st=makeStudentInput(),ctl=g.match.controllers.get(g.match.blue),update=ctl.update;
    ctl.update=(dt,m)=>{
     const r=g.lesson;
     if(!r.result&&!window.__manualAdvanced){
      advancedStudent(r,st,g.controlMode,{mistake:window.__advancedMistake||null});
      Object.assign(g.input.stick,st.stick);g.input.setThrottle(st.thr);g.input.boostToggle=st.ab;g.input.btn.brake=st.brk;g.input.btn.gun=st.gunOn;
     }
     return update(dt,m);
    };
    g.setTimeScale(8);
   };
  });
  await p.tap('#btnAcademy');
  assert.equal(await p.locator('#lessonGrid .lesson-card').count(),10);
  assert.equal(await p.locator('#advancedGrid .lesson-card').count(),3);
  assert.equal(await p.locator('[data-lesson="L01"].cleared').count(),1,'old progress preserved');
  if(width===667&&flight==='arcade'&&control==='expert')await shot(p,'advanced-667-catalog');
  for(const l of ADVANCED_LESSONS){
   await p.evaluate(id=>window.__game.openBriefing(id),l.id);
   if(advancedSupport(l,control)){
    assert.ok(await p.locator('#btnBriefGo').isDisabled());assert.match(await p.textContent('#briefSupport'),/Assisted.*Expert/);
    report.perf.advanced.push({width,id:l.id,mode:`${flight}:${control}`,blocked:true});continue;
   }
   if(l.id==='A01'&&width===667)await shot(p,'advanced-667-A01-brief');
   await p.tap('#btnBriefGo');
   await p.waitForFunction(()=>window.__game.lesson?.phaseT>3,null,{timeout:30000});
   // Actual touch tries to command a roll during observation; the demo still owns the jet.
   if(l.id==='A01'&&width===667){
    const before=await p.evaluate(()=>window.__game.match.blue.controls.roll);
    const cdp=await ctx.newCDPSession(p);
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{id:31,x:190,y:220}]});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{id:31,x:245,y:220}]});
    await p.waitForTimeout(100);
    assert.equal(await p.evaluate(()=>window.__game.match.blue.controls.roll),before,'touch cannot fly the instructor');
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
   }
   await p.waitForFunction(()=>window.__game.lesson.waiting,null,{timeout:120000});
   await p.waitForFunction(()=>window.__game.hud.traceLayout&&window.__game.hud.academyLayout);
   const lay=await p.evaluate(()=>({objective:window.__game.hud.academyLayout,trace:window.__game.hud.traceLayout,radio:window.__game.hud.radioLayout}));
   assert.ok(lay.objective.fontPx>=12);assert.ok(lay.objective.x>=34&&lay.trace.x+lay.trace.width<=width-34);
   assert.ok(lay.objective.y+lay.objective.height<185,'objective stays above reticle');
   assert.ok(lay.objective.lines.every(t=>!t.includes('…')),'instructions are not truncated');
   if(width===667&&flight==='arcade'&&control==='expert')await shot(p,`advanced-667-${l.id}-demo`);
   const frozen=await p.evaluate(()=>window.__game.match.time);await p.waitForTimeout(200);
   assert.equal(await p.evaluate(()=>window.__game.match.time),frozen,'handoff freezes the situation');
   await p.tap('#btnAdvance');
   await p.waitForFunction(()=>window.__game.lesson.phase.id==='guided');
   if(l.id==='T02'){
    // Human defenders need the existing LOOK control to see a pursuer behind them.
    await p.evaluate(()=>window.__game.setTimeScale(0));
    const cdp=await ctx.newCDPSession(p),box=await p.locator('[data-btn="look"]').boundingBox();
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{id:51,x:box.x+box.width/2,y:box.y+box.height/2}]});
    await p.waitForFunction(()=>window.__game.viewMode==='look');
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    await p.waitForFunction(()=>window.__game.viewMode==='chase'&&!window.__game.input.look());
    await p.evaluate(()=>window.__game.setTimeScale(8));
   }
   if(width===667&&l.id==='A01'){
    // Pause, resume and real touch through the live student's normal Input route.
    await p.evaluate(()=>{window.__manualAdvanced=true;window.__game.setTimeScale(0);});
    await p.tap('#pauseBtn');assert.equal(await p.evaluate(()=>window.__game.mode),'paused');
    await p.tap('#btnResume');
    const cdp=await ctx.newCDPSession(p);
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{id:41,x:185,y:205}]});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{id:41,x:225,y:170}]});
    await p.waitForFunction(()=>Math.abs(window.__game.input.axes().x)>.1);
    await cdp.send('Input.dispatchTouchEvent',{type:'touchCancel',touchPoints:[]});
    await p.waitForFunction(()=>window.__game.input.axes().x===0&&window.__game.input.axes().y===0);
    await p.evaluate(()=>{window.__manualAdvanced=false;window.__game.setTimeScale(8);});
   }
   await p.waitForFunction(()=>window.__game.lesson.waiting||window.__game.lesson.result,null,{timeout:120000});
   assert.equal(await p.evaluate(()=>window.__game.lesson.result?.success??null),null,'guided succeeds and awaits challenge');
   await p.tap('#btnAdvance');
   await p.waitForFunction(()=>window.__game.lesson.phase?.id==='challenge');
   await p.waitForFunction(()=>window.__game.lesson.phaseT>3,null,{timeout:30000});
   if(width===667&&flight==='arcade'&&control==='expert')await shot(p,`advanced-667-${l.id}-challenge`);
   await p.waitForFunction(()=>window.__game.mode==='debrief',null,{timeout:120000});
   const result=await p.evaluate(()=>window.__lastLesson),want=flyAdvanced(l,`${flight}:${control}`).result;
   assert.ok(result.success,`${width} ${l.id} ${flight}:${control}: ${result.reason}`);
   assert.deepEqual([result.grade,+result.time.toFixed(2)],[want.grade,+want.time.toFixed(2)],'browser reproduces Node through the normal controller');
   assert.ok(await p.locator('#debTraceFigure').isVisible());
   if(width===667&&flight==='arcade'&&control==='expert')await shot(p,`advanced-667-${l.id}-debrief`);
   report.perf.advanced.push({width,id:l.id,mode:result.mode,success:result.success,time:+result.time.toFixed(2),layout:lay});
  }
  if(control==='assisted'){
   await p.evaluate(()=>window.__game.openBriefing('A01'));await p.tap('#btnBriefExpert');
   assert.equal(await p.evaluate(()=>window.__game.controlMode),'expert');assert.ok(await p.locator('#btnBriefGo').isEnabled());
   assert.ok(await p.locator('#btnBriefExpert').isHidden());
  }
  await p.reload();await p.waitForFunction(()=>window.__game?.mode==='title');await p.tap('#btnAcademy');
  const preserved=await p.evaluate(()=>window.__game.academyProgress.lessons.L01);assert.equal(preserved.best,'S');assert.equal(preserved.attempts,2);
  console.log(`[advanced] ${width} ${flight}:${control} complete`);
  await ctx.close();
 }
 // A real failed sortie, causal debrief and quick retry without repeating briefing.
 const {ctx,p}=await page(iphone,'?mode=arcade&control=expert&lesson=T01&autostart=1','advanced-fail');
 await p.waitForFunction(()=>window.__game?.mode==='playing');
 await p.evaluate(async()=>{
  const {advancedStudent}=await import('/tools/advanced-student.mjs'),{makeStudentInput}=await import('/tools/academy-student.mjs');
  const g=window.__game,st=makeStudentInput(),ctl=g.match.controllers.get(g.match.blue),update=ctl.update;
  ctl.update=(dt,m)=>{if(!g.lesson.result){advancedStudent(g.lesson,st,'expert',{mistake:'shoot'});Object.assign(g.input.stick,st.stick);g.input.boostToggle=st.ab;g.input.btn.gun=st.gunOn;g.input.setThrottle(st.thr);}return update(dt,m);};
  g.setTimeScale(8);
 });
 await p.waitForFunction(()=>window.__game.lesson.waiting,null,{timeout:120000});await p.tap('#btnAdvance');
 await p.waitForFunction(()=>window.__game.mode==='debrief',null,{timeout:120000});
 assert.match(await p.textContent('#debSub'),/尚未改善位置就開火/);await shot(p,'advanced-812-causal-failure');
 await p.tap('#btnDebRetry');assert.equal(await p.evaluate(()=>window.__game.mode),'playing');assert.equal(await p.evaluate(()=>window.__game.lesson.phase.id),'demonstration');
 await ctx.close();
}
