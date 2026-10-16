#!/usr/bin/env node
// Headless AI-vs-AI batch runner. Uses the exact same sim + AI code as the browser game.
//
//   node tools/aivai.mjs                      # default suite
//   node tools/aivai.mjs --n 100 --blue ace --red veteran --spawn random
//   node tools/aivai.mjs --suite              # all scenarios, writes tools/out/aivai-report.json
//   node tools/aivai.mjs --suite --n 100 --write docs/aivai-report.json   # the committed report
//
// Flags: --n matches, --seed base seed, --blue/--red skill (rookie|veteran|ace|chaser|straight|circle),
//        --spawn default|random, --swap (J-16 on blue side), --verbose (print transitions of match 1)
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Match, defaultSpawn, randomSpawn, RULES } from '../src/sim/world.js';
import { makeRng, dist, DEG } from '../src/sim/math.js';
import { missilePk, gunLead, gunError } from '../src/sim/fire.js';
import { PilotAI, PLAYER_DAMAGE_SCALE } from '../src/ai/pilot.js';
import { StraightBot, CircleBot, ChaserBot, HumanProxy } from '../src/ai/bots.js';
import { PlayerController } from '../src/game/input.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const args = Object.fromEntries(process.argv.slice(2).map((a, i, arr) => a.startsWith('--')
  ? [a.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true] : null).filter(Boolean));

function makeCtrl(kind, ac, seed) {
  if (kind === 'straight') return new StraightBot(ac);
  if (kind === 'circle') return new CircleBot(ac);
  if (kind === 'chaser') return new ChaserBot(ac, { seed });
  if (kind === 'chaser-perfect') return new ChaserBot(ac, { perfect: true, seed });
  if (kind === 'human') return new HumanProxy(ac, { level: 'average', seed, PlayerController });
  if (kind === 'human-good') return new HumanProxy(ac, { level: 'good', seed, PlayerController });
  return new PilotAI(ac, { skill: kind, seed });
}

