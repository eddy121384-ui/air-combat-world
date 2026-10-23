#!/usr/bin/env node
// Ace Flight Academy headless verification. Every lesson is flown by the
// automated student through the real PlayerController in all four
// physics x control combinations (fixed seed), and deliberately wrong students
// must fail with the causal feedback the lesson promises.
//   node tools/test-academy.mjs [--only L03] [--verbose]
import assert from 'node:assert/strict';
import { LESSONS, lessonById } from '../src/academy/lessons.js';
import { createLessonSession } from '../src/academy/session.js';
import { loadProgress, recordAttempt, saveProgress } from '../src/academy/progress.js';
import { makeStudentInput, PLANS, BAD } from './academy-student.mjs';
import { RULES } from '../src/sim/world.js';
import { RADIO_MAX } from '../src/academy/runner.js';

const args = process.argv.slice(2);
const only = args.includes('--only') ? args[args.indexOf('--only') + 1] : null;
const verbose = args.includes('--verbose');
const MODES = ['arcade:assisted', 'arcade:expert', 'tactical:assisted', 'tactical:expert'];

export function fly(lesson, mode, plan, { maxT = 600, seed, resume = null, retry = 0 } = {}) {
  const [flight, control] = mode.split(':');
  const input = makeStudentInput();
  const { match, runner } = createLessonSession(lesson, { flight, control, input, resume, retry, ...(seed != null ? { seed } : {}) });
  // The student thinks inside the player's controller update, exactly like the
  // browser hook and a real thumb: after this step's lock update, before controls.
  const ctl = match.controllers.get(match.blue), orig = ctl.update;
  ctl.update = (dt, m) => { plan(runner, input, control); return orig(dt, m); };
  const dt = RULES.dt;
  while (!runner.result && runner.t < maxT) {
    match.step(dt);
    runner.step(dt);
  }
  return runner;
}

export const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
const table = [];
let failures = 0;
const runs = []; // every runner flown, for the radio / coaching checks below
for (const lesson of LESSONS) {
  if (only && lesson.id !== only) continue;
  const plan = PLANS[lesson.id];
  assert.ok(plan, `${lesson.id}: student plan missing`);
  for (const mode of MODES) {
    const r = fly(lesson, mode, plan);
    runs.push({ key: lesson.id, mode, r });
    // L10 is a real 1v1 vs VETERAN: at the fixed opening it must end decisively (a
    // win, or a loss with a stated reason); completability is the 12-seed check below.
    const ok = lesson.final ? !!r.result && (r.result.success || (r.result.reason || '').length > 4) : r.result?.success === true;
    table.push({ lesson: lesson.id, mode, ok, grade: r.result?.grade ?? (r.result ? 'lost' : '-'), t: +r.t.toFixed(1), reason: r.result?.reason ?? '' });
    if (!ok) failures++;
    if (verbose || !ok) console.log(`${lesson.id} ${mode}: ${r.result?.success ? 'CLEAR' : 'FAIL'} ${r.t.toFixed(1)}s ${r.result?.reason ?? ''}`
      + (verbose ? `\n   phases reached: ${r.phaseIdx}/${lesson.phases.length}  spoken: ${r.spoken.length}` : ''));
  }
}

// Wrong students must fail for the right reason (keyword in the feedback).
const EXPECT = {
  'L01:banked': { modes: ['arcade:expert', 'tactical:expert'], match: /機翼不平/ },
  'L02:rollNoPull': { modes: ['arcade:expert', 'tactical:expert'], match: /沒拉桿/ },
  'L03:noAB': { modes: MODES, match: /沒開 AB/ },
  'L03:noBrake': { modes: MODES, match: /BRK/ },
  'L03:dive': { modes: MODES, match: /第五課/ },
  'L04:yank': { modes: MODES, match: /燒掉/ },
  'L05:yank': { modes: ['arcade:expert', 'tactical:expert'], match: /BRK/ },
  'L05:yankNoBrake': { modes: ['arcade:expert', 'tactical:expert'], match: /G，能量高度掉了/ },
  'L06:stallPull': { modes: MODES, match: /拉了/ },
  'L06:late': { modes: MODES, match: /墜海|最低/ },
  'L07:pure': { modes: MODES, match: /衝過頭|lead|提前量/ },
  'L08:spray': { modes: MODES, match: /Pk|鎖定/ },
  'L09:ignore': { modes: MODES, match: /沒放熱焰彈/ },
  'L09:early': { modes: MODES, match: /太早/ },
  'L09:straight': { modes: MODES, match: /直線飛/ },
};
for (const [key, exp] of Object.entries(EXPECT)) {
  const [id] = key.split(':');
  if (only && id !== only) continue;
  for (const mode of exp.modes) {
    const r = fly(lessonById(id), mode, BAD[key], { maxT: 400 });
    runs.push({ key, mode, r });
    const ok = r.result && !r.result.success && exp.match.test(r.result.reason || '');
    table.push({ lesson: key, mode, ok, grade: 'fail-expected', t: +r.t.toFixed(1), reason: r.result?.reason ?? '(no result)' });
    if (!ok) { failures++; console.log(`${key} ${mode}: expected causal failure ${exp.match}, got ${JSON.stringify(r.result?.reason)} success=${r.result?.success}`); }
  }
}

