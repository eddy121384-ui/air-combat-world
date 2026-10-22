# Ace to Ace — Flight Feel & Gameplay Polish (2026-10-22)

Continues Draft PR #53 (`feat/ace-dual-flight-modes`). Two shared flight-physics
profiles (Arcade, Tactical) × two independent control interpretations (Assisted,
Expert) are kept; this pass makes each of the four combinations clearer, more
responsive and more worth playing. No new buttons; the iPhone touch layout,
independent throttle / AB / BRK, HUD, weapons and AI architecture are unchanged.
Legacy `feel=A` is byte-for-byte untouched; `feel=B` keeps following Tactical.

The design question for every change was: *does the player feel that they — not
the code — are flying the jet, and does each mode reward a different skill?*

## Method

1. **Measure the original first.** `tools/probe-flight-feel.mjs` drives the real
   `PlayerController` with a scripted stick and the shared `stepAircraft()` at
   60 Hz: roll capture / overshoot / tap granularity, pitch and G onset, level
   turns at full / MIL / moderate pull, low-speed authority, AB/MIL acceleration,
   top speeds, Assisted entry / light-stick / roll-out, and a PI "thumb" tracking a
   12°/s and 20°/s target with 0.15 s reaction delay. The baseline was run with the
   same probe on the pre-polish commit `0374cc6` (`docs/flight-feel-polish-baseline.json`);
   the result is `docs/flight-feel-polish-after.json`.
2. **Energy–maneuverability sweep** of both profiles (sustained vs instantaneous
   turn rate and specific excess power over speed) to see the structure behind
   the numbers, rather than tuning one probe value at a time.
3. **Full 1v1 batches** through the real player input path: the human proxy
   (`HumanProxy`, HUD-only cues, reaction delay, thumb drift) now flies either
   Assisted or Expert (`aivai.mjs --control`), against Rookie / Veteran / Ace, in both
   physics — and the *same proxy* was run on the original code for comparison.
4. **Real Chromium** (SwiftShader WebGL): settings menu, pause, four modes on the
   iPhone-sized touch layout with real CDP touches, one complete match per physics,
   and a side-by-side camera screenshot review.

## What was wrong (found by measuring, not by guessing)

| Finding | Evidence | Effect on play |
|---|---|---|
| Arcade top speed was the `MAX_SPEED` clamp (430 m/s), not drag | AB + any manoeuvre kept accelerating | A latched AB parks the jet where it turns worst (13.7°/s) and needs ~1.8 km to pull out of a dive |
| Arcade turned fastest at the 45 m/s clamp (~47°/s) | 0.25·maxG lift floor ⇒ n/v grows as v falls | Braking to a crawl beat every tactic; the HUD said STALL while physics rewarded it |
| Tactical MIL could sustain only ~3.4G and never reach 250 m/s from 150 | E-M sweep; probe `mil150to250s: null` | "Heavy", not "energy fight": once slow you could only dive |
| Expert roll ran on ~8° past the release point | probe roll overshoot 7.9° / 8.3° | Imprecise roll stop, extra corrections |
| Assisted mapped stick to G | 15 % stick ⇒ 63° bank for a ~4°/s turn | Small corrections threw the wings around |
| AI held 30 % rudder in hard turns | max-G circle bot sank 1.5 km and crashed 30/30 (Arcade) | Rudder in a steep bank yaws the nose seaward; wasted energy |
| `aivai --feel arcade/tactical` ran legacy A | `args.feel === 'B' ? 'B' : 'A'` | CI "Arcade/Tactical" AI smoke tests were silently testing A |
| `MIN_SPEED` clamp held a vertical climb up indefinitely | skilled proxy: 29/100 Arcade losses "out of bounds" at 10.4 km, 45 m/s | Free energy; the jet could hang and drift through the ceiling |
| Pause moved the camera to the title orbit | camera at (592, 2600, 99) while paused | On resume the camera swooped in from ~4 km; jet briefly off screen |
| Chase camera locked to the nose | 10G pull: jet glued to screen centre | Pulling felt like the world turning, not the pilot pulling |

## Changes

### Shared physics (player and AI alike)
- **Transonic drag rise** above 300 m/s (`WAVE_DRAG_SPEED`): top speed is set by drag.
  Arcade AB 430 → 364 m/s, Tactical AB 358 → 361, Tactical MIL 256 → 285.
- **Arcade lift curve** `(v / 0.9·v_corner)^1.3`, no floor: the turn-rate peak is at
  corner speed (35°/s over 127–181 m/s). Slowing down still shrinks the *radius*
  (AC-style brake turn) but no longer adds turn *rate*. Still ≥ 2× Tactical's G at 85 m/s.
- **Arcade induced drag** 0.35 → 0.42: full-G MIL turns now bleed (−6…−10 m/s²) into
  the tight-turn band; AB turns stay near energy-neutral. *AB = fast and wide, MIL /
  BRK = slow and tight* — the AC vocabulary, made physical.
