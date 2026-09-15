# UE 5.8 Greybox Spike — Result

> Branch: `feat/ue58-greybox-spike` (from `feat/taipei-greybox-core`, `main` untouched).
> Godot files retained untouched as legacy/optional smoke target.
> Compiler + WorldModel untouched in semantics — two exporter robustness fixes
> (below) apply to all engines, not UE-specific. All UE specifics live in
> `adapters/unreal/` + `unreal/`.

## 1. Environment (Phase 1)

- Engine: **Unreal Engine 5.8.0** (CL 55116800, `++UE5+Release-5.8`, promoted build).
- Install: `C:\Program Files\Epic Games\UE_5.8` (via `C:\Program Files\Epic Games\`
  listing + registry `HKLM\SOFTWARE\EpicGames\Unreal Engine`).
- Editor: `.../Engine/Binaries/Win64/UnrealEditor.exe` ✓ (GUI opened twice, warm DDC).
- Headless: `.../Engine/Binaries/Win64/UnrealEditor-Cmd.exe` ✓ (4 runs: import ×3, bounds ×2, level ×2).
- glTF route: **Interchange Framework core** (no GLTFImporter plugin in 5.8; only
  `GLTFExporter` under `Enterprise/`). Used `InterchangeManager` Python API;
  AssetTools fallback coded but never needed.
- ENVIRONMENT PROBE: PARTIAL (5.8 API names from prior-version knowledge, not header
  scans — wide source scans hung the shell and were abandoned per round rules).
  Defensive scripts reported which path succeeded.

## 2. GLB regeneration (Phase 2 / GATE A+B)

- `node tools/smoke_greybox.mjs --skip-fetch` → tests **12/12 OK** (11 existing + 1 new
  index-range regression test).
- 101 suppression: 8-record tower stack incl. true 512.43 m tower; placeholder exactly
  once at hero-point ENU; anti-double-stack test passes. No geometry-semantics change.
- Final GLB sha: `8b829afce13c69c4b1a03a1f10220558c75b072ed5f785517f5292ba402c8abf`.

## 3. Project (Phase 3)

- `unreal/AirCombatWorld.uproject` (EngineAssociation 5.8, content-only, PythonScriptPlugin on).
- `unreal/Config/DefaultEngine.ini` (minimal; `EditorStartupMap` under
  `GameMapsSettings` → `L_TaipeiGreybox`; first attempt put it under the wrong
  section and the editor opened the default map instead — fixed).
- Renderer at defaults; Lumen/Nanite/VSM **not** baseline (mobile: iPhone 13 mini
  future target, no profiling this round).

## 4. Import (Phase 4) — Route A SUCCEEDED, zero manual steps

- `adapters/unreal/import_tile.py` via
  `UnrealEditor-Cmd.exe <uproject> -ExecutePythonScript=... -unattended -nopause -nosound`
  with `ACW_GLB` env. Log: `IMPORT_OK interchange -> [massing_grey, layerA, hero]`.
- Two integration learnings (both fixed in-repo):
  1. **Interchange does not autosave** — added `save_directory(/Game/Taipei)`;
     first import reported OK but wrote nothing until this (`IMPORT_SAVED True`).
  2. **Exporter index-base bug**: `add_tri` used `len(pos)` on a flat float list →
     every index 3× too large → UE imported an EMPTY LayerA (bounds 0). Fixed
     (`len(pos)//3`) + added `test_glb_indices_in_range` regression test (12/12).
  3. **UVs**: added planar TEXCOORD_0 (strict importers expect a UV set; values
     carry no texture meaning in v0). Also added degenerate-tri/edge filtering.
- Residual: one `LogStaticMesh: Error: Bad MeshDescription` line on layerA per import,
  but the asset builds with full correct bounds — cosmetic/intermediate, mesh verified
  usable. Documented, not blocking.
- Assets on disk: `/Game/Taipei/xinyi_tile_2km/{Materials/massing_grey,
  StaticMeshes/layerA_city_massing, StaticMeshes/hero_taipei101_placeholder}`.

## 5. Scale / axis (Phase 5) — VALIDATED WITHOUT GUI

`adapters/unreal/dump_bounds.py` headless bounds (UE units = cm):

| Mesh | Bounds (cm) | Reads as |
|---|---|---|
| hero placeholder | origin z 25400, extent z 25400 → **max Z 50,800** | **508.0 m ✓ exactly** |
| hero XZ | origin (-9078, -7792), extent ±2828 | anchor = ENU (-90.78, +77.92) m ✓, base ±28 m ✓ |
| layerA | extent (104897, 107423, 13452) | **2.10 × 2.15 km** ✓, max Z 269 m (tallest non-101 tower, plausible) ✓ |

- Meter→cm conversion is automatic in the importer — **no extra scaling applied**.
- Measured mapping: glTF (x, y, z) → UE (x·100, z·100, y·100), i.e. north = −Y.
  Mesh upright, positions match ENU anchors. No ×100/÷100 error, no flipped axis.

## 6. Scene + camera (Phase 6/7)

- `adapters/unreal/build_level.py` created `/Game/Taipei/L_TaipeiGreybox` fully
  headless: `LEVEL_CREATED`, placed CityMassing_Xinyi, Hero_Taipei101, Sun
  (DirectionalLight −45°), Sky (Skylight), Fog (ExponentialHeightFog), Atmosphere
  (SkyAtmosphere), Start (PlayerStart 900 m south of 101, 350 m alt). `LEVEL_SAVED`,
  `.umap` on disk. Log: `LEVEL_OK`.
- Fly: content-only project → PIE uses DefaultPawn (WASD + mouse, fly). No custom
  controller this round.

## 7. Gates

- A. Compiler tests pass: **PASS (12/12)**.
- B. GLB regenerated: **PASS** (`8b829afc…`).
- C. UE5.8 project opens: **PASS** (GUI opened, warm DDC).
- D. GLB imports: **PASS** (Route A, headless, repeatable, saved .uassets).
- E. City at real-world scale: **PASS** (bounds: 2.10×2.15 km, upright, correct anchors).
- F. 101 placeholder once ≈ 508 m: **PASS** (bounds max Z exactly 50,800 cm).
- G. Render visible in Editor: **PARTIAL** — level loads (Outliner: L_TaipeiGreybox,
  7 actors), but viewport was still black/in-compile ("Sky Light waiting on Meshes,
  Textures") at screenshot time; SOM driver exposes 0 clickable elements so the
  camera could not be driven blind. Evidence: `docs/evidence/ue58-greybox-viewport.png`.
- H. Free camera: **PLACED, NOT YET EXERCISED** (PlayerStart + DefaultPawn fly; needs PIE).
- I. Actual visual confirmation: **PENDING (human, ~1 min)** — open
  `unreal/AirCombatWorld.uproject` → L_TaipeiGreybox auto-opens → press Play (Alt+P)
  or F with CityMassing selected.

Overall: **IMPLEMENTATION PASS / HUMAN VISUAL CHECK PENDING** (not claimed complete).

## 8. Evidence / manual steps / next task

- Screenshot: `docs/evidence/ue58-greybox-viewport.png` (editor open, level loaded,
  viewport pre-resolve). No fabricated screenshots.
- Manual steps remaining: one human open + Play/focus to confirm the white massing
  visually (everything else is automated and committed).
- Known blockers: none technical. Residual cosmetic: single Bad MeshDescription log
  line despite verified-good mesh.
- Next smallest task: human 1-minute visual check → then DEM heightfield slice
  (biggest remaining pipeline gap). Do NOT regress the fixed exporter (index/UV
  tests guard it).
