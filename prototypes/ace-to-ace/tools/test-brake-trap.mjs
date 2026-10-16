#!/usr/bin/env node
// Geometry-driven brake trap tests. Uses production AI, not duplicated manoeuvre logic.
import assert from 'node:assert/strict';
import { PilotAI } from '../src/ai/pilot.js';
import { createAircraft } from '../src/sim/aircraft.js';

const fwd = { x: 0, y: 0, z: -1 };
function fixture(skill = 'ace') {
  const ac = createAircraft('J16', 'red', { x: 0, y: 2500, z: 0 }, fwd, 185);
  const seen = [];
  const ai = new PilotAI(ac, { skill, seed: 34, onTactic: (event) => seen.push(event) });
  ai.mode = 'DEFEND'; ai.t = 10;
  const S = {
    f: fwd, r: { x: 0, y: 0, z: 350 }, R: 350, ata: Math.PI,
    tgtAta: 0, vc: 85, corner: 175, dE: 0, threats: [],
    tg: { pos: { x: 0, y: 2500, z: 350 }, vel: { x: 0, y: 0, z: -280 }, speed: 280 },
  };
  return { ai, ac, S, seen };
}

// Geometry and skill allow a trap; it does not magically declare success.
{
  const { ai, S, seen } = fixture();
  ai.doDefend(S, 1 / 60);
  assert.equal(ai.brakeAttempts, 1);
  assert.equal(ai.brakeTrapCommand(S, null).brake, true);
  assert.equal(ai.brakeSuccesses, 0);
  assert.equal(ai.radio.length, 0);
  assert.equal(seen.filter((e) => e.type === 'brakeStart').length, 1);

  // Moving the defender's own nose does not count; only crossing its original plane.
  S.f = { x: 0, y: 0, z: 1 };
  assert.equal(ai.brakeTrapCommand(S, null).brake, true);
  assert.equal(ai.brakeSuccesses, 0);
  S.f = fwd;

  // The pursuer *actually* passes the original nose plane.
  ai.t += 0.7;
  S.r = { x: 0, y: 0, z: -120 }; S.R = 120;
  S.tg.pos.z = -120;
  const reverse = ai.brakeTrapCommand(S, null);
  assert.equal(reverse.brake, undefined);
  assert.match(reverse.name, /reverse pursuit/);
  assert.equal(ai.brakeSuccesses, 1);
  assert.equal(seen.filter((e) => e.type === 'overshoot').length, 1);
  assert.equal(ai.radio.length, 1);
  ai.brakeTrapCommand(S, null);
  assert.equal(ai.brakeSuccesses, 1, 'no duplicate reversal event');
}

// Bad bait times out without a false triumph, and cannot instantly retry.
{
  const { ai, S, seen } = fixture();
  ai.doDefend(S, 1 / 60);
  ai.t += 1.9;
  assert.equal(ai.brakeTrapCommand(S, null), null);
  assert.equal(ai.brakeSuccesses, 0);
  assert.equal(seen.filter((e) => e.type === 'overshoot').length, 0);
  ai.doDefend(S, 1 / 60);
  assert.equal(ai.brakeAttempts, 1);
}

// Gates: closing geometry, skill and missile survival take precedence.
{
  const { ai, S } = fixture();
  S.vc = 5; ai.doDefend(S, 1 / 60);
  assert.equal(ai.brakeAttempts, 0, 'do not brake against a nonclosing target');
}
{
  const { ai, S } = fixture();
  S.threats.push({ ttg: 1 }); ai.doDefend(S, 1 / 60);
  assert.equal(ai.brakeAttempts, 0, 'do not bait while a missile threatens');
}
{
  const { ai, S } = fixture('rookie');
  ai.skill.tactics = 0; ai.doDefend(S, 1 / 60);
  assert.equal(ai.brakeAttempts, 0, 'rookie lacks advanced tactics');
}
{
  const { ai, S } = fixture();
  ai.doDefend(S, 1 / 60);
  S.threats.push({ ttg: 1 });
  assert.equal(ai.brakeTrapCommand(S, null), null);
  assert.equal(ai.brakeSuccesses, 0, 'cancel ongoing trick for missile defense');
}

console.log('Brake trap: conditions, confirmation, false positives, timeout, cooldown, safety PASS');
