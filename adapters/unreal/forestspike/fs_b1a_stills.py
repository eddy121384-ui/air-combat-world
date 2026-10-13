"""Native shaded stills + separate ID/LOD diagnostics. Transient edits only."""
import os,sys,time,traceback
sys.path.insert(0,os.path.dirname(__file__))
from fs_b1a_common import *
cal=json.loads((repo/'tools/forestspike/b1a/frozen_coverage.json').read_text())
assert levels.load_level(root+'/Perf/L_FSB1a_'+spec['id']+'_A1_v1_agl200_p10')
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();cvars=set_cvars(world);hs=components()
for key in ['r.AntiAliasingMethod','r.PostProcessAAQuality','r.ShadowQuality','r.Shadow.CSM.MaxCascades','r.Shadow.DistanceScale','r.ReflectionMethod','foliage.DitheredLOD']:
 cvars[key]=unreal.SystemLibrary.get_console_variable_float_value(key)
for a in actors.get_all_level_actors():
 if isinstance(a,unreal.LevelSequenceActor):actors.destroy_actor(a)
ground={s:unreal.MaterialLibrary.create_dynamic_material_instance(world,lib.load_asset(root+'/Materials/MI_Ground_S'+str(s))) for s in [0,1]}
trees={a:unreal.MaterialLibrary.create_dynamic_material_instance(world,lib.load_asset(root+'/Materials/MI_FS_Tree_'+a)) for a in ['A','B']}
terrain=[find_actor(actors,l).get_component_by_class(unreal.StaticMeshComponent) for l in ['FS_Terrain_Core','FS_Terrain_Context']]
rt=unreal.RenderingLibrary.create_render_target2d(world,1920,1080,unreal.TextureRenderTargetFormat.RTF_RGBA8,unreal.LinearColor(0,0,0,1),False)
camera=actors.spawn_actor_from_class(unreal.SceneCapture2D,unreal.Vector());cap=camera.get_component_by_class(unreal.SceneCaptureComponent2D)
for k,v in {'texture_target':rt,'capture_source':unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,'capture_every_frame':False,'capture_on_movement':False,'always_persist_rendering_state':True,'lod_distance_factor':1.,'fov_angle':91.4928}.items():cap.set_editor_property(k,v)
# UE SceneCapture defaults reflections to None even when the game project uses
# ScreenSpace (r.ReflectionMethod=2). Apply the shared baseline to every arm.
pp=cap.get_editor_property('post_process_settings')
pp.set_editor_property('override_reflection_method',True)
pp.set_editor_property('reflection_method',unreal.ReflectionMethod.SCREEN_SPACE)
cap.set_editor_property('post_process_settings',pp)
poses=list(spec['static_poses'])+[spec['paths']['V3']['poses'][i] for i in [2,6,9]]+[spec['paths']['V5']['poses'][i] for i in [0,3,6,9]]
jobs=[]
for pose in poses:
 for group in spec['groups']:jobs.append({'name':pose['id']+'_'+group+'_visual','kind':'visual','pose':pose,'group':group,'temporal_frames':64 if pose['group']=='V1' else 1})
 for group in ['A1','B1']:
  for kind in ['id','lod']:jobs.append({'name':pose['id']+'_'+group+'_'+kind,'kind':kind,'pose':pose,'group':group})
known={p['id'] for p in poses}
for pose in spec['paths']['V3']['poses']+spec['paths']['V5']['poses'][:-1]:
 if pose['id'] in known:continue
 for group in ['A1','B1']:
  for kind in ['id','lod']:jobs.append({'name':pose['id']+'_'+group+'_'+kind,'kind':kind,'pose':pose,'group':group})
