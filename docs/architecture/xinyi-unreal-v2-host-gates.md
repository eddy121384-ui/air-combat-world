# XinyiV2 UE5.8 host gates

Status: workstation tooling contract; **no runtime result**

## First command

From a clean PowerShell session with every Unreal process closed:

```powershell
tools/unreal_xinyi_v2/snapshot_host_state.ps1 -EngineRoot "C:\Program Files\Epic Games\UE_5.8"
```

The command creates a new immutable run directory under
`unreal/Saved/XinyiHostGates/<UTC>-<commit>/`. It uses exclusive receipt creation and never deletes,
saves, converts, imports, or edits a source package. A repeated run receives a new ID; an explicit
existing ID fails rather than overwriting evidence.

## Staged execution

1. **Snapshot:** require the source map, `_WP` map, 25 building assets, external actors and engine
   version; hash plugin, config, external objects and Landscape-named packages when present.
2. **Ownership:** in a fresh editor process, inventory Landscape roots, streaming proxies,
   components, heightfield collision components, actor descriptors, packages and runtime grids.
3. **Cook:** explicitly cook `/Game/XinyiV2/L_XinyiV2_Contract_WP` into a clean staging directory;
   preserve logs and manifests. Commandlet exit zero is only `PASS_COOK_COMMANDLET`, never packaged
   runtime PASS. Reject Editor-module runtime references and missing external actor/mesh/Landscape
   packages.
4. **Packaged streaming:** launch the packaged executable into the explicit map, execute the route in
   `host_gate_definitions.json`, and record source arrival, streaming-complete/timeout duration,
   runtime cell identity, actor GUID/package/tile identity, bounds and load/unload transitions. Both
   outside controls require zero building tiles. Fail if all 25 remain loaded for the full route.
5. **Landscape traces:** test all component centers, both sides of internal seams, internal corners
   and outside controls. Keep render ownership and collision ownership separate in the receipt.
6. **Building collision:** run independent positive roof/facade hits and negative street/courtyard/gap
   misses across low/high-rise and border cases, with distinct terrain/building channels. Do not
   mutate collision policy in this gate.
7. **Performance:** use the same packaged route/viewpoints for labelled cold and warm runs. Record
   startup-to-ready, frame-time samples and p50/p95/p99, worst streaming hitch, RAM/GPU memory when
   available, mesh draws/primitives and actor/component counts. There is deliberately no budget yet.

Every stage writes one JSON receipt using `xinyi-host-gate/v1`, inside the same run directory, with
input receipt hashes. Never edit a completed receipt. Resume at the first missing stage; do not rerun
an expensive passing stage unless an input, engine build, map/package hash or policy changes.
The normative envelope is `tools/unreal_xinyi_v2/schemas/host-gate-receipt.schema.json`; the
dependency-free validator enforces the critical runtime/static distinction in Cloud and on Windows.

## Current implementation boundary

The snapshot stage is executable and fail-closed. Later stage definitions are deliberately data-only
until their exact UE5.8 APIs are tested on the accepted workstation world. `run_host_gates.ps1`
therefore stops after preserving the snapshot rather than manufacturing a green receipt. A script
that says “not run” is less glamorous than a fake PASS, but considerably more useful.

## Receipt status vocabulary

- `PASS_SNAPSHOT`: required files were hashed without source mutation.
- `PASS_OWNERSHIP_AUDIT`: complete static ownership inventory; not streaming PASS.
- `PASS_COOK_COMMANDLET`: cook postconditions and manifests passed; not packaged runtime PASS.
- `PASS_PACKAGED_STREAMING`: packaged route observed required load/unload and controls.
- `PASS_LANDSCAPE_TRACES`: packaged ownership/seam/boundary traces passed.
- `PASS_BUILDING_COLLISION`: positive and negative-space packaged trace corpus passed.
- `PASS_PERFORMANCE_CAPTURE`: required metrics were captured; it does not mean a budget passed.
- `FAIL_*` / `NOT_RUN`: never promote or reinterpret as success.
