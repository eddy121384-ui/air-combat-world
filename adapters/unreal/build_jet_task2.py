"""Task 2 FINAL — placeholder jet + persistent forward movement.

ADDITIVE under /Game/Skyfront/Flight (city/map untouched):
  BP_SkyfrontJet (Pawn): primitive nose+wings+tail, ProjectileMovement
    150 m/s toward 300 m-lateral-of-101 point, basic SpringArm+Camera rig.
  BP_SkyfrontGameMode: DefaultPawnClass = BP_SkyfrontJet (native CDO prop).

Idempotent (safe to rerun after silent sessions): reuses existing assets,
skips component adds when already present. Saves ONLY the 2 new assets.
Prints TASK2_* at every step. Never raises.
"""

import traceback
import unreal

DEST = "/Game/Skyfront/Flight"
JET = "BP_SkyfrontJet"
GM = "BP_SkyfrontGameMode"
JET_VEL = unreal.Vector(-12862.0, 7717.0, 0.0)
CRUISE = 15000.0

PARTS = [
    ("Fuselage", "Cube", (0, 0, 0), (0, 0, 0), (15.0, 2.2, 2.2)),
    ("Nose", "Cone", (850, 0, 0), (-90, 0, 0), (2.2, 2.2, 3.0)),
    ("WingL", "Cube", (100, 335, 0), (0, 0, 0), (2.2, 4.5, 0.25)),
    ("WingR", "Cube", (100, -335, 0), (0, 0, 0), (2.2, 4.5, 0.25)),
    ("TailL", "Cube", (-650, 160, 0), (0, 0, 0), (1.5, 2.0, 0.2)),
    ("TailR", "Cube", (-650, -160, 0), (0, 0, 0), (1.5, 2.0, 0.2)),
    ("Fin", "Cube", (-650, 0, 200), (0, 0, 0), (1.5, 0.2, 2.5)),
]


def step(msg):
    print("TASK2_%s" % msg)


def get_or_create_bp(name, parent):
    lib = unreal.EditorAssetLibrary
    path = "%s/%s" % (DEST, name)
    if lib.does_asset_exist(path):
        step("EXISTS %s" % path)
        return lib.load_asset(path)
    try:
        factory = unreal.BlueprintFactory()
        factory.set_editor_property("parent_class", parent)
        bp = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, DEST, None, factory)
        step("CREATED %s" % path if bp else "NOCREATE %s" % name)
        return bp
    except Exception as e:  # noqa: BLE001
        step("NOCREATE %s %r" % (name, e))
        return None


def ensure_components(bp, tag):
    subsys = unreal.SubobjectDataSubsystem()
    g = subsys.k2_gather_subobject_data_for_blueprint(bp)
    step("%s subobjects=%d" % (tag, len(g)))
    if len(g) > 2:
        step("%s components-present skip-adds" % tag)
        return True
    ok = True
    arm_h = None
    for name, _mesh, _l, _r, _s in PARTS:
        p = unreal.AddNewSubobjectParams()
        p.set_editor_property("new_class", unreal.StaticMeshComponent)
        p.set_editor_property("blueprint_context", bp)
        p.set_editor_property("parent_handle", g[0])
        try:
            h = subsys.add_new_subobject(p)[0]
            r = subsys.rename_subobject(h, name)
            step("%s add %s rename=%r" % (tag, name, r))
            ok = ok and bool(r)
        except Exception as e:  # noqa: BLE001
            step("%s add %s FAIL %r" % (tag, name, e))
            ok = False
    try:
        p = unreal.AddNewSubobjectParams()
        p.set_editor_property("new_class", unreal.ProjectileMovementComponent)
        p.set_editor_property("blueprint_context", bp)
        p.set_editor_property("parent_handle", g[0])
        h = subsys.add_new_subobject(p)[0]
        step("%s add JetMotion rename=%r" % (
            tag, subsys.rename_subobject(h, "JetMotion")))
    except Exception as e:  # noqa: BLE001
        step("%s add JetMotion FAIL %r" % (tag, e))
        ok = False
    try:
        p = unreal.AddNewSubobjectParams()
        p.set_editor_property("new_class", unreal.SpringArmComponent)
        p.set_editor_property("blueprint_context", bp)
        p.set_editor_property("parent_handle", g[0])
        arm_h = subsys.add_new_subobject(p)[0]
        step("%s add ChaseArm rename=%r" % (
            tag, subsys.rename_subobject(arm_h, "ChaseArm")))
    except Exception as e:  # noqa: BLE001
        step("%s add ChaseArm FAIL %r" % (tag, e))
        ok = False
    try:
        p = unreal.AddNewSubobjectParams()
        p.set_editor_property("new_class", unreal.CameraComponent)
        p.set_editor_property("blueprint_context", bp)
        p.set_editor_property("parent_handle", g[0])
        cam_h = subsys.add_new_subobject(p)[0]
        step("%s add ChaseCam rename=%r" % (
            tag, subsys.rename_subobject(cam_h, "ChaseCam")))
        if arm_h is not None:
            try:
                subsys.attach_subobject(arm_h, cam_h)
                step("%s attach ChaseCam->ChaseArm ok" % tag)
            except Exception as e:  # noqa: BLE001
                step("%s attach FAIL %r (cam stays on root)" % (tag, e))
    except Exception as e:  # noqa: BLE001
        step("%s add ChaseCam FAIL %r" % (tag, e))
        ok = False
    step("%s adds-done ok=%s" % (tag, ok))
    return ok


