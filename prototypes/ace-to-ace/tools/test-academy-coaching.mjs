// Teaching contracts beyond completion: explanations, truthful feedback and transfer.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { LESSONS, lessonById } from '../src/academy/lessons.js';
import { createLessonSession } from '../src/academy/session.js';
import { placeJet, radioChunks, RADIO_CHARS } from '../src/academy/runner.js';
import { makeStudentInput, PLANS, BAD } from './academy-student.mjs';
import { fly } from './test-academy.mjs';

const modes=['arcade:assisted','arcade:expert','tactical:assisted','tactical:expert'];
const baseline=JSON.parse(readFileSync(new URL('../docs/academy-controls-baseline.json',import.meta.url)));
function session(id,mode='arcade:expert') {
  const [flight,control]=mode.split(':');
  return createLessonSession(lessonById(id),{flight,control,input:makeStudentInput()}).runner;
}

const long='先看機頭 W，再看 FPM。高度 2,200 m、速度 950 km/h；小幅修正，讓數字穩住！不要用機頭姿態代替真正的航跡。';
const chunks=radioChunks(long);
assert.ok(chunks.every(s=>Array.from(s).length<=RADIO_CHARS));
assert.equal(chunks.join('').replace(/\s/g,''),long.replace(/\s/g,''),'no lost or ellipsized instruction');
assert.match(radioChunks('平順地拉起。保留 400 km/h 再轉彎；不要為了追數字，反覆大幅修正搖桿。')[0],/^[\s\S]*[。；]$/);
{
  const r=session('L03');
  r.say('STALE PREVIOUS TASK');r.next();r.tickRadio(0);
  assert.ok(!r.queue.join('').includes('STALE'));
  assert.match(r.spoken.at(-1).text,/減到 650/,'current task precedes narrative');
  r.coachOnce('hazard','現在卸載，先救回速度。',{urgent:true});
  const count=r.queue.length;
  r.coachOnce('hazard','不可重複',{urgent:true});
  assert.equal(r.queue.length,count,'no repetitive nagging');
  r.tickRadio(0);assert.match(r.spoken.at(-1).text,/現在卸載/);
}

const after=[];
for(const mode of modes) {
  const orientation=session('L01',mode), firstInstruction=orientation.phase.say(orientation);
  assert.match(firstInstruction,mode.endsWith('assisted')?/飛控替你改平/:/機翼不會自己改平/);
  const turnIntro=session('L02',mode);
  const explanation=turnIntro.lesson.intro.map(line=>typeof line==='function'?line(turnIntro):line).join('');
  assert.match(explanation,mode.endsWith('assisted')?/放手.*飛控會改平/:/放手不會改平/);
  for(const lesson of LESSONS) {
    const r=fly(lesson,mode,PLANS[lesson.id]);
    after.push({lesson:lesson.id,mode,time:+r.t.toFixed(2),grade:r.result.grade,success:r.result.success});
    assert.ok(r.spoken.every(s=>Array.from(s.text).length<=RADIO_CHARS),`${lesson.id}/${mode}: short radio`);
    if(lesson.final) {
      const old=baseline.cases.find(x=>x.lesson==='L10'&&x.mode===mode);
      assert.deepEqual([r.result.success,r.result.grade,+r.t.toFixed(2)],[old.success,old.grade,old.time],
        'no combat/physics/AI/seed changes hidden behind teaching changes');
      if(r.result.success)assert.match(r.result.citation,/資格通過/);
    }
    if(lesson.id==='L04') {
      assert.ok(r.spoken.some(line=>line.text.includes('上一圈轉率多了')),'measured corner feedback survives the phase transition and is actually spoken');
    }
    if(lesson.id==='L05') {
      const drop=Math.round(4500-r.notes.diveAlt).toLocaleString('en-US');
      assert.ok(r.result.good.some(line=>line.includes(`實際減少 ${drop}`)),'energy debrief uses actual altitude');
    }
  }

  // A steady-flight objective cannot be passed by accumulating disconnected slices.
  const steady=session('L01',mode);
  steady.step(2.9);
  placeJet(steady.me,{bank:20});steady.step(.1);
  assert.equal(steady.d.held,0,'bad interval resets the hold');
  placeJet(steady.me,{bank:0});steady.step(2.9);
  assert.equal(steady.phase.id,'level');

  const turn=session('L02',mode);turn.next();turn.next();
  turn.me.pos.y+=201;turn.step(1/60);
  assert.equal(turn.result.success,false);assert.match(turn.result.reason,/上限 200/);

  // Judge fixture with real geometric before/after states. The three-pass path was
  // previously untested; closing speed must be recorded BEFORE crossing the target.
  const pursuit=session('L07',mode), foe=pursuit.foe;
  assert.deepEqual(pursuit.phase.markers(pursuit),[],'straight-tail sightlines must not stack three overlapping labels');
  placeJet(foe,{heading:90,speed:200});
  assert.equal(pursuit.phase.markers(pursuit).length,3,'turning reveals distinct pursuit references');
  placeJet(foe,{pos:{x:0,y:3000,z:0},heading:0,speed:200});
  for(let pass=0;pass<3;pass++) {
    placeJet(pursuit.me,{pos:{x:0,y:3000,z:1000},heading:0,speed:320});pursuit.step(1/60);
    placeJet(pursuit.me,{pos:{x:0,y:3000,z:-300},heading:0,speed:320});pursuit.step(1/60);
  }
  assert.equal(pursuit.result.success,false);assert.match(pursuit.result.reason,/第 3 次衝過頭/);
  assert.ok(pursuit.d.lastClose>0,'pre-pass approach speed, not negative post-pass separation');
  assert.ok(!pursuit.result.good.some(x=>x.includes('控制得很好')));

  const body=fly(lessonById('L08'),mode,BAD['L08:bodyAim']);
  assert.equal(body.result.success,false);
  assert.match(body.result.citation,/先修正/,'failure does not reuse a successful graduation/closing line');
  assert.ok(body.spoken.some(x=>x.t<body.t-2&&x.text.includes('你在追它現在的位置')),'correct while practising, not only after failure');
  assert.equal(body.result.stats.find(x=>x[0]==='機砲命中')[1],String(body.d.gunHits));

  const ignore=fly(lessonById('L09'),mode,BAD['L09:ignore']);
  assert.ok(!ignore.result.good.includes('3 枚飛彈全部躲掉。'),'failure cannot claim all missiles dodged');
  assert.ok(ignore.result.improve.some(x=>x.includes('被命中 2 枚')));

  // Transfer probe changes timing/range, NOT seeds or hit thresholds. Isolate the
  // missile drill: the calibrated full BFM lesson stays exactly as before.
  const defence=lessonById('L09');
  const varied={...defence,phases:[defence.phases[0]],tune:{all:{...defence.tune.all,
    launchIntervals:[1.25,6.75,14.25],launchRanges:[1900,2050,1750]}}};
  const transfer=fly(varied,mode,PLANS.L09);
  assert.equal(transfer.result.success,true,`${mode}: range-based defence transfers beyond a memorized timer`);
  assert.deepEqual(transfer.notes.launches.map(x=>x.distance),[1900,2050,1750]);
}
console.table(after.filter(x=>['L01','L03','L10'].includes(x.lesson)));
console.log('Academy coaching PASS: truthful debriefs, short/current radio, continuous holds, altitude limit, overshoot judge, proactive gun correction, varied missile-drill transfer x4');
