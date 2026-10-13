"""Preregistered matched short native clips. Only output window/path differ from full configs."""
import os,sys,traceback
sys.path.insert(0,os.path.dirname(__file__))
from fs_b1a_common import *
old=json.loads((repo/'unreal/ForestSpike/Saved/ForestSpike/b1a/movie_configs03/receipt.json').read_text())
result={'status':'FAIL_FS_B1A_MOVIE_CONFIGS','configs':[],'error':None}
try:
 for row in old['configs'][:8]:
  tag='clip_'+row['group']+'_'+row['path_id']+'_01';folder=repo/'unreal/ForestSpike/Saved/ForestSpike/b1a/movies'/tag
  assert not folder.exists();folder.mkdir(parents=True)
  config=duplicate(row['config'],root+'/Movies/MRQ_'+tag)
  out=config.find_setting_by_class(unreal.MoviePipelineOutputSetting)
  end=481 if row['path_id']=='V3' else 401
  out.set_editor_property('output_directory',unreal.DirectoryPath(str(folder/'frames')));out.set_editor_property('custom_end_frame',end)
  game=config.find_setting_by_class(unreal.MoviePipelineGameOverrideSetting,include_disabled_settings=True)
  assert not game.is_enabled() and not game.get_editor_property('use_lod_zero')
  assert lib.save_asset(config.get_path_name())
  result['configs'].append({**row,'tag':tag,'config':config.get_path_name(),'frames':end,'output_directory':str(folder/'frames'),
    'scope':'Matched native short clip; complete flight independently verified in game CSV. V3 t14..20, V5 az0..120; same initial 120-frame warm hold.'})
 result['status']='PASS_FS_B1A_MOVIE_CONFIGS'
except Exception:result['error']=traceback.format_exc();unreal.log_error(result['error'])
receipt(result);unreal.SystemLibrary.quit_editor()