export function runMatch({ seed, blue = 'veteran', red = 'veteran', spawn = 'default', swap = false, timeLimit }) {
  const rng = makeRng(seed * 7919 + 13);
  const sp = spawn === 'random' ? randomSpawn(rng) : defaultSpawn(rng);
  // a human-proxy "player" gets the player's difficulty damage rule, like in the game
  const humanBlue = String(blue).startsWith('human');
  const m = new Match({
    seed, timeLimit,
    blue: { type: swap ? 'J16' : 'F16V', name: 'BLUE', damageScale: humanBlue ? PLAYER_DAMAGE_SCALE[red] ?? 1 : 1 },
    red: { type: swap ? 'F16V' : 'J16', name: 'RED' }, spawn: sp,
  });
  const cb = makeCtrl(blue, m.blue, seed * 3 + 1);
  const cr = makeCtrl(red, m.red, seed * 3 + 2);
  m.setController(m.blue, cb); m.setController(m.red, cr);

  const st = {
    firstShot: null, launches: { blue: 0, red: 0 }, hits: { blue: 0, red: 0 },
    circling: 0, far: 0, oppBlue: 0, oppWindowsBlue: 0, oppRed: 0, oppWindowsRed: 0, maxQuiet: 0,
    lastEventT: 0, crashes: 0, missMsl: 0,
  };
  const turnHist = [];
  let inOppB = false, inOppR = false;
  m.on((ev) => {
    if (ev.type === 'missileLaunch' || (ev.type === 'gunFire' && ev.ac.stats.roundsFired % 15 === 1)) {
      const side = ev.ac.side;
      if (ev.type === 'missileLaunch') st.launches[side] += 1;
      if (!st.firstShot) st.firstShot = side;
      st.maxQuiet = Math.max(st.maxQuiet, ev.time - st.lastEventT);
      st.lastEventT = ev.time;
    }
    if (ev.type === 'missileHit') st.hits[ev.missile.owner.side] += 1;
    if (ev.type === 'missileMiss') st.missMsl += 1;
  });
  const dt = RULES.dt;
  let t = 0;
  const maxT = (timeLimit ?? RULES.timeLimit) + RULES.suddenDeath + 1;
  while (!m.result && t < maxT) {
    m.step(dt);
    t += dt;
    if (m.tick % 30 === 0) {
      const R = dist(m.blue.pos, m.red.pos);
      if (R > 5000) st.far += 0.5;
      turnHist.push({ t, turning: m.blue.nCur > 3 && m.red.nCur > 3 && R > 200 && R < 2500 });
      // circling = 20 s windows of mutual hard turning with no weapons fired
      const w = turnHist.filter((h) => h.t > t - 20);
      if (w.length >= 39 && w.every((h) => h.turning) && t - st.lastEventT > 20) st.circling += 0.5;
      // kill opportunities from each side's point of view (what a human could exploit)
      const oppB = opportunity(m.blue, m.red), oppR = opportunity(m.red, m.blue);
      if (oppB) { st.oppBlue += 0.5; if (!inOppB) st.oppWindowsBlue += 1; }
      if (oppR) { st.oppRed += 0.5; if (!inOppR) st.oppWindowsRed += 1; }
      inOppB = oppB; inOppR = oppR;
    }
  }
  st.maxQuiet = Math.max(st.maxQuiet, m.time - st.lastEventT);
  const res = m.result || { winner: null, reason: 'unfinished', time: m.time };
  const modes = (c) => c.timeInMode ? Object.fromEntries(Object.entries(c.timeInMode).map(([k, v]) => [k, +v.toFixed(1)])) : null;
  return {
    seed, winner: res.winner ? res.winner.side : null, reason: res.reason, time: +res.time.toFixed(1),
    hp: { blue: m.blue.hp, red: m.red.hp }, ...st,
    modesBlue: modes(cb), modesRed: modes(cr),
    stalemateBreaksBlue: cb.stale?.count || 0, stalemateBreaksRed: cr.stale?.count || 0,
    transitionsBlue: cb.transitions?.length || 0, transitionsRed: cr.transitions?.length || 0,
    gunHits: { blue: m.blue.stats.roundHits, red: m.red.stats.roundHits },
    flares: { blue: m.blue.stats.flaresUsed, red: m.red.stats.flaresUsed },
    _ctrl: { cb, cr },
  };
}

function opportunity(me, tg) {
  if (!me.alive || !tg.alive) return false;
  const R = dist(me.pos, tg.pos);
  if (me.lock.locked) {
    const ata = me.lock.ata;
    const f = { x: tg.vel.x / tg.speed, y: tg.vel.y / tg.speed, z: tg.vel.z / tg.speed };
    const los = { x: (tg.pos.x - me.pos.x) / R, y: (tg.pos.y - me.pos.y) / R, z: (tg.pos.z - me.pos.z) / R };
    const aspect = Math.acos(Math.max(-1, Math.min(1, f.x * los.x + f.y * los.y + f.z * los.z)));
    if (missilePk({ R, ata, aspect, mySpeed: me.speed, tgSpeed: tg.speed, tgG: tg.nCur }) > 0.45) return true;
  }
  if (R < 900) {
    const lead = gunLead(me, tg.pos, tg.vel);
    if (gunError(me, lead.point) < 4 * DEG) return true;
  }
  return false;
}

