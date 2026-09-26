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
2. **Ownership:** the current UE Python adapter inspects loaded Landscape actors and components.
   It does not enumerate unloaded actor descriptors or prove partition ownership. Its receipt is
   `NOT_RUN_OWNERSHIP_AUDIT` until a host-verified descriptor/proxy inventory exists.
3. **Cook:** `cook_xinyi_wp.ps1` is commandlet scaffolding and records an exit code and log.
   It does not yet isolate cooked output, inventory packages, reject Editor-module runtime
   references, or prove packaged reachability. A `PASS_COOK_COMMANDLET` receipt is only a
   commandlet result; keep the Issue #8 cook gate open.
4. **Packaged streaming:** launch the packaged executable into the explicit map, execute the route in
   `host_gate_definitions.json` (its seven example points are incomplete; derive all 25 tile
   centers from the accepted contract), and record source arrival, streaming-complete/timeout duration,
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

The snapshot writes a JSON receipt using `xinyi-host-gate/v1`. Input-receipt hashes and
end-to-end lineage for later stages are not implemented yet. Never edit a completed receipt.
Resume at the first missing stage; do not rerun
an expensive passing stage unless an input, engine build, map/package hash or policy changes.
The normative envelope is `tools/unreal_xinyi_v2/schemas/host-gate-receipt.schema.json`; the
dependency-free validator enforces the critical runtime/static distinction in Cloud and on Windows.

## Current implementation boundary

The snapshot stage is executable and fail-closed. `run_host_gates.ps1` stops after snapshot.
The JSON streaming, collision and performance helpers perform diagnostics on supplied data;
they cannot authenticate its source and now emit `NOT_RUN_*` (or `FAIL_*` on bad data), with
`runtime_validation=false`. No packaged runtime producer or full-route driver exists yet.
Do not promote a diagnostic result into an Issue #8 PASS.

## Receipt status vocabulary

- `PASS_SNAPSHOT`: required files were hashed without source mutation.
- `NOT_RUN_OWNERSHIP_AUDIT`: partial loaded-actor inventory; descriptor/proxy ownership still open.
- `PASS_COOK_COMMANDLET`: cook postconditions and manifests passed; not packaged runtime PASS.
- `NOT_RUN_PACKAGED_STREAMING`: external observation JSON passed partial checks; no runtime provenance.
- `NOT_RUN_LANDSCAPE_TRACES` / `NOT_RUN_BUILDING_COLLISION`: external trace JSON passed partial checks.
- `NOT_RUN_PERFORMANCE_CAPTURE`: supplied samples were summarized; no runtime provenance or budget.
- `FAIL_*` / `NOT_RUN_*`: never promote or reinterpret as success.
