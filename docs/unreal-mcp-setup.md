# Unreal MCP Setup — UE 5.8 × AirCombatWorld (verified 2026-09-12)

> Goal (met): 小愛/Hermes can read and operate the live UE 5.8 Editor on this
> project through Epic's official Unreal MCP. No PCG, no geometry changes, no DEM.

## 1. What was enabled (in-repo, committed)

- `unreal/AirCombatWorld.uproject` → Plugins add:
  - `ModelContextProtocol` (FriendlyName in editor: **Unreal MCP**,
    `Engine/Plugins/Experimental/ModelContextProtocol`) — the server.
  - `AllToolsets` (`Engine/Plugins/Experimental/Toolsets/AllToolsets`) —
    aggregator; its dependency `ToolsetRegistry` is auto-mounted by UE.
- `unreal/Config/DefaultGame.ini` → exact, verified section:
  ```ini
  [/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]
  bAutoStartServer=True
  ServerPortNumber=8000
  ```
  (Class/property names recovered via DLL string mining:
  `UModelContextProtocolSettings`, `bAutoStartServer`, `ServerPortNumber`.
  Editor-Preferences tick writes the same keys machine-locally; the project ini
  makes it durable and committable.)
- Endpoint (default, unchanged): `http://127.0.0.1:8000/mcp`
- Force-start override (no config needed): launch editor with
  `-ModelContextProtocolStartServer` (port override: `-ModelContextProtocolPort=N`).

## 2. Server behavior discovered (worth knowing)

- Transport: MCP Streamable HTTP on the single `/mcp` route. `initialize` and
  `tools/list` return plain JSON; `tools/call` returns `text/event-stream`.
- **Session is bound to one persistent HTTP/1.1 connection.** One-shot clients
  (fresh connection per request) get `200 + empty stream` on every call.
  `adapters/unreal/mcp_probe.py` keeps a single `http.client.HTTPConnection`
  for init → notify → calls and works reliably.
- Only 3 top-level tools: `list_toolsets`, `describe_toolset`, `call_tool`.
  Everything else dispatches through
  `call_tool {toolset_name, tool_name, arguments}`. 52 toolsets registered,
  including `EditorToolset.EditorAppToolset` (viewport/PIE/selection) and
  `editor_toolset.toolsets.actor.ActorTools` (`get/set_actor_transform`,
  `get_actor_bounds`, labels, tags, components).
- Actor references use full refPaths, e.g.
  `/Game/Taipei/L_TaipeiGreybox.L_TaipeiGreybox:PersistentLevel.StaticMeshActor_0`.
  `GetVisibleActors` returns internal names; resolve display labels with
  `ActorTools.get_label`.
- Tool calls dispatch on the editor thread: while the editor is still warming up
  (shaders), calls queue and answer slowly — allow 300 s client timeouts.

## 3. Verification (live editor, 2026-09-12)

Runner: `python adapters/unreal/mcp_verify.py` → `VERIFY_OK`. Evidence below
was read through MCP, not from files:

1. **Actors**: 12 listed; labels resolved — `StaticMeshActor_0 → CityMassing_Xinyi`,
   `StaticMeshActor_1 → Hero_Taipei101` (+ Sky/Fog/Atmosphere/managers).
2. **City transform/bounds**: location (0,0,0) scale 1;
   bounds min(-114983, -116885, 0) max(94810, 97961, 26904) cm =
   **2.10 × 2.15 km, 269 m max** ✓. Hero bounds max Z **exactly 50,800 cm = 508 m** ✓.
3. **Reversible edit**: `ExponentialHeightFog_0` +100 cm Z → verified → restored →
   verified equal. Nothing else touched.
- Note: `GetVisibleActors` does not return the DirectionalLight `Sun` or
  `PlayerStart` `Start` (likely visibility-filtered); both remain in the saved
  `.umap` from the deterministic `build_level.py` run. Non-blocking.

## 4. Wiring 小愛/Hermes (manual step — NOT auto-applied)

Hermes supports generic HTTP MCP (same shape as the existing godot entry).
Per standing safety rules the live Hermes config was NOT edited by the agent.
To connect, append to the `mcp_servers:` map in
`C:\Users\EDDY\AppData\Local\hermes\config.yaml`:

```yaml
  unreal:
    url: http://127.0.0.1:8000/mcp
    connect_timeout: 30
```

then restart Hermes (new session picks up MCP servers). Requires the UE editor
open with the project (MCP server runs in-editor). Minimal human steps:
1) paste the 3 lines, 2) restart Hermes, 3) keep the editor open.
Say the word and the agent will apply it on explicit confirmation.

## 5. Files

- `adapters/unreal/mcp_probe.py` — persistent-connection MCP client
  (`tools/list` / `call`), reusable for future agent ops.
- `adapters/unreal/mcp_verify.py` — the 3 checks above, rerunnable.
- `adapters/unreal/mcp_introspect.py` — one-off settings discovery (kept for record).
- This doc. No compiler/WorldModel/geometry changes in this round.
