"""North Taiwan forest world v1, stage 4 (UnrealEditor-Cmd): native Movie Render Queue configs (recipe of hf_mrq_configs.py, PR #31).

One config per sequence in nf_sequence.report.json (ACW_NF_MRQ_ONLY = comma list, default LS_NF_Stills,LS_NF_Flight): PNG,
1920x1080, sequence frame rate, deferred pass, 1 spatial / 1 temporal sample, engine/render warm-up frames so TSR history and World
Partition streaming settle at the first frame, no game / LOD overrides. Renders run in standalone -game (tools/ntw/forest_world/run_nf_mrq.ps1).
ACW_NF_MRQ_REV names the attempt (output folder). Receipt: reports/nf_mrq_configs.report.json.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from nf_common import MAP, OUT, lib, tools, write_report  # noqa: E402

REV = os.environ.get("ACW_NF_MRQ_REV", "01")
ONLY = os.environ.get("ACW_NF_MRQ_ONLY", "LS_NF_Stills,LS_NF_Flight").split(",")
CVARS = {k: float(v) for k, v in (kv.split("=") for kv in os.environ.get("ACW_NF_MRQ_CVARS", "").split(",") if kv)}
seqs = json.loads((OUT / "reports" / "nf_sequence.report.json").read_text(encoding="utf-8"))
for extra in sorted((OUT / "reports").glob("nf_sequence_*.report.json")):   # sequence revisions
    seqs["sequences"].update(json.loads(extra.read_text(encoding="utf-8"))["sequences"])
configs, err = [], None
try:
    for name in ONLY:
        row = seqs["sequences"][name]
        tag = "nf_%s_%s" % (name.replace("LS_NF_", "").lower(), REV)
        folder = OUT / "movies" / tag
        if folder.exists():
            raise RuntimeError("exists: %s" % folder)
        folder.mkdir(parents=True)
        cname = "MRQ_" + tag
        dest = MAP.replace("/Maps", "/Sequences") + "/" + cname
        if lib.does_asset_exist(dest):
            raise RuntimeError("exists: " + dest)
        c = tools.create_asset(cname, dest.rsplit("/", 1)[0], unreal.MoviePipelinePrimaryConfig, unreal.MoviePipelinePrimaryConfigFactory())
        out = c.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
        for k, v in {"output_directory": unreal.DirectoryPath(str(folder / "frames")), "file_name_format": "frame_{frame_number}",
                     "output_resolution": unreal.IntPoint(1920, 1080), "use_custom_frame_rate": False, "override_existing_output": False,
                     "zero_pad_frame_numbers": 4, "handle_frame_count": 0, "output_frame_step": 1}.items():
            out.set_editor_property(k, v)
        if os.environ.get("ACW_NF_MRQ_RANGE"):   # diagnostic renders of a sub-range (e.g. one held still)
            r0, r1 = (int(x) for x in os.environ["ACW_NF_MRQ_RANGE"].split(","))
            for k, v in {"use_custom_playback_range": True, "custom_start_frame": r0, "custom_end_frame": r1}.items():
                out.set_editor_property(k, v)
        if os.environ.get("ACW_NF_MRQ_STEP"):   # review renders: write every Nth frame only
            out.set_editor_property("output_frame_step", int(os.environ["ACW_NF_MRQ_STEP"]))
        game = c.find_or_add_setting_by_class(unreal.MoviePipelineGameOverrideSetting)
        for k in ["cinematic_quality_settings", "use_lod_zero", "disable_hlods", "use_high_quality_shadows", "override_view_distance_scale",
                  "flush_grass_streaming", "override_grass_cull_distance_scale", "override_grass_density_scale", "flush_streaming_managers",
                  "override_virtual_texture_feedback_factor"]:
            game.set_editor_property(k, False)
        game.set_is_enabled(False)
        aa = c.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
        for k, v in {"spatial_sample_count": 1, "temporal_sample_count": 1, "override_anti_aliasing": False, "engine_warm_up_count": 90,
                     "render_warm_up_count": 32, "use_camera_cut_for_warm_up": False}.items():
            aa.set_editor_property(k, v)
        c.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
        c.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
        cv = c.find_or_add_setting_by_class(unreal.MoviePipelineConsoleVariableSetting)
        for k, v in dict({"r.ScreenPercentage": 100., "r.MotionBlurQuality": 0., "r.RayTracing": 0.}, **CVARS).items():
            if not cv.add_or_update_console_variable(k, v):
                raise RuntimeError("cvar " + k)
        if not lib.save_asset(dest):
            raise RuntimeError("save " + dest)
        configs.append({"tag": tag, "sequence": row["path"], "frames": row["frames"], "config": c.get_path_name(), "map": MAP + "/L_NF_Yangmingshan",
                        "output_directory": str(folder / "frames"), "cvars": CVARS})
    status = "PASS_NF_MRQ_CONFIGS"
except Exception:  # noqa: BLE001
    status, err = "FAIL_NF_MRQ_CONFIGS", traceback.format_exc()
    unreal.log_error(err)
write_report("nf_mrq_configs_%s.report.json" % REV, {"status": status, "configs": configs, "error": err})
unreal.SystemLibrary.quit_editor()
