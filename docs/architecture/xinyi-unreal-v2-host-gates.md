# XinyiV2 UE5.8 host gates

Status: deterministic packaged streaming subgate **PASS** on the restored UE5.8 host
(`20260929T002733Z-44199b81`); other Issue #8 gates remain open.

## First command

From a clean PowerShell session with every Unreal process closed:

```powershell
tools/unreal_xinyi_v2/snapshot_host_state.ps1 -EngineRoot "C:\Program Files\Epic Games\UE_5.8"
```

The command creates a new immutable run directory under
`unreal/Saved/XinyiHostGates/<UTC>-<commit>/`. It uses exclusive receipt creation and never deletes,
saves, converts, imports, or edits a source package. A repeated run receives a new ID; an explicit
existing ID fails rather than overwriting evidence.

The snapshot includes all files under `unreal/Content/XinyiV2`, Xinyi external actors/objects,
the 25 building assets, available offline contracts, project config, the editor bridge's source
and descriptor, and the engine version file. It also records the protected paths' Git status.
Generated plugin `Binaries` and `Intermediate` are deliberately excluded: compiling the bridge
can change those files without changing the accepted source world.

Then prepare the coordinate-checked route using the `run_id` printed by the snapshot command:

```powershell
tools/unreal_xinyi_v2/prepare_streaming_route.ps1 -RunId "<run_id>"
```

The snapshot inventories offline contracts under `unreal/Saved/XinyiUnrealV2Inputs/run-*/unreal/Saved/XinyiUnrealV2Contract/`
and the direct `unreal/Saved/XinyiUnrealV2Contract/` path. With multiple contract candidates, supply
`-Contract "<path from 00-snapshot.json>"`; the wrapper refuses any file absent from the snapshot
or whose SHA-256 changed. Without a locally restored contract, route preparation stops and does
not fabricate positions. It writes `10-streaming-route.json` with two candidate outside controls
and the 25 tile centers in north-to-south serpentine order, using the accepted ENU-to-UE transform.
The controls are 5 km beyond the Landscape extent by default. Confirm that distance exceeds the
actual runtime loading range on the workstation; the controls must record zero building tiles.

For the packaged source-driven streaming subgate, build a Windows Development archive with
`BuildCookRun -build -cook -stage -pak -package -archive`, explicitly selecting only
`/Game/XinyiV2/L_XinyiV2_Contract_WP` as the map and using
`unreal/Saved/XinyiHostGates/<run_id>/packaged-development` as the archive directory. Then run:

```powershell
tools/unreal_xinyi_v2/run_packaged_streaming.ps1 -RunId "<run_id>"
```

The script requires the archive's inner game executable, route, snapshot and accepted runtime-world
manifest. It writes two fresh engine observations and logs, host launch attestations, then a strict
`30-packaged-streaming-gate.json` receipt. It preserves completed attempts and refuses partial-path
overwrites. `export_packaged_streaming_evidence.py` can produce a path-free review copy after the
post-run immutability check. All probes are opt-in and the actor they spawn is transient.

After the host tests, with the same branch and engine root, rehash the protected inventory:

```powershell
tools/unreal_xinyi_v2/verify_snapshot_unchanged.ps1 -RunId "<run_id>" -EngineRoot "C:\Program Files\Epic Games\UE_5.8"
```

This exclusively creates `90-source-immutability.json` and rejects changed, missing or newly added
protected files, Git-status drift and branch/HEAD drift. Run it once at the end of the host sequence;
it cannot overwrite an existing receipt. A PASS establishes that the snapshotted source bytes did
not change during the run. It does not prove streaming, collision, cook or packaged persistence.

## Staged execution

1. **Snapshot:** require the source map, `_WP` map, 25 building assets, external actors and engine
   version; hash plugin, config, offline contracts, external objects and Landscape-named packages
   when present. An offline contract is required for the next route-preparation step.
2. **Ownership:** the current UE Python adapter inspects loaded Landscape actors and components.
   It does not enumerate unloaded actor descriptors or prove partition ownership. Its receipt is
   `NOT_RUN_OWNERSHIP_AUDIT` until a host-verified descriptor/proxy inventory exists.
3. **Cook:** `cook_xinyi_wp.ps1` is commandlet scaffolding and records an exit code and log.
   It does not yet isolate cooked output, inventory packages, reject Editor-module runtime
   references, or prove packaged reachability. A `PASS_COOK_COMMANDLET` receipt is only a
   commandlet result; keep the Issue #8 cook gate open.
