"""Separate editor process: reload NEW saved maps and verify camera bindings."""
import json
import os
import traceback
from pathlib import Path
import unreal

build = json.loads(Path(os.environ['ACW_FS_B01_BUILD']).read_text(encoding='utf-8'))
output = Path(os.environ['ACW_FS_B01_REPORT'])
if output.exists():
    raise RuntimeError('Existing reopen evidence')
result = {'status': 'FAIL_FS_B01_REOPEN', 'maps': [], 'meshes': [], 'error': None}
try:
    assert build['status'] == 'PASS_FS_B01_BUILD_REOPEN_REQUIRED'
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    def audit_map(row):
        assert levels.load_level(row['world_path'])
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        seq = unreal.EditorAssetLibrary.load_asset(row['sequence_path'])
        bound = [{'name': str(b.get_name()), 'objects': [o.get_path_name() for o in unreal.MovieSceneSequenceExtensions.locate_bound_objects(seq, b, world)]} for b in seq.get_bindings()]
        cameras = [a.get_path_name() for a in actors.get_all_level_actors() if a.get_actor_label() == 'FS_PerfCamera']
        lsa = [a for a in actors.get_all_level_actors() if isinstance(a, unreal.LevelSequenceActor)]
        ok = any(c in b['objects'] for c in cameras for b in bound) and len(lsa) == 1 and lsa[0].get_editor_property('level_sequence_asset') == seq
        result['maps'].append({**row, 'after_reopen_bindings': bound, 'camera_paths': cameras,
                              'playback': [seq.get_playback_start(), seq.get_playback_end()], 'pass': ok})
        assert ok, 'Reopened camera binding/sequence reference invalid'
    for row in build['maps']:
        audit_map(row)
    for key, rec in build['meshes'].items():
        for kind in ('policy', 'debug_policy', 'debug_legacy'):
            mesh = unreal.EditorAssetLibrary.load_asset(rec[kind]['path'])
            actual = {'name': key, 'kind': kind, 'triangles': [mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())],
                      'screens': list(sub.get_lod_screen_sizes(mesh)),
                      'slots': [[sub.get_lod_material_slot(mesh, i, s) for s in range(mesh.get_num_sections(i))] for i in range(mesh.get_num_lods())]}
            actual['pass'] = actual['triangles'] == rec[kind]['triangles'] and all(abs(a-b)<1e-5 for a,b in zip(actual['screens'],rec[kind]['screens']))
            if kind.startswith('debug'):
                actual['pass'] &= actual['slots'] == [[i] * mesh.get_num_sections(i) for i in range(3)]
            result['meshes'].append(actual)
            assert actual['pass'], actual
    result['status'] = 'PASS_FS_B01_REOPEN'
except Exception:
    result['error'] = traceback.format_exc()
    unreal.log_error(result['error'])
with output.open('x', encoding='utf-8') as f:
    json.dump(result, f, indent=2)
unreal.log('FS_B01_REOPEN ' + result['status'])
unreal.SystemLibrary.quit_editor()
