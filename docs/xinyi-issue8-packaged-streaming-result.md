# XinyiV2 Issue #8: packaged source-driven streaming measurement

Date: 2026-09-29 (Asia/Taipei)
Branch: `codex/issue8-host-gate-tooling` (Draft PR #11)
World: `/Game/XinyiV2/L_XinyiV2_Contract_WP`
Host run ID: `20260929T002733Z-44199b81`

**PASS_PACKAGED_STREAMING for the deterministic World Partition load/unload subgate.** Two distinct fresh UE5.8 Windows Development game processes traversed the same 27-point contract route. At all 25 tile centers, the intended building tile was loaded. Every one of the 25 tiles generated both a real load and a real unload event over the route; the two outside controls each had zero loaded building tiles. Ordered tile inventories, deltas, and terrain inventories matched between the two processes. The accepted `_WP` map, source map, external actor packages, building assets, project config, and original bridge source remained byte-for-byte unchanged under the pre/post snapshot check.

| Observation | Packaged run 1 | Packaged run 2 |
|---|---:|---:|
| Distinct process ID | 31804 | 28148 |
| Route points completed | 27/27 | 27/27 |
| Unique building tiles seen / loaded / unloaded | 25 / 25 / 25 | 25 / 25 / 25 |
| West / east outside control loaded tiles | 0 / 0 | 0 / 0 |
| Missing target tile at its center | 0 | 0 |
| Missing references / placement drift | 0 / 0 cm | 0 / 0 cm |
| Max wait per point, including 5 s dwell | 24,404 ms | 10,639 ms |
| Max observed ticker gap (hitch indicator) | 1,252 ms | 2,467 ms |
| Streaming/reference errors / runtime `Warning:` lines | 0 / 0 | 0 / 0 |

UE5.8's `WorldPartitionRuntimeHashSet` reported a runtime loading range of **25,600 cm (256 m)**. The route's outside controls sit **5,000 m beyond** the Landscape boundary, so their zero-tile readings are outside the measured range rather than an assumed distance. The transient source was the sole active runtime source at each observation. The persistent Landscape root stayed present at all 27 stops; streamed terrain proxies were absent at the outside controls and numbered 1–3 at tile centers, with 9–24 render and collision components available there. Loaded runtime cell names and source positions are in the JSON evidence.

Both runtime logs record a brief `LogWorldPartition` streaming-performance transition from `Good` to `Critical` and back to `Good`. The transition lasted about 2.13 s in run 1 and 0.07 s in run 2. The ticker-gap measurement is a hitch indicator, not a frame-time percentile or an FPS result; this task defines no performance threshold. The longest completion wait in run 1 was at `tile-02-03`. These observations remain inputs to a later performance investigation.

## Execution and provenance

The mandatory snapshot command ran first. The default `python.exe` was a WindowsApps alias and failed closed without creating a snapshot; the same command then succeeded with Codex's bundled Python on `PATH`.

```powershell
.\tools\unreal_xinyi_v2\snapshot_host_state.ps1 -EngineRoot "C:\Program Files\Epic Games\UE_5.8"
.\tools\unreal_xinyi_v2\prepare_streaming_route.ps1 -RunId "20260929T002733Z-44199b81" -Contract "D:\Users\EDDY\Documents\GitHub\air-combat-world\unreal\Saved\XinyiUnrealV2Inputs\run-35822928983\unreal\Saved\XinyiUnrealV2Contract\xinyi_unreal_v2_contract.json"
```

The selected offline contract had SHA-256 `2095d6400eafd611094c35828550191cb4b6b8b9031493d9f420c9ffa6bec89c`, `PASS_CONTRACT`, 25 tiles, and the accepted building source/manifest hashes. A non-PIE `UnrealEditor.exe -game -NullRHI` diagnostic first exercised the full route successfully; it is not counted as packaged evidence. The packaged binary was then built with:

```powershell
& "C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\RunUAT.bat" BuildCookRun -project="D:\Users\EDDY\Documents\GitHub\air-combat-world\unreal\AirCombatWorld.uproject" -nop4 -unattended -utf8output -build -cook -stage -pak -package -archive -archivedirectory="D:\Users\EDDY\Documents\GitHub\air-combat-world\unreal\Saved\XinyiHostGates\20260929T002733Z-44199b81\packaged-development" -targetplatform=Win64 -clientconfig=Development -map=/Game/XinyiV2/L_XinyiV2_Contract_WP -noXGE
.\tools\unreal_xinyi_v2\run_packaged_streaming.ps1 -RunId "20260929T002733Z-44199b81"
.\tools\unreal_xinyi_v2\verify_snapshot_unchanged.ps1 -RunId "20260929T002733Z-44199b81"
```

UAT returned exit code 0 and `BUILD SUCCESSFUL`; 631 packages cooked and the Development archive was generated. `run_packaged_streaming.ps1` launched the inner `Windows/AirCombatWorld/Binaries/Win64/AirCombatWorld.exe` twice, each with the explicit `_WP` map, `-NullRHI`, route and manifest paths, run ID, and a unique output/log path. It recorded independent launch IDs, PIDs, exit codes and SHA-256 hashes. The runtime plugin was opt-in through command-line arguments and spawned only a transient source actor. The host validator required exact `MOVE`/`POINT` marker order in each engine log, correct process identity and hashes, source arrival/completion, all actor/cell/terrain observations, identical run inventories, and zero critical errors. The post-run `90-source-immutability.json` returned `PASS_SOURCE_IMMUTABILITY` for all 107 inventoried file rows.

The UAT log contains six repeated slow Derived Data Cache warnings concerning engine template material shader maps, with zero `Error:` lines and zero missing-package lines. The packaged runtime logs have no `Warning:` or streaming/reference error lines; the World Partition `Critical` performance state transitions above are retained separately.

The reviewable, path-free per-point receipt is [packaged-streaming.json](evidence/xinyi-host-streaming-20260929/packaged-streaming.json). Full engine-authored raw observations, process attestations, logs, the snapshot, route, gate receipt, and immutability receipt remain on this workstation under `unreal/Saved/XinyiHostGates/20260929T002733Z-44199b81/`; their hashes are referenced in the committed JSON. The generated `_WP` and source assets remain intentional local untracked state and were not committed or regenerated.

This result closes only the deterministic runtime source-driven streaming measurement. Issue #8 remains open for HLOD, collision/trace policy, broader cook/package reachability, and a separate performance baseline. Draft PRs #9 and #11 remain Draft.
