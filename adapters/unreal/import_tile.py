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
    # Interchange does NOT autosave: flush to .uasset on disk explicitly.
    try:
        ok = unreal.EditorAssetLibrary.save_directory(DEST_DIR, recursive=True)
        print("IMPORT_SAVED %s (save_directory -> %s)" % (DEST_DIR, ok))
    except Exception as e:  # noqa: BLE001
        print("IMPORT_SAVE_FAIL %r" % e)


main()
