"""Read-only UE5.8 audit of a persisted XinyiV2 world and its actor ownership.

The selected source or converted map is loaded without mutation. A narrow
native accessor reports streaming state that UE5.8 does not expose to Python.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import unreal

LEVEL = os.environ.get("ACW_XINYI_V2_AUDIT_LEVEL", "/Game/XinyiV2/L_XinyiV2_Contract")
TERRAIN_LABEL = "Terrain_Xinyi_MOI2025"
RUNTIME_PREFIX = "XinyiRuntimeTile_"
REPORT_PATH = Path(
    os.environ.get(
        "ACW_XINYI_V2_WP_AUDIT_REPORT",
        str(
            Path(unreal.Paths.project_saved_dir())
            / "XinyiUnrealV2"
            / "ue_world_partition_audit.json"
        ),
    )
).resolve()


def _string(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        return repr(value)


def _class_name(obj: Any) -> str:
    if obj is None:
        return ""
    try:
        return str(obj.get_class().get_name())
    except Exception:  # noqa: BLE001
        return type(obj).__name__


def _path_name(obj: Any) -> str:
    if obj is None:
        return ""
    try:
        return str(obj.get_path_name())
    except Exception:  # noqa: BLE001
        return _string(obj)


def _outermost_package(obj: Any) -> str:
    if obj is None:
        return ""
    try:
        package = obj.get_outermost()
        return _path_name(package)
    except Exception:  # noqa: BLE001
        return ""


def _prop(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    try:
        return obj.get_editor_property(name)
    except Exception:  # noqa: BLE001
        try:
            return getattr(obj, name)
        except Exception:  # noqa: BLE001
            return default


def _asset_paths(values: Any) -> list[str]:
    if not values:
        return []
    out = []
    for value in list(values):
        text = _path_name(value) or _string(value)
        if text:
            out.append(text)
    return sorted(out)


def _actor_row(actor: unreal.Actor) -> dict[str, Any]:
    loc = actor.get_actor_location()
    scale = actor.get_actor_scale3d()
    hlod = _prop(actor, "hlod_layer")
    external_data_layer = _prop(actor, "external_data_layer_asset")
    components = list(actor.get_components_by_class(unreal.ActorComponent))
    component_classes: dict[str, int] = {}
    for comp in components:
        name = _class_name(comp)
        component_classes[name] = component_classes.get(name, 0) + 1

    return {
        "label": actor.get_actor_label(),
        "class": _class_name(actor),
        "path": _path_name(actor),
        "outermost_package": _outermost_package(actor),
        "location_cm": [float(loc.x), float(loc.y), float(loc.z)],
        "scale": [float(scale.x), float(scale.y), float(scale.z)],
        "is_spatially_loaded": bool(_prop(actor, "is_spatially_loaded", False)),
        "runtime_grid": _string(_prop(actor, "runtime_grid", "")),
        "data_layer_assets": _asset_paths(_prop(actor, "data_layer_assets", [])),
        "external_data_layer_asset": _path_name(external_data_layer),
        "hlod_layer": _path_name(hlod),
        "component_classes": dict(sorted(component_classes.items())),
    }


def _desc_value(desc: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(desc, name)
    except Exception:  # noqa: BLE001
        try:
            return desc.get_editor_property(name)
        except Exception:  # noqa: BLE001
            return default


def _desc_row(desc: Any) -> dict[str, Any]:
    return {
        "label": _string(_desc_value(desc, "label", "")),
        "name": _string(_desc_value(desc, "name", "")),
        "actor_package": _string(_desc_value(desc, "actor_package", "")),
        "actor_path": _string(_desc_value(desc, "actor_path", "")),
        "runtime_grid": _string(_desc_value(desc, "runtime_grid", "")),
        "is_spatially_loaded": bool(
            _desc_value(desc, "is_spatially_loaded", False)
        ),
        "actor_is_editor_only": bool(
            _desc_value(desc, "actor_is_editor_only", False)
        ),
        "data_layer_assets": [
            _string(x)
            for x in list(_desc_value(desc, "data_layer_assets", []) or [])
        ],
    }


def main() -> None:
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not levels.load_level(LEVEL):
        raise RuntimeError("failed to load persisted XinyiV2 level: %s" % LEVEL)

    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = editor.get_editor_world()
    if world is None:
        raise RuntimeError("editor world is unavailable after loading XinyiV2")

    world_settings = world.get_world_settings()
    world_partition = _prop(world_settings, "world_partition")
    partitioned = world_partition is not None
    native_partition = json.loads(
        unreal.XinyiWorldPartitionAuditLibrary.inspect_current_editor_world_partition()
    )

    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = list(actor_sub.get_all_level_actors())
    runtime_actors = sorted(
        [a for a in actors if a.get_actor_label().startswith(RUNTIME_PREFIX)],
        key=lambda a: a.get_actor_label(),
    )
    terrain = next(
        (a for a in actors if a.get_actor_label() == TERRAIN_LABEL),
        None,
    )

    target_actors = ([terrain] if terrain is not None else []) + runtime_actors
    actor_rows = [_actor_row(actor) for actor in target_actors]

    all_descriptor_rows: list[dict[str, Any]] = []
    descriptor_rows: list[dict[str, Any]] = []
    descriptor_error = ""
    if partitioned:
        try:
            descs = unreal.WorldPartitionBlueprintLibrary.get_actor_descs() or []
            all_descriptor_rows = [_desc_row(desc) for desc in list(descs)]
            descriptor_rows = [
                row
                for row in all_descriptor_rows
                if row["label"] == TERRAIN_LABEL
                or row["label"].startswith(RUNTIME_PREFIX)
            ]
        except Exception as exc:  # noqa: BLE001
            descriptor_error = repr(exc)

    failures = []
    if native_partition.get("status") != "PASS":
        failures.append(
            {"reason": "native_partition_inspection_failed", "result": native_partition}
        )
    elif native_partition.get("present") != partitioned:
        failures.append(
            {"reason": "native_partition_presence_mismatch", "result": native_partition}
        )
    if partitioned and any(
        not isinstance(native_partition.get(key), bool)
        for key in (
            "initialized",
            "supports_streaming",
            "enable_streaming",
            "streaming_enabled_in_editor",
            "can_stream",
        )
    ):
        failures.append(
            {"reason": "native_partition_streaming_state_missing", "result": native_partition}
        )
    if partitioned:
        terrain_descs = [
            row for row in descriptor_rows if row["label"] == TERRAIN_LABEL
        ]
        runtime_descs = [
            row
            for row in descriptor_rows
            if row["label"].startswith(RUNTIME_PREFIX)
        ]
        if len(terrain_descs) != 1:
            failures.append(
                {
                    "reason": "terrain_actor_descriptor_count",
                    "expected": 1,
                    "actual": len(terrain_descs),
                }
            )
        if len(runtime_descs) != 25:
            failures.append(
                {
                    "reason": "runtime_tile_actor_descriptor_count",
                    "expected": 25,
                    "actual": len(runtime_descs),
                }
            )
        if descriptor_error:
            failures.append(
                {
                    "reason": "actor_descriptor_read_failed",
                    "error": descriptor_error,
                }
            )
    else:
        if terrain is None:
            failures.append({"reason": "terrain_missing"})
        if len(runtime_actors) != 25:
            failures.append(
                {
                    "reason": "runtime_tile_actor_count",
                    "expected": 25,
                    "actual": len(runtime_actors),
                }
            )

    class_counts: dict[str, int] = {}
    for actor in actors:
        name = _class_name(actor)
        class_counts[name] = class_counts.get(name, 0) + 1

    wp_enable_streaming = native_partition.get("enable_streaming") if partitioned else False
    wp_default_hlod = (
        _path_name(_prop(world_partition, "default_hlod_layer"))
        if partitioned
        else ""
    )

    target_packages = sorted(
        {
            row["outermost_package"]
            for row in actor_rows
            if row["outermost_package"]
        }
    )
    descriptor_packages = sorted(
        {
            row["actor_package"]
            for row in descriptor_rows
            if row["actor_package"]
        }
    )

    report = {
        "status": (
            "PASS_WORLD_PARTITION_AUDIT"
            if not failures
            else "FAIL_WORLD_PARTITION_AUDIT"
        ),
        "audit_is_read_only": True,
        "world_saved_after_audit": False,
        "level": LEVEL,
        "world_path": _path_name(world),
        "world_package": _outermost_package(world),
        "world_settings_class": _class_name(world_settings),
        "world_partition": {
            "present": partitioned,
            "class": _class_name(world_partition),
            "path": _path_name(world_partition),
            "enable_streaming": wp_enable_streaming,
            "supports_streaming": native_partition.get("supports_streaming"),
            "streaming_enabled_in_editor": native_partition.get("streaming_enabled_in_editor"),
            "can_stream": native_partition.get("can_stream"),
            "initialized": native_partition.get("initialized"),
            "default_hlod_layer": wp_default_hlod,
        },
        "decision_input": (
            "CURRENT_LEVEL_PARTITIONED"
            if partitioned
            else "CURRENT_LEVEL_NON_PARTITIONED"
        ),
        "target_counts": {
            "loaded_terrain": 1 if terrain is not None else 0,
            "loaded_runtime_building_tiles": len(runtime_actors),
            "all_loaded_level_actors": len(actors),
            "descriptor_terrain": len(
                [row for row in descriptor_rows if row["label"] == TERRAIN_LABEL]
            ),
            "descriptor_runtime_building_tiles": len(
                [
                    row
                    for row in descriptor_rows
                    if row["label"].startswith(RUNTIME_PREFIX)
                ]
            ),
        },
        "loaded_actor_class_counts": dict(sorted(class_counts.items())),
        "target_actor_outermost_packages": target_packages,
        "all_actor_descriptor_count": len(all_descriptor_rows),
        "target_actor_descriptor_count": len(descriptor_rows),
        "actor_descriptor_packages": descriptor_packages,
        "actor_descriptor_error": descriptor_error,
        "targets": actor_rows,
        "actor_descriptors": descriptor_rows,
        "failures": failures,
        "next_step": (
            "Measure current World Partition streaming ownership before mutation."
            if partitioned
            else (
                "Do not convert this level in place yet; compare isolated "
                "partitioned migration/test-level options first."
            )
        ),
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    unreal.log(
        "XINYI_V2_WORLD_PARTITION_AUDIT_JSON "
        + json.dumps(report, separators=(",", ":"))
    )

    if failures:
        raise RuntimeError("XinyiV2 World Partition audit prerequisites failed")


main()
