"""Build two tiny deterministic QA materials for XinyiV2 whitebox capture.

These are presentation assets only. They live under /Game/XinyiV2/QA and are
never assigned to the saved production level by this script.

Outputs:
- /Game/XinyiV2/QA/M_XinyiV2_BuildingWhitebox
- /Game/XinyiV2/QA/M_XinyiV2_TerrainWhitebox
"""
import json
import os
from pathlib import Path

import unreal

OUT_DIR = Path(
    os.environ.get(
        "ACW_XINYI_V2_CAPTURE_DIR",
        str(Path(unreal.Paths.project_saved_dir()) / "XinyiUnrealV2" / "Captures"),
    )
).resolve()
REPORT = OUT_DIR / "whitebox_materials_report.json"

QA_DIR = "/Game/XinyiV2/QA"
BUILDING_PATH = QA_DIR + "/M_XinyiV2_BuildingWhitebox"
TERRAIN_PATH = QA_DIR + "/M_XinyiV2_TerrainWhitebox"

OUT_DIR.mkdir(parents=True, exist_ok=True)

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
asset_lib = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def rebuild_material(asset_path, rgb, roughness):
    name = asset_path.rsplit("/", 1)[-1]

    # QA materials are never referenced by the saved runtime map; rebuilding them
    # is safe and keeps the authored graph deterministic across iterations.
    if asset_lib.does_asset_exist(asset_path):
        if not asset_lib.delete_asset(asset_path):
            raise RuntimeError("failed to replace QA material: %s" % asset_path)

    material = asset_tools.create_asset(
        name,
        QA_DIR,
        unreal.Material,
        unreal.MaterialFactoryNew(),
    )
    if material is None:
        raise RuntimeError("failed to create QA material: %s" % asset_path)

    base = mel.create_material_expression(
        material,
        unreal.MaterialExpressionConstant3Vector,
        -320,
        -40,
    )
    base.set_editor_property(
        "constant",
        unreal.LinearColor(float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0),
    )
    mel.connect_material_property(
        base,
        "",
        unreal.MaterialProperty.MP_BASE_COLOR,
    )

    rough = mel.create_material_expression(
        material,
        unreal.MaterialExpressionConstant,
        -320,
        140,
    )
    rough.set_editor_property("r", float(roughness))
    mel.connect_material_property(
        rough,
        "",
        unreal.MaterialProperty.MP_ROUGHNESS,
    )

    mel.recompile_material(material)
    if not asset_lib.save_asset(asset_path):
        raise RuntimeError("failed to save QA material: %s" % asset_path)

    reopened = asset_lib.load_asset(asset_path)
    if reopened is None:
        raise RuntimeError("QA material did not persist: %s" % asset_path)

    return {
        "path": asset_path,
        "rgb_linear": list(rgb),
        "roughness": float(roughness),
    }


# Deliberately restrained whitebox palette: buildings read cool/light, terrain
# reads warmer/darker. These are QA separation colors, not art direction.
building = rebuild_material(
    BUILDING_PATH,
    (0.72, 0.79, 0.86),
    0.82,
)
terrain = rebuild_material(
    TERRAIN_PATH,
    (0.30, 0.38, 0.28),
    0.92,
)

report = {
    "status": "PASS_WHITEBOX_MATERIALS",
    "building": building,
    "terrain": terrain,
    "scope": "QA presentation assets only; saved world geometry is untouched",
}
REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("XINYI_V2_WHITEBOX_MATERIALS_JSON " + json.dumps(report, separators=(",", ":")))
