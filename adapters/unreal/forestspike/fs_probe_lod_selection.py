"""Diagnostic only: existing capture backend, transient forced-LOD comparison.

No asset/level saves. Refuses an existing evidence set. Jobs include automatic
selection (-1), forced 0/1/2 under identical unlit ID rendering.
"""
import json
import os
import sys
from pathlib import Path

import unreal

repo = Path(os.environ["ACW_REPO_ROOT"])
sys.path.insert(0, str(repo / "adapters/unreal/forestspike"))
spec = json.loads(Path(os.environ["ACW_FS_SPEC"]).read_text())
out = repo / "unreal/ForestSpike/Saved/ForestSpike"
if (out / "captures" / spec["set"]).exists() or (out / "reports" / ("fs_capture.%s.report.json" % spec["set"])).exists():
    raise RuntimeError("refusing to overwrite diagnostic evidence")
import fs_capture

original_configure = fs_capture.configure


def configure(job):
    original_configure(job)
    # Match the real 500m test cull even though ID jobs normally disable cull.
    for component in [fs_capture.hism_a] + fs_capture.hism_b:
        component.set_cull_distances(0, 50000)
    force = int(job["force_lod"])
    unreal.SystemLibrary.execute_console_command(fs_capture.world, "foliage.ForceLOD %d" % force)
    actual = unreal.SystemLibrary.get_console_variable_int_value("foliage.ForceLOD")
    if actual != force:
        raise RuntimeError("force LOD command readback mismatch")
    job["force_lod_cvar_readback"] = actual


fs_capture.configure = configure
