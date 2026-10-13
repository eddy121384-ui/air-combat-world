"""Fresh-process persistence check of new native-static map/sequence copies."""
import os,sys,traceback,math
sys.path.insert(0,os.path.dirname(__file__))
from fs_b1a_common import *
old=json.loads((repo/'unreal/ForestSpike/Saved/ForestSpike/b1a/native_static_configs02/receipt.json').read_text())
result={'status':'FAIL_FS_B1A_MOVIE_CONFIGS','configs':[],'error':None}
try:
 assert old['status']=='PASS_FS_B1A_NATIVE_STATIC_REOPEN_REQUIRED' and len(old['configs'])==16
 for c in old['configs']:
  assert levels.load_level(c['map']);world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();cam=find_actor(actors,'FS_PerfCamera');seq=lib.load_asset(c['sequence'])
  binding=bind(seq,world);assert len(binding)==1 and binding[0]['objects']==[cam.get_path_name()]
  loc,rot=aim(c['pose']);actual=cam.get_actor_location();assert math.dist([loc.x,loc.y,loc.z],[actual.x,actual.y,actual.z])<.01
  config=lib.load_asset(c['config']);game=config.find_setting_by_class(unreal.MoviePipelineGameOverrideSetting,include_disabled_settings=True)
  assert not game.is_enabled() and not game.get_editor_property('use_lod_zero')
  result['configs'].append({**c,'after_reopen_bindings':binding})
 result['status']='PASS_FS_B1A_MOVIE_CONFIGS'
except Exception:result['error']=traceback.format_exc();unreal.log_error(result['error'])
receipt(result);unreal.SystemLibrary.quit_editor()