function summarize(label, rs) {
  const n = rs.length;
  const pct = (k) => (100 * k / n).toFixed(0) + '%';
  const avg = (f) => (rs.reduce((s, r) => s + f(r), 0) / n);
  const wins = { blue: rs.filter((r) => r.winner === 'blue').length, red: rs.filter((r) => r.winner === 'red').length };
  const draws = rs.filter((r) => !r.winner).length;
  const reasons = {};
  for (const r of rs) reasons[r.reason] = (reasons[r.reason] || 0) + 1;
  const firstShotWins = rs.filter((r) => r.firstShot && r.winner === r.firstShot).length;
  const firstShotN = rs.filter((r) => r.firstShot && r.winner).length;
  const times = rs.map((r) => r.time).sort((a, b) => a - b);
  const modeAvg = (key) => {
    const acc = {};
    for (const r of rs) if (r[key]) for (const [k, v] of Object.entries(r[key])) acc[k] = (acc[k] || 0) + v / r.time;
    return Object.fromEntries(Object.entries(acc).map(([k, v]) => [k, +(100 * v / n).toFixed(0)]));
  };
  const s = {
    label, n,
    winBlue: pct(wins.blue), winRed: pct(wins.red), draws: pct(draws), reasons,
    medianTime: times[Math.floor(n / 2)], p10Time: times[Math.floor(n * 0.1)], p90Time: times[Math.floor(n * 0.9)],
    firstShooterWins: firstShotN ? pct(firstShotWins * n / firstShotN) : 'n/a',
    avgMissiles: { blue: +avg((r) => r.launches.blue).toFixed(1), red: +avg((r) => r.launches.red).toFixed(1) },
    missileHitRate: {
      blue: (100 * rs.reduce((s, r) => s + r.hits.blue, 0) / Math.max(1, rs.reduce((s, r) => s + r.launches.blue, 0))).toFixed(0) + '%',
      red: (100 * rs.reduce((s, r) => s + r.hits.red, 0) / Math.max(1, rs.reduce((s, r) => s + r.launches.red, 0))).toFixed(0) + '%',
    },
    circlingSecPerMatch: +avg((r) => r.circling).toFixed(1),
    matchesWithCircling20s: rs.filter((r) => r.circling > 0).length,
    farSecPerMatch: +avg((r) => r.far).toFixed(1),
    maxQuietSec: Math.max(...rs.map((r) => r.maxQuiet)).toFixed(0), avgMaxQuietSec: avg((r) => r.maxQuiet).toFixed(0),
    oppWindowsPerMinBlue: +(avg((r) => r.oppWindowsBlue / (r.time / 60))).toFixed(2),
    oppWindowsPerMinRed: +(avg((r) => r.oppWindowsRed / (r.time / 60))).toFixed(2),
    stalemateBreaks: +avg((r) => r.stalemateBreaksBlue + r.stalemateBreaksRed).toFixed(2),
    flaresPerMatch: +avg((r) => r.flares.blue + r.flares.red).toFixed(1),
    modeShareBlue: modeAvg('modesBlue'), modeShareRed: modeAvg('modesRed'),
  };
  return s;
}

function printSummary(s) {
  console.log(`\n== ${s.label}  (n=${s.n})`);
  console.log(`  wins  blue ${s.winBlue} | red ${s.winRed} | draw ${s.draws}   reasons ${JSON.stringify(s.reasons)}`);
  console.log(`  time  median ${s.medianTime}s  p10 ${s.p10Time}s  p90 ${s.p90Time}s   first shooter wins ${s.firstShooterWins}`);
  console.log(`  msl   per match blue ${s.avgMissiles.blue} red ${s.avgMissiles.red}   hit rate blue ${s.missileHitRate.blue} red ${s.missileHitRate.red}   flares/match ${s.flaresPerMatch}`);
  console.log(`  flow  circling ${s.circlingSecPerMatch}s/match (${s.matchesWithCircling20s} matches)  >5km ${s.farSecPerMatch}s/match  longest quiet ${s.maxQuietSec}s (avg ${s.avgMaxQuietSec}s)`);
  console.log(`  opp   kill windows/min blue ${s.oppWindowsPerMinBlue} red ${s.oppWindowsPerMinRed}   stalemate breaks/match ${s.stalemateBreaks}`);
  if (Object.keys(s.modeShareBlue).length) console.log(`  modes blue ${JSON.stringify(s.modeShareBlue)}`);
  if (Object.keys(s.modeShareRed).length) console.log(`  modes red  ${JSON.stringify(s.modeShareRed)}`);
}

