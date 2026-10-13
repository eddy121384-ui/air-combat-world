"""Native-game static/F11 capture, identical pipeline to accepted MRQ movies."""
import os,sys,traceback
sys.path.insert(0,os.path.dirname(__file__))
from fs_b1a_common import *
old=json.loads((repo/'unreal/ForestSpike/Saved/ForestSpike/b1a/movie_configs03/receipt.json').read_text())
reopen=json.loads((repo/'unreal/ForestSpike/Saved/ForestSpike/b1a/reopen02/receipt.json').read_text())
result={'status':'FAIL_FS_B1A_MOVIE_CONFIGS','configs':[],'error':None}
try:
 for row in [r for r in reopen['maps'] if not r['path_id']]:
  source=next(c for c in old['configs'][:8] if c['group']==row['group'])
  tag='static_'+row['group']+'_'+row['view']+'_02';folder=repo/'unreal/ForestSpike/Saved/ForestSpike/b1a/movies'/tag
  assert not folder.exists();folder.mkdir(parents=True)
  # Formal static maps have no LevelSequence. Copy them first and bind only
  # after loading the new world; never edit the already measured fixture.
  dest=root+'/NativeStatic/L_'+tag;assert not lib.does_asset_exist(dest)
  assert levels.load_level(row['world_path'])
  world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
  assert unreal.EditorLoadingAndSavingUtils.save_map(world,dest)
  del world
  assert levels.load_level(dest)
  world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();cam=find_actor(actors,'FS_PerfCamera')
  seq=unreal.AssetToolsHelpers.get_asset_tools().create_asset('LS_'+tag,root+'/NativeStatic',unreal.LevelSequence,unreal.LevelSequenceFactoryNew())
  seq.set_display_rate(unreal.FrameRate(60,1));seq.set_clock_source(unreal.UpdateClockSource.TICK);seq.set_playback_start(0);seq.set_playback_end(184)
  binding=seq.add_possessable(cam);section=binding.add_track(unreal.MovieScene3DTransformTrack).add_section();section.set_range(0,184)
  loc,rot=aim(row['pose'])
  for channel,value in zip(section.get_all_channels(),[loc.x,loc.y,loc.z,rot.roll,rot.pitch,rot.yaw,1,1,1]):
   for frame in [0,183]:channel.add_key(unreal.FrameNumber(frame),float(value),0,unreal.MovieSceneTimeUnit.DISPLAY_RATE,unreal.MovieSceneKeyInterpolation.LINEAR)
  cut=seq.add_track(unreal.MovieSceneCameraCutTrack).add_section();cut.set_range(0,184);cut.set_camera_binding_id(unreal.MovieSceneSequenceExtensions.get_binding_id(seq,binding))
  assert lib.save_asset(seq.get_path_name()) and levels.save_current_level()
  before=bind(seq,world);assert len(before)==1 and before[0]['objects']==[cam.get_path_name()]
  config=duplicate(source['config'],root+'/Movies/MRQ_'+tag)
  out=config.find_setting_by_class(unreal.MoviePipelineOutputSetting)
  out.set_editor_property('output_directory',unreal.DirectoryPath(str(folder/'frames')))
  out.set_editor_property('custom_end_frame',184)
  game=config.find_setting_by_class(unreal.MoviePipelineGameOverrideSetting,include_disabled_settings=True)
  assert not game.is_enabled() and not game.get_editor_property('use_lod_zero')
  assert lib.save_asset(config.get_path_name())
  result['configs'].append({**source,'tag':tag,'config':config.get_path_name(),'map':dest,'sequence':seq.get_path_name(),'pose':row['pose'],'before_close_bindings':before,'path_id':row['view'],'frames':184,'output_directory':str(folder/'frames'),
   'scope':'Native static pipeline alignment follow-up: first120 fixed warm output frames; 120..183 are64 consecutive static frames. No shader/material/lighting/LOD change.'})
 assert len(result['configs'])==16
 result['status']='PASS_FS_B1A_NATIVE_STATIC_REOPEN_REQUIRED'
except Exception:result['error']=traceback.format_exc();unreal.log_error(result['error'])
receipt(result);unreal.SystemLibrary.quit_editor()