// The final checkride is a real 1v1 vs VETERAN: completable, not guaranteed. The
// HUD-only "good" human proxy must win a fair share over 12 openings in every mode.
if (!only || only === 'L10') {
  for (const mode of MODES) {
    let wins = 0;
    for (let k = 0; k < 12; k++) if (fly(lessonById('L10'), mode, PLANS.L10, { seed: 52031 + k, maxT: 420 }).result?.success) wins++;
    const ok = wins >= 4;
    table.push({ lesson: 'L10 x12 seeds', mode, ok, grade: `${wins}/12 wins`, t: 0 });
    if (!ok) { failures++; console.log(`L10 ${mode}: only ${wins}/12 wins for the good proxy`); }
  }
}

// Radio discipline: every subtitle actually spoken fits a phone HUD line budget.
{
  let worst = { len: 0 };
  for (const { key, mode, r } of runs) for (const l of r.spoken) if (l.text.length > worst.len) worst = { len: l.text.length, key, mode, text: l.text };
  const ok = worst.len <= RADIO_MAX + 6;
  table.push({ lesson: 'radio length', mode: 'all', ok, grade: `max ${worst.len} chars`, t: 0 });
  if (!ok) { failures++; console.log(`radio line too long (${worst.len}) in ${worst.key} ${worst.mode}: ${worst.text}`); }
}

// Coaching reacts to what the student actually did (cue keys fired during the run).
const CUES = {
  'L01': { modes: MODES, cues: ['good'] },
  'L02:rollNoPull': { modes: ['arcade:expert', 'tactical:expert'], cues: ['nopull'] },
  'L03:noAB': { modes: MODES, cues: ['ab'] },
  'L03:noBrake': { modes: MODES, cues: ['brk'] },
  'L04': { modes: MODES, cues: ['band'] },
  'L05': { modes: MODES, cues: ['same'] },
  'L05:yankNoBrake': { modes: ['arcade:expert', 'tactical:expert'], cues: ['yank'] },
  'L06:stallPull': { modes: MODES, cues: ['pull'] },
  'L07': { modes: MODES, cues: ['in'] },
  'L07:pure': { modes: MODES, cues: ['closure'] },
  'L08': { modes: MODES, cues: ['lock', 'first'] },
  'L09': { modes: MODES, cues: ['flr1', 'brk1', 'flr2'], never: ['brk2', 'brk3', 'flr3'] },
  'L09:early': { modes: MODES, cues: ['early1'] },
};
for (const [key, exp] of Object.entries(CUES)) {
  if (only && key.split(':')[0] !== only) continue;
  for (const mode of exp.modes) {
    const run = runs.find((x) => x.key === key && x.mode === mode);
    if (!run) continue;
    const fired = new Set((run.r.cues || []).map((c) => c.key));
    const missing = exp.cues.filter((c) => !fired.has(c)), extra = (exp.never || []).filter((c) => fired.has(c));
    const ok = !missing.length && !extra.length;
    table.push({ lesson: `cue ${key}`, mode, ok, grade: ok ? exp.cues.join('+') : `missing ${missing} extra ${extra}`, t: 0 });
    if (!ok) { failures++; console.log(`${key} ${mode}: coaching cues missing [${missing}] unexpected [${extra}] fired [${[...fired]}]`); }
  }
}

