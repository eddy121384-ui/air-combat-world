"""Existing SceneCapture rig, new output paths, one transient overlay actor."""
import hashlib
import json
import os
import re
from pathlib import Path
import sys

repo=Path(os.environ['ACW_REPO_ROOT']).resolve()
variant=os.environ['ACW_EXEMPLAR_VARIANT']
assert variant in ('before','r1','r2') and repo.name=='xinyi-material-ue58-round1'
home=repo/'unreal/Saved/XinyiExemplar/Walkup269873'
kit=json.loads((home/('kit_'+('r1' if variant=='before' else variant)+'.json')).read_text())
capture_run=os.environ.get('ACW_EXEMPLAR_CAPTURE_RUN','')
assert re.fullmatch(r'[a-zA-Z0-9_-]*',capture_run)
run_home=home/'runs'/capture_run if capture_run else home
out=run_home/'captures'/variant
out.mkdir(parents=True,exist_ok=True)
os.environ['ACW_XINYI_LOOK_TOD']='day'
os.environ['ACW_XINYI_LOOK_CLOUDS']='off'
os.environ['ACW_XINYI_LOOK_SHOTS']=','.join(kit['shots'])
os.environ['ACW_XINYI_LOOK_PERF']=','.join(kit['shots'])
sys.path.insert(0,str(repo/'adapters/unreal/lookdev'))
import unreal
import xinyi_look_capture as capture

# Original module schedules callbacks; no capture happens until this script returns.
capture.OUT=out
capture.shot_specs.update(kit['shots'])

def receipt(name,data):
    (out/name).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    unreal.log('EXEMPLAR_CAPTURE '+str(data.get('status')))

capture.write_report=receipt
settings={**{f'sg.{v}Quality':2 for v in ('ViewDistance','AntiAliasing','Shadow','GlobalIllumination',
          'Reflection','PostProcess','Texture','Effects','Foliage','Shading')},
          'r.ScreenPercentage':100,'r.MotionBlurQuality':0,'r.RayTracing':0}
for k,v in settings.items():
    unreal.SystemLibrary.execute_console_command(capture.world,f'{k} {v}')
placement=None
if variant!='before':
    build=json.loads((home/('import_'+variant+'.json')).read_text())
    assert build['status']=='PASS_EXEMPLAR_IMPORT'
    mesh=unreal.EditorAssetLibrary.load_asset(build['mesh'])
    actor=capture.actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector())
    actor.set_actor_label('XinyiExemplar_Walkup269873_Transient_ToggleOffToRestore')
    component=actor.get_component_by_class(unreal.StaticMeshComponent)
    component.set_static_mesh(mesh)
    component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    component.set_cast_shadow(True)
    pivot=kit['pivot_enu_m']
    desired=[pivot[0]*100,-pivot[1]*100,pivot[2]*100]
    expected=kit['expected_local_bounds']['origin_cm']
    actual=build['actual_bounds_origin_cm']
    placement=[desired[i]+expected[i]-actual[i] for i in range(3)]
    actor.set_actor_location(unreal.Vector(*placement),False,True)

meta={'variant':variant,'building_id':kit['building_id'],'shots':kit['shots'],
      'resolution':[capture.W,capture.H],'lighting':'day','clouds':'off',
      'observed_settings':{k:unreal.SystemLibrary.get_console_variable_int_value(k) for k in settings},
      'level_sha256':hashlib.sha256((repo/'unreal/Content/XinyiLook/L_XinyiLook_Hero.umap').read_bytes()).hexdigest(),
      'base_material_sha256':hashlib.sha256((repo/'unreal/Content/XinyiLook/Materials/M_XinyiCity.uasset').read_bytes()).hexdigest(),
      'overlay_actors_added':0 if variant=='before' else 1,'overlay_placement_ue_cm':placement,
      'level_saved':False,'draw_call_limit':'One extra mesh section: +1 draw per visible raster pass; shadow/depth passes additional. Scene-wide RHI draw calls not measured.',
      'gpu_limit':'GPU-synchronised SceneCapture wall time includes CPU submit/readback, not pure GPU or mobile FPS'}
receipt('metadata.json',meta)