- **Tactical** engine 1.05, parasite 0.72, induced 0.82: the corner-speed peak
  (27°/s at 9G) is unchanged; AB sustained turn ~20°/s at 6.5–7G; MIL sustains
  ~4.2G and can accelerate; a 9G corner pull with AB still bleeds ~8 m/s². Moderate
  pulls are near-sustainable, full pulls buy nose authority with energy.
- **Roll stop** factor Arcade 0.38 → 0.20, Tactical 0.42 → 0.28 (onset unchanged).
- **Stall at the speed floor** (Arcade < 62 m/s, Tactical < 75 m/s): the auto-trim
  fades out and the nose falls; the `MIN_SPEED` clamp no longer holds a vertical climb
  up for free.

### Controls
- **Assisted**: stick deflection ∝ turn *rate* (full stick unchanged, still ≤ 85 % of
  available G before pull); fine-aim rudder fades out smoothly instead of switching
  off at |x| = 0.3. Never touches throttle or AB; cannot exceed available G.
- **Expert**: unchanged mapping (x = roll rate, y = pitch, no auto-level); benefits
  from the crisper roll stop and the camera.

### AI
- Rudder only for fine tracking (`(1 − fine)` instead of `(1 − 0.7·fine)`).
  Same skill tables, same physics as the player.

### Camera and HUD (presentation only)
- Chase camera trails the jet's attitude: 0.15 s direction lag, 0.2 s roll lag (the
  previous up-vector smoothing), +5 m pull-back at high G. In a 25°/s turn the nose
  (W) leads the view by ~4°. Straight-and-level framing is unchanged; aiming
  symbology is still projected from the real nose / velocity / lead point.
- **Edge-of-envelope buffet**: a small camera shake only when pulling ≥ 82 % of the
  lift available *and* > 3G — you feel the limit; a mild pull is silent.
- **Speed-trend bar** left of the speed box (amber when bleeding > 4 m/s²) and a
  **green diamond** when the current speed offers ≥ 92 % of the best instantaneous
  turn rate. Both read the shared model; neither changes what the jet can do.
- **PULL UP** is energy-aware (`sim/warnings.js`): pull-out radius at the G available
  now plus 1 s of reaction, instead of a fixed 600 m.
- Settings cards explain the core skill of each mode in one line.

## Before / after (F-16V, deterministic probe, `docs/flight-feel-polish-*.json`)

| Measurement | Arcade × Assisted | Arcade × Expert | Tactical × Assisted | Tactical × Expert |
|---|---|---|---|---|
| Roll-stop overshoot after release | 7.9° → **3.5°** | 7.9° → **3.5°** | 8.3° → **5.1°** | 8.3° → **5.1°** |
| Roll to 90° (full stick) | 0.38 s | 0.38 s | 0.42 s | 0.42 s |
| Nose travel 0.5 s full pull @230 | 10.8° | 10.8° | 8.9° | 8.9° |
| AB top speed / MIL top speed (m/s) | 430 → **364** / 310 | same | 358 → 361 / 256 → **285** | same |
| MIL 150 → 250 m/s | 23.7 s | 23.7 s | impossible → **31.6 s** | same |
| AB 150 → 250 m/s | 9.0 s | 9.0 s | 11.9 → **10.3 s** | same |
| Full turn + AB: sustained rate / end speed | 18.5 → 19.3°/s / 278 → 266 | 22.2 → **23.6°/s** / 265 → 247 | 20.9 → 20.8°/s / 161 → 207 | 21.4 → **24.8°/s** / 145 → 166 |
| Full turn MIL: sustained rate / end speed | 25.6 → **28.1** / 195 → 175 | 33.0 → **34.1** / 170 → 143 | 16.9 → **18.9** / 130 → 145 | 17.4 → **19.6** / 119 → 132 |
| Moderate turn (55 %, 85 % thr): end speed | 231 → 230 | 229 → 223 | 180 → **210** | 171 → **196** |
| Sustained rate at 110 m/s | 30.6 → 27.5°/s | 34.1 → 30.6°/s | 14.9 → 15.3°/s | 16.6 → 17.0°/s |
| Track 12°/s target: mean nose error | 1.70° → 1.69° | 2.54° → 2.51° | 1.53° → 1.59° | 2.54° → 2.77° |
| Track 20°/s target: mean nose error | 2.75° → 2.71° | 5.21° → 5.40° | 2.66° → 2.65° | 3.69° → **3.41°** |
| Assisted 15 % stick: peak bank | 63° → **54°** | — | 60° → **49°** | — |
| Assisted full stick: 90° heading | 4.13 → 4.08 s | — | 4.43 → 4.52 s | — |
| Assisted centred: wings level | 0.43 s | — | 0.45 s | — |

Reading the table: pitch response and roll rate were already good and are kept.
Tracking precision is essentially unchanged — the scripted thumb is the limit there,
and Expert is *meant* to be harder to track with than Assisted. The meaningful
changes are the roll stop, the speed structure (no clamp, a real corner in Arcade,
recoverable energy in Tactical) and a clear MIL-vs-AB / moderate-vs-full contrast.

