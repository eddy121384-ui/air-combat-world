# Xinyi Greybox Cleanup Pass — Result

> Branch: `feat/ue58-greybox-spike` (from `feat/taipei-greybox-core`, **`main` untouched**).
> Milestone: gameplay-readable greybox for the first arcade flight prototype.
> Verdict: **READY FOR CORE FLIGHT PROTOTYPE** (human 1-min GUI visual check still pending).
> Nothing from the Core Flight Prototype was implemented.

## 1. Before editing (scene state documented first)

- Level `/Game/Taipei/L_TaipeiGreybox` (untouched by this pass, verified clean in worktree):
  `CityMassing_Xinyi` + `Hero_Taipei101` (origin, scale 1), Sun (DirectionalLight −45°),
  Sky (SkyLight), Fog (ExponentialHeightFog), Atmosphere (SkyAtmosphere),
  Start (PlayerStart, 900 m south of 101, 350 m alt).
- City geometry = **one merged mesh** (`layerA_city_massing`, 5819 buildings, 1 primitive,
  1 uniform-white material `massing_grey`) + separate hero placeholder → read as one
  undifferentiated white pile at flight speed. That was the problem to fix.
- Baseline screenshot retained: `docs/evidence/ue58-greybox-viewport.png` (unchanged).
- Automation: live MCP unavailable (editor closed, ports 8000/8090/8091 shut).
  Used the proven headless path only (`UnrealEditor-Cmd` + `adapters/unreal/*.py`,
  7 runs this round). No MCP infrastructure work. `unreal_native` / `unreal_bridge`
  left alone per scope.

## 2. Source truth (authoritative, untouched)

- `sample_buildings.geojson`, `worldmodel_sample.json`, `build_tile.py`, `export_glb.py`,
  `geo.py`, `worldmodel.py`: **zero changes** (compiler tests 12/12 still pass).
- Extruded set identical to v0: **5819 buildings** (low 3289 + mid 2250 + high 280),
  skip reasons byte-identical (`zero_area` 5296 / `building_fully_skipped` 5305 /
  `self_intersecting` 10). Grouping only re-buckets; no footprint/position/height edited.
- Taipei 101: placeholder form, anchor and **508 m height preserved exactly**.

## 3. What changed (presentation / derived layer only)

| # | Change | Files |
|---|--------|-------|
| 1 | Derived GLB `xinyi_tile_2km_greybox.glb` + report (gitignored, regenerable via script below): LayerA split into 3 deterministic height buckets, warm-tan ground plane 2600×2600 m @ y=−0.2 m, hero unchanged except accent color | `tools/compiler/build_greybox_tile.py` (new) |
| 2 | Offline proof maps (PIL only, no new deps): top-down readability schematic + height histogram, both honestly labeled OFFLINE/canonical-source | `tools/compiler/render_greybox_map.py` (new), `docs/evidence/greybox_topdown.png`, `docs/evidence/greybox_heights.png` |
| 3 | New additive level `/Game/Taipei/L_TaipeiGreybox_Clean`: 5 mesh actors + Sun/Sky/Fog/Atmosphere (neutral daylight, no renderer changes) + `Start_City` (v0 spot) + `Start_Flight` (east offset, 400 m alt) | `adapters/unreal/build_greybox_level.py` (new), `unreal/Content/Taipei/L_TaipeiGreybox_Clean.umap`, `unreal/Content/Taipei/XinyiGreybox/` (5 StaticMeshes + 5 MaterialInstanceConstants) |
| 4 | This doc | `docs/greybox-cleanup-result.md` |

Visual grouping (cheap, deterministic, mobile-safe — 5 opaque flat MICs, no textures,
no transparency, no Lumen/Nanite/VSM, draw calls 1 → 5):

| Bucket | Rule | Base color |
|--------|------|------------|
| low | h ≤ 20 m (3289 bldgs) | near-white (0.87, 0.88, 0.90) |
| mid | 20 < h ≤ 60 m (2250 bldgs) | mid grey (0.62, 0.63, 0.66) |
| high | h > 60 m (280 bldgs) | dark tower (0.30, 0.31, 0.34) |
| ground | 2600×2600 m plane | warm tan (0.55, 0.51, 0.44) — hue-separated from cool building greys |
| hero | 101 placeholder, 508 m | warm orange accent (0.85, 0.55, 0.20) |

Palette history (kept honest): v1 dark-ground hid high-rises; v2 light-grey ground hid
mid-rises; v3 warm-tan ground verified READABLE via schematic review. Colors live in the
builder (single source of truth), never hand-edited in the editor.

## 4. Geometry cleanup (narrow: obvious garbage only)

- **Removed/fixed: nothing.** Investigation showed there was nothing to remove:
  - Giant spikes: none (tallest non-101 = 269.05 m, matches real Xinyi high-rises).
  - Floating fragments: none (every extrusion starts at y = 0).
  - 315 candidate "small-area × tall" records all have area 0 → already filtered by the
    existing triangulate predicate (skip counts identical to v0).
  - 290 close tower pairs (< 30 m, h > 100 m) are legitimate Xinyi CBD complex clustering.
- **Intentionally preserved:** genuine irregular footprints, all height variation,
  multi-record complexes. Real cities are messy; uncertain objects were kept.
- Incidental: one headless run's editor autosave touched `L_TaipeiGreybox.umap`;
  restored via `git checkout` — original level is byte-clean in this commit's parent
  and untouched by this commit.