4. **Packaged streaming:** `XinyiHostStreamingProbe` and `run_packaged_streaming.ps1` now launch the
   Development executable into the explicit map and traverse all 27 contract points twice in distinct
   fresh processes. The engine records source arrival, completion/wait time, loaded runtime cell names,
   tile asset identities, placement drift, terrain ownership and load/unload transitions. The host
   validates the child PIDs, executable/raw/log hashes, marker order and both empty outside controls.
   This subgate passed on run `20260929T002733Z-44199b81`; see
   `docs/xinyi-issue8-packaged-streaming-result.md`. This measures runtime streaming, not the wider
   cook/reachability, collision or performance gates.
5. **Landscape traces:** test all component centers, both sides of internal seams, internal corners
   and outside controls. Keep render ownership and collision ownership separate in the receipt.
6. **Building collision:** run independent positive roof/facade hits and negative street/courtyard/gap
   misses across low/high-rise and border cases, with distinct terrain/building channels. Do not
   mutate collision policy in this gate.
7. **Performance:** use the same packaged route/viewpoints for labelled cold and warm runs. Record
   startup-to-ready, frame-time samples and p50/p95/p99, worst streaming hitch, RAM/GPU memory when
   available, mesh draws/primitives and actor/component counts. There is deliberately no budget yet.

The snapshot writes a JSON receipt using `xinyi-host-gate/v1`. The packaged streaming path now
records route/snapshot and executable/raw/log hashes; end-to-end lineage for the remaining gates is
not implemented yet. Never edit a completed receipt.
Resume at the first missing stage; do not rerun
an expensive passing stage unless an input, engine build, map/package hash or policy changes.
The normative envelope is `tools/unreal_xinyi_v2/schemas/host-gate-receipt.schema.json`; the
dependency-free validator enforces the critical runtime/static distinction in Cloud and on Windows.

## Current implementation boundary

The snapshot and route-preparation stages remain fail-closed. `run_host_gates.ps1` stops after
snapshot; call the route wrapper separately with that run ID. The independent generic JSON streaming,
collision and performance helpers still perform diagnostics on supplied data and cannot authenticate
its source. The packaged streaming path is separate: the opt-in runtime plugin writes engine
observations, the host launcher records the actual two process launches and file hashes, and
`validate_packaged_streaming.py` checks provenance plus the generic streaming semantics. Do not
promote a generic `NOT_RUN_*` diagnostic into a runtime PASS. The packaged streaming receipt is
`PASS_PACKAGED_STREAMING` only when this complete host path passes.

The streaming diagnostic requires `--observations` and `--repeat-observations` from two distinct
reported processes, each containing one observation for every planned stop in order. Each
point records its source location, completion flag and wait time, loaded tile IDs and actor count,
load/unload deltas, Landscape render/collision component counts, missing references, placement drift,
hitch and errors. The capture also names the run, map, fresh packaged process, route-plan SHA-256
and snapshot SHA-256. The analyzer compares all tile IDs with the accepted contract, requires every
tile at its center, both controls empty, an observed load and unload for each tile, and identical
ordered membership/delta/terrain inventories across the two captures. The distinct-process fields
are supplied data, so these checks cannot authenticate that either process actually ran.

## Receipt status vocabulary

- `PASS_SNAPSHOT`: required files were hashed without source mutation.
- `PASS_SOURCE_IMMUTABILITY`: protected files and Git state still match the snapshot; not runtime PASS.
- `NOT_RUN_OWNERSHIP_AUDIT`: partial loaded-actor inventory; descriptor/proxy ownership still open.
- `PASS_COOK_COMMANDLET`: cook postconditions and manifests passed; not packaged runtime PASS.
- `PASS_PACKAGED_STREAMING`: two host-attested fresh Development game processes completed the full
  27-point source-driven route, with the expected load/unload/terrain observations and no gate errors.
- `NOT_RUN_PACKAGED_STREAMING`: external observation JSON passed partial checks; no runtime provenance.
- `NOT_RUN_LANDSCAPE_TRACES` / `NOT_RUN_BUILDING_COLLISION`: external trace JSON passed partial checks.
- `NOT_RUN_PERFORMANCE_CAPTURE`: supplied samples were summarized; no runtime provenance or budget.
- `FAIL_*` / `NOT_RUN_*`: never promote or reinterpret as success.
