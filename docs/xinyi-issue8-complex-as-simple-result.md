# XinyiV2 Complex-As-Simple collision result

Run `20260929T032005Z-93dbf36a` tested `CTF_UseComplexAsSimple` for the 25 Xinyi building tile meshes in a UE5.8 Windows Development package. The candidate used the same executable and cooked payload as the current-policy baseline. At runtime only, the probe changed each loaded building mesh `BodySetup` from trace flag enum 1 (`UseSimpleAndComplex`) to enum 3 (`UseComplexAsSimple`) and recreated the component physics state. It did not save packages or edit the accepted `_WP` world.

The exact previous 101-step corpus was reused (SHA-256 `b006d10276e955c9c0a2a2ce9ee77f00144c6d95e4b2e8767fc9332e244512ec`). Both runs completed source-driven World Partition streaming at every step. The candidate audited 25/25 original trace flags as enum 1, applied enum 3 to 25/25, and recreated 25 component physics states. All gameplay line traces and sweeps used `bTraceComplex=false`.

## Correctness

- The candidate produced a building hit for all 15 positive rays. Fourteen hits matched the corpus tile identity. `tile_boundary_mass` first hit adjacent tile `+000_+000` at 1,566.33 cm rather than expected tile `+001_+000`; the current convex baseline hit the expected tile at distance 0. The accepted collision validator requires the expected tile identity, so positive correctness is 14/15 and the gate fails. This is the same sample that failed the earlier complex-reference identity check.
- Certified negative space was clear in 27/27 candidate samples. The current convex baseline falsely blocked 17/27.
- Candidate sweeps passed all four expectations: the 50 cm sphere and 50x50x100 cm box remained clear through the certified gap, while the low-rise sphere and high-rise box blocked on their expected tiles.
- The transient 80 cm simulated box, with CCD and gravity disabled, generated a blocking hit against static tile `-003_-002` under the candidate policy.

## A/B observations

Both modes used executable SHA-256 `1567fee425193d9032332ce9d8729fe926ea4c27dd26a555c6277b5caad6f692` and the same 10,705,822-byte pak. The archive contains the baseline convex data and triangle data, so it measures runtime-policy cost under identical payload conditions; it does not estimate a production cook that removes unused convex data. The 239-byte archive-total difference in the host receipts is a second runtime-generated CrashReportClient INI, not payload growth.

| Measurement | Current convex | Complex-as-simple | Candidate / baseline |
|---|---:|---:|---:|
| BodySetup resource bytes | 25,169,660 | 25,136,009 | 0.9987x |
| Runtime peak process memory | 298,319,872 | 301,772,800 | 1.0116x |
| Host peak working set | 405,430,272 | 389,476,352 | 0.9606x |
| Host peak private bytes | 293,023,744 | 293,466,112 | 1.0015x |
| Median query average | 2.698 us | 2.282 us | 0.8457x |
| P95 query average | 3.184 us | 5.694 us | 1.7885x |
| Maximum query average | 7.623 us | 6.744 us | 0.8846x |
| Frame P95 | 1.853 ms | 1.946 ms | 1.0502x |
| Frame P99 | 3.248 ms | 3.459 ms | 1.0651x |
| Worst frame | 45.798 ms | 54.037 ms | 1.18098x |
| Maximum streaming wait | 324.257 ms | 327.514 ms | 1.0100x |

The measured runtime costs do not show an obvious blocking pathology in this corpus, though P95 query time and the single worst frame increased. Correctness decides this gate before a performance acceptance decision is needed.

Each process logged the same four optional profiler capture DLL load failures (`aqProf`, two VTune DLLs, and WinPixGpuCapturer). The validator found no candidate-specific runtime error. Post-run source immutability passed for all 107 protected rows.

Review evidence: [machine-readable A/B gate](evidence/xinyi-complex-as-simple-20260929/complex-as-simple-gate.json), [source immutability receipt](evidence/xinyi-complex-as-simple-20260929/source-immutability.json), and the previously committed [exact collision corpus](evidence/xinyi-host-collision-20260929/collision-plan.json). Full package, raw runtime JSON, host launch receipts, and logs remain uncommitted under `unreal/Saved/XinyiHostGates/20260929T032005Z-93dbf36a` on the validation host.

## Verdict

**COMPLEX-AS-SIMPLE = FAIL.** The candidate fixes all certified false-positive empty-space collisions and supports the required sweeps and simulated-object collision, but it does not satisfy the established 15/15 expected-tile positive contract. No accepted asset, world-partition configuration, terrain, geometry, placement, or source GLB was changed, and no follow-up architecture work was started.
