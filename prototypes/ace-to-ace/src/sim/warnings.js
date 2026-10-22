// Cockpit warnings shared by the HUD and the HUD-only human proxy, so the proxy
// reacts to exactly what a player is shown. Reads the shared flight model only.
import { clamp, G } from './math.js';
import { availableG, MIN_SPEED } from './aircraft.js';

/** Altitude (m) needed to pull out of the current descent with the G available
 *  now, plus ~1 s of reaction. 0 when climbing or level. */
export function pullUpAltitude(ac) {
  const v = Math.max(ac.speed, MIN_SPEED);
  const sink = -ac.vel.y;
  if (sink <= 0) return 0;
  const dive = Math.asin(clamp(sink / v, 0, 1));
  const n = Math.max(1.5, availableG(ac));
  const radius = (v * v) / (G * (n - 1));
  return radius * (1 - Math.cos(dive)) + sink * 1.0;
}

/** HUD "PULL UP": very low, or descending with less room than the pull-out needs. */
export const pullUpWarning = (ac) => ac.pos.y < 250
  || (-ac.vel.y > 15 && ac.pos.y < Math.max(600, 1.25 * pullUpAltitude(ac) + 150));