## 4b. GUI persistence failure — post-mortem (follow-up fix, same branch)

GUI validation of the first commit FAILED: fresh GUI open of `L_TaipeiGreybox_Clean`
showed only 8 actors (Ground/Hero/lights/starts) — the 3 `CityMassing_*` actors
were missing. Verdict was lowered to NOT READY pending this fix.

- **Root cause** (log-proven): `EditorLevelLibrary.new_level()` on an EXISTING map
  path only logs `LevelEditorSubsystem: Error: NewLevel. Failed to validate the
  destination. An asset already exists at this location` and does NOT raise a Python
  exception. v1 `build_greybox_level.py` therefore printed `GREYBOX_CREATED`, spawned
  12 actors into the auto-loaded STARTUP map (`L_TaipeiGreybox`), and
  `save_current_level()` persisted the WRONG map — while `L_TaipeiGreybox_Clean.umap`
  stayed at the previous 8-actor version (confirmed by binary string scan: zero
  `CityMassing_*` labels). Same-session spawn logs are NOT persistence proof.
- **Fix** (`build_greybox_level.py` v2): load-or-create via `does_asset_exist` +
  `load_level`; assert current world is `L_TaipeiGreybox_Clean` (abort otherwise);
  wipe-then-respawn for determinism; in-process 11-label gate before saving.
- **New gate** (`adapters/unreal/verify_greybox_reopen.py`): a SEPARATE fresh
  `UnrealEditor-Cmd` process loads the saved map and asserts all 11 required labels:
  `REOPEN_OK 11/11` (run 2026-09-14 21:52 UTC). Umap binary re-scan: 32,589 bytes,
  all 11 actor labels + 5 mesh refs present. No load errors for the 5 new assets
  in the reopen run (the single physics warning in that log concerns the OLD v0
  `layerA_city_massing` at startup, pre-existing and unrelated).
- Verdict restored to **READY FOR CORE FLIGHT PROTOTYPE** (GUI 1-min confirm still
  recommended on the new commit).

## 5. Validation (measured in UE 5.8, not inferred)

| Check | Result |
|-------|--------|
| Hero height | origin z 25,400 + extent z 25,400 → **max Z 50,800 cm = 508 m ✓ exactly** |
| Hero anchor | (−9077.6, −7792.4) cm = ENU (−90.78, +77.92) m ✓; base ±28.28 m ✓ |
| City span | X 209,794 cm = **2.10 km** ✓; Y 214,847 cm = **2.15 km** ✓ |
| Bucket ceilings | low 20.0 m / mid 59.65 m / high 269.05 m ✓ |
| Ground | 2600×2600 m @ z = −20 cm ✓; all actors at origin, scale 1, no transform drift |
| Level | `GREYBOX_OK`, 12/12 actors placed, `GREYBOX_SAVED`; original level untouched |
| Import | `IMPORT_OK` (5 meshes + 5 MICs) + `IMPORT_SAVED True` (final palette run) |
| Tests | `pytest tests/test_compiler.py` → **12/12 pass** (no exporter regression) |
| Readability | top-down schematic reviewed READABLE: city mass / open ground / block structure / corridors / hero all identifiable; histogram confirms bucket split |

## 6. Performance notes (mobile-first: iPhone 13 mini / 30 fps direction)

- +4 draw calls, 5 flat opaque MICs, 249,750 verts total (+6 vs v0: ground quad).
  No textures, transparency, shadows changes, dynamic lights, or per-building logic.
- No expensive rendering dependency introduced (Lumen / Nanite / VSM / PCG untouched;
  renderer settings untouched). Full optimization pass still ahead but nothing built
  here will need to be thrown away for assuming desktop rendering.

## 7. Evidence

- `docs/evidence/greybox_topdown.png` — top-down bucket schematic (OFFLINE, canonical data)
- `docs/evidence/greybox_heights.png` — extruded-height histogram by bucket
- `docs/evidence/ue58-greybox-viewport.png` — original baseline (retained)
- Headless logs: `IMPORT_OK` / `GREYBOX_OK` / `BOUNDS_DONE` (in `unreal/Saved/Logs/`)
- (Helper thumbnails `*_small.png` are local-only vision aids, not committed.)

## 8. Known limitations / next steps

1. **No in-editor GUI screenshot this round** (headless cannot capture a viewport).
   Requested follow-up: open `L_TaipeiGreybox_Clean` in UE 5.8 → Play from `Start_Flight` →
   1-min visual confirm; file any tuning as small follow-up commits.
2. Ground is a flat color plane + building gaps only; production road system out of scope.
3. Lighting is neutral-daylight test values only, not a final lighting pass.

## 9. Reproduce / revert

```bash
python tools/compiler/build_tile.py          # v0 GLB (untouched path)
python tools/compiler/build_greybox_tile.py  # derived greybox GLB + report
python tools/compiler/render_greybox_map.py  # offline proof maps
# in UnrealEditor-Cmd (see spike doc for exact flags):
#   import_tile.py  (ACW_GLB=<greybox glb>, ACW_DEST=/Game/Taipei/XinyiGreybox)
#   build_greybox_level.py (ACW_SRC_DIR=/Game/Taipei/XinyiGreybox)
#   dump_bounds.py  (ACW_ASSET=/Game/Taipei/XinyiGreybox)
```

Revert: delete the derived GLB/report + `git rm` the `XinyiGreybox/` folder and
`L_TaipeiGreybox_Clean.umap`. `L_TaipeiGreybox` and all of v0 are intact.