## Full 1v1 batches (human proxy through the real input path)

n = 100 per cell, default head-on opening, same seeds, **same proxy code** on the
original commit and on this branch (`aivai.mjs --n 100 --blue human|human-good
--red <skill> --feel <physics> --control <assisted|expert>`). Proxy win rate,
original → polished. "Good" = faster reactions, steadier thumb and one energy habit
(burner off above 1.3× corner speed, back on near corner). The proxy is a model of a
player, not a player; ±10 points is noise at this n.

| Combination | Average proxy vs Rookie / Veteran / Ace | Good proxy vs Rookie / Veteran / Ace |
|---|---|---|
| Arcade × Assisted | 31 → **63** / 3 → **15** / 0 → 3 | 72 → 72 / 35 → 40 / 9 → **23** |
| Arcade × Expert | 22 → 20 / 1 → 2 / 0 → 0 | 88 → 95 / 67 → **81** / 22 → **42** |
| Tactical × Assisted | 80 → 82 / 53 → 31 / 29 → 8 | 73 → 57 / 50 → 36 / 29 → 21 |
| Tactical × Expert | 91 → 41 / 63 → 24 / 34 → 8 | 97 → 95 / 85 → 83 / 60 → 53 |

| AI sanity (n = 100 / 60) | Original | Polished |
|---|---|---|
| Veteran vs Veteran, Arcade / Tactical (blue win) | 58 % / 42 % | 54 % / 51 % |
| Ace vs Rookie, Arcade / Tactical | 93 % / 60 % | 95 % / **82 %** |
| Straight drone killed (both) | 100 % | 100 % |
| Max-G circle bot, Arcade: outcome | crashed itself 60/60 | AI wins 88 % (31 on time), 12 % draw |

How to read it:

- **Arcade × Assisted is now the newcomer mode the menu promises**: an average
  proxy beats Rookie 63 % (was 31 %). The original loss mode was the 430 m/s
  clamp trap and, for skilled players, hanging at the speed floor through the ceiling
  (29/100 out-of-bounds before the stall fix, 1/100 after).
- **Expert rewards the pilot more than before**: the good proxy gains most in both
  Expert columns (Arcade vs Ace 22 → 42 %). The average Expert proxy is a crude
  closed-loop thumb and stays weak — Expert is meant to have a skill floor.
- **Tactical punishes ignoring energy and rewards managing it.** The old Tactical drag
  dragged *everyone* into a slow knife fight (AI below 150 m/s 27 % of the time, 28 % of
  it defending), where an always-AB pursuit happened to work. Now the AI holds its
  speed near corner and the always-AB average proxy sits at ~258 m/s and loses; the gap
  between average and good proxy (one energy habit) grew from +32 to +59 points vs
  Veteran in Tactical × Expert. Veteran and Ace are harder in Tactical; Rookie remains
  beatable with Assisted (82 %).
- **Known open item:** in Arcade a bot that holds a max-G AB level turn forever is
  hard for the AI to finish (116 s of circling per match; it still wins 88 % on HP).
  Before, the same bot crashed itself because of the AI rudder bug, so this check was
  not actually testing the stalemate breaker. A tighter Arcade stalemate breaker is AI
  work outside this pass.

## Browser checks (Chromium + SwiftShader, not iPhone Safari)

- `browser-check.mjs --scenario settings` (desktop click and iPhone-sized tap): select,
  cancel, Enter-while-open, save, reload persistence, pause pitch-only change (same
  sortie continues, inverted stick pulls immediately), pause physics change (same
  seed restart, both jets switch), cancel from pause, camera stays on the jet during
  pause and resume, rematch keeps the preset.
- `--scenario modes`: all four combinations with real CDP touches on the floating
  stick — Expert keeps rolling on a latched stick and holds bank when centred;
  Assisted banks into a level turn, turns, and rolls out when centred; aft stick pulls
  G; AB toggles; throttle stays at the player's 72 %. One complete chaser 1v1 per
  physics to the result screen, Enter rematch keeps the physics for both jets.
- Full `browser-check.mjs` (lookdev, title, settings, modes, fight, manual, touch,
  AI-vs-AI, result): 0 console/page errors.

## Still needs a player on a real iPhone (Safari, landscape)

- Whether the 0.15 s camera lag and the buffet feel good at 60 fps, or are too much /
  too little (SwiftShader renders ~10–20 fps; screenshots cannot show motion feel).
- Expert roll on the latched touch stick: is re-centring precise enough, or does a
  slightly off-centre release leave an annoying slow roll? (Touch dead zone unchanged.)
- Assisted light-stick corrections for gun tracking with a real thumb.
- Legibility of the speed-trend bar and best-turn diamond at phone size, in sunlight.
- Whether Arcade × Assisted is now winnable and fun for a newcomer against Rookie /
  Veteran, and whether Tactical × Expert rewards energy discipline in practice.
- Safari specifics: multi-touch stick + throttle + BRK at once, audio unlock, pause on
  app switch, 120 Hz ProMotion frame pacing.
