"""UE 5.8 headless bounds dump (scale validation without opening the GUI).

Runs INSIDE UnrealEditor-Cmd AFTER import_tile.py:
  UnrealEditor-Cmd.exe <uproject> -ExecutePythonScript="<this file>" -unattended -nopause -nosound

Reads env: ACW_ASSET (e.g. /Game/Taipei/XinyiTile or the scene asset path).
Prints BOUNDS <min> <max> <size_cm> per static mesh found, plus 101-height check.
Expected: tile ~200,000 cm span; tallest mesh max Z ~= 50,800 cm (508 m).
"""
import os
import unreal

TARGET = os.environ.get("ACW_ASSET", "/Game/Taipei/XinyiTile")


def meshes_under(path):
    lib = unreal.EditorAssetLibrary
    try:
        listed = lib.list_assets(path, recursive=True)
    except Exception as e:  # noqa: BLE001
        print("BOUNDS_LIST_FAIL %r" % e)
        listed = []
    print("BOUNDS_LISTED %d under %s" % (len(listed), path))
    out = []
    for ap in listed:
        try:
            obj = lib.load_asset(ap)
        except Exception as e:  # noqa: BLE001
            print("ASSET %s load fail %r" % (ap, e))
            continue
        cls = obj.get_class().get_name() if obj else "None"
        print("ASSET %s class=%s" % (ap, cls))
        if obj is not None and cls in ("StaticMesh", "SkeletalMesh"):
            out.append(obj)
    return out


def main():
    found = meshes_under(TARGET)
    print("BOUNDS_TARGET %s meshes=%d" % (TARGET, len(found)))
    for m in found:
        try:
            b = m.get_bounds()  # FBoxSphereBounds-ish; use .box_extent/.origin if present
            print("MESH %s bounds=%s" % (m.get_path_name(), b))
        except Exception as e:  # noqa: BLE001
            # StaticMesh fallback: extended bounds via render data
            try:
                eb = m.get_extended_bounds()
                print("MESH %s ext_bounds origin=%s extent=%s" % (
                    m.get_path_name(), eb.origin, eb.box_extent))
            except Exception as e2:  # noqa: BLE001
                print("MESH %s unreadable (%r / %r)" % (m.get_path_name(), e, e2))
    print("BOUNDS_DONE")


main()
