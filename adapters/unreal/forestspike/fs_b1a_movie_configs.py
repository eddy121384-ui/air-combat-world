"""Native MRQ output configs; explicitly disable all cinematic/game/LOD overrides."""
import os,sys,traceback
sys.path.insert(0,os.path.dirname(__file__))
from fs_b1a_common import *
reopen=json.loads((repo/'unreal/ForestSpike/Saved/ForestSpike/b1a/reopen02/receipt.json').read_text())
assert reopen['status']=='PASS_FS_B1A_REOPEN'
tools=unreal.AssetToolsHelpers.get_asset_tools();configs=[];error=None
try:
 for row in [r for r in reopen['maps'] if r['path_id']]+[next(r for r in reopen['maps'] if r['group']=='A1' and r['view']=='V3')]:
  pilot=len(configs)==8;rev=os.environ.get('ACW_FS_B1A_MOVIE_REV','01');tag='mrq_pilot_A1_V3_'+rev if pilot else 'native_'+row['group']+'_'+row['view']+'_'+rev
  folder=repo/'unreal/ForestSpike/Saved/ForestSpike/b1a/movies'/tag
  assert not folder.exists();folder.mkdir(parents=True)
  name='MRQ_'+tag;asset_path=root+'/Movies/'+name
  assert not lib.does_asset_exist(asset_path)
  config=tools.create_asset(name,root+'/Movies',unreal.MoviePipelinePrimaryConfig,unreal.MoviePipelinePrimaryConfigFactory())
  out=config.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
  end=151 if pilot else 121+spec['paths'][row['view']]['flight_intervals']
  for k,v in {'output_directory':unreal.DirectoryPath(str(folder/'frames')),'file_name_format':'frame_{frame_number}',
    'output_resolution':unreal.IntPoint(1920,1080),'use_custom_frame_rate':True,'output_frame_rate':unreal.FrameRate(60,1),
    'override_existing_output':False,'use_custom_playback_range':True,'custom_start_frame':0,'custom_end_frame':end,'zero_pad_frame_numbers':4,'handle_frame_count':0,'output_frame_step':1}.items():out.set_editor_property(k,v)
  game=config.find_or_add_setting_by_class(unreal.MoviePipelineGameOverrideSetting)
  for k in ['cinematic_quality_settings','use_lod_zero','disable_hlods','use_high_quality_shadows','override_view_distance_scale','flush_grass_streaming','override_grass_cull_distance_scale','override_grass_density_scale','flush_streaming_managers','override_virtual_texture_feedback_factor']:game.set_editor_property(k,False)
  game.set_is_enabled(False)
  aa=config.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
  for k,v in {'spatial_sample_count':1,'temporal_sample_count':1,'override_anti_aliasing':False,'engine_warm_up_count':0,'render_warm_up_count':0,'use_camera_cut_for_warm_up':False}.items():aa.set_editor_property(k,v)
  config.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
  config.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
  cv=config.find_or_add_setting_by_class(unreal.MoviePipelineConsoleVariableSetting)
  for k,v in {'foliage.ForceLOD':-1.,'r.ForceLOD':-1.,'foliage.LODDistanceScale':1.,'foliage.RandomLODRange':0.,'r.ViewDistanceScale':1.,'r.ScreenPercentage':100.,'r.MotionBlurQuality':0.,'r.RayTracing':0.}.items():assert cv.add_or_update_console_variable(k,v)
  assert lib.save_asset(asset_path)
  config.initialize_transient_settings()
  settings={'tag':tag,'config':config.get_path_name(),'map':row['world_path'],'sequence':row['sequence_path'],'group':row['group'],'path_id':row['view'],'frames':end,'res':[1920,1080],
    'game_overrides_enabled':game.is_enabled(),'force_lod_zero':game.get_editor_property('use_lod_zero'),'cinematic_quality':game.get_editor_property('cinematic_quality_settings'),
    'spatial_samples':1,'temporal_samples':1,'aa_override':False,'warm_hold_in_sequence':120,'output_directory':str(folder/'frames')}
  assert not settings['game_overrides_enabled'] and not settings['force_lod_zero'] and not settings['cinematic_quality']
  configs.append(settings)
except Exception:error=traceback.format_exc();unreal.log_error(error)
receipt({'status':'PASS_FS_B1A_MOVIE_CONFIGS' if len(configs)==9 and not error else 'FAIL_FS_B1A_MOVIE_CONFIGS','configs':configs,'error':error})
unreal.SystemLibrary.quit_editor()
