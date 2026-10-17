// Display-only orientation readout for the arcade HUD.
// Independent of the chase camera: it stays useful with no visible sea/sky horizon.
import { forwardOf, upOf, rightOf, clamp } from '../sim/math.js';

const RAD2DEG = 180 / Math.PI;

export function attitudeOf(q) {
  const f = forwardOf(q), u = upOf(q), r = rightOf(q);
  const pitch = Math.asin(clamp(f.y, -1, 1)) * RAD2DEG;
  // Positive = right wing down, matching aircraft.bankAngle().
  const bank = Math.atan2(-r.y, u.y) * RAD2DEG;
  // Compass: 000 = North (-Z), 090 = East (+X).
  const heading = (Math.atan2(f.x, -f.z) * RAD2DEG + 360) % 360;
  return { pitch, bank, heading };
}
