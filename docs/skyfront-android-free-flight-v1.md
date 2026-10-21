# Skyfront Homeland — Android Free Flight Prototype v1

Draft, do not merge. Base: PR #55 (`feat/ntw-forest-mobile-profile-v1`, North Taiwan / Yangmingshan forest map + Mobile Forest
Profile). Target device: Samsung Galaxy Tab S11 (sideloaded test APK).

## What it is

A minimal playable free flight over the PR #55 map: one paper plane, a chase camera, tablet touch controls and a flight HUD.
No combat, enemies, missions, weapons, shop or menus.

| Part | Implementation |
|---|---|
| Game module | `unreal/TreeLookdev/Source/SkyfrontFreeFlight` (C++, runtime). The project gains a game target; no new content assets |
| Plane | `AFreeFlightPawn`: low-poly paper dart (`ProceduralMeshComponent`, ~6 m long, white paper + red keel), swept collision sphere |
| Flight model | Arcade, kinematic: throttle sets a cruise speed (180–830 km/h at 0–100 %), climbing costs / diving gains speed, stick up/down = pitch rate, stick left/right = **bank angle** up to 75° (release = wings level, a held thumb cannot roll the plane over), bank gives a coordinated turn (×1.6 arcade gain) |
| Camera | Spring-arm chase camera, 13 m behind / 5 m above looking 14° down (the dart reads as a plan shape), position + rotation lag |
| Controls | `AFreeFlightPlayerController`, polled touches: left half = floating stick (pull down = climb), right side = throttle slide (+ sideways rudder), RESET and PITCH STD/INV buttons. Keyboard / gamepad for desktop testing |
| HUD | `AFreeFlightHUD` (canvas): speed km/h, altitude m (TWVD2001), height above ground, heading + cardinal, throttle bar, PULL UP warning |
| Reset | RESET button; automatic 2 s after hitting terrain or the sea, 1.5 s after leaving the 26.5 km map (+0.5 km margin) |
| Start | Over the Sanzhi coast, 800 m, compass heading 144° (SE) toward Zhuzishan / Datun (configurable, `DefaultGame.ini`) |
| Game mode | `GlobalDefaultGameMode=/Script/SkyfrontFreeFlight.FreeFlightGameMode`. The map's perf camera sequence (`NF_PerfSequence`) is stopped at runtime, map content is not edited |

Code: `unreal/TreeLookdev/Source/` (+ `TreeLookdev.uproject` module / `ProceduralMeshComponent`, `Config/DefaultEngine.ini` game mode and
Android settings). Scripts: `tools/skyfront/package_android.ps1` (APK), `tools/skyfront/run_ff_autotest.ps1` (desktop smoke flight).
Nothing in PR #55's forest, terrain, materials or Mobile Forest Profile was changed; the Android build uses its `[Android DeviceProfile]` as is.

## Android build environment (this host)

| Item | State |
|---|---|
| UE 5.8 Android target platform | Installed 2026-10-21 through the Epic Games Launcher (the Launcher build had only the editor-side Android stubs) |
| JDK | Microsoft OpenJDK 17.0.20 (winget) |
| Android SDK | `C:\Android\Sdk`: platform-tools, platforms;android-34, build-tools;35.0.1, ndk;27.2.12479018 (r27c), cmake;3.22.1 — the versions of UE 5.8 `Android_SDK.json`. Only `android-sdk-license` accepted |
| Environment variables | Set per packaging process by `package_android.ps1` (JAVA_HOME, ANDROID_HOME, NDKROOT); no system-wide change |

## Results

### APK

| | |
|---|---|
| File | `SkyfrontFreeFlight-0.1.0-dev-arm64.apk`, 551,634,430 bytes, SHA-256 `877ad2a9…24923157` (`docs/evidence/skyfront/free_flight_v1/apk_manifest.json`) |
| Package | `com.skyfront.homeland.freeflight` 0.1.0 (1), label "Skyfront Free Flight", landscape, minSdk 29 / targetSdk 34, `arm64-v8a` only |
| Rendering | Vulkan only, mobile renderer (`SF_VULKAN_ES31_ANDROID`), `Android_ASTC` textures |
| Data | Inside the APK (`assets/main.obb.png`, 427 MB): one file, no OBB copy |
| Config / signing | Development (console + logs on), APK Signature Scheme v2 with the Android debug certificate — test build, not for a store |
| Build | BuildCookRun exit 0: arm64 compile with NDK r27c, cook 821 packages in 4.8 min with 0 errors / 1 benign cvar-priority warning, Gradle `BUILD SUCCESSFUL`, `apksigner verify` OK |

### Desktop smoke flight (gameplay logic, not phone performance)

