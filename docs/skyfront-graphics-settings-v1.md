# Skyfront Homeland — In-Game Graphics Settings v1

Draft, do not merge. Base: PR #56 (Android Free Flight v1). Evidence: `docs/evidence/skyfront/graphics_settings_v1/`.

Every statement below is tagged **[PC]** = verified on this host (Windows, Intel UHD 770, editor `-game`, ES3.1 mobile-renderer preview
with the Android device-profile cvars, or SM5), **[code]** = read from UE 5.8 source / config, or **[S11]** = waiting for the Galaxy Tab S11.
No frame-rate claim is made for the S11.

## 1. Diagnosis of the Tab S11 feedback

### 1a. "Buildings and forest disappear 1–2 km out" — missing 3D objects

| Finding | Evidence |
|---|---|
| The S11 (Dimensity 9400+, `Mali-G925-Immortalis`) matches `Android_Mali_G9xx_Vulkan → Android_Mali_G9xx → Android_Mali_G710 → Android_Epic → Android` + the PR #55 `[Android DeviceProfile]` cvars. Engine scalability is already Epic (`sg.* = 3`, `r.ViewDistanceScale 1.0`) | [code] `BaseDeviceProfiles.ini` match rules |
| **Buildings:** the town HISMs are cooked and not spatially loaded (543 components found at runtime), end cull 9 km — but the PR #55 Android cvar `foliage.MaxEndCullDistance=165000` is applied by the engine to **every** HISM (`HierarchicalInstancedStaticMesh.cpp`: `EndCull = min(MaxEndCullDistance, EndCull)`), so the 9 km towns were cut at **1.65 km** | [code]; [PC] same-view: towns 6–7 km away absent at a 3 km cull, present at 5 / 7 / 9 km (`crops_far_towns_south_by_preset.jpg`) |
| **Trees, cook:** `r.CookOutUnusedDetailModeComponents=1` + `r.DetailMode=0` in the Android profile make the cooker drop the Medium / High rank-band HISMs (`SceneComponent.cpp SceneComponentNeedsLoadForTarget`) — 45 % of the trees are not in the APK, no runtime setting can bring them back | [code] |
| **Trees, distance:** mobile thinning ends at 1.5 km (`ThinEndM`), all HISMs capped at 1.65 km | [code] PR #55 MPC values |
| **Trees + terrain, precision (device only):** all `M_NF_*` materials use the default float precision; on mobile the pixel-shader material math is `half` (`Common.ush`: `MaterialFloat = half`). The forest thinning and Landscape distance bands work in centimetres (ThinEnd 150 000–340 000, far bands 350 000–1 100 000); fp16 tops out at 65 504, so beyond **~655 m** the dissolve math overflows (trees vanish early) and the far colour bands collapse. Mali evaluates mediump as real fp16; the PC ES3.1 preview evaluates `half` as float, which is why the PR #55 preview never showed it | [code]; [S11] to confirm visually |
| World range: the 26.5 km Landscape is always resident, no far-clip limit; World Partition tree cells load to 3.2 km | [code] PR #52 grid |
| Resolution: `r.MobileContentScaleFactor=1.0` (Android tiers) = 1280×720-based → the S11 rendered ~1280×800 on its 2560×1600 panel and upscaled | [code] `AndroidWindow.cpp` |
| `r.Shadow.CSM.MaxMobileCascades` (PR #55 profile) does not exist in UE 5.8 — a no-op; the cascade count is `r.Shadow.CSM.MaxCascades` | [code] |

### 1b. "Terrain and forest look plastic" — flat materials / lighting (handled separately)

| Cause | Fix |
|---|---|
| fp16 overflow of the far-band / canopy-shell math (above) flattens the far Landscape into one band | `r.Mobile.FloatPrecisionMode=1` (full precision for material expressions; lighting stays half) [S11] |
| No ambient occlusion at all on the mobile renderer (desktop has SSAO) | `r.Mobile.AmbientOcclusion=True` (cooked permutation) + AO row (High / Ultra on) [PC] |
| 50 % render resolution upscaled; 55 % trees; canopy texture under the near trees | resolution / density / tree-distance rows |
| PC check: at Ultra the ES3.1 mobile renderer now looks close to the SM5 desktop renderer at the same pose (`sm5_vs_es31_ultra_forest_layers.jpg`) | [PC] |

Not changed: tree species, terrain data, Landscape material graph, textures (ASTC stays at the engine default 6×6; Android world textures
are not size-capped). If the S11 still looks blocky after this build, ASTC 4×4 for the canopy / terrain-skin textures is the next lever.

## 2. What was built

`USkyfrontGameUserSettings` (`Source/SkyfrontFreeFlight/SkyfrontGameUserSettings.*`), a `UGameUserSettings` subclass
(`GameUserSettingsClassName`): saved in `GameUserSettings.ini`, restored and applied at every launch, applied live from the menu.
Values are set with `ECVF_SetByCode` (outranks the device profile) and read back for the overlay.

| Row | Levels | Drives |
|---|---|---|
| Tree distance | 1.5 / 2.2 / 3.0 / 3.4 km | `MPC_NF_Forest` mobile twins (NearFullM, ThinEndM, ThinGammaM, FadeWidthM, ShellStartM / EndM, ClumpGainM); World Partition loading range 2.4 / 2.8 / 3.2 / 3.6 km (`wp.Runtime.OverrideRuntimeSpatialHashLoadingRange`); level 4 = the PC forest curve |
| Forest density | 55 / 78 / 100 % | `r.DetailMode` 0 / 1 / 2 = PR #50 rank bands (all cooked now) + `RankKeepM`, CrownGainM, NearCanopyM |
| (derived) | — | `r.ViewDistanceScale` = max over the visible bands of (band's dissolve distance / its baked HISM cull), so no band is culled before it has dissolved |
| Building distance | 3 / 5 / 7 / 9 km | end cull set on the 543 town HISMs (÷ view distance scale); `foliage.MaxEndCullDistance` cap removed |
| Terrain detail | LOD ×1.0 / 1.25 / 1.5 / 2.0 | `r.LandscapeLODDistributionScale`, `r.LandscapeLOD0DistributionScale` |
| Render resolution | 50 / 62 / 75 / 87 / 100 % | `r.ScreenPercentage` of the native back buffer (`r.MobileContentScaleFactor=0` on Android) |
| Shadows | off / 400 / 600 / 1000 / 1500 m | `r.ShadowQuality`, `r.Shadow.DistanceScale`, `r.Shadow.CSM.MaxCascades` 1 / 2 / 2 / 3, `r.Shadow.MaxCSMResolution` 1024 / 1024 / 2048 / 2048 |
| Ambient occlusion | off / on | `r.AmbientOcclusionLevels`, half-resolution mobile SSAO |
| Frame rate cap | 30 / 60 | `t.MaxFPS` + `r.SetFramePace`; presets do not change it |

| Preset | Trees | Density | Towns | Terrain | Res | Shadows | AO |
|---|---|---|---|---|---|---|---|
| Power Saver | 1.5 km | 55 % | 3 km | ×1.0 | 50 % | 400 m ×1 | off |
| **Balanced** (default) | 2.2 km | 78 % | 5 km | ×1.25 | 62 % | 600 m ×2 | off |
| High | 3.0 km | 100 % | 7 km | ×1.5 | 75 % | 1 km ×2 2048 | on |
| Ultra | 3.4 km | 100 % | 9 km | ×2.0 | 87 % | 1.5 km ×3 2048 | on |

Power Saver reproduces the PR #55 phone forest (apart from the town fix). Changing a row turns the preset into CUSTOM (or back into the
preset it matches). DEFAULTS = Balanced, diagnostics on.

**Menu (tablet):** GFX button (top bar) → panel on the right; the plane holds its pose and the scene stays visible on the left, so a change
is seen immediately. Four preset buttons, eight `<` / `>` rows with level pips, DEFAULTS, DIAG ON/OFF, FLY. Touch targets ≥ 6.8 % of the screen
height (~10 mm on the S11). Desktop: G opens the menu.

**Diagnostics overlay (no ADB needed), top left:** FPS, frame ms (1 s average and worst), GPU ms, FPS cap; current mode, last change's
apply time and worst frame within 3 s; scene resolution vs back buffer and CSF; trees: dissolve distance, effective HISM cull range, WP
range; forest: DetailMode, shown / loaded tree HISMs and instances (census every 2 s); towns: effective cull read back from a component,
foliage cap; shadows / AO / landscape LOD as read back from the cvars; active device profile and RHI.

## 3. PC verification

### Same view, preset switched live (`run_gfx_compare.ps1`, `-ffgfxtest`)

Two poses held still: `forest_layers` (250 m over the Sanzhi north slope, 8.6 km across the forest bands to Qixingshan) and `towns_south`
(north hills, 7 km over Tianmu / Shilin / Beitou). Each preset is applied live; measurement starts after World Partition streaming and
shader compiles report done; 5 s sample; screenshot; next preset 3 frames later.

GPU time, ES3.1 mobile-renderer preview at 2560×1600, Intel UHD 770 [PC] (run `es31_b`):

| View | Power Saver | Balanced | High | Ultra | Balanced again |
|---|---:|---:|---:|---:|---:|
| forest_layers | 52 ms | 85 ms | 142 ms | 237 ms | 85 ms |
| towns_south | 25 ms | 41 ms | 71 ms | 108 ms | 41 ms |

SM5 desktop renderer, same poses / presets [PC]: forest 88 / 141 / 237 / 350 ms, towns 39 / 69 / 130 / 174 ms. These are relative costs of
the presets on a laptop iGPU only — they predict nothing about the S11's frame rate.

Visible change [PC]: towns — Power Saver shows no 3D buildings in the basin 6–7 km out, Balanced the nearer districts, High / Ultra the town to
the Tamsui river (`crops_far_towns_south_by_preset.jpg`); forest — density and mid-range crowns, shadows, AO (`diff_forest_layers_ultra_vs_powersaver.png`).
Mean absolute pixel change vs Power Saver over the scene (HUD masked): Balanced 5.8, High 7.7, Ultra 8.6 /255; the same preset twice: 0.7.

### Switch hitch [PC]

Worst frame within 3 s of a live preset switch: 0.13–0.62 s (first run with cold shader cache: 1.7–2.7 s, PC-only on-demand shader
compiles). Per row, from Balanced, each row stepped alone (baseline frame ~90 ms):

| Row | Worst frame (up / down) |
|---|---|
| Forest density | 483 / 450 ms — `r.DetailMode` change recreates every render state (engine scalability callback) |
| Tree distance | 177 / 222 ms — World Partition loading range change |
| Shadows | 181 / 184 ms — shadow map reallocation |
| Building distance | 182 / 90 ms |
| Terrain detail, resolution, AO, FPS cap | 90–107 ms (no hitch) |

Streaming after a switch completed within 0.1–1.1 s at a held pose (3.0–4.3 s after an 8 km teleport).

### Persistence and flight [PC]

- Saved section `[/Script/SkyfrontFreeFlight.SkyfrontGameUserSettings]` in `Saved/Config/<Platform>/GameUserSettings.ini` (Preset, eight row
  levels, diagnostics flag). Restore test: the ini set to Ultra + 60 fps, game relaunched → the start-up apply logged
  `preset=ULTRA tree=3400m dm=2 vds=1.000 bld=9000m res=87% shadow=1500m/3/2048 ao=1 fps=60 wp=3600m` (`restore_test_ultra_apply.txt`).
- The PR #56 scripted flight (stick climb / bank turn / throttle / dive / RESET) ran unchanged under Ultra in the same launch.
- Menu screenshot: `menu_open_balanced.jpg` (Balanced, overlay showing 278 k of 357 k loaded trees = DetailMode 1).
- Final run `es31_c` (committed config incl. full-precision materials) reproduces `es31_b` within 2 % — expected, the PC preview evaluates
  `half` as float, so the precision fix is invisible on PC.

## 4. Waiting for the S11

1. The precision fix: trees visible to the selected tree distance (not dissolving at ~650 m), far mountains showing the macro forest
   colour and terrain-skin bands instead of one flat colour.
2. Each preset: FPS / frame ms / GPU ms from the overlay over the forest at 240–400 km/h; then 10 minutes for thermals. Which presets
   hold 30 fps and whether High / Ultra can hold 60 is unknown until then.
3. Hitch of a live switch on the phone CPU (overlay "last change" line), especially Forest density.
4. Memory: all tree bands are now in the APK and loaded (PR #55 estimated ~265 MB of tree instances for the stripped phone cook vs 482 MB with all bands), and the Ultra WP range loads more cells.
5. Device profile name and back-buffer size in the overlay (expected `Android_Mali_G9xx_Vulkan`, 2560×1600, CSF 0.00).
6. Mobile SSAO cost and look on Mali; fp32 material math cost.

## 5. APK

| | |
|---|---|
| File | `SkyfrontFreeFlight-0.2.0-dev-arm64.apk`, 807,215,998 bytes, SHA-256 `6ac8d5e4…01b0d41d` (`apk_manifest.json`) |
| Package | `com.skyfront.homeland.freeflight` **0.2.0 (versionCode 2)**, arm64-v8a, minSdk 29 / targetSdk 34, Vulkan only, Android_ASTC |
| Signing | same Android debug certificate as 0.1.0 (SHA-256 `269f7e2c…`) → installs over 0.1.0 as an update |
| Data | inside the APK (`assets/main.obb.png` 683 MB; 0.1.0: 427 MB) — the +256 MB are the Medium / High tree bands no longer stripped |
| Build | BuildCookRun exit 0; cook 821 packages, 0 errors (12.2 min incl. Vulkan shaders for the AO + full-precision permutations); `apksigner verify` OK |

## 6. Install

Same as PR #56: download `SkyfrontFreeFlight-0.2.0-dev-arm64.apk` from your private cloud on the tablet and open it. It is signed with the same
debug key and has a higher version code, so it installs over 0.1.0 as an update. Settings live in the app's storage; uninstalling resets them.

## 7. Reproduce

```
tools/skyfront/run_gfx_compare.ps1 -Tag es31            # same-view presets + row hitch sweep, ES3.1 mobile preview
tools/skyfront/run_gfx_compare.ps1 -Tag sm5 -Sm5        # same, desktop renderer reference
tools/skyfront/package_android.ps1                      # APK -> unreal/TreeLookdev/Saved/Skyfront/android_archive/
```
