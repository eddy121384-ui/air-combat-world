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

const args = process.argv.slice(2);
const only = args.includes('--only') ? args[args.indexOf('--only') + 1] : null;
const verbose = args.includes('--verbose');
const MODES = ['arcade:assisted', 'arcade:expert', 'tactical:assisted', 'tactical:expert'];

export function fly(lesson, mode, plan, { maxT = 600, seed } = {}) {
  const [flight, control] = mode.split(':');
  const input = makeStudentInput();
  const { match, runner } = createLessonSession(lesson, { flight, control, input, ...(seed != null ? { seed } : {}) });
  const dt = RULES.dt;
  while (!runner.result && runner.t < maxT) {
    plan(runner, input, control);
    match.step(dt);
    runner.step(dt);
  }
  return runner;
}

export const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
const table = [];
let failures = 0;
for (const lesson of LESSONS) {
  if (only && lesson.id !== only) continue;
  const plan = PLANS[lesson.id];
  assert.ok(plan, `${lesson.id}: student plan missing`);
  for (const mode of MODES) {
    const r = fly(lesson, mode, plan);
    const ok = r.result?.success === true;
    table.push({ lesson: lesson.id, mode, ok, grade: r.result?.grade ?? '-', t: +r.t.toFixed(1), reason: r.result?.reason ?? '' });
    if (!ok) failures++;
    if (verbose || !ok) console.log(`${lesson.id} ${mode}: ${ok ? 'CLEAR' : 'FAIL'} ${r.t.toFixed(1)}s ${r.result?.reason ?? ''}`
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
};
for (const [key, exp] of Object.entries(EXPECT)) {
  const [id] = key.split(':');
  if (only && id !== only) continue;
  for (const mode of exp.modes) {
    const r = fly(lessonById(id), mode, BAD[key], { maxT: 400 });
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
console.log(`Academy PASS: ${LESSONS.length} lesson(s) x 4 modes cleared by the student; wrong students fail with causal feedback`);

}
