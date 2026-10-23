#!/usr/bin/env node
// W = nose forward, FPM = the *actual* velocity/displacement vector.
// This runs against the same production flight physics used by the AI and player.
import assert from 'node:assert/strict';
import { angleBetween, forwardOf, len, norm, sub, scale, addScaled, dot } from '../src/sim/math.js';
import { createAircraft, stepAircraft, FLIGHT_PATH_LAG } from '../src/sim/aircraft.js';
const degrees = rad => rad * 180 / Math.PI;
const angle = ac => degrees(angleBetween(forwardOf(ac.q), ac.vel));
const approx = (a, b, tol, msg) => assert.ok(Math.abs(a - b) < tol, `${msg}: ${a} vs ${b}`);

function fighter() {
  return createAircraft('F16V', 'blue', { x: 0, y: 2500, z: 0 },
    { x: 0, y: 0, z: -1 }, 230);
}

// Straight: the markers truly coincide, no artificial fixed offset.
{
  const ac = fighter();
  for (let i = 0; i < 180; i++) stepAircraft(ac, 1 / 60);
  approx(angle(ac), 0, 1e-5, 'level cruise should have W/FPM overlap');
  assert.equal(ac.aoaVisual, 0, 'no fabricated angle of attack at level flight');
}

// Actual motion and velocity must agree each tick, including high G.
{
  const ac = fighter();
  ac.controls.pitch = 1; ac.controls.boost = true;
  let greatest = 0;
  for (let i = 0; i < 210; i++) {
    const before = { ...ac.pos };
    stepAircraft(ac, 1 / 60);
    greatest = Math.max(greatest, angle(ac));
    const displacement = sub(ac.pos, before);
    approx(len(sub(displacement, scale(ac.vel, 1 / 60))), 0, 1e-7,
      'FPM must point in direction of real aircraft displacement');
    approx(len(ac.vel), ac.speed, 1e-7, 'velocity keeps speed magnitude');
    assert.ok(Number.isFinite(ac.aoaVisual), 'stable finite AoA proxy');
  }
  assert.ok(greatest > 2 && greatest < 8,
    `high G must produce visible but plausible relative nose/track offset, got ${greatest} deg`);
  assert.ok(ac.speed < 230, 'high-G turning still dissipates energy');
  assert.ok(dot(forwardOf(ac.q), { x: 0, y: 1, z: 0 }) >
      dot(norm(ac.vel), { x: 0, y: 1, z: 0 }),
    'during pull-up W must appear above the flight-path marker');
  ac.controls.pitch = 0;
  for (let i = 0; i < 150; i++) stepAircraft(ac, 1 / 60);
  assert.ok(angle(ac) < 0.1, 'FPM converges back to W after the pull ends');
}

// Damped frame-rate-independent response: simulation is fixed-step but should
// not wildly disagree when tested at 120Hz.
function run(dt) {
  const ac = fighter();
  ac.controls.pitch = 0.8;
  for (let i = 0; i < Math.round(2 / dt); i++) stepAircraft(ac, dt);
  return { angle: angle(ac), pos: ac.pos, speed: ac.speed };
}
const a = run(1 / 60), b = run(1 / 120);
assert.ok(a.angle > 1 && b.angle > 1);
approx(a.angle, b.angle, 0.25, 'response stable from 60 to 120 Hz');
approx(a.speed, b.speed, 2, 'energy remains stable');
assert.ok(FLIGHT_PATH_LAG > 0 && FLIGHT_PATH_LAG < 0.25, 'short response avoids arcade drift');
console.log('Flight path PASS: W/FPM independent in high G; real displacement, recovery, frame rate, energy');
