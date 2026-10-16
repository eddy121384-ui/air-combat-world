# Skyfront Homeland — Agent Guide

Applies repo-wide to Claude Code, Codex, and other coding agents. Keep this file short; task-specific contracts belong in `docs/`.

## Start with the current state

- This is a mobile-first air-combat game; Unreal Engine 5.8 and Taipei/Xinyi are active development tracks.
- Inspect the current branch, working tree, relevant issues/PRs, and latest test evidence before changing anything.
- Treat dated status reports as evidence, not timeless instructions; never promote a historical FAIL to PASS.
- For city geometry, read `docs/architecture/xinyi-citygen-v2.md` and `docs/architecture/xinyi-citygen-guardrails.md`.
- For terrain/placement, read `docs/architecture/xinyi-terrain-integration-plan.md` and newer accepted evidence.

## Engineering style

- Do the smallest change that solves the assigned problem. Prefer established libraries and existing scripts.
- Avoid speculative refactors, new abstractions, elaborate harnesses, and unrelated cleanup.
- Do not expand scope or change accepted geometry, art, runtime policy, or test thresholds without justification and approval.
- Keep reproducible inputs, provenance, source hashes, and useful failure evidence.
- Do not weaken QA, add building-specific exceptions, or tune acceptance criteria merely to pass a gate.

## Branches, worktrees, and concurrent agents

- Work on the assigned branch/worktree; use a separate branch for unrelated work. Do not merge PRs without authorization.
- Before host-heavy work, check for other Unreal processes and concurrent sessions.
- Do not reset, stash, discard, overwrite, or delete another agent's files, builds, or worktree.
- Protect accepted Unreal world assets, source GLBs, manifests, and local Git stashes, including uncommitted assets.
- If required input is missing or ownership is unclear, stop and ask instead of regenerating or restoring blindly.

## Validation and reporting

- Run proportionate tests for the change; distinguish local tests, CI, packaged Unreal runtime, visual QA, and performance.
- A test PASS proves only the gate it actually exercised. Record failures, unknowns, contamination, and inherited evidence explicitly.
- Predefine bounded repeat tests when diagnosing intermittent failures; do not retry until green or change rules after failures.
- Keep PRs Draft while their required acceptance gates remain open; never claim unverified correctness or performance.
- Report concise results: changed files, commit/PR, tests, unresolved risks, and next action.

## Xinyi production invariants

- Production building inputs use precision-preserving EPSG:3826 → ENU, not the coarse EPSG:4326 forensic snapshot.
- Preserve deterministic 500 m tile ownership, holes/courtyards, hero suppression, and full source-part accounting.
- Float32-quantize tile-local footprints before GEOS revalidation and constrained Delaunay triangulation.
- Validate actual exported GLBs and Blender-imported meshes before Unreal; do not repair upstream defects inside Unreal.
- Source, CRS, dependency, tile, or QA-policy changes require the regression gates specified by the citygen guardrails.

## Unreal build and disk hygiene

- Check available disk space and estimate peak temporary usage before large Cook/Build/test batches.
- Reuse hash-verified packages; avoid repeated gigabyte-scale copies. Hardlink only immutable payloads on the same volume.
- Keep per-run writable `Saved`, logs, and receipts separate; never modify a shared hardlinked package in place.
- After a batch, retain necessary raw evidence and at least one verified reproducible package for an active gate.
- Inventory obsolete duplicate packages, staged builds, and temporary Cook outputs; clean only confirmed-safe artifacts.
- Check active processes, other worktrees, hardlink references, and protected-file hashes before deletion.
- Do not silently purge accepted assets, source data, stashes, historical evidence, or shared caches.
- Report disk space reclaimed and what was deliberately retained; do not rebuild merely to verify a cleanup.

## Handoff

- Leave the repository understandable: scope, status, exact verification, known failures, and how to resume.
- Prefer a short PR/issue update over another large process document.
