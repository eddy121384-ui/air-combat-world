"""Three minimal MCP verifications against the live UE 5.8 editor (stdlib only).

Actor references use full refPaths (GetVisibleActors output), e.g.
  {"actor": {"refPath": "/Game/Taipei/L_TaipeiGreybox.L_TaipeiGreybox:PersistentLevel.StaticMeshActor_0"}}

1. List actors (EditorAppToolset.GetVisibleActors); resolve labels; assert the
   city + hero meshes are present (by label or by bounds).
2. Read CityMassing transform + bounds (ActorTools); assert ~2 km span.
3. Reversible nudge on non-critical ExponentialHeightFog (+100 cm Z, restore,
   round-trip assert). Nothing else is touched.

Usage: python adapters/unreal/mcp_verify.py
Env: MCP_URL (default http://127.0.0.1:8000/mcp)
Exit 0 + VERIFY_OK only if all three pass.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp_probe import Session

APP = "EditorToolset.EditorAppToolset"
ACT = "editor_toolset.toolsets.actor.ActorTools"
LEVEL_PREFIX = "/Game/Taipei/L_TaipeiGreybox.L_TaipeiGreybox:PersistentLevel."


def call(s: Session, toolset: str, tool: str, args: dict) -> str:
    res = s.call("call_tool", {"toolset_name": toolset, "tool_name": tool,
                               "arguments": args})
    if res.get("isError"):
        raise SystemExit(f"TOOL {tool} ERROR: {str(res)[:600]}")
    return "\n".join(c.get("text", "") for c in res.get("content", [])
                     if isinstance(c, dict))


def ref(name: str) -> dict:
    return {"actor": {"refPath": LEVEL_PREFIX + name}}


def main() -> None:
    s = Session(os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp"))

    # 1. list + label every actor
    out = call(s, APP, "GetVisibleActors", {})
    actors = json.loads(out)["returnValue"]
    labels = {}
    for a in actors:
        short = a["refPath"].split(".")[-1]
        try:
            lab = json.loads(call(s, ACT, "get_label", ref(short)))
            labels[short] = lab.get("returnValue", lab) if isinstance(lab, dict) else lab
        except SystemExit as e:
            labels[short] = f"ERR {str(e)[:80]}"
    print("LABELS >>>")
    for k, v in labels.items():
        print(f"  {k} -> {v}")
    inv = {str(v): k for k, v in labels.items()}
    assert "CityMassing_Xinyi" in inv, "city actor missing"
    assert "Hero_Taipei101" in inv, "hero actor missing"
    print("VERIFY 1/3 OK: city + hero present")
    city_ref, hero_ref = inv["CityMassing_Xinyi"], inv["Hero_Taipei101"]

    # 2. city transform + bounds (~2.10 x 2.15 km, max Z ~269 m => cm below)
    t = call(s, ACT, "get_actor_transform", ref(city_ref))
    b = call(s, ACT, "get_actor_bounds", ref(city_ref))
    print("CITY TRANSFORM >>>", t[:400])
    print("CITY BOUNDS >>>", b[:500])
    nums = [float(x) for x in __import__("re").findall(r"-?\d+\.?\d*", b)]
    span = max(nums) - min(nums)
    assert span > 100000, f"city bounds span too small: {span}"
    print("VERIFY 2/3 OK: city bounds span >100,000 cm")

    # hero height ~= 50800 cm
    hb = call(s, ACT, "get_actor_bounds", ref(hero_ref))
    print("HERO BOUNDS >>>", hb[:400])
    hnums = [float(x) for x in __import__("re").findall(r"-?\d+\.?\d*", hb)]
    assert any(50000 < v < 52000 for v in hnums), f"hero 508 m not found: {hnums[:8]}"
    print("VERIFY 2b/3 OK: hero ~50800 cm tall")

    # 3. reversible nudge on fog (+100 cm Z, restore, round-trip)
    fog_candidates = [k for k, v in labels.items() if "Fog" in str(v) or "Fog" in k]
    assert fog_candidates, "no fog actor to test on"
    fog = fog_candidates[0]
    before = json.loads(call(s, ACT, "get_actor_transform", ref(fog)))
    loc = _loc(before)
    call(s, ACT, "set_actor_transform",
         {**ref(fog), "xform": {"location": {"x": loc[0], "y": loc[1], "z": loc[2] + 100}}})
    mid = _loc(json.loads(call(s, ACT, "get_actor_transform", ref(fog))))
    assert abs(mid[2] - (loc[2] + 100)) < 0.01, f"nudge failed: {mid}"
    call(s, ACT, "set_actor_transform",
         {**ref(fog), "xform": {"location": {"x": loc[0], "y": loc[1], "z": loc[2]}}})
    after = _loc(json.loads(call(s, ACT, "get_actor_transform", ref(fog))))
    assert abs(after[2] - loc[2]) < 0.01, f"restore failed: {after}"
    print(f"VERIFY 3/3 OK: {fog} nudged +100cm Z and restored exactly")
    print("VERIFY_OK")


def _loc(t: dict) -> tuple:
    v = t.get("returnValue", t)
    if isinstance(v, dict) and "location" in v:
        v = v["location"]
    if isinstance(v, dict) and all(k in v for k in ("x", "y", "z")):
        return (float(v["x"]), float(v["y"]), float(v["z"]))
    raise SystemExit(f"unparseable transform: {str(t)[:200]}")


if __name__ == "__main__":
    main()
