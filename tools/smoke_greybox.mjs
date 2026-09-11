// Smoke: full greybox-core chain in documented order (GATE A–F structural).
// Usage: node tools/smoke_greybox.mjs [--skip-fetch]
//   --skip-fetch: reuse existing data/generated (offline rerun).
// Steps: fetch sample -> worldmodel -> tile GLB -> copy to godot assets ->
//        scene-reference check -> unittest.
import { copyFile, mkdir } from "node:fs/promises";
import { execFile } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { existsSync, readFileSync } from "node:fs";

const run = promisify(execFile);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..");
const skipFetch = process.argv.includes("--skip-fetch");

async function step(label, cmd, args, cwd) {
  console.log(`\n### ${label}\n$ ${cmd} ${args.join(" ")}`);
  const { stdout, stderr } = await run(cmd, args, { cwd, timeout: 590000 });
  if (stdout.trim()) console.log(stdout.trim().split("\n").slice(-6).join("\n"));
  if (stderr.trim()) console.error(stderr.trim().split("\n").slice(-4).join("\n"));
}

if (!skipFetch) await step("GATE A — fetch", "node", ["tools/taipei/fetch_sample.mjs"], REPO);
await step("GATE B — worldmodel", "python", ["worldmodel.py"], path.join(REPO, "tools/compiler"));
await step("GATE C/D/E — tile + hero", "python", ["build_tile.py"], path.join(REPO, "tools/compiler"));

// install tile into the Godot project tree (gitignored copy)
const src = path.join(REPO, "data/generated/taipei/xinyi_tile_2km.glb");
const dstDir = path.join(REPO, "godot/greybox/assets");
await mkdir(dstDir, { recursive: true });
await copyFile(src, path.join(dstDir, "xinyi_tile_2km.glb"));
console.log(`\n### installed tile -> godot/greybox/assets/xinyi_tile_2km.glb`);

// GATE F (structural): scene references resolve
const tscn = readFileSync(path.join(REPO, "godot/greybox/scenes/greybox.tscn"), "utf8");
for (const ref of ["res://assets/xinyi_tile_2km.glb", "res://scripts/debug_camera.gd"]) {
  if (!tscn.includes(ref)) throw new Error(`scene missing reference: ${ref}`);
  const disk = path.join(REPO, "godot/greybox", ref.replace("res://", ""));
  if (!existsSync(disk)) throw new Error(`referenced file not on disk: ${ref}`);
  console.log(`ref OK: ${ref}`);
}

await step("Phase 6 — tests", "python", ["-m", "unittest", "discover", "-s", "tests"], REPO);
console.log("\nSMOKE PASS (structural; in-engine visual pending — no engine on build machine)");
