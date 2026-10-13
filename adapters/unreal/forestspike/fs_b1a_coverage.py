"""New policy copies and actual orthographic coverage. Never save an old map."""
import os,sys
sys.path.insert(0,os.path.dirname(__file__))
from fs_b1a_common import *
import time,traceback
reuse=lib.does_directory_exist(root)
if reuse:
 assert os.environ.get('ACW_FS_B1A_REUSE_COVERAGE_ASSETS')=='1'
 for key,rec in prior['meshes'].items():
  mesh=lib.load_asset(root+'/Meshes/'+key)
  assert [mesh.get_num_triangles(i) for i in range(3)]==rec['policy']['triangles']
  assert all(abs(x-y)<1e-5 for x,y in zip(sub.get_lod_screen_sizes(mesh),spec['lod_screens']))
else:
 for key,rec in prior['meshes'].items():
  duplicate(rec['policy']['path'],root+'/Meshes/'+key)
  duplicate(rec['debug_policy']['path'],root+'/Debug/'+key)
 for name in ['M_FS_Ground','M_FS_Tree','MI_FS_Tree_A','MI_FS_Tree_B']:
  duplicate('/Game/ForestSpike/Materials/'+name,root+'/Materials/'+name)
 for arm in ['A','B']:
  mic=lib.load_asset(root+'/Materials/MI_FS_Tree_'+arm)
  mic.set_editor_property('parent',lib.load_asset(root+'/Materials/M_FS_Tree'))
  unreal.MaterialEditingLibrary.update_material_instance(mic);assert lib.save_asset(mic.get_path_name())
assert levels.load_level('/Game/ForestSpike/L_ForestSpike_B0')
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
cvars=set_cvars(world);hs=components()
ground=unreal.MaterialLibrary.create_dynamic_material_instance(world,lib.load_asset(root+'/Materials/M_FS_Ground'))
for k,v in {'Dbg':1,'IdGamma':0,'Und':0,'SCore':0,'SCtx':0,'dS':500,'wS':100}.items():ground.set_scalar_parameter_value(k,v)
for label in ['FS_Terrain_Core','FS_Terrain_Context']:
 find_actor(actors,label).get_component_by_class(unreal.StaticMeshComponent).set_material(0,ground)
mids={}
for arm in ['A','B']:
 mid=unreal.MaterialLibrary.create_dynamic_material_instance(world,lib.load_asset(root+'/Materials/MI_FS_Tree_'+arm))
 mid.set_scalar_parameter_value('Dbg',1);mid.set_scalar_parameter_value('IdGamma',0);mids[arm]=mid
px=spec['coverage']['px'];out=output().parent/'captures';out.mkdir()
rt=unreal.RenderingLibrary.create_render_target2d(world,px,px,unreal.TextureRenderTargetFormat.RTF_RGBA8,unreal.LinearColor(0,0,0,1),False)
camera=actors.spawn_actor_from_class(unreal.SceneCapture2D,unreal.Vector(0,0,100000),unreal.Rotator(0,-90,-90))
cap=camera.get_component_by_class(unreal.SceneCaptureComponent2D)
for k,v in {'texture_target':rt,'capture_source':unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,'capture_every_frame':False,'capture_on_movement':False,'always_persist_rendering_state':True,'projection_type':unreal.CameraProjectionMode.ORTHOGRAPHIC,'ortho_width':100000.,'lod_distance_factor':1.}.items():cap.set_editor_property(k,v)
cap.set_editor_property('show_flag_settings',[unreal.EngineShowFlagsSetting(show_flag_name=n,enabled=False) for n in ['Atmosphere','Fog','VolumetricFog','PostProcessing','AntiAliasing']])
jobs=[{'arm':a,'count':spec['initial_counts'][a],'name':'coverage_'+a} for a in ['A','B']]
state={'i':0,'ticks':0,'rows':[],'start':time.monotonic()}
def finish(ok,error=None):
 unreal.unregister_slate_post_tick_callback(handle)
 receipt({'status':'PASS_FS_B1A_COVERAGE_CAPTURE' if ok else 'FAIL_FS_B1A_COVERAGE_CAPTURE','cvars':cvars,'id_gamma':0,'reused_verified_new_assets':reuse,'coverage_spec':spec['coverage'],'captures':state['rows'],'error':error,
 'mesh_readback':{k:{'triangles':[lib.load_asset(root+'/Meshes/'+k).get_num_triangles(i) for i in range(3)],'screens':list(sub.get_lod_screen_sizes(lib.load_asset(root+'/Meshes/'+k)))} for k in hs}})
 unreal.EditorPythonScripting.set_keep_python_script_alive(False);unreal.SystemLibrary.quit_editor()
def tick(dt):
 try:
  if state['i']==len(jobs):finish(True);return
  j=jobs[state['i']]
  if state['ticks']==0:
   populate(hs,j['arm'],j['count'])
   for h in hs.values():h.set_cull_distances(0,2000000);h.set_material(0,mids[j['arm']])
   unreal.SystemLibrary.execute_console_command(world,'foliage.RebuildFoliageTrees')
   unreal.AutomationLibrary.finish_loading_before_screenshot()
  cap.capture_scene();state['ticks']+=1
  if state['ticks']==52:
   unreal.log('FS_B1A_RENDER_BEGIN '+j['name']);unreal.SystemLibrary.execute_console_command(world,'foliage.LogFoliageFrame')
  if state['ticks']<60:return
  unreal.RenderingLibrary.read_render_target_pixel(world,rt,0,0)
  path=out/(j['name']+'.png');assert not path.exists()
  unreal.RenderingLibrary.export_render_target(world,rt,str(out),path.name)
  state['rows'].append({**j,'file':str(path),'sha256':sha(path),'res':[px,px],'instances':{k:h.get_instance_count() for k,h in hs.items()}})
  unreal.log('FS_B1A_RENDER_END '+j['name']);state['i']+=1;state['ticks']=0
 except Exception:finish(False,traceback.format_exc())
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle=unreal.register_slate_post_tick_callback(tick)
