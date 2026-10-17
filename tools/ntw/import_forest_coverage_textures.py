"""Run in UE5.8 Editor Python; imports selected DATA TEXTURES only, never a map.

ACW_FOREST_DATA=<absolute coverage_v1 dir>
ACW_FOREST_CELLS=C+0038+0346,C+0038+0345
No default cells, no tree generation, no modification of existing assets.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import zipfile

import unreal


def main():
    root = Path(os.environ["ACW_FOREST_DATA"])
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for filename in ("unreal_masks.zip", "cells.csv"):
        if hashlib.sha256((root / filename).read_bytes()).hexdigest() != manifest["outputs_sha256"][filename]:
            raise ValueError("Coverage bundle checksum mismatch: " + filename)
    requested = os.environ["ACW_FOREST_CELLS"].split(",")
    records = {r["CellId"]: r for r in csv.DictReader((root / "cells.csv").open(encoding="utf-8"))}
    if not requested or any(c not in records for c in requested) or len(set(requested)) != len(requested):
        raise ValueError("Specify unique existing cell IDs")
    destination = "/Game/NTWForestCoverageV1/Data"
    cache = Path(unreal.Paths.project_saved_dir()) / "NTWForestCoverageV1Textures"
    cache.mkdir(parents=True, exist_ok=True)
    tasks = []
    # Validate every destination before starting imports: never overwrite assets.
    for cell in requested:
        for suffix in ("masks", "classes", "rules"):
            name = "T_" + cell.replace("+", "p").replace("-", "m") + "_" + suffix
            if unreal.EditorAssetLibrary.does_asset_exist(destination + "/" + name):
                raise ValueError("Destination exists; use a clean isolated project: " + name)
    with zipfile.ZipFile(root / "unreal_masks.zip") as bundle:
        for cell in requested:
            for suffix in ("masks", "classes", "rules"):
                name = "T_" + cell.replace("+", "p").replace("-", "m") + "_" + suffix
                path = cache / (name + ".png")
                path.write_bytes(bundle.read(f"cells/{cell}/{suffix}.png"))
                task = unreal.AssetImportTask()
                task.set_editor_property("filename", str(path))
                task.set_editor_property("destination_path", destination)
                task.set_editor_property("destination_name", name)
                task.set_editor_property("automated", True)
                task.set_editor_property("replace_existing", False)
                task.set_editor_property("save", False)
                tasks.append(task)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    for task in tasks:
        paths = task.get_editor_property("imported_object_paths")
        if len(paths) != 1:
            raise RuntimeError("Unexpected texture import result")
        texture = unreal.load_asset(paths[0])
        texture.set_editor_property("srgb", False)
        # Uncompressed RGBA8 retains exact class codes and mask channels; BC compression would not.
        texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
        texture.set_editor_property("filter", unreal.TextureFilter.TF_NEAREST)
        texture.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        texture.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
        texture.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
        unreal.EditorAssetLibrary.save_loaded_asset(texture)
        unreal.log("Forest coverage DATA ONLY: " + paths[0])


if __name__ == "__main__":
    main()