`-ffautotest` drives the real touch-handling code with scripted finger samples (stick, throttle slide, RESET) in the editor `-game`,
ES3.1 mobile renderer + the `[Android DeviceProfile]` cvars, 2560×1600 offscreen; telemetry per second + HUD screenshots in
`docs/evidence/skyfront/free_flight_v1/`.

| Check | Result |
|---|---|
| Spawn | 800 m over the Sanzhi coast, heading 144° SE, 396 km/h, camera on the plane (the map's perf sequence does not steal it) |
| Stick pull / push | pitch +26° climb, then level-off; speed 396 → 375 km/h in the climb |
| Stick right (held) | bank settles at 36°, heading 144° → 171° in 8 s, no roll-over; release → wings level in ~1 s (bank 36° → 2° → 0°) |
| Throttle slide | 33 % → 98 % in 2 s, 381 → 636 km/h after 4 s |
| Dive | pitch −24°, speed rises to 800 km/h |
| RESET button | back to the start pose and speed |
| Terrain (`-ffcrash`, start over the Datun forest at 1300 m) | AGL 490 m = DEM height 809 m ✓; held dive → terrain hit at AGL 1.7 m → "CRASHED" → automatic reset 2 s later (twice) |

The bank-turn run predates the ×1.6 turn gain (same build otherwise); the APK has the gain. Desktop frame rates on the Intel
UHD 770 (12–38 fps) say nothing about the Tab S11.

## Install on the Galaxy Tab S11

1. Copy `SkyfrontFreeFlight-0.1.0-dev-arm64.apk` (552 MB) to the tablet, e.g. upload it to your private cloud and download it on the tablet
   (or USB file transfer). Optional: compare the SHA-256 with the `.sha256` file next to it.
2. On the tablet open the APK from **My Files → Downloads** (or the cloud app). Android asks to allow installs from that app:
   **Settings → Allow from this source** → back → **Install**. If Auto Blocker is on (Settings → Security and privacy → Auto Blocker), turn it off
   for the install; Play Protect may warn about an unknown developer → **Install anyway**.
3. Start **Skyfront Free Flight**. The first launch compiles Vulkan pipelines while loading — expect a longer first start
   and some hitches in the first minute.
4. Play in landscape, two thumbs:
   - **Left thumb anywhere on the left half**: floating stick. Pull **down** = climb, push up = dive, left / right = bank and turn.
     `PITCH STD` (top right) switches to `PITCH INV` if you prefer push-up-to-climb.
   - **Right thumb on the right side**: slide up / down = throttle (bar on the right edge); sideways = rudder.
   - **RESET** (top right): back to the start. Crashing into terrain or the sea, or leaving the map, resets automatically.
5. Uninstall: long-press the icon → Uninstall (or Settings → Apps).

## Current limits

- Untested on any phone or tablet: this host has no device and no USB access to the Tab S11. Frame rate, thermals, memory, touch feel and
  the Vulkan driver path are all unverified.
- Development build with the debug signature (larger, includes the Vulkan validation layer library; not enabled at runtime).
- One plane, no stall / spin, no aerobatic roll (stick commands bank angle up to 75°); pitch has no auto-level.
- No pause menu, no sound, no settings screen; quality is whatever the engine's Android device profile + the PR #55 `[Android DeviceProfile]` pick for the device.
- Collision is the Landscape and the sea level only: trees and buildings have no collision in the PR #55 map (by design there), so the plane flies through them.
- `GlobalDefaultGameMode` is the free-flight game mode on this branch: a Win64 package of this branch would also start in free flight
  (the PR #50–#55 packaged perf flight needs the default game mode).

## Waiting for the device test

1. Install + first start on the Tab S11 (Vulkan device profile chosen, no crash, time to first frame).
2. Touch: stick / throttle / buttons with two thumbs, multi-touch at the same time, HUD readable at arm's length.
3. Frame rate over the forest at 240–400 km/h (`stat fps` / `stat unit` via the Development console, 4-finger tap), and after 10 minutes (thermal).
4. Visual: near forest feel and far mountain shapes as in the PR #55 ES3.1 preview; sky dome; no terrain stepping.
5. Memory (PSS) and World Partition streaming hitches.
6. If the forest is too heavy: the PR #55 report §5 fallback levers (shorter thinning distance, lower `r.MobileContentScaleFactor`, 30 fps cap) —
   only after measuring on the device.

## Reproduce

```
tools/skyfront/run_ff_autotest.ps1 -Tag es31 -Mobile                       # desktop smoke flight
tools/skyfront/package_android.ps1                                          # APK -> unreal/TreeLookdev/Saved/Skyfront/android_archive/
```
The UE project content is untracked (PR #55 worktree copy, see `docs/north-taiwan-forest-mobile-profile-v1.md`).
