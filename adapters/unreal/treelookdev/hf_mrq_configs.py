"""Hillside forest look-dev v1, stage 3 (UnrealEditor-Cmd): native Movie Render Queue configs (PR #31 policy, tl_flight_mrq_configs.py).

One config per sequence map of hf_build.report.json (stills_forest, stills_empty, flight_forest): PNG, 1920x1080, 60 fps, deferred pass,
1 spatial / 1 temporal sample, no AA override, no cinematic / game / LOD overrides, LOD / view-distance cvars at defaults. Renders run in
standalone -game (tools/forest/run_hf_mrq.ps1), the only mode in which an unsaved ISM usage flag shows up as grey HISMs.
Env ACW_HF_MRQ_REV (default 01) is part of the output folder name; ACW_HF_MRQ_ONLY = comma list of map keys.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_common import OUT, lib, write_report  # noqa: E402

REV = os.environ.get("ACW_HF_MRQ_REV", "01")
ONLY = os.environ.get("ACW_HF_MRQ_ONLY", "stills_forest,stills_empty,flight_forest").split(",")
build = json.loads((OUT / "reports" / "hf_build.report.json").read_text(encoding="utf-8"))
tools = unreal.AssetToolsHelpers.get_asset_tools()
configs, err = [], None
try:
    for key in ONLY:
        row = build["maps"][key]
        tag = "hf_%s_%s_%s" % (key, build["rev"], REV)
        folder = OUT / "hillside" / "movies" / tag
        if folder.exists():
            raise RuntimeError("exists: %s" % folder)
        folder.mkdir(parents=True)
        name = "MRQ_" + tag
        folder_asset = row["map"].rsplit("/", 1)[0]
        dest = folder_asset + "/" + name
        if lib.does_asset_exist(dest):
            raise RuntimeError("exists: " + dest)
        c = tools.create_asset(name, folder_asset, unreal.MoviePipelinePrimaryConfig, unreal.MoviePipelinePrimaryConfigFactory())
        out = c.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
        end = row["frames"]
        for k, v in {"output_directory": unreal.DirectoryPath(str(folder / "frames")), "file_name_format": "frame_{frame_number}",
                     "output_resolution": unreal.IntPoint(1920, 1080), "use_custom_frame_rate": True, "output_frame_rate": unreal.FrameRate(60, 1),
                     "override_existing_output": False, "use_custom_playback_range": True, "custom_start_frame": 0, "custom_end_frame": end,
                     "zero_pad_frame_numbers": 4, "handle_frame_count": 0, "output_frame_step": 1}.items():
            out.set_editor_property(k, v)
        game = c.find_or_add_setting_by_class(unreal.MoviePipelineGameOverrideSetting)
        for k in ["cinematic_quality_settings", "use_lod_zero", "disable_hlods", "use_high_quality_shadows", "override_view_distance_scale",
                  "flush_grass_streaming", "override_grass_cull_distance_scale", "override_grass_density_scale", "flush_streaming_managers",
                  "override_virtual_texture_feedback_factor"]:
            game.set_editor_property(k, False)
        game.set_is_enabled(False)
        aa = c.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
        for k, v in {"spatial_sample_count": 1, "temporal_sample_count": 1, "override_anti_aliasing": False, "engine_warm_up_count": 0,
                     "render_warm_up_count": 0, "use_camera_cut_for_warm_up": False}.items():
            aa.set_editor_property(k, v)
        c.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
        c.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
        cv = c.find_or_add_setting_by_class(unreal.MoviePipelineConsoleVariableSetting)
        for k, v in {"foliage.ForceLOD": -1., "r.ForceLOD": -1., "foliage.LODDistanceScale": 1., "foliage.RandomLODRange": 0.,
                     "r.ViewDistanceScale": 1., "r.ScreenPercentage": 100., "r.MotionBlurQuality": 0., "r.RayTracing": 0.}.items():
            if not cv.add_or_update_console_variable(k, v):
                raise RuntimeError("cvar " + k)
        if not lib.save_asset(dest):
            raise RuntimeError("save " + dest)
        configs.append({"tag": tag, "key": key, "config": c.get_path_name(), "map": row["map"], "sequence": row["sequence"], "frames": end,
                        "still_frames": row.get("still_frames"), "output_directory": str(folder / "frames"), "game_overrides_enabled": game.is_enabled()})
    status = "PASS_HF_MRQ_CONFIGS"
except Exception:  # noqa: BLE001
    status, err = "FAIL_HF_MRQ_CONFIGS", traceback.format_exc()
    unreal.log_error(err)
write_report("hf_mrq_configs.report.json", {"status": status, "configs": configs, "error": err})
unreal.SystemLibrary.quit_editor()
