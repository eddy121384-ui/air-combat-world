"""Shared helpers for the ForestSpike B0 Unreal adapters (UE5.8 editor Python).

Scope: an isolated test project (unreal/ForestSpike). Nothing here reads or writes the Xinyi production
project, maps, shaders or tree placement.
"""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import unreal

REPO = Path(os.environ.get("ACW_REPO_ROOT", "")).resolve() if os.environ.get("ACW_REPO_ROOT") else None
if REPO is None or not (REPO / "AGENTS.md").is_file():
    raise RuntimeError("ACW_REPO_ROOT must point at the air-combat-world checkout")

OUT = Path(os.environ.get("ACW_FS_OUT", str(REPO / "unreal/ForestSpike/Saved/ForestSpike")))
INPUTS = OUT / "inputs"
REPORTS = OUT / "reports"
CAPTURES = OUT / "captures"
MODELS = REPO / "assets/forestspike/b0/models"
SHADER = REPO / "tools/forestspike/shaders/fs_forest.hlsl"
VIEWPOINTS = REPO / "tools/forestspike/viewpoints.json"

ROOT = "/Game/ForestSpike"
MAT_DIR = ROOT + "/Materials"
TEX_DIR = ROOT + "/Textures"
MESH_DIR = ROOT + "/Meshes"
LEVEL = ROOT + "/L_ForestSpike_B0"

CORE_M = 1000.0
CTX_M = 6000.0

lib = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def write_report(name: str, report: dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / name
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    unreal.log("FS_REPORT %s %s" % (name, json.dumps({"status": report.get("status")})))
    return path


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError("missing input: %s" % path)
    return json.loads(path.read_text(encoding="utf-8"))


def enu_to_ue_cm(e: float, n: float, u: float) -> unreal.Vector:
    """UE X = east, UE Y = -north, UE Z = up (cm). Same mapping as the accepted XinyiLook adapters."""
    return unreal.Vector(e * 100.0, -n * 100.0, u * 100.0)


def mesh_bounds(mesh):
    b = mesh.get_bounds()
    return ([float(b.origin.x), float(b.origin.y), float(b.origin.z)],
            [float(b.box_extent.x), float(b.box_extent.y), float(b.box_extent.z)])


def ensure_dir(path: str):
    if not lib.does_directory_exist(path):
        lib.make_directory(path)


def find_actor(actors, label):
    for a in actors.get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def now_s() -> float:
    return time.monotonic()