def configure_jet(bp):
    lib = unreal.EditorAssetLibrary
    meshes = {}
    for m in ("Cube", "Cone"):
        try:
            meshes[m] = lib.load_asset(
                "/Engine/BasicShapes/%s.%s" % (m, m))
            step("mesh %s %s" % (m, "ok" if meshes[m] else "MISS"))
        except Exception as e:  # noqa: BLE001
            meshes[m] = None
            step("mesh %s FAIL %r" % (m, e))
    if meshes["Cube"] is None:
        return False
    try:
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        step("jet compiled")
    except Exception as e:  # noqa: BLE001
        step("jet compile FAIL %r" % (e,))
        return False
    try:
        cdo = unreal.get_default_object(
            unreal.BlueprintEditorLibrary.generated_class(bp))
    except Exception as e:  # noqa: BLE001
        step("jet cdo FAIL %r" % (e,))
        return False
    try:
        smcs = cdo.get_components_by_class(unreal.StaticMeshComponent)
        step("jet smc-count=%d" % len(smcs))
    except Exception as e:  # noqa: BLE001
        step("jet enum FAIL %r" % (e,))
        return False
    by_name = {}
    for c in smcs:
        try:
            by_name[c.get_name()] = c
        except Exception:  # noqa: BLE001
            pass
    step("jet smc-names=%s" % sorted(by_name.keys()))
    ok = True
    for name, mesh, loc, rot, scl in PARTS:
        c = by_name.get(name)
        if c is None:
            step("jet %s NOT-FOUND" % name)
            ok = False
            continue
        try:
            c.set_editor_property("static_mesh", meshes[mesh])
            c.set_editor_property("relative_location", unreal.Vector(*loc))
            c.set_editor_property("relative_rotation", unreal.Rotator(*rot))
            c.set_editor_property("relative_scale3d", unreal.Vector(*scl))
            step("jet %s configured" % name)
        except Exception as e:  # noqa: BLE001
            step("jet %s SET FAIL %r" % (name, e))
            ok = False
    try:
        pmcs = cdo.get_components_by_class(unreal.ProjectileMovementComponent)
        step("jet pmc-count=%d" % len(pmcs))
        if pmcs:
            pm = pmcs[0]
            pm.set_editor_property("velocity", JET_VEL)
            pm.set_editor_property("initial_speed", CRUISE)
            pm.set_editor_property("max_speed", CRUISE)
            pm.set_editor_property("projectile_gravity_scale", 0.0)
            pm.set_editor_property("b_should_bounce", False)
            pm.set_editor_property("b_rotation_follows_velocity", True)
            pm.set_editor_property("b_initial_velocity_in_local_space",
                                   False)
            step("jet JetMotion configured")
        else:
            ok = False
    except Exception as e:  # noqa: BLE001
        step("jet JetMotion SET FAIL %r" % (e,))
        ok = False
    try:
        arms = cdo.get_components_by_class(unreal.SpringArmComponent)
        cams = cdo.get_components_by_class(unreal.CameraComponent)
        step("jet arm=%d cam=%d" % (len(arms), len(cams)))
        if arms:
            a = arms[0]
            a.set_editor_property("relative_location",
                                  unreal.Vector(0, 0, 550))
            a.set_editor_property("relative_rotation",
                                  unreal.Rotator(-10, 0, 0))
            a.set_editor_property("target_arm_length", 2200.0)
            a.set_editor_property("b_do_collision_test", False)
            a.set_editor_property("b_enable_camera_lag", True)
            a.set_editor_property("camera_lag_speed", 6.0)
            a.set_editor_property("b_enable_camera_rotation_lag", True)
            a.set_editor_property("camera_rotation_lag_speed", 7.0)
            a.set_editor_property("b_inherit_pitch", True)
            a.set_editor_property("b_inherit_yaw", True)
            a.set_editor_property("b_inherit_roll", False)
            step("jet ChaseArm configured")
        if cams:
            cams[0].set_editor_property("field_of_view", 85.0)
            step("jet ChaseCam configured")
    except Exception as e:  # noqa: BLE001
        step("jet cam SET FAIL %r" % (e,))
        ok = False
    return ok


