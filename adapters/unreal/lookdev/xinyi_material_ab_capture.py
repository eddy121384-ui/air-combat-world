"""Reuse the accepted SceneCapture2D harness with fixed A/B views.

Candidate material assignments are transient component overrides. Never save a level.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

repo = Path(os.environ['ACW_REPO_ROOT']).resolve()
if repo.name != 'xinyi-material-ue58-round1':
    raise RuntimeError('Capture requires the isolated worktree')
variant = os.environ['ACW_XINYI_MATERIAL_VARIANT']
if variant not in ('baseline', 'candidate'):
    raise RuntimeError('Unknown A/B variant')
cfg = json.loads((repo / 'tools/lookdev/material_round1_shots.json').read_text())
os.environ['ACW_XINYI_LOOK_SHOTS'] = ','.join(cfg['shots'])
os.environ['ACW_XINYI_LOOK_PERF'] = 'walkup,wuxing_roofs'
sys.path.insert(0, str(repo / 'adapters/unreal/lookdev'))
import unreal
import xinyi_look_capture as capture

capture.shot_specs.update(cfg['shots'])
capture.OUT = repo / 'unreal/Saved/XinyiLook/unreal/material_ab_captures' / variant
capture.OUT.mkdir(parents=True, exist_ok=True)

settings = {
    'sg.ViewDistanceQuality': 2, 'sg.AntiAliasingQuality': 2, 'sg.ShadowQuality': 2,
    'sg.GlobalIlluminationQuality': 2, 'sg.ReflectionQuality': 2, 'sg.PostProcessQuality': 2,
    'sg.TextureQuality': 2, 'sg.EffectsQuality': 2, 'sg.FoliageQuality': 2, 'sg.ShadingQuality': 2,
    'r.ScreenPercentage': 100, 'r.MotionBlurQuality': 0, 'r.RayTracing': 0,
}
for name, value in settings.items():
    unreal.SystemLibrary.execute_console_command(capture.world, f'{name} {value}')
swapped = []
if variant == 'candidate':
    mat = unreal.EditorAssetLibrary.load_asset('/Game/XinyiMaterialAB/Materials/M_XinyiCity_Masks')
    if mat is None:
        raise RuntimeError('Candidate material is missing')
    for label, actor in capture.labels.items():
        if not label.startswith(capture.RUNTIME_PREFIX):
            continue
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        mesh = component.get_editor_property('static_mesh')
        if mesh is None or not mesh.get_path_name().startswith('/Game/XinyiLook/Meshes/Tiles/'):
            raise RuntimeError('Unexpected runtime mesh: ' + label)
        if component.get_num_materials() != 1:
            raise RuntimeError('Unexpected material slots: ' + label)
        component.set_material(0, mat)
        swapped.append(label)
    if len(swapped) != 25:
        raise RuntimeError('Expected exactly 25 transient material overrides')

def file_sha(relative):
    return hashlib.sha256((repo / relative).read_bytes()).hexdigest()

metadata = {
    'variant': variant, 'backend': 'existing xinyi_look_capture.py; SceneCapture2D FINAL_COLOR_LDR',
    'resolution': [capture.W, capture.H], 'time_of_day': 'day', 'clouds': 'off',
    'requested_console_settings': settings,
    'observed_console_settings': {k: unreal.SystemLibrary.get_console_variable_int_value(k) for k in settings},
    'camera_specs': cfg['shots'], 'transient_material_overrides': swapped,
    'level_saved': False,
    'look_level_sha256': file_sha('unreal/Content/XinyiLook/L_XinyiLook_Hero.umap'),
    'baseline_city_material_sha256': file_sha('unreal/Content/XinyiLook/Materials/M_XinyiCity.uasset'),
    'motion_limit': 'discrete camera translations at 6 m intervals; continuous-flight flicker not certified',
    'performance_limit': 'Windows GPU-synchronised SceneCapture wall time including submit/readback overhead; no mobile claim',
}
(capture.OUT / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
