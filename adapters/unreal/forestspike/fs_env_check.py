"""ForestSpike B0 stage 0: engine / RHI / GPU environment receipt (UE5.8 editor Python)."""
import json
import os
import platform
import time
from pathlib import Path

import unreal

out = Path(os.environ["ACW_FS_OUT"]) / "reports"
out.mkdir(parents=True, exist_ok=True)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def cvar(name):
    try:
        return unreal.SystemLibrary.get_console_variable_float_value(name)
    except Exception as e:  # noqa: BLE001
        return "ERR %s" % e


rep = {
    "status": "PASS_FS_ENV",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "rhi_adapter": unreal.SystemLibrary.get_rhi_adapter_name() if hasattr(unreal.SystemLibrary, "get_rhi_adapter_name") else None,
    "platform": platform.platform(),
    "cvars": {k: cvar(k) for k in (
        "r.DynamicGlobalIlluminationMethod", "r.ReflectionMethod", "r.Shadow.Virtual.Enable", "r.AntiAliasingMethod",
        "r.CustomDepth", "r.ScreenPercentage", "r.Nanite", "r.GPUCrashDebugging", "r.D3D12.GraphicsAdapter")},
    "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
}
(out / "env.report.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
unreal.log("FS_ENV " + json.dumps(rep))
unreal.SystemLibrary.quit_editor()
