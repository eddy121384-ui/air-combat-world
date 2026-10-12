"""Run the UNMODIFIED Xinyi Blender imported-buffer audit on an NTW pilot tile set (Windows-safe).

tools/citygen_v2/blender_full_xinyi_audit.py imports the Unix-only `resource` module (it was written for the Linux
CI). Rather than edit the accepted audit, this wrapper installs a stand-in `resource` (max_rss reported as 0)
and then executes the audit verbatim via runpy.

usage (from repo root):
  blender -b --python tools/ntw/run_blender_audit.py -- --tiles <dir/tiles> --numerical <dir/pilot.report.json> \
          --out <audit.json> --screenshots <dir>
"""
import runpy
import sys
import types
from pathlib import Path

try:
    import resource  # noqa: F401
except ImportError:
    stub = types.ModuleType("resource")
    stub.RUSAGE_SELF = 0
    stub.getrusage = lambda _who: types.SimpleNamespace(ru_maxrss=0)
    sys.modules["resource"] = stub

AUDIT = Path(__file__).resolve().parents[1] / "citygen_v2" / "blender_full_xinyi_audit.py"
runpy.run_path(str(AUDIT), run_name="__main__")
