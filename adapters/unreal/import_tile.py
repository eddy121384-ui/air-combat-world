"""UE 5.8 headless import for the City Compiler GLB tile (Route A attempt).

Runs INSIDE UnrealEditor-Cmd:
  UnrealEditor-Cmd.exe <uproject> -ExecutePythonScript="<this file>" -unattended -nopause -nosound

Reads env: ACW_GLB (absolute path to xinyi_tile_2km.glb), ACW_DEST (default /Game/Taipei).
Strategy: official Interchange Framework first, legacy AssetTools task as fallback.
Prints IMPORT_OK <asset_path> or IMPORT_FAIL <reason>. Never touches WorldModel/compiler.
"""
import os
import unreal

GLB = os.environ.get("ACW_GLB", "")
DEST_DIR = os.environ.get("ACW_DEST", "/Game/Taipei")
DEST_ASSET = DEST_DIR + "/XinyiTile"


def try_interchange(src, dest_dir):
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    source_data = unreal.InterchangeManager.create_source_data(src)
    params = unreal.ImportAssetParameters()
    # Keep the tile as static meshes; do not merge, do not touch scale.
    result = mgr.import_asset(dest_dir, source_data, params)
    return result


def try_asset_tools(src, dest_dir):
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    task = unreal.AssetImportTask()
    task.filename = src
    task.destination_path = dest_dir
    task.automated = True
    task.save = True
    tools.import_asset_tasks([task])
    return [a.get_path_name() for a in task.imported_object_paths or []]


def disable_nanite(dest_dir):
    """Mobile-first guard: the Interchange importer enables Nanite by default.

    Skyfront targets iPhone 13 mini / SM5 raster — Nanite needs SM6, so any
    Nanite-enabled mesh makes the GUI demand SM6 and refuse to display. This
    pass runs on EVERY import (present and future regenerations): it switches
    Nanite off on all StaticMeshes under dest_dir and saves them. Prints
    NANITE_OFF lines; failures are reported, never silent.
    """
    lib = unreal.EditorAssetLibrary
    try:
        listed = lib.list_assets(dest_dir, recursive=True)
    except Exception as e:  # noqa: BLE001
        print("NANITE_LIST_FAIL %r" % e)
        return 0
    fixed, already, failed = 0, 0, []
    for ap in listed:
        # Official path (verified live on UE 5.8): subsystem setter flips the
        # in-memory flag; plain save_asset() then persists it. Two hard-won
        # lessons encoded here:
        #  1. set_editor_property alone never dirties the package, and
        #     mark_package_dirty() does not exist in 5.8 (nor does the
        #     save_asset only_if_dirty keyword) — so "set + save" silently
        #     saves nothing. The subsystem setter is what actually applies.
        #  2. If a GUI editor holds these assets open, the OS file lock makes
        #     every save fail (MoveFile unable to move) with save_asset()
        #     returning False. Never run imports while the GUI is open.
        # Fresh-process verify_greybox_reopen.py (REOPEN_NANITE_OK) is the
        # truth signal — same-session read-backs are vacuous (asset cache).
        try:
            obj = lib.load_asset(ap)
            if obj is None or obj.get_class().get_name() != "StaticMesh":
                continue
            ns = obj.get_editor_property("nanite_settings")
            if not ns.get_editor_property("enabled"):
                already += 1
                continue
            sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
            ns.set_editor_property("enabled", False)
            obj.set_editor_property("nanite_settings", ns)
            sub.set_nanite_settings(obj, ns, True)
            if not lib.save_asset(ap):
                failed.append("%s (save declined — GUI holding the file?)" % ap)
                continue
            fixed += 1
            print("NANITE_OFF %s" % ap)
        except Exception as e:  # noqa: BLE001
            failed.append("%s (%r)" % (ap, e))
    print("NANITE_SUMMARY fixed=%d already_off=%d failed=%d" % (fixed, already, len(failed)))
    for f in failed:
        print("NANITE_FAIL %s" % f)
    return fixed


def main():
    if not GLB or not os.path.isfile(GLB):
        print("IMPORT_FAIL no valid ACW_GLB: %r" % GLB)
        return
    print("IMPORT_SRC %s" % GLB)
    print("IMPORT_DEST %s" % DEST_DIR)
    imported = None
    try:
        imported = try_interchange(GLB, DEST_DIR)
        print("IMPORT_OK interchange -> %s" % imported)
    except Exception as e:  # noqa: BLE001 - report, then fall back
        print("IMPORT_NOTE interchange path failed (%r); trying AssetTools" % e)
        try:
            imported = try_asset_tools(GLB, DEST_DIR)
            print("IMPORT_OK assettools -> %s" % imported)
        except Exception as e2:  # noqa: BLE001
            print("IMPORT_FAIL %r" % e2)
            return
    # Mobile-first: strip importer-default Nanite BEFORE the explicit save,
    # so every (re)import lands SM5-raster-safe. Then flush to .uasset.
    disable_nanite(DEST_DIR)
    try:
        ok = unreal.EditorAssetLibrary.save_directory(DEST_DIR, recursive=True)
        print("IMPORT_SAVED %s (save_directory -> %s)" % (DEST_DIR, ok))
    except Exception as e:  # noqa: BLE001
        print("IMPORT_SAVE_FAIL %r" % e)


main()
