#!/usr/bin/env node
// Fixed-step flight-control regression: tests player input -> shared F-16 flight model.
// The physical flight model is intentionally unchanged by this UI/control pass.
import assert from 'node:assert/strict';
import { DEG } from '../src/sim/math.js';
import { createAircraft, stepAircraft, bankAngle, headingOf } from '../src/sim/aircraft.js';
import { PlayerController } from '../src/game/input.js';

function fixture(assist, startSpeed = 230) {
  const ac = createAircraft('F16V', 'blue', { x: 0, y: 3000, z: 0 },
    { x: 0, y: 0, z: -1 }, startSpeed);
  const stick = { x: 0, y: 0, acro: false };
  const input = {
    axes: () => ({ x: stick.x, y: stick.y, yaw: 0 }),
    acro: () => stick.acro, boost: () => true, brake: () => false,
    gun: () => false, consume: () => false,
  };
  const pilot = new PlayerController(ac, input, { assist, invert: false });
  let turned = 0, previous = headingOf(ac);
  function step(frames = 1) {
    for (let k = 0; k < frames; k++) {
      Object.assign(ac.controls, pilot.update());
      stepAircraft(ac, 1 / 60);
      const h = headingOf(ac);
      turned += Math.atan2(Math.sin(h - previous), Math.cos(h - previous));
      previous = h;
    }
  }
  return { ac, stick, pilot, step, get turnDeg() { return turned / DEG; } };
}

// Manual stick deflection is a held BANK ANGLE, not a sustained 240-degree/s spin.
{
  const m = fixture(false);
  m.stick.x = 1;
  m.step(180);
  assert.ok(Math.abs(bankAngle(m.ac) / DEG - 85) < 3, 'holds 85-degree right bank');
  assert.ok(Math.abs(m.ac.rollRateCur) < 0.15, 'roll rate decays after reaching target');
  // Touch-up does not clear axes: unchanged stick must preserve bank.
  m.step(120);
  assert.ok(Math.abs(bankAngle(m.ac) / DEG - 85) < 3, 'stays banked while stick is held');
  m.stick.x = 0; // player deliberately moves virtual stick to neutral
  m.step(90);
  assert.ok(Math.abs(bankAngle(m.ac) / DEG) < 3, 'intentional neutral levels wings');
}

// To perform a real tight turn, bank AND pull: obey physical G/energy limitations.
{
  const m = fixture(false);
  m.stick.x = 1;
  m.stick.y = -0.95; // default flight convention: pull back
  m.step(540);
  assert.ok(m.turnDeg > 175, 'manual high-G bank-and-pull turns >175 degrees in 9 s');
  assert.ok(m.ac.speed < 195, 'high-G pull dissipates energy');
  assert.ok(m.ac.gLoad <= m.ac.type.maxG + 0.01, 'unchanged F-16 G limit applies');
}

// ASSIST must be responsive without a new nonphysical turning boost.
{
  const m = fixture(true);
  m.stick.x = 1;
  m.step(540);
  assert.ok(m.turnDeg > 175, 'assist hard turn turns >175 degrees in 9 s');
  assert.ok(m.ac.gLoad <= m.ac.type.maxG + 0.01, 'assist still obeys aircraft G limit');
  assert.ok(m.ac.speed < 190, 'assist still trades energy for high-G');
}

// ACRO is explicit: while held, raw roll is available; after release capture bank
// until the next deliberate X input (no sudden snap to old joystick bank).
{
  const m = fixture(false);
  m.stick.x = 1; m.stick.acro = true;
  let spin = 0;
  for (let i = 0; i < 120; i++) {
    m.step();
    spin += m.ac.rollRateCur / 60;
  }
  assert.ok(spin > 6, 'ACRO performs an actual continuous full roll');
  m.stick.acro = false;
  m.step(100);
  const held = bankAngle(m.ac);
  assert.ok(Math.abs(m.ac.rollRateCur) < 0.15, 'ACRO release settles into angle hold');
  m.step(60);
  const after = bankAngle(m.ac);
  assert.ok(Math.abs(Math.atan2(Math.sin(after - held), Math.cos(after - held))) < 3 * DEG,
    'ACRO release does not resume previous 85-degree command');
  m.stick.x = 0;
  m.step(100);
  assert.ok(Math.abs(bankAngle(m.ac) / DEG) < 3, 'acro hold exits on a new stick command');
}

// Steep ASSIST pitch must not turn persistent touch input into infinite aileron roll.
{
  const ac = createAircraft('F16V', 'blue', { x: 0, y: 4500, z: 0 },
    { x: 0, y: 0.97, z: -0.243 }, 230);
  const input = { axes: () => ({ x: 1, y: 0, yaw: 0 }), acro: () => false,
    boost: () => true, brake: () => false, gun: () => false, consume: () => false };
  const pilot = new PlayerController(ac, input, { assist: true, invert: false });
  const cmd = pilot.update();
  assert.ok(Math.abs(cmd.roll) < 0.15, 'steep assist never maps held X to raw spin');
}

console.log('Controls PASS: manual bank hold, neutral, high-G energy, assist steep climb, ACRO roll/release');
