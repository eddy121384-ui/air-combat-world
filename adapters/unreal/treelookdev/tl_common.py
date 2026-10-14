"""Shared helpers for the TreeLookdev adapters (UE5.8 editor Python). Isolated project unreal/TreeLookdev only."""
from __future__ import annotations

import json
import os
from pathlib import Path

import unreal

REPO = Path(os.environ["ACW_REPO_ROOT"]).resolve()
if not (REPO / "AGENTS.md").is_file():
    raise RuntimeError("ACW_REPO_ROOT must point at the air-combat-world checkout")
GAME = Path(os.environ.get("ACW_TL_GAME", str(REPO / "out/treegen/machilus_game")))
OUT = Path(os.environ.get("ACW_TL_OUT", str(REPO / "unreal/TreeLookdev/Saved/TreeLookdev")))
REPORTS = OUT / "reports"
CAPTURES = OUT / "captures"

ROOT = "/Game/TreeLookdev"
TEX_DIR = ROOT + "/Textures"
MAT_DIR = ROOT + "/Materials"
MESH_DIR = ROOT + "/Meshes"
LEVEL = ROOT + "/L_TL_Machilus"
TREE_MESH = MESH_DIR + "/Machilus/machilus_lod0"
# LOD policy (UE screen size = projected sphere diameter / screen; ~3.08 R / D at 60 deg hfov, R = 8.5 m):
# LOD0 < ~52 m, LOD1 52-175 m, LOD2 beyond (50 m AGL camera, slant 152 m -> LOD1; 200 m AGL, 391 m -> LOD2).
LOD_SCREENS = [1.0, 0.5, 0.15]

lib = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def write_report(name, report):
    REPORTS.mkdir(parents=True, exist_ok=True)
    p = REPORTS / name
    p.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    unreal.log("TL_REPORT %s %s" % (name, report.get("status")))
    return p


def views():
    return json.loads((GAME / "views.json").read_text(encoding="utf-8"))


def b2u(p):
    """Blender metres (x east, y north, z up) -> UE cm (X east, Y = -north, Z up). Same rule as the XinyiLook / ForestSpike adapters."""
    return unreal.Vector(p[0] * 100.0, -p[1] * 100.0, p[2] * 100.0)


def b2u_dir(d):
    return unreal.Vector(d[0], -d[1], d[2])


def find_actor(actors, label):
    for a in actors.get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def ensure_dir(path):
    if not lib.does_directory_exist(path):
        lib.make_directory(path)
