# Mobile Flight Controls v2 — validation notes

Baseline: draft PR #63, `feat/ace-mobile-yaw-controls`, remote HEAD
`dbfbd5deeb1277bcba62de6fd9b8dce68c169afb`. Both baseline CI jobs passed
([run](https://github.com/eddy121384-ui/air-combat-world/actions/runs/39921154163)).
The 16 existing Node commands also passed locally before changes.

## LEVEL

- Tap the 42 CSS px LVL button (or L) to request recovery; tap again or make
  a roll/pitch input above 0.12 to cancel. Pause, blur, hidden page, menus,
  new sorties and results cancel it too.
- `LevelAssist` supplies bounded roll/pitch commands through PlayerController.
  Roll error/rate and nose/flight-path feedback approach level gradually.
  It never writes aircraft pose, velocity, position, power or weapon state.
  Recovery uses at most 3 G and releases after 0.45 s within bank 3°,
  flight-path angle 1.5°, pitch 2° and roll rate 0.08 rad/s.
- Low speed (<110 m/s), low altitude (<500 m in this game's flat ground model)
  or limited available G produces a warning. Recovery times out at 20 s.
  This is an explicitly requested aid, not terrain avoidance or stall rescue.
  Expert neutral controls and the existing Assisted controller are unchanged.
- L06 introduces the limitation without changing its assessment.

Validation: `node tools/test-level-assist.mjs` covers 20 recoveries across all
four modes, including climbs, dives and near-inverted entries. It checks
bounded inputs, untouched aircraft state/power, damping, completion and manual
handover. All 17 Node regression commands passed (including all academy
lessons and the 52 wrong-student cases); established L10 outcomes are retained.
`browser-check.mjs --scenario level` exercises real CDP touch at 812×375 and
667×375 in all four modes, including 34 px side/21 px bottom safe areas,
60° bank entry, recovery, repeat-tap cancellation, manual override and pause.
Zero browser errors. Existing browser scenarios remain in CI.

![Actual Chromium 667×375 safe-area preview](screens/mobile-controls-v2/level-667-safe.png)

Chromium touch emulation is not iPhone Safari acceptance. Real-device checks
remain: safe-area placement, multi-finger LVL handover and interrupted touches.
