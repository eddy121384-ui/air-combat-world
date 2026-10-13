"""New four-arm fixtures, using accepted save/reload-before-binding construction."""
import os,sys,time,traceback
sys.path.insert(0,os.path.dirname(__file__))
from fs_b1a_common import *
cal=json.loads((repo/'tools/forestspike/b1a/frozen_coverage.json').read_text())
assert cal['status']=='PASS_FS_B1A_COVERAGE'
assert not lib.does_directory_exist(root+'/Perf')
tools=unreal.AssetToolsHelpers.get_asset_tools();mel=unreal.MaterialEditingLibrary
result={'status':'FAIL_FS_B1A_BUILD','root':root,'maps':[],'mesh_readback':{},'error':None,'registration_sha256':sha(repo/'tools/forestspike/b1a/registered.json'),'coverage_sha256':sha(repo/'tools/forestspike/b1a/frozen_coverage.json')}
def make_sequence(cam,world,name,path):
 seq=tools.create_asset('LS_'+name,root+'/Perf',unreal.LevelSequence,unreal.LevelSequenceFactoryNew())
 seq.set_display_rate(unreal.FrameRate(60,1));seq.set_clock_source(unreal.UpdateClockSource.TICK)
 seq.set_playback_start(0);seq.set_playback_end(path['sequence_end_frame'])
 binding=seq.add_possessable(cam);section=binding.add_track(unreal.MovieScene3DTransformTrack).add_section()
 section.set_range(0,path['sequence_end_frame']);channels=list(section.get_all_channels())
 keys=[(0,path['poses'][0])]+[(120+i*path['frames_per_pose'],p) for i,p in enumerate(path['poses'])]+[(path['sequence_end_frame']-1,path['poses'][-1])]
 for frame,p in keys:
  loc,rot=aim(p)
  for c,v in zip(channels,[loc.x,loc.y,loc.z,rot.roll,rot.pitch,rot.yaw,1,1,1]):c.add_key(unreal.FrameNumber(frame),float(v),0,unreal.MovieSceneTimeUnit.DISPLAY_RATE,unreal.MovieSceneKeyInterpolation.LINEAR)
 cut=seq.add_track(unreal.MovieSceneCameraCutTrack).add_section();cut.set_range(0,path['sequence_end_frame'])
 cut.set_camera_binding_id(unreal.MovieSceneSequenceExtensions.get_binding_id(seq,binding))
 assert lib.save_asset(seq.get_path_name())
 lsa=actors.spawn_actor_from_class(unreal.LevelSequenceActor,unreal.Vector());lsa.set_actor_label('FS_B1A_Sequence')
 lsa.set_editor_property('level_sequence_asset',seq);ps=lsa.get_editor_property('playback_settings')
 ps.set_editor_property('auto_play',True);ps.set_editor_property('loop_count',unreal.MovieSceneSequenceLoopCount(0))
 ps.set_editor_property('finish_completion_state_override',unreal.MovieSceneCompletionModeOverride.FORCE_KEEP_STATE);lsa.set_editor_property('playback_settings',ps)
 bindings=bind(seq,world);assert any(cam.get_path_name() in b['objects'] for b in bindings)
 return seq.get_path_name(),bindings
def one(group,view,pose,path=None):
 cfg=spec['groups'][group];arm=cfg['arm'];name='L_FSB1a_'+spec['id']+'_'+group+'_'+view;dest=root+'/Perf/'+name
 assert not lib.does_asset_exist(dest)
 assert levels.load_level('/Game/ForestSpike/B01_20261013d/Perf/L_FSP_B01_20261013d_'+arm+'_V3')
 for a in actors.get_all_level_actors():
  if isinstance(a,unreal.LevelSequenceActor):actors.destroy_actor(a)
 hs=components();populate(hs,arm,cal['counts'][arm])
 for h in hs.values():h.set_material(0,lib.load_asset(root+'/Materials/MI_FS_Tree_'+arm))
 for label in ['FS_Terrain_Core','FS_Terrain_Context']:
  find_actor(actors,label).get_component_by_class(unreal.StaticMeshComponent).set_material(0,lib.load_asset(root+'/Materials/MI_Ground_S'+str(cfg['s'])))
 cam=find_actor(actors,'FS_PerfCamera');loc,rot=aim(pose);cam.set_actor_location_and_rotation(loc,rot,False,True)
 cc=cam.get_component_by_class(unreal.CameraComponent);cc.set_editor_property('field_of_view',pose['fov_h_deg']);cc.set_editor_property('aspect_ratio',16/9);cc.set_editor_property('constrain_aspect_ratio',True)
 world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
 unreal.SystemLibrary.execute_console_command(world,'foliage.RebuildFoliageTrees')
 assert unreal.EditorLoadingAndSavingUtils.save_map(world,dest)
 del world,cam,cc,hs,h,a
 assert levels.load_level(dest)
 world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();cam=find_actor(actors,'FS_PerfCamera')
 assert world.get_path_name().split('.')[0]==dest
 row={'group':group,'arm':arm,'s':cfg['s'],'view':view,'name':name,'world_path':dest,'pose':pose,'path_id':view if path else None}
 if path:row['sequence_path'],row['before_close_bindings']=make_sequence(cam,world,name,path)
 assert levels.save_current_level();result['maps'].append(row)
 unreal.log('FS_B1A_BUILT '+name)
try:
 for key,rec in prior['meshes'].items():
  mesh=lib.load_asset(root+'/Meshes/'+key)
  actual={'triangles':[mesh.get_num_triangles(i) for i in range(3)],'screens':list(sub.get_lod_screen_sizes(mesh))}
  assert actual['triangles']==rec['policy']['triangles'] and all(abs(x-y)<1e-5 for x,y in zip(actual['screens'],spec['lod_screens']))
  result['mesh_readback'][key]=actual
 for s in [0,1]:
  mic=tools.create_asset('MI_Ground_S'+str(s),root+'/Materials',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
  mic.set_editor_property('parent',lib.load_asset(root+'/Materials/M_FS_Ground'))
  for k,v in {'SCore':s,'SCtx':s,'Und':0,'dS':500,'wS':100,'Dbg':0,'IdGamma':1}.items():mel.set_material_instance_scalar_parameter_value(mic,k,float(v))
  mel.update_material_instance(mic);assert lib.save_asset(mic.get_path_name())
 for group in spec['groups']:
  for p in spec['static_poses']:one(group,p['id'],p)
  for view,path in spec['paths'].items():one(group,view,path['poses'][0],path)
 assert len(result['maps'])==24
 result['status']='PASS_FS_B1A_BUILD_REOPEN_REQUIRED'
except Exception:
 result['error']=traceback.format_exc();unreal.log_error(result['error'])
receipt(result);unreal.SystemLibrary.quit_editor()
