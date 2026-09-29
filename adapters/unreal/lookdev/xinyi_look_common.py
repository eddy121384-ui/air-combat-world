"""Shared helpers for the XinyiLook Unreal adapters (UE5.8 editor Python).

Scope: visual layer only. Everything lives under /Game/XinyiLook and in a
separate level. The accepted /Game/XinyiV2 assets and L_XinyiV2_Contract are
read, never written.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import unreal

REPO = Path(os.environ.get("ACW_REPO_ROOT", "")).resolve() if os.environ.get("ACW_REPO_ROOT") else None
if REPO is None or not (REPO / "AGENTS.md").is_file():
    raise RuntimeError("ACW_REPO_ROOT must point at the air-combat-world checkout")

LOOK_OUT = REPO / "unreal/Saved/XinyiLook"
CONTRACT_DIR = REPO / "unreal/Saved/XinyiUnrealV2Contract"
SHADER = REPO / "tools/lookdev/shaders/xinyi_city.hlsl"
SHOTS = REPO / "tools/lookdev/preview/shots.json"
REPORT_DIR = LOOK_OUT / "unreal"

ROOT = "/Game/XinyiLook"
MAT_DIR = ROOT + "/Materials"
TEX_DIR = ROOT + "/Textures"
MESH_DIR = ROOT + "/Meshes"
SOURCE_LEVEL = "/Game/XinyiV2/L_XinyiV2_Contract"
LOOK_LEVEL = ROOT + "/L_XinyiLook_Hero"
MPC_PATH = MAT_DIR + "/MPC_XinyiLook"

TERRAIN_LABEL = "Terrain_Xinyi_MOI2025"
RUNTIME_PREFIX = "XinyiRuntimeTile_"
LOOK_PREFIX = "XinyiLook_"

# Landscape extent of the accepted contract (ENU metres).
E0, E1, N0, N1 = -1500.0, 1000.0, -1000.0, 1500.0

lib = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def write_report(name: str, report: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / name
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    unreal.log("XINYI_LOOK_REPORT " + name + " " + json.dumps({"status": report.get("status")}))
    return path


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError("missing offline look-dev output: %s (run tools/lookdev/build_all.py)" % path)
    return json.loads(path.read_text(encoding="utf-8"))


def tile_key(tile: str) -> str:
    return "_".join(("p" if p[0] == "+" else "m") + p[1:] for p in tile.split("_"))


def enu_to_ue_cm(e: float, n: float, u: float) -> unreal.Vector:
    """Validated mapping: UE X = east, UE Y = -north, UE Z = up (cm)."""
    return unreal.Vector(e * 100.0, -n * 100.0, u * 100.0)


def mesh_bounds(mesh) -> tuple[list, list]:
    b = mesh.get_bounds()
    return ([float(b.origin.x), float(b.origin.y), float(b.origin.z)],
            [float(b.box_extent.x), float(b.box_extent.y), float(b.box_extent.z)])


def max_err(a, b) -> float:
    return max(abs(float(a[i]) - float(b[i])) for i in range(3))


def finite3(v) -> bool:
    return all(math.isfinite(float(x)) for x in v)


def ensure_dir(path: str):
    if not lib.does_directory_exist(path):
        lib.make_directory(path)