out=output().parent/'captures';out.mkdir();state={'i':0,'ticks':0,'rows':[],'temporal':[],'start':time.monotonic(),'current_arm':None,'current_lod':None}
def configure(j):
 cfg=spec['groups'][j['group']];arm=cfg['arm'];dbg=j['kind']!='visual';lod=j['kind']=='lod'
 if state['current_arm']!=arm or state['current_lod']!=lod:
  populate(hs,arm,cal['counts'][arm],debug=lod);state['current_arm']=arm;state['current_lod']=lod
 for h in hs.values():
  for slot in range(3):h.set_material(slot,None)
  if not lod:h.set_material(0,trees[arm])
 for m in ground.values():m.set_scalar_parameter_value('Dbg',1 if dbg else 0);m.set_scalar_parameter_value('IdGamma',0)
 for m in trees.values():m.set_scalar_parameter_value('Dbg',1 if dbg else 0);m.set_scalar_parameter_value('IdGamma',0)
 for h in terrain:h.set_visibility(not lod,True);h.set_material(0,ground[cfg['s']])
 cap.set_editor_property('show_flag_settings',[unreal.EngineShowFlagsSetting(show_flag_name=n,enabled=not dbg) for n in ['Atmosphere','Fog','VolumetricFog','PostProcessing','AntiAliasing','TemporalAA']])
 loc,rot=aim(j['pose']);camera.set_actor_location_and_rotation(loc,rot,False,True)
 unreal.log('FS_B1A_TREE_BEGIN '+j['name']);unreal.SystemLibrary.execute_console_command(world,'foliage.RebuildFoliageTrees');unreal.log('FS_B1A_TREE_END '+j['name'])
def finish(ok,error=None):
 unreal.unregister_slate_post_tick_callback(handle)
 receipt({'status':'PASS_FS_B1A_STILLS_CAPTURE' if ok else 'FAIL_FS_B1A_STILLS_CAPTURE','cvars':cvars,'captures':state['rows'],'error':error,'scope':'Native 1920x1080 SceneCapture2D FINAL_COLOR_LDR. Diagnostic ID/LOD passes have AA/fog/post off; shaded passes retain baseline TAA/lighting/shadows.'})
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);unreal.SystemLibrary.quit_editor()
def tick(dt):
 try:
  if time.monotonic()-state['start']>7200:raise RuntimeError('Still capture timeout')
  if state['i']==len(jobs):finish(True);return
  j=jobs[state['i']]
  if state['ticks']==0:configure(j);state['temporal']=[];unreal.AutomationLibrary.finish_loading_before_screenshot()
  cap.capture_scene();state['ticks']+=1
  if state['ticks']==52:
   unreal.log('FS_B1A_RENDER_BEGIN '+j['name']);unreal.SystemLibrary.execute_console_command(world,'foliage.LogFoliageFrame')
  warm=120 if j['kind']=='visual' else 60
  if state['ticks']<=warm:return
  unreal.RenderingLibrary.read_render_target_pixel(world,rt,0,0)
  index=state['ticks']-warm-1
  if j.get('temporal_frames',1)>1:
   folder=out/'temporal'/j['name'];folder.mkdir(parents=True,exist_ok=True)
   frame=folder/('frame_%04d.png'%index);assert not frame.exists()
   unreal.RenderingLibrary.export_render_target(world,rt,str(folder),frame.name)
   state['temporal'].append({'frame':index,'file':str(frame),'sha256':sha(frame),'res':[1920,1080]})
   if index==0:
    import shutil
    path=out/(j['name']+'.png');assert not path.exists();shutil.copyfile(frame,path)
   if index+1<j['temporal_frames']:return
  else:
   path=out/(j['name']+'.png');assert not path.exists()
   unreal.RenderingLibrary.export_render_target(world,rt,str(out),path.name)
  path=out/(j['name']+'.png')
  state['rows'].append({'job':j,'file':str(path),'sha256':sha(path),'res':[1920,1080],'counts':{k:h.get_instance_count() for k,h in hs.items()},'temporal':list(state['temporal']),'warm_capture_ticks':warm})
  unreal.log('FS_B1A_RENDER_END '+j['name']);state['i']+=1;state['ticks']=0
 except Exception:finish(False,traceback.format_exc())
unreal.EditorPythonScripting.set_keep_python_script_alive(True);handle=unreal.register_slate_post_tick_callback(tick)