export function runBatch(cfg) {
  const n = cfg.n ?? 50;
  const rs = [];
  for (let i = 0; i < n; i++) {
    const r = runMatch({ ...cfg, seed: (cfg.seed ?? 1) + i });
    delete r._ctrl;
    rs.push(r);
  }
  return rs;
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const t0 = Date.now();
  const n = +(args.n || 40);
  const suites = args.suite ? [
    { label: 'veteran F-16V vs veteran J-16 (arcade head-on start)', blue: 'veteran', red: 'veteran', spawn: 'default' },
    { label: 'veteran vs veteran (random geometry)', blue: 'veteran', red: 'veteran', spawn: 'random' },
    { label: 'veteran vs veteran, aircraft swapped (J-16 blue)', blue: 'veteran', red: 'veteran', spawn: 'random', swap: true },
    { label: 'ace vs rookie (skill gradient)', blue: 'ace', red: 'rookie', spawn: 'default' },
    { label: 'naive chaser F-16V vs veteran J-16 (proxy: aggressive new player)', blue: 'chaser', red: 'veteran', spawn: 'default' },
    { label: 'perfect zero-latency chaser vs veteran J-16 (superhuman stress test)', blue: 'chaser-perfect', red: 'veteran', spawn: 'default' },
    { label: 'human proxy (average) vs ROOKIE J-16 — via real player input path', blue: 'human', red: 'rookie', spawn: 'default' },
    { label: 'human proxy (average) vs VETERAN J-16', blue: 'human', red: 'veteran', spawn: 'default' },
    { label: 'human proxy (average) vs ACE J-16', blue: 'human', red: 'ace', spawn: 'default' },
    { label: 'human proxy (good) vs VETERAN J-16', blue: 'human-good', red: 'veteran', spawn: 'default' },
    { label: 'human proxy (good) vs ACE J-16', blue: 'human-good', red: 'ace', spawn: 'default' },
    { label: 'straight drone vs veteran J-16 (sanity: must kill quickly)', blue: 'straight', red: 'veteran', spawn: 'random' },
    { label: 'max-G circler vs veteran J-16 (sanity: must break the circle)', blue: 'circle', red: 'veteran', spawn: 'random' },
  ] : [{ label: `${args.blue || 'veteran'} vs ${args.red || 'veteran'} (${args.spawn || 'default'})`, blue: args.blue || 'veteran', red: args.red || 'veteran', spawn: args.spawn || 'default', swap: !!args.swap }];
  const report = [];
  for (const s of suites) {
    const rs = runBatch({ ...s, n, seed: +(args.seed || 1) });
    const sum = summarize(s.label, rs);
    printSummary(sum);
    report.push({ ...sum, matches: rs.map(({ modesBlue, modesRed, ...r }) => r) });
  }
  if (args.verbose) {
    const r = runMatch({ seed: +(args.seed || 1), blue: args.blue || 'veteran', red: args.red || 'veteran', spawn: args.spawn || 'default' });
    console.log(`\nmatch seed ${r.seed}: winner ${r.winner} by ${r.reason} at ${r.time}s`);
    for (const [name, c] of [['BLUE', r._ctrl.cb], ['RED', r._ctrl.cr]]) {
      if (!c.transitions) continue;
      console.log(`  ${name} transitions:`);
      for (const tr of c.transitions.slice(0, 60)) console.log(`   ${tr.t.toFixed(1).padStart(6)}s ${tr.from.padEnd(7)} -> ${tr.to.padEnd(7)} ${tr.why}`);
      console.log(`  ${name} radio: ${c.radio.slice(0, 12).map((x) => x.text).join(' / ')}`);
    }
  }
  if (args.suite) {
    const outPath = args.write ? join(HERE, '..', args.write) : join(HERE, 'out', 'aivai-report.json');
    mkdirSync(dirname(outPath), { recursive: true });
    // committed report keeps the summaries only (per-match rows stay in tools/out)
    const slim = args.write ? report.map(({ matches, ...sum }) => sum) : report;
    writeFileSync(outPath, JSON.stringify(slim, null, 1));
    console.log(`\nwrote ${outPath}`);
  }
  console.log(`\n(${((Date.now() - t0) / 1000).toFixed(1)}s)`);
}
