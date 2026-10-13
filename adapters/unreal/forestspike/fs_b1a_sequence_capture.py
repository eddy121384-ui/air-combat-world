"""Native fixed-step saved-sequence replay, actual bound camera readback, persistent TAA state."""
import os,sys,time,traceback,math
sys.path.insert(0,os.path.dirname(__file__))
from fs_b1a_common import *
sys.path.insert(0,str(repo/'tools/forestspike/b1a'))
from integrity import expected
from motion_integrity import angle
group=os.environ['ACW_FS_B1A_GROUP'];view=os.environ['ACW_FS_B1A_PATH']
reopen=json.loads((repo/'unreal/ForestSpike/Saved/ForestSpike/b1a/reopen02/receipt.json').read_text())
cfg=next(r for r in reopen['maps'] if r['group']==group and r['view']==view)
assert levels.load_level(cfg['world_path'])
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();cvars=set_cvars(world)
cam=find_actor(actors,'FS_PerfCamera');seq=lib.load_asset(cfg['sequence_path']);bindings=bind(seq,world)
assert any(cam.get_path_name() in b['objects'] for b in bindings)
player,player_actor=unreal.LevelSequencePlayer.create_level_sequence_player(world,seq,unreal.MovieSceneSequencePlaybackSettings())
rt=unreal.RenderingLibrary.create_render_target2d(world,1920,1080,unreal.TextureRenderTargetFormat.RTF_RGBA8,unreal.LinearColor(0,0,0,1),False)
cap_actor=actors.spawn_actor_from_class(unreal.SceneCapture2D,unreal.Vector());cap=cap_actor.get_component_by_class(unreal.SceneCaptureComponent2D)
for k,v in {'texture_target':rt,'capture_source':unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,'capture_every_frame':False,'capture_on_movement':False,'always_persist_rendering_state':True,'lod_distance_factor':1.,'fov_angle':cam.get_component_by_class(unreal.CameraComponent).get_editor_property('field_of_view')}.items():cap.set_editor_property(k,v)
end=int(os.environ.get('ACW_FS_B1A_MOVIE_END',120+spec['paths'][view]['flight_intervals']))
out=output().parent/'frames';out.mkdir();state={'frame':0,'records':[],'start':time.monotonic()}
unreal.AutomationLibrary.finish_loading_before_screenshot()
def finish(ok,error=None):
 unreal.unregister_slate_post_tick_callback(handle)
 receipt({'status':'PASS_FS_B1A_SEQUENCE_CAPTURE' if ok else 'FAIL_FS_B1A_SEQUENCE_CAPTURE','group':group,'view':view,'cvars':cvars,
 'sequence':cfg['sequence_path'],'bindings':bindings,'native_camera_frames':state['records'],'error':error,'fps':60,'res':[1920,1080],
 'scope':'Native SceneCapture2D fixed-step evaluation of the saved Level Sequence. Actual bound camera verified every frame; persistent temporal state. Not real-time viewport/cadence or performance measurement.'})
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);unreal.SystemLibrary.quit_editor()
def tick(dt):
 try:
  if time.monotonic()-state['start']>1800:raise RuntimeError('Sequence capture timeout')
  f=state['frame']
  if f>end:finish(True);return
  params=unreal.MovieSceneSequencePlaybackParams();params.set_editor_property('frame',unreal.FrameTime(unreal.FrameNumber(f)));params.set_editor_property('update_method',unreal.UpdatePositionMethod.JUMP)
  player.set_playback_position(params)
  loc=cam.get_actor_location();rot=cam.get_actor_rotation();fw=cam.get_actor_forward_vector();up=cam.get_actor_up_vector()
  xyz=[loc.x,loc.y,loc.z];forward=[fw.x,fw.y,fw.z];upv=[up.x,up.y,up.z];target,tf,tu,phase,seg,t=expected(spec,cfg,f)
  errors={'position_m':math.dist(xyz,target)/100,'forward_deg':angle(forward,tf),'up_deg':angle(upv,tu)}
  assert errors['position_m']<=.05 and max(errors['forward_deg'],errors['up_deg'])<=.02,(f,errors)
  cap_actor.set_actor_location_and_rotation(loc,rot,False,True)
  if f%120==52:
   unreal.log('FS_B1A_SEQUENCE_LOD_REQUEST '+str(f));unreal.SystemLibrary.execute_console_command(world,'foliage.LogFoliageFrame')
  cap.capture_scene();unreal.RenderingLibrary.read_render_target_pixel(world,rt,0,0)
  path=out/('frame_%04d.png'%f);assert not path.exists()
  unreal.RenderingLibrary.export_render_target(world,rt,str(out),path.name)
  assert path.read_bytes()[:8]==b'\x89PNG\r\n\x1a\n'
  state['records'].append({'frame':f,'phase':phase,'segment':seg,'path_t_s':t,'pos_cm':xyz,'forward':forward,'up':upv,'errors':errors,'file':path.name,'bytes':path.stat().st_size,'sha256':sha(path)})
  if f%120==0:unreal.log('FS_B1A_SEQUENCE_FRAME '+str(f))
  state['frame']+=1
 except Exception:finish(False,traceback.format_exc())
unreal.EditorPythonScripting.set_keep_python_script_alive(True);handle=unreal.register_slate_post_tick_callback(tick)
