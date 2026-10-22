// Build one Academy lesson on top of a normal Match. Shared by the browser game
// and the headless tests so both run exactly the same setup.
import { Match } from '../sim/world.js';
import { PlayerController } from '../game/input.js';
import { LessonRunner } from './runner.js';

export const ACADEMY_SEED = 52031;

/**
 * @param {object} lesson   definition from lessons.js
 * @param {object} o        { flight, control, input, settings, seed }
 * @returns {{ match, runner, player }}
 */
export function createLessonSession(lesson, { flight, control, input, settings = {}, seed = ACADEMY_SEED }) {
  const match = new Match({
    seed, flightFeel: flight,
    blue: { type: 'F16V', name: 'F-16V', damageScale: lesson.rules?.playerDamage ?? 1 },
    red: { type: 'J16', name: lesson.foeName || 'J-16' },
  });
  const player = new PlayerController(match.blue, input, { ...settings, assist: control === 'assisted' });
  const runner = new LessonRunner(lesson, match, { flight, control });
  // Lesson rules filter the player's commands (e.g. "engine at idle"); the
  // aircraft itself is the unmodified shared flight model.
  match.setController(match.blue, { player, update: (dt, m) => runner.filter(player.update(dt, m)) });
  return { match, runner, player };
}