// Checkpoint retry: fly the good plan until a checkpoint phase, then stall there
// (no input) so the phase fails; the failed result offers a resume snapshot, and
// resuming with the good plan clears the lesson without re-flying earlier phases.
// A checkpoint clear is capped at A.
if (!only || ['L04', 'L05', 'L06', 'L08', 'L09'].includes(only)) {
  // two ways to fail a phase: do nothing, or yank full aft stick at idle power
  const idle = (s) => { s.stick.x = 0; s.stick.y = 0; s.thr = 0.72; s.ab = false; s.brk = false; s.gunOn = false; s.presses.clear(); };
  const yank = (s) => { idle(s); s.stick.y = -1; s.thr = 0; };
  for (const lesson of LESSONS) {
    if (only && lesson.id !== only) continue;
    lesson.phases.forEach((ph, k) => {
      if (!ph.checkpoint || k === 0) return;
      for (const mode of ['arcade:expert', 'tactical:assisted']) {
        const plan = PLANS[lesson.id];
        let first = null, res = null;
        for (const bad of [idle, yank]) {
          first = fly(lesson, mode, (r, s, c) => (r.phaseIdx < k ? plan(r, s, c) : bad(s)), { maxT: 400 });
          res = first.result;
          if (res && !res.success && res.phase === ph.id) break; // (Assisted can recover a stall hands-off)
        }
        let ok = res && !res.success && res.phase === ph.id && res.resume?.from === k;
        let second = null;
        if (ok) {
          second = fly(lesson, mode, plan, { maxT: 400, resume: res.resume, retry: 1 });
          ok = second.result?.success === true && second.result.checkpoint === true && second.result.grade !== 'S'
            && second.spoken[0]?.text.includes(ph.name) && !second.spoken.some((l) => (lesson.intro || []).includes(l.text));
        }
        table.push({ lesson: `${lesson.id} resume@${ph.name}`, mode, ok, grade: second?.result?.grade ?? '-', t: +(second?.t ?? 0).toFixed(1) });
        if (!ok) { failures++; console.log(`${lesson.id} checkpoint ${ph.name} ${mode}: first=${JSON.stringify(res && { s: res.success, phase: res.phase, from: res.resume?.from, why: res.reason })} second=${JSON.stringify(second?.result && { s: second.result.success, cp: second.result.checkpoint, g: second.result.grade, why: second.result.reason })} said0=${second?.spoken[0]?.text}`); }
      }
    });
  }
}

// L10 graduation: a win awards a TAC NAME that quotes the real reason.
{
  const win = runs.find((x) => x.key === 'L10' && x.r.result?.success);
  // the loop stops at the result; the closing radio is still queued (the browser keeps ticking it)
  const said = win ? [...win.r.spoken.map((l) => l.text), ...win.r.queue.map((q) => q.text)] : [];
  const ok = !!win && /^[A-Z]+$/.test(win.r.result.extra?.name || '') && said.some((l) => l.includes(win.r.result.extra.name));
  table.push({ lesson: 'L10 TAC NAME', mode: win?.mode ?? '-', ok, grade: win?.r.result.extra?.name ?? '-', t: 0 });
  if (!ok) { failures++; console.log('L10: a win must award a TAC NAME on the radio'); }
}

// Progress: best grade kept, modes accumulated, broken storage tolerated.
{
  const mem = new Map();
  const store = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  let p = loadProgress(store);
  recordAttempt(p, 'L01', { success: false, mode: 'arcade:expert' });
  recordAttempt(p, 'L01', { success: true, grade: 'B', time: 80, mode: 'arcade:expert' });
  recordAttempt(p, 'L01', { success: true, grade: 'S', time: 55, mode: 'tactical:assisted' });
  recordAttempt(p, 'L01', { success: true, grade: 'A', time: 60, mode: 'arcade:expert' });
  assert.ok(saveProgress(p, store));
  p = loadProgress(store);
  assert.deepEqual([p.lessons.L01.best, p.lessons.L01.bestTime, p.lessons.L01.attempts, p.lessons.L01.modes.length], ['S', 55, 4, 2]);
  const broken = { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } };
  assert.deepEqual(loadProgress(broken), { lessons: {} });
  assert.equal(saveProgress(p, broken), false);
}

console.table(table.map(({ reason, ...row }) => row));
if (failures) { console.error(`${failures} academy check(s) failed`); process.exit(1); }
console.log(`Academy PASS: L01-L09 x 4 modes cleared by the student, L10 decisive in every mode and won on >= 4/12 openings; wrong students fail with causal feedback`);

}
