// Academy progress in localStorage only (no accounts, no backend). Private
// browsing or a blocked store simply means progress is not kept.
const KEY = 'ace2ace.academy.v1';
const RANK = { S: 4, A: 3, B: 2, C: 1, D: 0 };

export function loadProgress(store = globalThis.localStorage) {
  try {
    const p = JSON.parse(store?.getItem(KEY) || '{}');
    return p && typeof p.lessons === 'object' ? p : { lessons: {} };
  } catch { return { lessons: {} }; }
}

/** Record one attempt; keeps the best grade and which flight/control modes cleared it. */
export function recordAttempt(progress, lessonId, { success, grade, time, mode }) {
  const p = progress.lessons[lessonId] ||= { attempts: 0, cleared: false, best: null, bestTime: null, modes: [] };
  p.attempts += 1;
  if (success) {
    p.cleared = true;
    if (!p.best || RANK[grade] > RANK[p.best]) p.best = grade;
    if (p.bestTime == null || time < p.bestTime) p.bestTime = Math.round(time);
    if (mode && !p.modes.includes(mode)) p.modes.push(mode);
  }
  p.last = success ? 'clear' : 'fail';
  return progress;
}

export function saveProgress(progress, store = globalThis.localStorage) {
  try { store?.setItem(KEY, JSON.stringify(progress)); return true; } catch { return false; }
}

export const PROGRESS_KEY = KEY;
