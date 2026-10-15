"""TreeLookdev moving-camera gate, stage 2 (UnrealEditor-Cmd): native Movie Render Queue configs, one per (condition, path).
Same settings policy as the ForestSpike B1a native clips: PNG, 1920x1080, 60 fps, deferred pass, 1 spatial / 1 temporal sample, no AA override, no
cinematic / game / LOD overrides, foliage + view-distance cvars at defaults. Env ACW_TL_FLIGHT_REV (default 01) is part of the output folder name.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
import unreal  # noqa: E402
from tl_common import OUT, ROOT, lib, write_report  # noqa: E402

REV = os.environ.get("ACW_TL_FLIGHT_REV", "01")
build = json.loads((OUT / "reports" / "tl_flight_build.report.json").read_text(encoding="utf-8"))
tools = unreal.AssetToolsHelpers.get_asset_tools()
configs, err = [], None
try:
    for row in build["maps"]:
        if row["cond"] not in os.environ.get("ACW_TL_FLIGHT_CONDS", "A,D").split(","):
            continue
        tag = "mrq_%s_%s_%s" % (row["cond"], row["path"], REV)
        folder = OUT / "flight" / "movies" / tag
        if folder.exists():
            raise RuntimeError("exists: %s" % folder)
        folder.mkdir(parents=True)
        name = "MRQ_" + tag
        folder_asset = row["map"].rsplit("/", 1)[0]
        dest = folder_asset + "/" + name
        if lib.does_asset_exist(dest):
            lib.delete_asset(dest)
        c = tools.create_asset(name, folder_asset, unreal.MoviePipelinePrimaryConfig, unreal.MoviePipelinePrimaryConfigFactory())
        out = c.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
        end = row["frames"] + 1
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
                     "r.ViewDistanceScale": 1., "r.ScreenPercentage": 100., "r.MotionBlurQuality": 0., "r.RayTracing": 0.,
                     **({"r.TextureStreaming": 0.} if os.environ.get("ACW_TL_FLIGHT_NOSTREAM") == "1" else {})}.items():
            if not cv.add_or_update_console_variable(k, v):
                raise RuntimeError("cvar " + k)
        if not lib.save_asset(dest):
            raise RuntimeError("save " + dest)
        configs.append({"tag": tag, "cond": row["cond"], "path": row["path"], "config": c.get_path_name(), "map": row["map"], "sequence": row["sequence"],
                        "frames": end, "output_directory": str(folder / "frames"), "game_overrides_enabled": game.is_enabled()})
    status = "PASS_TL_FLIGHT_MRQ_CONFIGS"
except Exception:  # noqa: BLE001
    status, err = "FAIL_TL_FLIGHT_MRQ_CONFIGS", traceback.format_exc()
    unreal.log_error(err)
write_report("tl_flight_mrq_configs.report.json", {"status": status, "configs": configs, "error": err})
unreal.SystemLibrary.quit_editor()
