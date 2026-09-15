"""Introspect Unreal MCP settings keys (runs inside UnrealEditor-Cmd).

Prints: MCP-related classes in `unreal`, their config properties, and current
values. Used once to discover the exact Auto-Start/endpoint keys — no guessing.
"""
import unreal

print("MCP_CLASSES_BEGIN")
names = [n for n in dir(unreal) if "mcp" in n.lower() or "modelcontext" in n.lower()
         or "toolset" in n.lower()]
for n in sorted(names):
    print("  " + n)
print("MCP_CLASSES_END")

for n in sorted(names):
    try:
        cls = getattr(unreal, n)
        cdo = unreal.get_default_object(cls)
        if cdo is None:
            continue
        print(f"PROPS {n}:")
        for p in sorted(dir(cdo)):
            if p.startswith("_"):
                continue
            try:
                v = getattr(cdo, p)
                if isinstance(v, (bool, int, float, str)):
                    print(f"  {p} = {v!r}")
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        print(f"  ({n}: {e!r})")
print("MCP_INTROSPECT_DONE")
