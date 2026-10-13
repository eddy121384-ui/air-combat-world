"""Create NEW B0.1 meshes/maps/sequences. Never save an original asset."""
import json
import math
import os
import sys
import traceback
from pathlib import Path

import unreal

repo = Path(os.environ['ACW_REPO_ROOT'])
sys.path.insert(0, str(repo / 'adapters/unreal/forestspike'))
from fs_common import find_actor

spec = json.loads(Path(os.environ['ACW_FS_B01_SPEC']).read_text(encoding='utf-8'))
root = spec['asset_root']
report_path = Path(os.environ['ACW_FS_B01_REPORT'])
lib = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
result = {'status': 'FAIL_FS_B01_BUILD', 'asset_root': root, 'spec': spec, 'meshes': {}, 'maps': [], 'error': None}
if report_path.exists() or lib.does_directory_exist(root):
    raise RuntimeError('Refusing existing B0.1 namespace or receipt')


def save(path):
    if not path.startswith(root + '/') or not lib.save_asset(path):
        raise RuntimeError('New asset save failed: ' + path)


def copy(source, dest):
    if lib.does_asset_exist(dest) or not dest.startswith(root + '/'):
        raise RuntimeError('Refusing duplicate target: ' + dest)
    obj = lib.duplicate_asset(source, dest)
    if not obj:
        raise RuntimeError('Duplicate failed: ' + source)
    return obj


def audit_mesh(mesh):
    b = mesh.get_bounds()
    return {'path': mesh.get_path_name(), 'triangles': [mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())],
            'screens': list(sub.get_lod_screen_sizes(mesh)), 'sphere_radius_cm': float(b.sphere_radius),
            'bounds_origin_cm': [b.origin.x, b.origin.y, b.origin.z],
            'material_slots_per_lod': [[sub.get_lod_material_slot(mesh, i, s) for s in range(mesh.get_num_sections(i))] for i in range(mesh.get_num_lods())]}


def aim(p):
    x, n, z = p['eye_enu']
    return unreal.Vector(x * 100, -n * 100, z * 100), unreal.Rotator(0, p['pitch_deg'], p['heading_deg'] - 90)


def bound(seq, world):
    return [{'name': str(b.get_name()), 'objects': [o.get_path_name() for o in unreal.MovieSceneSequenceExtensions.locate_bound_objects(seq, b, world)]}
            for b in seq.get_bindings()]


