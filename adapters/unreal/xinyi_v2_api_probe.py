"""Probe the actual UE 5.8 Python surface needed by the XinyiV2 gate.

Run inside UnrealEditor-Cmd before implementing Landscape creation/import. The
goal is to discover what the installed promoted UE 5.8 build really exposes
instead of guessing from older experimental Python docs.

Reads:
  ACW_XINYI_V2_PROBE_OUT (optional absolute JSON output path)

Prints XINYI_V2_API_PROBE_JSON <json>.
"""
import json
import os

import unreal


def public_names(obj, needles):
    names = []
    for name in dir(obj):
        low = name.lower()
        if any(n in low for n in needles):
            names.append(name)
    return sorted(names)


def class_probe(name):
    obj = getattr(unreal, name, None)
    if obj is None:
        return {"available": False, "names": []}
    return {
        "available": True,
        "repr": str(obj),
        "names": public_names(
            obj,
            (
                "import",
                "height",
                "landscape",
                "component",
                "section",
                "partition",
                "stream",
                "create",
                "spawn",
                "world",
                "bounds",
                "location",
                "scale",
            ),
        ),
    }


def main():
    try:
        engine_version = unreal.SystemLibrary.get_engine_version()
    except Exception as exc:  # noqa: BLE001
        engine_version = "unknown (%r)" % exc

    landscape_symbols = sorted(
        n
        for n in dir(unreal)
        if any(k in n.lower() for k in ("landscape", "worldpartition", "interchange"))
    )

    report = {
        "engine_version": str(engine_version),
        "classes": {
            name: class_probe(name)
            for name in (
                "Landscape",
                "LandscapeProxy",
                "LandscapeStreamingProxy",
                "LandscapeComponent",
                "LandscapeHeightfieldCollisionComponent",
                "EditorLevelLibrary",
                "EditorAssetLibrary",
                "EditorActorSubsystem",
                "UnrealEditorSubsystem",
                "InterchangeManager",
            )
        },
        "matching_unreal_symbols": landscape_symbols,
    }

    out = os.environ.get("ACW_XINYI_V2_PROBE_OUT", "")
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")

    print("XINYI_V2_API_PROBE_JSON " + json.dumps(report, separators=(",", ":")))


main()
