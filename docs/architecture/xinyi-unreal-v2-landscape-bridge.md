# Xinyi Unreal V2 — UE5.8 Landscape Bridge Contract

Status: implementation prepared; live UE5.8 compilation/materialization gate pending.

## Why a bridge exists

The accepted Xinyi terrain pipeline already produces deterministic MOI 2025
bare-earth DTM elevation data, a 631 x 631 Unreal Landscape heightfield, and a
locked coordinate contract.

The promoted UE 5.8 Python bindings expose Landscape classes and methods that
modify an **existing** Landscape, but they do not expose a reliable from-zero
component-bearing Landscape creation path. Spawning `unreal.Landscape` through
the generic actor path is known to produce a placeholder rather than the complete
editor creation pipeline.

The engine's C++ API does expose `ALandscapeProxy::Import`.

Therefore this branch uses a minimal editor-only C++ bridge rather than:
- clicking Landscape Mode manually;
- treating the Blender terrain GLB as production terrain;
- inventing a second terrain generator in C++;
- trying to hide the missing Python binding with UI automation.

## Authority boundary

Python remains authoritative for:

```text
MOI source/provenance
-> CRS / ENU transform
-> vertical datum alignment
-> 20 m DTM sampling
-> 631 x 631 topology
-> uint16 encoding
-> source/output hashes
-> building ground elevation
-> building expected world bounds
```

The bridge is authoritative for exactly one operation:

```text
validated little-endian RAW16 + locked topology/transform
-> ALandscape::Import
-> real ALandscape + components in the current editor world
```

The bridge must never:
- fetch terrain;
- resample terrain;
- choose a CRS;
- alter the global vertical offset;
- flatten terrain below buildings;
- inspect building IDs to alter terrain;
- generate artistic terrain;
- change building geometry.

## Plugin

`unreal/Plugins/XinyiLandscapeBridge`

The plugin is:
- Editor-only;
- source-controlled;
- build products ignored;
- reproducibly compiled against the installed UE 5.8 build before the local gate.

The reflected Python surface is intentionally tiny:

```text
unreal.XinyiLandscapeLibrary.create_landscape_from_raw16(...)
unreal.XinyiLandscapeLibrary.inspect_landscape_by_label(...)
```

## Create gate

The bridge refuses malformed topology before mutation.

For the current contract:

```text
SizeX = SizeY = 631
NumSubsections = 2
SubsectionSizeQuads = 63

ComponentSizeQuads = 2 * 63 = 126
ComponentsX = ComponentsY = (631 - 1) / 126 = 5
Expected Landscape components = 25
```

The RAW16 byte count must be exactly:

```text
631 * 631 * 2
```

The bridge decodes little-endian uint16 explicitly rather than depending on host
endianness.

The actor transform comes from the offline contract. For the current Xinyi area:

```text
location:
  west/min-east  -> UE X = -150000 cm
  north/max-north -> UE Y = -150000 cm
  Z = 0

scale:
  X = 396.825396825 cm
  Y = 396.825396825 cm
  Z = 200
```

No offset is visually tuned in Unreal.

## Post-import checks

Immediately after `ALandscape::Import`, the bridge records:

- Landscape label/path;
- component count;
- NumSubsections;
- SubsectionSizeQuads;
- ComponentSizeQuads;
- actor location;
- actor scale;
- component bounds;
- LandscapeInfo validity;
- Landscape extent in quads.

Creation fails if the component count is not 25.

## Persistence gate

Creation-session success is not sufficient.

The level is saved, UnrealEditor-Cmd exits, and a second process reloads the map.
The fresh process requires:

- real Landscape found by label;
- 25 components;
- valid LandscapeInfo;
- extent `[0, 0, 630, 630]`;
- locked actor location;
- locked scale;
- horizontal bounds spanning the same 2.5 km Xinyi square.

Only the fresh-reopen receipt can promote the Landscape stage.

## Building placement is independent of importer frame

The offline contract now emits expected UE world bounds for every one of the
11,130 validated building components.

After UE5.8 imports StaticMesh assets, a zero-mutation preflight:

1. uniquely joins each imported asset to its validated source component;
2. compares actual vs expected extents under one global tolerance;
3. rejects changed/ambiguous geometry;
4. computes:

```text
actor translation =
expected UE world-bounds origin
-
imported StaticMesh bounds origin
```

This makes the final placement independent of whether Interchange kept tile-local
coordinates, baked a glTF node transform, or recentered the mesh.

The rule is importer conditioning, not per-building artistic placement.

## Local entry point

With GitHub CLI authenticated and UE 5.8 installed:

```powershell
tools/unreal_xinyi_v2/fetch_and_run_local_gate.ps1
```

The fetch wrapper selects the latest successful offline-contract artifact,
downloads it, validates the 25 GLBs, builds the bridge, and runs the staged
UnrealEditor-Cmd gates.

Do not open the UE GUI during the gate; previous greybox work proved stale GUI
processes can hold package file locks and make apparent saves non-persistent.

## What still remains after this bridge passes

A passing real Landscape is not the final runtime verdict.

The remaining engine work is:

```text
building placement representation
-> fresh reopen
-> World Partition ownership/streaming
-> HLOD strategy
-> collision
-> cook/commandlet
-> memory / draw calls / frame timing
```

The decision between direct actors, merge/cluster representation, or HLOD must be
based on measured UE5.8 Interchange asset granularity and runtime metrics, not
chosen before the import evidence exists.
