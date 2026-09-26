"""Read-only UE5.8 inventory of Landscape partition and collision ownership."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import unreal

LEVEL = "/Game/XinyiV2/L_XinyiV2_Contract_WP"
OUT = os.environ.get("ACW_XINYI_HOST_OWNERSHIP_REPORT", "")
RUN_ID = os.environ.get("ACW_XINYI_HOST_RUN_ID", "")


def path_name(value):
    try:
        return str(value.get_path_name())
    except Exception:  # noqa: BLE001
        return ""


def prop(value, name):
    try:
        return value.get_editor_property(name)
    except Exception:  # noqa: BLE001
        return None


def main():
    if not OUT or not RUN_ID:
        raise RuntimeError("ownership output and run ID are required")
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not levels.load_level(LEVEL):
        raise RuntimeError("failed to load isolated XinyiV2 WP map")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    rows = []
    for actor in actors:
        class_name = actor.get_class().get_name()
        if "Landscape" not in class_name:
            continue
        components = []
        for component in actor.get_components_by_class(unreal.ActorComponent):
            component_class = component.get_class().get_name()
            if "Landscape" in component_class or "Heightfield" in component_class:
                components.append({"class": component_class, "path": path_name(component), "package": path_name(component.get_outermost())})
        rows.append({"label": actor.get_actor_label(), "class": class_name, "path": path_name(actor), "package": path_name(actor.get_outermost()), "is_spatially_loaded": prop(actor, "is_spatially_loaded"), "runtime_grid": str(prop(actor, "runtime_grid") or ""), "components": components})
    roots = [row for row in rows if row["class"] == "Landscape"]
    proxies = [row for row in rows if "StreamingProxy" in row["class"]]
    landscape_components = sum(sum(c["class"] == "LandscapeComponent" for c in row["components"]) for row in rows)
    collision_components = sum(sum("HeightfieldCollision" in c["class"] for c in row["components"]) for row in rows)
    failures = []
    if len(roots) != 1:
        failures.append({"reason": "landscape_root_count", "actual": len(roots)})
    if landscape_components != 25:
        failures.append({"reason": "landscape_component_count", "actual": landscape_components})
    receipt = {"schema": "xinyi-host-gate/v1", "receipt_type": "landscape_ownership", "status": "PASS_OWNERSHIP_AUDIT" if not failures else "FAIL_OWNERSHIP_AUDIT", "runtime_validation": False, "created_utc": datetime.now(timezone.utc).isoformat(), "run_id": RUN_ID, "level": LEVEL, "root_count": len(roots), "streaming_proxy_count": len(proxies), "landscape_component_count": landscape_components, "heightfield_collision_component_count": collision_components, "actors": rows, "failures": failures, "audit_is_read_only": True}
    path = Path(OUT)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    if failures:
        raise RuntimeError("Landscape ownership audit failed")


main()
