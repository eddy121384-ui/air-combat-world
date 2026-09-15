"""Read-only Nanite probe (runs inside UnrealEditor-Cmd).

Prints, per StaticMesh under ACW_SRC_DIR (default /Game/Taipei/XinyiGreybox)
and ACW_EXTRA_DIR (default /Game/Taipei/xinyi_tile_2km, v0 baseline, report-only):
  - whether a nanite_settings editor property exists
  - its `enabled` value and the available attribute names (to craft the setter)

Changes nothing. Exit signal is the NANITE_ log lines.
"""
import os
import unreal

DIRS = [os.environ.get("ACW_SRC_DIR", "/Game/Taipei/XinyiGreybox"),
        os.environ.get("ACW_EXTRA_DIR", "/Game/Taipei/xinyi_tile_2km")]


def main():
    lib = unreal.EditorAssetLibrary
    for d in DIRS:
        try:
            listed = lib.list_assets(d, recursive=True)
        except Exception as e:  # noqa: BLE001
            print("NANITE_LIST_FAIL %s %r" % (d, e))
            continue
        for ap in listed:
            try:
                obj = lib.load_asset(ap)
            except Exception:  # noqa: BLE001
                continue
            if obj is None or obj.get_class().get_name() != "StaticMesh":
                continue
            try:
                ns = obj.get_editor_property("nanite_settings")
            except Exception as e:  # noqa: BLE001
                print("NANITE_NOPROP %s (%r)" % (ap, e))
                continue
            try:
                enabled = ns.get_editor_property("enabled")
            except Exception as e:  # noqa: BLE001
                enabled = "unreadable (%r)" % e
            try:
                attrs = sorted(str(a) for a in dir(ns) if not a.startswith("_"))[:20]
            except Exception:  # noqa: BLE001
                attrs = []
            print("NANITE_MESH %s enabled=%s" % (ap, enabled))
            print("NANITE_ATTRS %s" % ",".join(attrs))
    print("NANITE_PROBE_DONE")


main()
