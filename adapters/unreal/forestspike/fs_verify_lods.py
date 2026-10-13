"""Read existing ForestSpike render LODs without importing, saving or changing assets.

ACW_REPO_ROOT: existing B0 checkout. ACW_FS_LOD_REPORT: NEW receipt path.
Source filenames/settings are evidence, never a substitute for render triangles.
"""
import datetime
import hashlib
import json
import os
import traceback
from pathlib import Path

import unreal

repo = Path(os.environ["ACW_REPO_ROOT"])
report_path = Path(os.environ["ACW_FS_LOD_REPORT"])
if report_path.exists():
    raise RuntimeError("Refusing to overwrite LOD evidence: " + str(report_path))
report = {"schema": "forestspike.lod_readback/1", "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "engine": unreal.SystemLibrary.get_engine_version(), "run_id": os.environ["ACW_FS_RUN_ID"],
          "status": "FAIL_FS_LOD_READBACK", "failures": [], "sources": [], "meshes": [], "sequence_audit": []}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def property_or_error(obj, name):
    try:
        return str(obj.get_editor_property(name))
    except Exception as exc:
        return {"unavailable": str(exc)}


try:
    manifest = json.loads((repo / "assets/forestspike/b0/pr18_manifest.json").read_text(encoding="utf-8"))
    originals = Path(os.environ["ACW_FS_PR18_ROOT"])
    report["pr18_manifest_sha256"] = sha(repo / "assets/forestspike/b0/pr18_manifest.json")
    original_manifest = originals / "manifest.json"
    if sha(original_manifest) != report["pr18_manifest_sha256"]:
        report["failures"].append("PR18 manifest byte mismatch")
    for asset in manifest["assets"] + [manifest["reference_original"]]:
        name = Path(asset["filename"]).name
        copy = repo / "assets/forestspike/b0/models" / name
        original = originals / asset["filename"]
        row = {"filename": name, "expected_sha256": asset["sha256"], "copy_sha256": sha(copy),
               "pr18_sha256": sha(original), "expected_triangles": asset["triangles"]}
        row["pass"] = row["expected_sha256"] == row["copy_sha256"] == row["pr18_sha256"]
        report["sources"].append(row)
        if not row["pass"]:
            report["failures"].append("source hash mismatch: " + name)
    assets = json.loads((repo / "unreal/ForestSpike/Saved/ForestSpike/reports/fs_assets.report.json").read_text())
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for key, rec in assets["meshes"].items():
        mesh = unreal.EditorAssetLibrary.load_asset(rec["asset"])
        count = int(mesh.get_num_lods())
        row = {"name": key, "asset": rec["asset"], "render_lod_count": count,
               "source_lod_count": int(sub.get_lod_count(mesh)),
               "triangles": [int(mesh.get_num_triangles(i)) for i in range(count)],
               "vertices": [int(mesh.get_num_vertices(i)) for i in range(count)],
               "screen_sizes": list(sub.get_lod_screen_sizes(mesh)),
               "source_models": property_or_error(mesh, "source_models"),
               "asset_import_data": property_or_error(mesh, "asset_import_data"),
               "nanite_settings": property_or_error(mesh, "nanite_settings"),
               "lod_selection_status": "NOT_VERIFIED_RUNTIME"}
        row["reduction_settings"] = [str(sub.get_lod_reduction_settings(mesh, i)) for i in range(row["source_lod_count"])]
        if key.startswith("Tree_B_"):
            arch = key[len("Tree_B_"):]
            expected = [a["triangles"] for a in sorted(manifest["assets"], key=lambda a: a.get("lod", 0))
                        if a.get("archetype") == arch]
            row["expected_triangles"] = expected
            row["triangles_pass"] = row["triangles"] == expected and count == 3
            if not row["triangles_pass"]:
                report["failures"].append({"mesh": key, "expected": expected, "actual": row["triangles"]})
        report["meshes"].append(row)
    if os.environ.get("ACW_FS_AUDIT_SEQUENCES") == "1":
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        for arm in ("A", "B"):
            name = arm + "_S1_v3i_t14_t32"
            audit = {"name": name, "status": "NOT_VERIFIED"}
            try:
                level_path = "/Game/ForestSpike/Perf/L_FSP_" + name
                if not levels.load_level(level_path):
                    raise RuntimeError("load failed: " + level_path)
                world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
                cameras = [a for a in actors.get_all_level_actors() if a.get_actor_label() == "FS_PerfCamera"]
                audit["cameras"] = [c.get_path_name() for c in cameras]
                seq = unreal.EditorAssetLibrary.load_asset("/Game/ForestSpike/Perf/LS_FSP_" + name)
                audit["playback_start"] = seq.get_playback_start()
                audit["playback_end"] = seq.get_playback_end()
                audit["bindings"] = []
                for binding in seq.get_bindings():
                    objects = unreal.MovieSceneSequenceExtensions.locate_bound_objects(seq, binding, world)
                    audit["bindings"].append({"name": str(binding.get_name()),
                                              "resolved_objects": [o.get_path_name() for o in objects]})
                audit["status"] = "BOUND_CAMERA" if cameras and any(c.get_path_name() in b["resolved_objects"] for c in cameras for b in audit["bindings"]) else "FAIL_CAMERA_BINDING"
            except Exception:
                audit["error"] = traceback.format_exc()
            report["sequence_audit"].append(audit)
    if not report["failures"]:
        report["status"] = "PARTIAL_FS_LOD_READBACK_RUNTIME_SELECTION_REQUIRED"
except Exception:
    report["failures"].append(traceback.format_exc())
report["completed_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
report_path.parent.mkdir(parents=True, exist_ok=True)
with report_path.open("x", encoding="utf-8") as out:
    json.dump(report, out, indent=2)
    out.write("\n")
unreal.log("FS_LOD_READBACK " + report["status"] + " " + str(report_path))
unreal.SystemLibrary.quit_editor()