def save_bp(bp, tag):
    try:
        ok = unreal.EditorAssetLibrary.save_asset(
            bp.get_path_name().split(".")[0])
        step("%s SAVED -> %s" % (tag, ok))
        return bool(ok)
    except Exception as e:  # noqa: BLE001
        step("%s SAVE FAIL %r" % (tag, e))
        return False


def wire_gamemode(gm, jet):
    try:
        jet_cls = unreal.BlueprintEditorLibrary.generated_class(jet)
        gm_gen = unreal.BlueprintEditorLibrary.generated_class(gm)
    except Exception as e:  # noqa: BLE001
        step("gm class FAIL %r" % (e,))
        return False
    if jet_cls is None or gm_gen is None:
        step("gm class None (compile first)")
        return False
    try:
        cdo = unreal.get_default_object(gm_gen)
        try:
            cdo.modify()
        except Exception:  # noqa: BLE001
            pass
        cdo.set_editor_property("default_pawn_class", jet_cls)
        step("gm default_pawn_class set")
        return True
    except Exception as e:  # noqa: BLE001
        step("gm pawn FAIL %r" % (e,))
        return False


def main():
    try:
        step("START")
        jet = get_or_create_bp(JET, unreal.Pawn)
        if jet is None:
            step("ABORT no-jet")
            return
        ensure_components(jet, "jet")
        cfg_ok = configure_jet(jet)
        step("jet configure_ok=%s" % cfg_ok)
        try:
            unreal.BlueprintEditorLibrary.compile_blueprint(jet)
            step("jet recompiled")
        except Exception as e:  # noqa: BLE001
            step("jet recompile FAIL %r" % (e,))
        if not save_bp(jet, "jet"):
            step("ABORT jet-save")
            return
        gm = get_or_create_bp(GM, unreal.GameModeBase)
        if gm is None:
            step("ABORT no-gm")
            return
        if not wire_gamemode(gm, jet):
            step("ABORT gm-wire")
            return
        try:
            unreal.BlueprintEditorLibrary.compile_blueprint(gm)
            step("gm compiled")
        except Exception as e:  # noqa: BLE001
            step("gm compile FAIL %r" % (e,))
        if not save_bp(gm, "gm"):
            step("ABORT gm-save")
            return
        step("VERIFY jet=%s gm=%s" % (
            unreal.EditorAssetLibrary.does_asset_exist(
                "%s/%s" % (DEST, JET)),
            unreal.EditorAssetLibrary.does_asset_exist(
                "%s/%s" % (DEST, GM))))
        step("OK" if cfg_ok else "OK-PARTIAL")
    except Exception:  # noqa: BLE001
        step("FATAL")
        traceback.print_exc()
    step("DONE")


main()