try:
    reuse = os.environ.get('ACW_FS_B01_REUSE_MESH_BUILD')
    if reuse:
        prior = json.loads(Path(reuse).read_text(encoding='utf-8'))
        assert prior['status'] == 'PASS_FS_B01_BUILD_REOPEN_REQUIRED'
        result['meshes'] = prior['meshes']
        result['reused_mesh_receipt'] = reuse
        for key, rec in result['meshes'].items():
            actual = audit_mesh(lib.load_asset(rec['policy']['path']))
            assert actual['triangles'] == rec['policy']['triangles']
            assert all(abs(a-b)<1e-5 for a,b in zip(actual['screens'],spec['lod_screens']))
    else:
        mats = []
        for i, color in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1))):
            name = 'M_LOD%d' % i
            mat = tools.create_asset(name, root + '/Debug', unreal.Material, unreal.MaterialFactoryNew())
            mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
            mat.set_editor_property('two_sided', True)
            mat.set_editor_property('used_with_instanced_static_meshes', True)
            node = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector)
            node.set_editor_property('constant', unreal.LinearColor(*color))
            unreal.MaterialEditingLibrary.connect_material_property(node, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
            unreal.MaterialEditingLibrary.recompile_material(mat)
            save(root + '/Debug/' + name)
            mats.append(mat)
        original = json.loads((repo / 'unreal/ForestSpike/Saved/ForestSpike/reports/fs_assets.report.json').read_text())['meshes']
        for key, rec in original.items():
            if not key.startswith('Tree_'):
                continue
            source = lib.load_asset(rec['asset'])
            mesh = copy(rec['asset'], root + '/Meshes/' + key)
            if not sub.set_lod_screen_sizes(mesh, spec['lod_screens']):
                raise RuntimeError('Screen-size policy failed: ' + key)
            save(root + '/Meshes/' + key)
            row = {'original': audit_mesh(source), 'policy': audit_mesh(mesh)}
            for policy, src in (('legacy', rec['asset']), ('policy', root + '/Meshes/' + key)):
                path = root + '/Debug/' + key + '_' + policy
                dbg = copy(src, path)
                dbg.set_editor_property('static_materials', [unreal.StaticMaterial(material_interface=m, material_slot_name='LOD%d' % i) for i, m in enumerate(mats)])
                for lod in range(dbg.get_num_lods()):
                    for section in range(dbg.get_num_sections(lod)):
                        sub.set_lod_material_slot(dbg, lod, lod, section)
                save(path)
                row['debug_' + policy] = audit_mesh(dbg)
            result['meshes'][key] = row

    def build_map(arm):
        name = 'L_FSP_B01_' + spec['id'] + '_' + arm + '_V3'
        dest = root + '/Perf/' + name
        if lib.does_asset_exist(dest):
            raise RuntimeError('Refusing existing map')
        # Load the original read-only in memory and save ONLY under a new name.
        # EditorAssetLibrary.duplicate_asset(UWorld) leaves a standalone world
        # that LoadLevel cannot collect; never use asset duplication for maps.
        if not levels.load_level('/Game/ForestSpike/Perf/L_FSP_' + arm + '_S1_v3i_t14_t32'):
            raise RuntimeError('Cannot load template map')
        for actor in list(actors.get_all_level_actors()):
            if isinstance(actor, unreal.LevelSequenceActor):
                actors.destroy_actor(actor)
        cam = find_actor(actors, 'FS_PerfCamera')
        if not cam:
            raise RuntimeError('Camera missing')
        loc, rot = aim(spec['path']['poses'][0])
        cam.set_actor_location_and_rotation(loc, rot, False, True)
        for key in result['meshes']:
            label = 'FS_ArmA' if key == 'Tree_A' else 'FS_ArmB_' + key.removeprefix('Tree_B_')
            comp = find_actor(actors, label).get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
            comp.set_static_mesh(lib.load_asset(result['meshes'][key]['policy']['path']))
            comp.set_cull_distances(0, 50000)
            comp.set_forced_lod_model(0)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        # The map has its FINAL package name before the possessable is added.
        if not unreal.EditorLoadingAndSavingUtils.save_map(world, dest):
            raise RuntimeError('Pre-binding save failed')
        # SaveMap is Save-As: it writes a COPY and leaves the template world
        # active. Reload the saved copy before binding, otherwise the binding
        # still embeds the old package path (the historical B0 defect).
        del world, cam, comp
        if not levels.load_level(dest):
            raise RuntimeError('Cannot reload newly saved map before binding')
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        cam = find_actor(actors, 'FS_PerfCamera')
        assert world.get_path_name().split('.')[0] == dest
        seq_name = 'LS_' + name
        seq_path = root + '/Perf/' + seq_name
        seq = tools.create_asset(seq_name, root + '/Perf', unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
        seq.set_display_rate(unreal.FrameRate(60, 1))
        seq.set_clock_source(unreal.UpdateClockSource.TICK)
        seq.set_playback_start(0)
        seq.set_playback_end(spec['sequence_end_frame'])
        binding = seq.add_possessable(cam)
        section = binding.add_track(unreal.MovieScene3DTransformTrack).add_section()
        section.set_range(0, spec['sequence_end_frame'])
        channels = list(section.get_all_channels())
        keys = [(0, spec['path']['poses'][0])] + [(spec['warm_frames'] + i * 120, p) for i, p in enumerate(spec['path']['poses'])]
        keys.append((spec['sequence_end_frame'] - 1, spec['path']['poses'][-1]))
        for frame, pose in keys:
            p, r = aim(pose)
            for c, value in zip(channels, [p.x, p.y, p.z, r.roll, r.pitch, r.yaw, 1, 1, 1]):
                c.add_key(unreal.FrameNumber(frame), float(value), 0, unreal.MovieSceneTimeUnit.DISPLAY_RATE, unreal.MovieSceneKeyInterpolation.LINEAR)
        cut = seq.add_track(unreal.MovieSceneCameraCutTrack).add_section()
        cut.set_range(0, spec['sequence_end_frame'])
        cut.set_camera_binding_id(unreal.MovieSceneSequenceExtensions.get_binding_id(seq, binding))
        save(seq_path)
        lsa = actors.spawn_actor_from_class(unreal.LevelSequenceActor, unreal.Vector())
        lsa.set_actor_label('FS_B01_Sequence')
        lsa.set_editor_property('level_sequence_asset', seq)
        playback = lsa.get_editor_property('playback_settings')
        playback.set_editor_property('auto_play', True)
        playback.set_editor_property('loop_count', unreal.MovieSceneSequenceLoopCount(0))
        playback.set_editor_property('finish_completion_state_override', unreal.MovieSceneCompletionModeOverride.FORCE_KEEP_STATE)
        lsa.set_editor_property('playback_settings', playback)
        bindings = bound(seq, world)
        if not any(cam.get_path_name() in b['objects'] for b in bindings):
            raise RuntimeError('New binding did not resolve before save')
        if not levels.save_current_level():
            raise RuntimeError('Final map save failed')
        result['maps'].append({'arm': arm, 'name': name, 'world_path': dest, 'sequence_path': seq_path,
                              'before_close_bindings': bindings, 'camera_path': cam.get_path_name(), 'sequence_frames': spec['sequence_end_frame']})
    for arm in ('A', 'B'):
        build_map(arm)
    result['status'] = 'PASS_FS_B01_BUILD_REOPEN_REQUIRED'
except Exception:
    result['error'] = traceback.format_exc()
    unreal.log_error(result['error'])
report_path.parent.mkdir(parents=True, exist_ok=True)
with report_path.open('x', encoding='utf-8') as f:
    json.dump(result, f, indent=2)
unreal.log('FS_B01_BUILD ' + result['status'])
unreal.SystemLibrary.quit_editor()
