"""Separate-process audit of all new B1a fixtures and fixed render state."""
import os,sys,traceback
sys.path.insert(0,os.path.dirname(__file__))
from fs_b1a_common import *
build=json.loads(Path(os.environ['ACW_FS_B1A_BUILD']).read_text())
cal=json.loads((repo/'tools/forestspike/b1a/frozen_coverage.json').read_text())
result={'status':'FAIL_FS_B1A_REOPEN','maps':[],'error':None}
def one(row):
 assert levels.load_level(row['world_path'])
 world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();cvars=set_cvars(world)
 cam=find_actor(actors,'FS_PerfCamera');cc=cam.get_component_by_class(unreal.CameraComponent)
 hs=components();states={}
 for key,h in hs.items():
  mesh=h.get_editor_property('static_mesh');active=(key=='Tree_A')==(row['arm']=='A')
  states[key]={'count':h.get_instance_count(),'mesh':mesh.get_path_name(),'visible':h.get_editor_property('visible'),'forced_lod_model':h.get_editor_property('forced_lod_model'),
    'lod_scale':h.get_editor_property('instance_lod_distance_scale'),'cull_end_cm':h.get_editor_property('instance_end_cull_distance'),'screens':list(sub.get_lod_screen_sizes(mesh)),'cast_shadow':h.get_editor_property('cast_shadow'),'material':h.get_material(0).get_path_name()}
  assert states[key]['forced_lod_model']==0 and states[key]['lod_scale']==1 and states[key]['cull_end_cm']==50000 and states[key]['cast_shadow']
  assert states[key]['visible']==active and all(abs(x-y)<1e-5 for x,y in zip(states[key]['screens'],spec['lod_screens']))
 assert sum(x['count'] for x in states.values())==cal['counts'][row['arm']]
 materials={}
 for label in ['FS_Terrain_Core','FS_Terrain_Context']:
  h=find_actor(actors,label).get_component_by_class(unreal.StaticMeshComponent);m=h.get_material(0)
  materials[label]={'mesh':h.get_editor_property('static_mesh').get_path_name(),'material':m.get_path_name(),'parameters':{k:unreal.MaterialEditingLibrary.get_material_instance_scalar_parameter_value(m,k) for k in ['SCore','SCtx','Und','dS','wS','Dbg']}}
  assert materials[label]['parameters']=={'SCore':row['s'],'SCtx':row['s'],'Und':0,'dS':500,'wS':100,'Dbg':0}
 sc=find_actor(actors,'FS_Sun').get_component_by_class(unreal.DirectionalLightComponent)
 shadows={k:sc.get_editor_property(k) for k in ['dynamic_shadow_distance_movable_light','dynamic_shadow_cascades','cascade_distribution_exponent','intensity']}
 rr={**row,'hism':states,'terrain':materials,'sun':shadows,'cvars':cvars,'camera_fov':cc.get_editor_property('field_of_view'),'pass':True}
 if row['path_id']:
  seq=lib.load_asset(row['sequence_path']);b=bind(seq,world)
  lsa=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.LevelSequenceActor)]
  assert len(lsa)==1 and lsa[0].get_editor_property('level_sequence_asset')==seq and any(cam.get_path_name() in x['objects'] for x in b)
  rr['after_reopen_bindings']=b;rr['playback_range']=[seq.get_playback_start(),seq.get_playback_end()]
 result['maps'].append(rr)
try:
 assert build['status']=='PASS_FS_B1A_BUILD_REOPEN_REQUIRED'
 for row in build['maps']:one(row)
 assert len(result['maps'])==24
 assert all(r['sun']==result['maps'][0]['sun'] for r in result['maps'])
 result['status']='PASS_FS_B1A_REOPEN'
except Exception:
 result['error']=traceback.format_exc();unreal.log_error(result['error'])
receipt(result);unreal.SystemLibrary.quit_editor()
