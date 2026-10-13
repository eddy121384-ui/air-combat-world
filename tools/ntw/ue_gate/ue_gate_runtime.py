"""Phase 2B runtime gate - stage 2 (runs INSIDE UnrealEditor.exe of the ISOLATED project with a real RHI; never AirCombatWorld).

Play-In-Editor on /Game/NTWGate/L_NTWGate (built by ue_gate_build.py). Everything below is measured in the PIE world:
  1. collision: ~66k vertical line traces (Visibility channel, simple collision) along the 4 Xinyi edges (inside/outside offsets),
     the 4 corners, the cell seam and two chunk seams, and DEM nodes; hit actor + height recorded for offline comparison with the
     expected heights (prepare_gate_inputs.py)
  2. actor precision: PIE actor transforms of every gate actor, landscape corner positions through the actor transform, and two
     always-loaded probes (near origin / 156 km away) - read-back, +0.01 cm moves and traces onto their top faces
  3. LOD combinations: SceneCapture2D frames for 13 seam cameras x (landscape LOD, static-mesh LOD) combos x {stitch v2, v1} x
     {no policy, Xinyi border components forced to LOD0}; a magenta unlit plane 200 m below the terrain exposes any hole
  4. altitude series 150/300/600/800/3000 m (automatic LOD)
  5. 300 m/s flights (real elapsed time, terrain-following 150/300/600/800 m AGL) across the cell seam and the Xinyi sector:
     per-frame time, loaded chunk actors, runtime cell states, streaming completion, ground presence under/ahead of the aircraft;
     one captured flight at 300 m AGL
  6. failure-evidence session: the OpenWorld template default runtime grid (252 m cells / 768 m range) with the same flight
Desktop editor PIE only: NOT a mobile / packaged measurement.
env: ACW_GATE_INPUTS, ACW_GATE_OUT, ACW_GATE_MODE (probe | full)
"""
import json
import math
import os
import time
import traceback

import unreal

INP = json.load(open(os.environ["ACW_GATE_INPUTS"], encoding="utf-8"))
OUT = os.environ["ACW_GATE_OUT"]
MODE = os.environ.get("ACW_GATE_MODE", "full")
LEVEL = "/Game/NTWGate/L_NTWGate"
CONFIGURED_GRID = (160000, 800000)
TEMPLATE_GRID = (25200, 76800)
TT = unreal.TraceTypeQuery.TRACE_TYPE_QUERY1
CENTRE_CM = [(308000.0 - 296000.0) * 100.0, -(2768000.0 - 2760000.0) * 100.0, 60000.0]   # centre of the two cells, 600 m
IMG = os.path.join(OUT, "img")
os.makedirs(IMG, exist_ok=True)
os.makedirs(os.path.join(OUT, "flights"), exist_ok=True)

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ued = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
GS = unreal.GameplayStatics
rep = {"stage": "runtime", "mode": MODE, "started": time.time(), "steps": [], "notes": [
    "Desktop UnrealEditor PIE (D3D12) on the development PC - not a packaged build, not mobile hardware.",
    "Frame times include the gate's own per-frame Python work (traces, actor queries)."]}


def step(name, **kw):
    rep["steps"].append(dict(name=name, t=round(time.time() - rep["started"], 1), **kw))
    unreal.log("NTWGATE " + name)
    save_report()


