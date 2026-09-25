# XinyiV2 Unreal 5.8 isolated World Partition result

Date: 2026-09-25 Asia/Taipei

Issue: #8

Branch: `feat/xinyi-unreal-v2`

## Result

**PASS_ISOLATED_WORLD_PARTITION_CONVERSION.** The existing validated
`/Game/XinyiV2/L_XinyiV2_Contract` map was converted with the `_WP` suffix,
then both maps were audited in fresh UE5.8 editor processes.

| Check | Result |
|---|---:|
| Original source map remains non-partitioned | PASS |
| Original source map has one Landscape and 25 building tile actors | PASS |
| New `/Game/XinyiV2/L_XinyiV2_Contract_WP` map has World Partition | PASS |
| Converted map actor descriptors | 32 |
| Converted map target descriptors | 1 terrain + 25 building tiles |
| Converted map streaming enabled and supported | PASS |
| Converted map initialized and able to stream | PASS |
| Original 29 untracked Unreal files retained with identical SHA-256 hashes | PASS |

The source map SHA-256 remained
`7592f40b655cba7dd48a5b3bd8443dfb0ef04bba6244c2620b944b46d387459f`.
The conversion created a separate local `_WP` map and external actor packages.
These generated Unreal packages are local host state; they are not committed.

Local receipts:

- `unreal/Saved/XinyiUnrealV2/ue_world_partition_source_postconvert.json`
- `unreal/Saved/XinyiUnrealV2/ue_world_partition_converted.json`
- `unreal/Saved/XinyiUnrealV2/wp-convert-report-only.log`
- `unreal/Saved/XinyiUnrealV2/wp-convert-isolated.log`
- `unreal/Saved/XinyiUnrealV2/ue_collision_baseline.json`

## Host findings

The UE5.8 `WorldPartitionConvertCommandlet` requires
`-AllowCommandletRendering` even for `-ReportOnly`. Using the normal renderer
stalled in `PartitionLandscape` while shader workers compiled for more than
15 minutes. With `-NullRHI`, the same report-only step partitioned the
Landscape in under a second, and the isolated conversion completed.

The project also needed a `GameFeatureData` Asset Manager rule. Without it,
the commandlet reported result 0 but the process exited 1 due to startup
errors. The rule leaves the cook decision at `Unknown`.

UE5.8's Python binding does not expose `WorldPartition.enable_streaming`.
The earlier Python audit therefore reported a misleading `false` through its
fallback. The editor-only native accessor now reads Unreal's actual
`IsStreamingEnabled`, `SupportsStreaming`, `IsStreamingEnabledInEditor`, and
`CanStream` values. The fresh-process converted-world audit reports all four
as `true`.

## Collision baseline

A read-only UE5.8 audit loaded all 25 persisted runtime StaticMeshes. The
import receipt accounts for 485,936 triangles. Each tile asset has the default
collision trace flag and exactly one simple convex collision shape; no other
simple shapes were found. The audit status is `PASS_COLLISION_BASELINE`, which
means the properties were measured, not that building collision is accepted.
A single convex shape over a tile containing many distinct buildings cannot
establish per-building contact or preserve gaps between buildings. Collision
policy and runtime trace tests remain open. The audit changed no assets.

## Remaining Issue #8 gates

This result establishes partition ownership and saved actor descriptors. It
does not measure runtime source-driven load/unload. The next gate is a
deterministic streaming-source traversal that records which building tile
cells load and unload, without changing the validated source world. HLOD,
collision policy and trace tests, cook, memory, draw-call, and frame-time
decisions remain pending.
