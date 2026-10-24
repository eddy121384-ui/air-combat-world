"""Read-only dependency probe in an isolated project; NOT a render or baseline."""
import json
import os
from pathlib import Path
import traceback

import unreal

repo = Path(os.environ['ACW_REPO_ROOT']).resolve()
if repo.name != 'xinyi-material-ue58-round1':
    raise RuntimeError('Probe requires the isolated material-test worktree')
out = repo / 'investigation'
out.mkdir(exist_ok=True)
report = {'status': 'FAIL_CONTRACT_DEPENDENCIES', 'map_saved': False,
          'screenshot_count': 0, 'mode': 'NullRHI dependency inspection only'}
try:
    level = '/Game/XinyiV2/L_XinyiV2_Contract'
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not levels.load_level(level):
        raise RuntimeError('Cannot load ' + level)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    tiles, landscapes = [], []
    for actor in actors:
        label = actor.get_actor_label()
        if label.startswith('XinyiRuntimeTile_'):
            component = actor.get_component_by_class(unreal.StaticMeshComponent)
            mesh = component.get_editor_property('static_mesh') if component else None
            tiles.append({'label': label, 'mesh': mesh.get_path_name() if mesh else None,
                          'materials': [m.get_path_name() if m else None for m in component.get_materials()] if component else []})
        if isinstance(actor, unreal.Landscape):
            landscapes.append({'label': label,
                               'components': len(actor.get_components_by_class(unreal.LandscapeComponent))})
    report.update(level=level, actors=len(actors), runtime_tiles=tiles, landscapes=landscapes)
    if len(tiles) != 25 or any(not t['mesh'] or not t['materials'] or None in t['materials'] for t in tiles):
        raise RuntimeError('Expected 25 runtime tile meshes with resolved materials')
    if sum(a['components'] for a in landscapes) != 25:
        raise RuntimeError('Expected 25 existing Landscape components')
    report['status'] = 'PASS_CONTRACT_DEPENDENCIES'
except Exception:
    report['error'] = traceback.format_exc()
finally:
    (out / 'contract-dependency-probe.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    unreal.log('XINYI_MATERIAL_CONTRACT_PROBE ' + report['status'])
    unreal.SystemLibrary.quit_editor()