def save_report():
    with open(os.path.join(OUT, "runtime.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1, default=str)


def V(p):
    return unreal.Vector(float(p[0]), float(p[1]), float(p[2]))


def decode(hr):
    """(z_cm, kind, label, normal_z) of a HitResult; None if no blocking hit."""
    if hr is None:
        return None
    t = hr.to_tuple()
    if not t[0]:
        return None
    vecs = [x for x in t if isinstance(x, unreal.Vector)]
    actor = next((x for x in t if isinstance(x, unreal.Actor)), None)
    p = vecs[1] if len(vecs) > 1 else vecs[0]
    nz = vecs[3].z if len(vecs) > 3 else None
    return p.z, kind_of(actor), (actor.get_actor_label() if actor else ""), nz


def kind_of(a):
    if a is None:
        return "?"
    tags = [str(x) for x in a.tags]
    if "NTWChunk" in tags:
        return "C"
    if "NTWStitch" in tags:
        return "S3" if "v3" in tags else "S2" if "v2" in tags else "S1"
    if "NTWFlange" in tags:
        return "F"
    if "NTWBall" in tags:
        return "B"
    if "NTWProbe" in tags:
        return "P"
    if "NTWCrackPlane" in tags:
        return "M"
    if "Landscape" in a.get_class().get_name():
        return "L"
    return "X:" + a.get_class().get_name()


class Ctx:
    pass


def game_world():
    return ued.get_game_world()


def tagged(gw, tag):
    return list(GS.get_all_actors_with_tag(gw, tag))


def trace_down(ctx, x, y, z0=150000.0, z1=-40000.0):
    hr = unreal.SystemLibrary.line_trace_single(ctx.gw, unreal.Vector(x, y, z0), unreal.Vector(x, y, z1), TT, False, ctx.ignore,
                                               unreal.DrawDebugTrace.NONE, True)
    return decode(hr)


def setup(gw):
    c = Ctx()
    c.gw = gw
    c.pawn = GS.get_player_pawn(gw, 0)
    c.pc = GS.get_player_controller(gw, 0)
    lands = list(GS.get_all_actors_of_class(gw, unreal.Landscape))
    if len(lands) != 1:
        raise RuntimeError("PIE actor census: landscapes=%d" % len(lands))
    c.land = lands[0]
    c.comps = list(c.land.get_components_by_class(unreal.LandscapeComponent))
    bx = [k.get_editor_property("section_base_x") for k in c.comps]
    by = [k.get_editor_property("section_base_y") for k in c.comps]
    c.border = [k for k, x, y in zip(c.comps, bx, by) if x in (min(bx), max(bx)) or y in (min(by), max(by))]
    c.cap = tagged(gw, "NTWCapture")[0]
    c.cc = c.cap.get_component_by_class(unreal.SceneCaptureComponent2D)
    c.rt = unreal.RenderingLibrary.create_render_target2d(gw, 960, 540, unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                                          unreal.LinearColor(0.0, 0.0, 0.0, 1.0), False)
    cc = c.cc
    cc.set_editor_property("texture_target", c.rt)
    cc.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    cc.set_editor_property("capture_every_frame", False)
    cc.set_editor_property("capture_on_movement", False)
    cc.set_editor_property("always_persist_rendering_state", True)
    try:
        cc.set_editor_property("max_view_distance_override", 4000000.0)
    except Exception:  # noqa: BLE001
        pass
    pp = unreal.PostProcessSettings()
    pp.set_editor_property("override_auto_exposure_method", True)
    pp.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    pp.set_editor_property("override_auto_exposure_apply_physical_camera_exposure", True)
    pp.set_editor_property("auto_exposure_apply_physical_camera_exposure", False)
    pp.set_editor_property("override_auto_exposure_bias", True)
    pp.set_editor_property("auto_exposure_bias", 1.0)
    pp.set_editor_property("override_motion_blur_amount", True)
    pp.set_editor_property("motion_blur_amount", 0.0)
    pp.set_editor_property("override_bloom_intensity", True)
    pp.set_editor_property("bloom_intensity", 0.0)
    cc.set_editor_property("post_process_settings", pp)
    cc.set_editor_property("post_process_blend_weight", 1.0)
    for cmd in ("r.ScreenPercentage 100", "r.MotionBlurQuality 0", "r.RayTracing 0", "t.MaxFPS 0", "r.VSync 0", "r.VSyncEditor 0"):
        unreal.SystemLibrary.execute_console_command(gw, cmd)
    c.m_dbg = unreal.load_asset("/Game/NTWGate/Materials/M_NTW_DebugStitch")
    c.m_ter = unreal.load_asset("/Game/NTWGate/Materials/M_NTW_Terrain")
    return c


def late_setup(ctx, strict=True):
    """After the first streaming wait: spatially loaded actors (stitches, buildings, chunks) exist now. Fail closed on a census
    mismatch (strict = configured grid, where every chunk cell is in range from the centre). The template-grid session only
    records what its 768 m loading range brought in."""
    stitches = tagged(ctx.gw, "NTWStitch")
    chunks = tagged(ctx.gw, "NTWChunk")
    ctx.buildings = tagged(ctx.gw, "XinyiBuildings")
    ctx.census = {"stitches": len(stitches), "chunks": len(chunks), "unique_chunk_labels": len({c.get_actor_label() for c in chunks}),
                  "xinyi_building_tiles": len(ctx.buildings)}
    if strict and (len(stitches) not in (1, 2) or len(chunks) != 50 or len({c.get_actor_label() for c in chunks}) != 50 or len(ctx.buildings) != 25):
        raise RuntimeError("PIE actor census near Xinyi: stitches=%d chunks=%d buildings=%d" % (len(stitches), len(chunks), len(ctx.buildings)))
    ctx.chunks = chunks
    ctx.st = {next(t for t in ("v3", "v2", "v1") if t in [str(x) for x in a.tags]): a for a in stitches}
    ctx.flanges = {next(str(t) for t in a.tags if str(t).startswith("w")): a for a in tagged(ctx.gw, "NTWFlange")}
    ctx.balls = sorted(tagged(ctx.gw, "NTWBall"), key=lambda a: a.get_actor_label())
    ctx.census.update(flanges=sorted(ctx.flanges), balls=len(ctx.balls), stitch_tags=sorted(ctx.st))
    ctx.ignore = list(ctx.buildings) + ([ctx.pawn] if ctx.pawn else [])


def set_crack_mode(ctx, on):
    """Crack-detection captures: no fog / atmosphere / clouds, so a hole shows the magenta plane untinted (the first probe saw
    a real stitch/chunk gap only as a fog-tinted purple band). Visual captures keep the atmosphere."""
    flags = [unreal.EngineShowFlagsSetting(show_flag_name=f, enabled=not on) for f in ("Fog", "Atmosphere", "VolumetricFog", "Cloud")]
    ctx.cc.set_editor_property("show_flag_settings", flags)


def capture(ctx, name, loc, target=None, rot=None, fov=50.0):
    loc = V(loc)
    if rot is None:
        rot = unreal.MathLibrary.find_look_at_rotation(loc, V(target))
    ctx.cap.set_actor_location_and_rotation(loc, rot, False, True)
    ctx.cc.set_editor_property("fov_angle", float(fov))
    ctx.cc.capture_scene()
    ctx.cc.capture_scene()
    unreal.RenderingLibrary.export_render_target(ctx.gw, ctx.rt, IMG, name + ".png")
    return name + ".png"


def teleport(ctx, p, yaw=0.0, pitch=0.0):
    rot = unreal.Rotator(0.0, pitch, yaw)
    ctx.pawn.set_actor_location_and_rotation(V(p), rot, False, True)
    if ctx.pc:
        ctx.pc.set_control_rotation(rot)


def wait_streaming(ctx, timeout=90.0):
    """Streaming settled: >= 1 s elapsed (the streaming source registers a few frames after a teleport) and 15 consecutive
    frames with IsAllStreamingCompleted. None on timeout."""
    t0 = time.time()
    ok = 0
    while True:
        ok = ok + 1 if streaming_done(ctx) else 0
        if ok >= 15 and time.time() - t0 >= 1.0:
            return round(time.time() - t0, 2)
        if time.time() - t0 > timeout:
            return None
        yield None


def streaming_done(ctx):
    return bool(unreal.NtwGateLibrary.is_all_streaming_completed(ctx.gw))


def cell_states(ctx):
    try:
        return json.loads(unreal.NtwGateLibrary.runtime_cell_states(ctx.gw))
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}


def set_land_lod(ctx, lod, policy):
    """policy 'none': every component lod (-1 = auto); 'border0': Xinyi border components HARD-forced to LOD0 (PR #25);
    'bias': border components keep automatic LOD with LODBias -5 (the 2B-C run showed NO effect: identical cracks to 'none');
    'distF': automatic LOD everywhere with the Landscape LOD0 / LOD distribution multiplied by F (r.LandscapeLOD0DistributionScale
    and r.LandscapeLODDistributionScale; production equivalent: the per-Landscape LOD0DistributionSetting / LODDistributionSetting)."""
    f = float(policy[4:]) if policy.startswith("dist") else 1.0
    for cv in ("r.LandscapeLOD0DistributionScale", "r.LandscapeLODDistributionScale"):
        unreal.SystemLibrary.execute_console_command(ctx.gw, "%s %g" % (cv, f))
    for k in ctx.comps:
        b = k in ctx.border
        k.set_forced_lod(0 if (policy == "border0" and b) else (-1 if (policy == "bias" and b) else lod))
        k.set_lod_bias(-5 if (policy == "bias" and b) else 0)


def set_stitch(ctx, which, debug=False):
    for tag, a in ctx.st.items():
        a.set_actor_hidden_in_game(tag != which)
        a.static_mesh_component.set_material(0, ctx.m_dbg if debug else ctx.m_ter)


# --------------------------------------------------------------------------------------------------------------- phases
def warmup(ctx, seconds):
    """Shader / texture warmup: capture until consecutive frames stop changing (or the time budget is used)."""
    cam = INP["altitude_cameras"][1]
    t0 = time.time()
    n = 0
    while time.time() - t0 < seconds:
        capture(ctx, "warmup", cam["loc"], cam["target"], fov=cam["fov"])
        n += 1
        yield 2.0
    step("warmup", seconds=round(time.time() - t0, 1), captures=n)


def collision_traces(ctx, limit=None, key="traces", out_name="traces.json"):
    tr = INP[key][:limit] if limit else INP[key]
    labels, res = {}, []
    t0 = time.time()
    for i, t in enumerate(tr):
        h = trace_down(ctx, t["ue"][0], t["ue"][1])
        if h is None:
            res.append(None)
        else:
            z, kind, label, nz = h
            li = labels.setdefault(label, len(labels))
            res.append([round(z / 100.0, 4), kind, li, None if nz is None else round(nz, 4)])
        if i % 2000 == 1999:
            yield None
    with open(os.path.join(OUT, out_name), "w", encoding="utf-8") as fh:
        json.dump({"n": len(tr), "labels": sorted(labels, key=labels.get), "hits": res}, fh)
    step("collision_traces", key=key, n=len(tr), misses=sum(1 for r in res if r is None), seconds=round(time.time() - t0, 1),
         kinds={k: sum(1 for r in res if r and r[1] == k) for k in sorted({r[1] for r in res if r})})


def precision(ctx):
    acts = []
    for tag in ("NTWChunk", "NTWStitch", "XinyiBuildings", "NTWProbe", "NTWCrackPlane"):
        for a in tagged(ctx.gw, tag):
            l, r, s = a.get_actor_location(), a.get_actor_rotation(), a.get_actor_scale3d()
            acts.append({"label": a.get_actor_label(), "tags": [str(x) for x in a.tags], "loc": [l.x, l.y, l.z],
                         "rot": [r.roll, r.pitch, r.yaw], "scale": [s.x, s.y, s.z]})
    lt = ctx.land.get_actor_transform()
    l, r, s = ctx.land.get_actor_location(), ctx.land.get_actor_rotation(), ctx.land.get_actor_scale3d()
    corners = {}
    for nm, (i, j) in {"q00": (0, 0), "q630_0": (630, 0), "q0_630": (0, 630), "q630_630": (630, 630)}.items():
        p = unreal.MathLibrary.transform_location(lt, unreal.Vector(float(i), float(j), 0.0))
        corners[nm] = [p.x, p.y, p.z]
    land = {"label": ctx.land.get_actor_label(), "loc": [l.x, l.y, l.z], "rot": [r.roll, r.pitch, r.yaw], "scale": [s.x, s.y, s.z],
            "corners_cm": corners, "components": len(ctx.comps), "border_components": len(ctx.border)}
    probes = {}
    for a in tagged(ctx.gw, "NTWProbe"):
        nm = [str(x) for x in a.tags if str(x) in ("near", "far")][0]
        l0 = a.get_actor_location()
        a.set_actor_location(unreal.Vector(l0.x + 0.01, l0.y - 0.01, l0.z), False, True)
        l1 = a.get_actor_location()
        a.set_actor_location(l0, False, True)
        hits = []
        for dx, dy in ((123.45, -67.89), (-321.0, 222.2), (0.37, 0.61)):
            h = trace_down(ctx, l0.x + dx, l0.y + dy, l0.z + 200000.0, l0.z - 200000.0)
            hits.append(None if h is None else {"z_cm": h[0], "kind": h[1], "expected_top_cm": l0.z + 500.0, "err_cm": h[0] - (l0.z + 500.0)})
        probes[nm] = {"pie_cm": [l0.x, l0.y, l0.z], "moved_cm": [l1.x - l0.x, l1.y - l0.y, l1.z - l0.z], "traces": hits}
    with open(os.path.join(OUT, "precision.json"), "w", encoding="utf-8") as fh:
        json.dump({"actors": acts, "landscape": land, "probes": probes}, fh, indent=1)
    step("precision", actors=len(acts), landscape=land, probes=probes)


# (name, landscape LOD, stitch mesh LOD, chunk mesh LOD); -1 = automatic. Forced per component: r.ForceLOD is a VIEW override
# that also forces every landscape component (LandscapeRender.cpp GetViewLodOverride), so it cannot express mixed combinations.
COMBOS = [("auto", -1, -1, -1), ("L0_T0_C0", 0, 0, 0), ("L0_T0_C2", 0, 0, 2), ("L0_T0_C4", 0, 0, 4), ("L0_T2_C0", 0, 2, 0),
          ("L0_T2_C2", 0, 2, 2), ("L1_T0_C0", 1, 0, 0), ("L2_T0_C0", 2, 0, 0), ("L3_T0_C0", 3, 0, 0), ("L2_T2_C2", 2, 2, 2),
          ("L3_T3_C3", 3, 3, 3), ("L3_T4_C4", 3, 4, 4)]


def set_mesh_lods(ctx, stitch_lod, chunk_lod):
    for a in ctx.chunks:
        a.static_mesh_component.set_forced_lod_model(0 if chunk_lod < 0 else chunk_lod + 1)
    for a in ctx.st.values():
        a.static_mesh_component.set_forced_lod_model(0 if stitch_lod < 0 else stitch_lod + 1)


def lod_matrix(ctx, cams, combos):
    shots = []
    set_crack_mode(ctx, True)
    for stitch in ("v2", "v1"):
        set_stitch(ctx, stitch)
        for name, L, T, C in combos:
            for policy in (("none", "border0") if L != 0 else ("none",)):
                set_mesh_lods(ctx, T, C)
                set_land_lod(ctx, L, policy)
                yield None
                yield None
                yield 0.4
                for cam in cams:
                    fn = "lod_%s_%s_%s_%s" % (stitch, policy, name, cam["name"])
                    capture(ctx, fn, cam["loc"], cam["target"], fov=cam["fov"])
                    shots.append({"file": fn + ".png", "stitch": stitch, "policy": policy, "combo": name, "land_lod": L,
                                  "stitch_lod": T, "chunk_lod": C, "camera": cam["name"]})
                yield None
    set_mesh_lods(ctx, -1, -1)
    set_land_lod(ctx, -1, "none")
    set_stitch(ctx, "v2", debug=True)
    yield 0.4
    for cam in cams:
        fn = "debug_v2_auto_%s" % cam["name"]
        capture(ctx, fn, cam["loc"], cam["target"], fov=cam["fov"])
        shots.append({"file": fn + ".png", "stitch": "v2", "policy": "none", "combo": "auto_debugcolour", "camera": cam["name"]})
    set_stitch(ctx, "v2")
    set_crack_mode(ctx, False)
    with open(os.path.join(OUT, "lod_matrix.json"), "w", encoding="utf-8") as fh:
        json.dump(shots, fh, indent=1)
    step("lod_matrix", captures=len(shots), combos=[c[0] for c in combos])


def altitude_series(ctx):
    shots = []
    set_stitch(ctx, "v2")
    set_mesh_lods(ctx, -1, -1)
    for policy in ("none", "border0"):
        set_land_lod(ctx, -1, policy)
        yield 0.4
        for cam in INP["altitude_cameras"]:
            teleport(ctx, cam["loc"])
            yield from wait_streaming(ctx, 30.0)
            yield 0.3
            fn = "alt_%s_%s" % (policy, cam["name"])
            capture(ctx, fn, cam["loc"], cam["target"], fov=cam["fov"])
            shots.append({"file": fn + ".png", "policy": policy, "camera": cam["name"]})
    set_land_lod(ctx, -1, "none")
    step("altitude_series", captures=len(shots), shots=shots)


def flight(ctx, agl, tag, with_capture, max_seconds=None, crack=False, period=1.0):
    path = INP["flight"]["paths"][str(agl)]
    spd = INP["flight"]["speed_mps"] * 100.0
    seg = 5000.0
    total = seg * (len(path) - 1)
    d = (path[-1][0] - path[0][0], path[-1][1] - path[0][1])
    dl = math.hypot(*d)
    ux, uy = d[0] / dl, d[1] / dl
    yaw = math.degrees(math.atan2(uy, ux))
    ahead = (0.0, 50000.0, 100000.0, 200000.0, 400000.0, 600000.0)
    # building tiles have no collision; while flying they stream in / out, so only the pawn is ignored (a streamed-out actor
    # in the ignore list is an invalid object and aborted the first template-grid session)
    ctx.ignore = [ctx.pawn] if ctx.pawn else []
    teleport(ctx, path[0], yaw)
    w = yield from wait_streaming(ctx, 90.0)
    yield 2.0
    c0 = cell_states(ctx)
    if crack:
        set_crack_mode(ctx, True)
    rec, caps = [], []
    t, last, next_cap = 0.0, time.perf_counter(), 0.0
    while True:
        yield None
        now = time.perf_counter()
        dt = now - last
        last = now
        t += dt
        s = spd * t
        if s > total or (max_seconds and t > max_seconds):
            break
        i = min(int(s // seg), len(path) - 2)
        f = (s - i * seg) / seg
        p = [path[i][k] + f * (path[i + 1][k] - path[i][k]) for k in range(3)]
        ctx.pawn.set_actor_location(V(p), False, True)
        if ctx.pc:
            ctx.pc.set_control_rotation(unreal.Rotator(0.0, -8.0, yaw))
        n_chunks = len(tagged(ctx.gw, "NTWChunk"))
        cs = cell_states(ctx)
        done = streaming_done(ctx)
        g = ""
        for a in ahead:
            h = trace_down(ctx, p[0] + ux * a, p[1] + uy * a)
            g += "-" if h is None else h[1][0]
        rec.append([round(time.time(), 4), round(dt * 1000.0, 3), round(GS.get_world_delta_seconds(ctx.gw) * 1000.0, 3), round(s / 100.0, 1),
                    n_chunks, cs.get("loaded"), cs.get("activated"), cs.get("total"), int(done), g])
        if with_capture and t >= next_cap:
            fn = "flight_%s_%04.1fs" % (tag, t)
            capture(ctx, fn, [p[0] - ux * 30000.0, p[1] - uy * 30000.0, p[2] + 8000.0], rot=unreal.Rotator(0.0, -10.0, yaw), fov=70.0)
            caps.append({"file": fn + ".png", "t": round(t, 2), "s_m": round(s / 100.0, 1), "crack_mode": crack})
            next_cap += period
    if crack:
        set_crack_mode(ctx, False)
    out = {"tag": tag, "agl_m": agl, "speed_mps": INP["flight"]["speed_mps"], "elapsed_s": round(t, 3), "streaming_wait_s": w,
           "cells_before": c0, "ahead_cm": ahead, "dir": [ux, uy], "start_cm": path[0],
           "columns": ["wall", "dt_ms", "world_dt_ms", "s_m", "chunk_actors", "cells_loaded", "cells_activated", "cells_total",
                       "streaming_complete", "ground_ahead"], "frames": rec, "captures": caps}
    with open(os.path.join(OUT, "flights", tag + ".json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    dts = sorted(r[1] for r in rec)
    step("flight", tag=tag, agl_m=agl, frames=len(rec), elapsed_s=round(t, 2), streaming_wait_s=w,
         dt_ms_p50=dts[len(dts) // 2] if dts else None, dt_ms_p99=dts[int(len(dts) * 0.99)] if dts else None,
         dt_ms_max=dts[-1] if dts else None, ground_miss_frames=sum(1 for r in rec if "-" in r[9][:5]), captures=len(caps))


# ------------------------------------------------------------------------------------------- Phase 2B-C closure phases
def decode_full(hr):
    if hr is None:
        return None
    t = hr.to_tuple()
    if not t[0]:
        return None
    vecs = [x for x in t if isinstance(x, unreal.Vector)]
    actor = next((x for x in t if isinstance(x, unreal.Actor)), None)
    p = vecs[1] if len(vecs) > 1 else vecs[0]
    return [round(p.x / 100.0, 4), round(p.y / 100.0, 4), round(p.z / 100.0, 4), kind_of(actor), round(float(t[2]), 5), bool(t[1])]


def set_flange(ctx, which):
    for tag, a in ctx.flanges.items():
        a.set_actor_enable_collision(tag == which)


def run_sweeps(ctx, out_name):
    res = []
    for i, sw in enumerate(INP["sweeps"]):
        a, b = V(sw["start"]), V(sw["end"])
        if sw["radius_m"] <= 0:
            hr = unreal.SystemLibrary.line_trace_single(ctx.gw, a, b, TT, False, ctx.ignore, unreal.DrawDebugTrace.NONE, True)
        else:
            hr = unreal.SystemLibrary.sphere_trace_single(ctx.gw, a, b, sw["radius_m"] * 100.0, TT, False, ctx.ignore,
                                                          unreal.DrawDebugTrace.NONE, True)
        res.append(decode_full(hr))
        if i % 1000 == 999:
            yield None
    with open(os.path.join(OUT, out_name), "w", encoding="utf-8") as fh:
        json.dump({"n": len(res), "hits": res}, fh)
    step("sweeps", out=out_name, n=len(res), misses=sum(1 for r in res if r is None))


def set_ccd(ctx, on):
    for ball in ctx.balls:
        ball.static_mesh_component.set_use_ccd(bool(on))


def run_drops(ctx, out_name, v0_mps, height_m, key="drops"):
    """Movable 10 cm spheres dropped onto points EXACTLY on the boundary line (and the 4 corners), or onto the 1 m inside /
    outside controls (key drops_in / drops_out); 4 s of simulation. Velocities are reset explicitly on every batch."""
    D = INP[key]
    for ball, d in zip(ctx.balls, D):
        c = ball.static_mesh_component
        c.set_simulate_physics(False)
        ball.set_actor_location(unreal.Vector(d["ue_xy"][0], d["ue_xy"][1], (d["surface_z_m"] + height_m) * 100.0), False, True)
    yield None
    for ball in ctx.balls[:len(D)]:
        c = ball.static_mesh_component
        c.set_simulate_physics(True)
        c.set_physics_linear_velocity(unreal.Vector(0.0, 0.0, v0_mps * 100.0), False)
        try:
            c.set_physics_angular_velocity_in_degrees(unreal.Vector(0.0, 0.0, 0.0), False)
        except Exception:  # noqa: BLE001
            pass
        c.wake_rigid_body()
    traj = [[] for _ in D]
    t0 = time.time()
    while time.time() - t0 < 4.0:
        yield None
        tt = round(time.time() - t0, 3)
        for i, ball in enumerate(ctx.balls[:len(D)]):
            l = ball.get_actor_location()
            traj[i].append([tt, round(l.x / 100.0, 4), round(l.y / 100.0, 4), round(l.z / 100.0, 4)])
    for ball in ctx.balls[:len(D)]:
        ball.static_mesh_component.set_simulate_physics(False)
        ball.set_actor_location(unreal.Vector(11000000.0, -10997000.0, 30000.0), False, True)
    with open(os.path.join(OUT, out_name), "w", encoding="utf-8") as fh:
        json.dump({"v0_mps": v0_mps, "height_m": height_m, "key": key, "drops": D, "trajectories": traj}, fh)
    fell = sum(1 for d, tr in zip(D, traj) if tr and tr[-1][3] < d["surface_z_m"] - 1.0)
    step("physics_drops", out=out_name, v0_mps=v0_mps, height_m=height_m, balls=len(D), fell_through=fell)


def collision_variant(ctx, v):
    tag = v or "none"
    set_flange(ctx, v)
    yield None
    yield from collision_traces(ctx, key="traces", out_name="traces_%s.json" % tag)
    yield from collision_traces(ctx, key="micro_traces", out_name="micro_%s.json" % tag)
    yield from run_sweeps(ctx, "sweeps_%s.json" % tag)
    yield from run_drops(ctx, "drops_%s_v0.json" % tag, 0.0, 3.0)
    yield from run_drops(ctx, "drops_%s_v100.json" % tag, -100.0, 30.0)


def capture_set(ctx, prefix, cams, meta, shots):
    for cam in cams:
        fn = "%s_%s" % (prefix, cam["name"])
        capture(ctx, fn, cam["loc"], cam["target"], fov=cam["fov"])
        shots.append(dict(meta, file=fn + ".png", camera=cam["name"]))


def set_chunk_pattern(ctx, even_lod, odd_lod, stitch_lod):
    for a in ctx.chunks:
        lab = a.get_actor_label()                       # NTW_<cell>_ch<a><b>
        par = (int(lab[-2]) + int(lab[-1]) + (0 if "0345" in lab else 1)) % 2
        lod = even_lod if par == 0 else odd_lod
        a.static_mesh_component.set_forced_lod_model(0 if lod < 0 else lod + 1)
    for a in ctx.st.values():
        a.static_mesh_component.set_forced_lod_model(0 if stitch_lod < 0 else stitch_lod + 1)


LAND_POLICIES = ("none", "border0", "bias")


def closure_lod(ctx):
    shots = []
    cams = INP["cameras"]
    set_crack_mode(ctx, True)
    teleport(ctx, CENTRE_CM)
    yield from wait_streaming(ctx, 60.0)
    # 1) Landscape border policy under AUTOMATIC mesh + Landscape LOD (13 seam cameras)
    for pol in LAND_POLICIES:
        set_mesh_lods(ctx, -1, -1)
        set_land_lod(ctx, -1, pol)
        yield None
        yield 0.5
        capture_set(ctx, "pol_%s_auto" % pol, cams, {"test": "landscape_policy", "policy": pol, "land_lod": -1, "stitch_lod": -1, "chunk_lod": -1}, shots)
        yield None
    # 2) stitch x chunk: every forced combination, Landscape at LOD0 everywhere (isolates the stitch / chunk seam)
    set_land_lod(ctx, 0, "none")
    for T in range(5):
        for C in range(5):
            set_mesh_lods(ctx, T, C)
            yield None
            yield 0.3
            capture_set(ctx, "tc_T%d_C%d" % (T, C), cams, {"test": "stitch_x_chunk", "policy": "L0", "land_lod": 0, "stitch_lod": T, "chunk_lod": C}, shots)
            yield None
    # 3) chunk / chunk mixed LOD (checkerboard), stitch automatic
    for a_, b_ in ((0, 2), (1, 3), (2, 4), (0, 4)):
        set_chunk_pattern(ctx, a_, b_, -1)
        yield None
        yield 0.3
        capture_set(ctx, "chk_%d_%d" % (a_, b_), cams, {"test": "chunk_checkerboard", "policy": "L0", "land_lod": 0, "stitch_lod": -1,
                                                       "chunk_lod": "%d/%d" % (a_, b_)}, shots)
        yield None
    # 4) automatic-LOD dolly transitions (everything automatic), per Landscape border policy
    set_mesh_lods(ctx, -1, -1)
    for pol in LAND_POLICIES:
        set_land_lod(ctx, -1, pol)
        yield 0.5
        for path in INP["dolly"]:
            for i, st_ in enumerate(path["steps"]):
                capture(ctx, "dolly_%s_%s_%02d" % (pol, path["name"], i), st_["loc"], path["target"], fov=path["fov"])
                shots.append({"test": "dolly", "policy": pol, "path": path["name"], "step": i, "dist_m": st_["dist_m"], "alt_m": st_["alt_m"],
                              "file": "dolly_%s_%s_%02d.png" % (pol, path["name"], i), "camera": "dolly_" + path["name"]})
                yield None
    set_crack_mode(ctx, False)
    set_land_lod(ctx, -1, LAND_POLICIES[-1])
    with open(os.path.join(OUT, "closure_lod.json"), "w", encoding="utf-8") as fh:
        json.dump(shots, fh, indent=1)
    step("closure_lod", captures=len(shots))


def low_scalability_flight(ctx, name):
    """Same 300 m AGL flight at engine scalability 0, so CPU-side streaming hitches are less masked by the integrated GPU."""
    unreal.SystemLibrary.execute_console_command(ctx.gw, "scalability 0")
    yield 1.0
    yield from flight(ctx, 300, "%s_agl300_scal0" % name, False)
    unreal.SystemLibrary.execute_console_command(ctx.gw, "scalability 3")
    yield 1.0


def session(name, grid, kind):
    g = json.loads(unreal.NtwGateLibrary.configure_runtime_grid(grid[0], grid[1]))
    step("session_grid", session=name, requested=grid, previous=g, now=json.loads(unreal.NtwGateLibrary.describe_runtime_grid()))
    les.editor_request_begin_play()
    t0 = time.time()
    while game_world() is None:
        if time.time() - t0 > 180:
            raise RuntimeError("PIE did not start")
        yield None
    yield 3.0
    ctx = setup(game_world())
    teleport(ctx, CENTRE_CM)     # every chunk cell is within the 8 km loading range from here (nearest chunk corner <= 6.8 km)
    w = yield from wait_streaming(ctx, 120.0)
    late_setup(ctx, strict=(kind != "template"))
    step("pie_started", census=ctx.census, session=name, pie_start_s=round(time.time() - t0, 1), streaming_wait_s=w, cells=cell_states(ctx),
         chunk_actors=len(tagged(ctx.gw, "NTWChunk")), landscape_components=len(ctx.comps), border_components=len(ctx.border),
         pawn=ctx.pawn.get_class().get_name() if ctx.pawn else None, world=ctx.gw.get_name())
    if kind == "closure_lod":
        # Phase 2B-C LOD re-run on the neighbour-skirt terrain (v4) with Landscape LOD-distribution policies; flights after
        global LAND_POLICIES
        LAND_POLICIES = tuple(os.environ.get("ACW_GATE_LAND_POLICIES", "none,border0,dist4,dist16").split(","))
        yield from warmup(ctx, 30.0)
        set_flange(ctx, "w05")
        yield from closure_lod(ctx)
        fpols = [p_ for p_ in LAND_POLICIES if p_ != "border0"]
        for pol in fpols:
            set_land_lod(ctx, -1, pol)
            yield from flight(ctx, 300, "%s_%s_agl300_crackcap" % (name, pol), True, crack=True, period=0.5)
        for pol in fpols:
            set_land_lod(ctx, -1, pol)
            for agl in (150, 300, 600, 800):
                yield from flight(ctx, agl, "%s_%s_agl%d" % (name, pol, agl), False)
        set_land_lod(ctx, -1, LAND_POLICIES[-1])
    elif kind == "probe_points":
        res = []
        for v in (None, "w05", "w10"):
            set_flange(ctx, v)
            yield 0.3
            for pr in INP["probes"]:
                A, B = V(pr["a"]), V(pr["b"])
                if pr["r"] <= 0:
                    hr = unreal.SystemLibrary.line_trace_multi(ctx.gw, A, B, TT, False, ctx.ignore, unreal.DrawDebugTrace.NONE, True)
                else:
                    hr = unreal.SystemLibrary.sphere_trace_multi(ctx.gw, A, B, pr["r"] * 100.0, TT, False, ctx.ignore, unreal.DrawDebugTrace.NONE, True)
                hits = [decode_full(h) for h in (hr or [])]
                res.append(dict(pr, flange=v or "none", hits=hits))
        with open(os.path.join(OUT, "probe_points.json"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1)
        step("probe_points", n=len(res))
    elif kind == "physics":
        # final collision configuration (surface-only complex collision + flange variants): traces, micro, sweeps, then
        # physics drops on the boundary and on 1 m inside / outside controls, repeated in two orders; 100 m/s drops with
        # CCD off and on (all three point sets) to separate tunnelling from seam leaks
        yield from warmup(ctx, 10.0)
        for v in (None, "w05", "w10"):
            set_flange(ctx, v)
            yield 0.3
            yield from collision_traces(ctx, key="traces", out_name="traces_%s.json" % (v or "none"))
            yield from collision_traces(ctx, key="micro_traces", out_name="micro_%s.json" % (v or "none"))
            yield from run_sweeps(ctx, "sweeps_%s.json" % (v or "none"))
        for rep_ in (1, 2):
            for v in ((None, "w05", "w10") if rep_ == 1 else ("w10", "w05", None)):
                set_flange(ctx, v)
                yield 0.5
                set_ccd(ctx, False)
                for key in ("drops", "drops_in", "drops_out"):
                    yield from run_drops(ctx, "phys_r%d_%s_%s_v0.json" % (rep_, v or "none", key), 0.0, 3.0, key)
                for ccd in (False, True):
                    set_ccd(ctx, ccd)
                    for key in ("drops", "drops_in", "drops_out"):
                        yield from run_drops(ctx, "phys_r%d_%s_%s_v100%s.json" % (rep_, v or "none", key, "_ccd" if ccd else ""), -100.0, 30.0, key)
                set_ccd(ctx, False)
    elif kind == "closure":
        yield from warmup(ctx, 30.0)
        for v in (None, "w10", "w05"):
            yield from collision_variant(ctx, v)
        set_flange(ctx, "w10")
        precision(ctx)
        yield from closure_lod(ctx)
        set_land_lod(ctx, -1, "bias")
        for agl in (150, 300, 600, 800):
            yield from flight(ctx, agl, "%s_bias_agl%d" % (name, agl), False)
        yield from flight(ctx, 300, "%s_bias_agl300_crackcap" % name, True, crack=True, period=0.5)
        set_land_lod(ctx, -1, "none")
        yield from flight(ctx, 300, "%s_none_agl300_crackcap" % name, True, crack=True, period=0.5)
        set_land_lod(ctx, -1, "bias")
    elif kind == "micro":
        yield from collision_traces(ctx, key="micro_traces", out_name="micro_traces.json")
    elif MODE == "probe":
        hr = unreal.SystemLibrary.line_trace_single(ctx.gw, unreal.Vector(1000000.0, -700000.0, 150000.0), unreal.Vector(1000000.0, -700000.0, -40000.0),
                                                   TT, False, ctx.ignore, unreal.DrawDebugTrace.NONE, True)
        step("probe_hit_tuple", tuple=[type(x).__name__ + ":" + str(x)[:80] for x in (hr.to_tuple() if hr else [])])
        yield from warmup(ctx, 60.0)
        yield from collision_traces(ctx, limit=400)
        precision(ctx)
        yield from lod_matrix(ctx, INP["cameras"][:2], [COMBOS[0], COMBOS[2], COMBOS[4], COMBOS[8]])
        yield from flight(ctx, 300, name + "_probe", True, max_seconds=8.0)
    elif kind == "full":
        yield from warmup(ctx, 30.0)
        yield from collision_traces(ctx)
        precision(ctx)
        yield from lod_matrix(ctx, INP["cameras"], COMBOS)
        yield from altitude_series(ctx)
        for agl in (150, 300, 600, 800):
            yield from flight(ctx, agl, "%s_agl%d" % (name, agl), False)
        yield from low_scalability_flight(ctx, name)
        yield from flight(ctx, 300, "%s_agl300_captured" % name, True)
    else:
        yield from warmup(ctx, 10.0)
        yield from flight(ctx, 300, "%s_agl300" % name, False)
        yield from flight(ctx, 150, "%s_agl150" % name, False)
        yield from low_scalability_flight(ctx, name)
        yield from flight(ctx, 300, "%s_agl300_captured" % name, True)
    les.editor_request_end_play()
    t0 = time.time()
    while game_world() is not None and time.time() - t0 < 60:
        yield None
    yield 2.0
    step("pie_ended", session=name)


def main():
    step("editor_background_throttle_off", previous=bool(unreal.NtwGateLibrary.set_editor_background_throttle(False)))
    w = unreal.EditorLevelLibrary.get_editor_world()
    if w is None or w.get_name() != "L_NTWGate":
        les.load_level(LEVEL)
        yield 5.0
    step("level", world=unreal.EditorLevelLibrary.get_editor_world().get_name(), grid=json.loads(unreal.NtwGateLibrary.describe_runtime_grid()))
    yield 5.0
    if MODE in ("closure", "physics", "probe_points", "closure_lod"):
        yield from session("configured", CONFIGURED_GRID, MODE)
    elif MODE == "followup":
        yield from session("configured", CONFIGURED_GRID, "micro")
    else:
        yield from session("configured", CONFIGURED_GRID, "full" if MODE == "full" else "probe")
    if MODE in ("full", "followup"):     # (closure: configured scenario only, clean exit)
        yield from session("template_default_grid", TEMPLATE_GRID, "template")
    unreal.NtwGateLibrary.configure_runtime_grid(*CONFIGURED_GRID)
    step("grid_restored", grid=json.loads(unreal.NtwGateLibrary.describe_runtime_grid()))


_state = {"gen": None, "until": 0.0, "handle": None, "quitting": 0}


def finish():
    rep["seconds"] = round(time.time() - rep["started"], 1)
    save_report()
    if game_world() is not None:
        les.editor_request_end_play()
    _state["quitting"] = 1


def tick(_dt):
    if _state["quitting"]:
        _state["quitting"] += 1
        if _state["quitting"] > 30 and game_world() is None:
            unreal.unregister_slate_post_tick_callback(_state["handle"])
            unreal.SystemLibrary.quit_editor()
        return
    if time.time() < _state["until"]:
        return
    try:
        cmd = next(_state["gen"])
        if isinstance(cmd, (int, float)):
            _state["until"] = time.time() + float(cmd)
    except StopIteration:
        rep.setdefault("status", "COMPLETED")
        finish()
    except Exception:  # noqa: BLE001
        rep["status"] = "ERROR"
        rep["error"] = traceback.format_exc()
        unreal.log_error(rep["error"])
        finish()


_state["gen"] = main()
_state["handle"] = unreal.register_slate_post_tick_callback(tick)
try:
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
except Exception:  # noqa: BLE001
    pass
