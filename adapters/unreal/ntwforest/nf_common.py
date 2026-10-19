"""Shared helpers for the North Taiwan forest world v1 stages (UE 5.8 editor Python, project unreal/TreeLookdev).

The species game assets (PR #33 / #36 / #43) are only referenced, never modified:
form A = 紅楠 chain T, B = 紅楠 second crown form, C = 相思樹 tight clump chain, J = 柳杉. New content lives under /Game/NorthForest.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import unreal

REPO = Path(os.environ["ACW_REPO_ROOT"]).resolve()
if not (REPO / "AGENTS.md").is_file():
    raise RuntimeError("ACW_REPO_ROOT must point at the air-combat-world checkout")
RUN = Path(os.environ.get("ACW_NF_RUN", str(REPO / "data/generated/ntw/forest_world/v1")))
OUT = Path(os.environ.get("ACW_NF_OUT", str(REPO / "unreal/TreeLookdev/Saved/NorthForest")))
REPORTS = OUT / "reports"

ROOT = "/Game/NorthForest"
MAT = ROOT + "/Materials"
TEX = ROOT + "/Textures"
MAP = ROOT + "/Maps"
SRC_MAT = "/Game/TreeLookdev/Materials"
TREES = "/Game/HillsideForest/Trees"
FORM_MESH = {
    "A": TREES + "/A_CSide100/machilus_budget_side100_lod0/StaticMeshes/machilus_budget_side100_lod0",
    "B": TREES + "/CrownB/machilus_balanced_lod0/StaticMeshes/machilus_balanced_lod0",
    "C": TREES + "/AcaciaTight/acacia_acacia_tight_lod0/StaticMeshes/acacia_acacia_tight_lod0",
    "J": TREES + "/Cryptomeria/cryptomeria_cryptomeria_lod0/StaticMeshes/cryptomeria_cryptomeria_lod0",
}
# source materials (duplicated into /Game/NorthForest/Materials with the distance-thinning fade; originals untouched)
FORM_LEAF_SRC = {"A": "M_TL_LeafCards", "B": "M_TL_LeafCards", "C": "M_TL_AcaciaW_LeafCards", "J": "M_TL_Cryptomeria_LeafCards"}
FORM_BARK_SRC = {"A": "M_TL_Bark", "B": "M_TL_Bark", "C": "M_TL_Acacia_Bark", "J": "M_TL_Cryptomeria_Bark"}
# leaf tint variants = the accepted hillside-forest instances (hf_build.py LEAF_VARIANTS), parameters of the source graphs only
LEAF_VARIANTS = {
    0: {}, 1: {"TintHi": (1.34, 1.26, 0.80), "TintLo": (0.90, 0.94, 0.70), "Brightness": 0.50},
    2: {"TintHi": (0.98, 1.04, 1.00), "TintLo": (0.66, 0.76, 0.78), "Brightness": 0.34},
    3: {"TintHi": (1.42, 1.34, 0.72), "TintLo": (0.92, 0.96, 0.66), "Brightness": 0.52},
    4: {"TintHi": (1.30, 1.26, 0.82), "TintLo": (0.84, 0.92, 0.66), "Brightness": 0.44},
    5: {"TintHi": (1.24, 1.16, 0.84), "TintLo": (0.92, 0.92, 0.74), "Brightness": 0.44},
    6: {"TintHi": (1.36, 1.26, 0.74), "TintLo": (1.00, 0.98, 0.70), "Brightness": 0.48},
    7: {"TintHi": (1.08, 1.06, 0.90), "TintLo": (0.80, 0.84, 0.74), "Brightness": 0.40},
    8: {}, 9: {"TintHi": (1.16, 1.12, 0.92), "TintLo": (0.90, 0.92, 0.84), "Brightness": 0.47},
}
VARIANT_FORM = {0: "A", 1: "A", 2: "A", 3: "B", 4: "B", 5: "C", 6: "C", 7: "C", 8: "J", 9: "J"}

lib = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def write_report(name, report):
    REPORTS.mkdir(parents=True, exist_ok=True)
    p = REPORTS / name
    p.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    unreal.log("NF_REPORT %s %s" % (name, report.get("status")))
    return p


def ensure_dir(path):
    if not lib.does_directory_exist(path):
        lib.make_directory(path)


def E(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, out, b, pin):
    if not mel.connect_material_expressions(a, out, b, pin):
        raise RuntimeError("connect failed %s.%s -> %s" % (a.get_name(), out, pin))


def find_actor(label):
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def terrain_meta():
    return json.loads((RUN / "terrain.json").read_text(encoding="utf-8"))
