"""Auto LOD color readback. No forced LOD, no asset saves, separate cull tests."""
import hashlib
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path
import unreal

repo=Path(os.environ['ACW_REPO_ROOT'])
sys.path.insert(0,str(repo/'adapters/unreal/forestspike'))
from fs_common import find_actor
from fs_instances import ARCHETYPES, load_pool, pivot_shift, place

spec=json.loads(Path(os.environ['ACW_FS_B01_SPEC']).read_text())
build=json.loads(Path(os.environ['ACW_FS_B01_BUILD']).read_text())
bounds_file=os.environ.get('ACW_FS_B01_BOUNDS')
bounds=json.loads(Path(bounds_file).read_text()) if bounds_file else None
if bounds:
    assert bounds['status']=='PASS_FS_B01_SOURCE_BOUNDS_RECONSTRUCTION'
report_path=Path(os.environ['ACW_FS_B01_REPORT'])
output=report_path.parent/'captures'
if output.exists() or report_path.exists():raise RuntimeError('Existing LOD evidence')
output.mkdir()
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert levels.load_level('/Game/ForestSpike/L_ForestSpike_B0')
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
lib=unreal.EditorAssetLibrary
hs={key:find_actor(actors,'FS_ArmA' if key=='Tree_A' else 'FS_ArmB_'+key.removeprefix('Tree_B_')).get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent) for key in build['meshes']}
for label in ('FS_Terrain_Core','FS_Terrain_Context'):
    find_actor(actors,label).get_component_by_class(unreal.StaticMeshComponent).set_visibility(False,True)
for cmd in ('foliage.ForceLOD -1','r.ForceLOD -1','foliage.LODDistanceScale 1','foliage.RandomLODRange 0','r.ViewDistanceScale 1','r.ScreenPercentage 100'):
    unreal.SystemLibrary.execute_console_command(world,cmd)
cvars={name:unreal.SystemLibrary.get_console_variable_float_value(name) for name in ('foliage.ForceLOD','r.ForceLOD','foliage.LODDistanceScale','foliage.RandomLODRange','r.ViewDistanceScale')}
assert cvars['foliage.ForceLOD']==-1 and cvars['r.ForceLOD']==-1
rt=unreal.RenderingLibrary.create_render_target2d(world,1920,1080,unreal.TextureRenderTargetFormat.RTF_RGBA8,unreal.LinearColor(0,0,0,1),False)
cap_actor=actors.spawn_actor_from_class(unreal.SceneCapture2D,unreal.Vector())
cap=cap_actor.get_component_by_class(unreal.SceneCaptureComponent2D)
for key,value in (('texture_target',rt),('capture_source',unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR),('capture_every_frame',False),('capture_on_movement',False),('always_persist_rendering_state',True),('lod_distance_factor',1.0)):
    cap.set_editor_property(key,value)
flags=[]
for name in ('Atmosphere','Fog','VolumetricFog','PostProcessing','AntiAliasing'):
    flags.append(unreal.EngineShowFlagsSetting(show_flag_name=name,enabled=False))
cap.set_editor_property('show_flag_settings',flags)
pool,pool_count,pool_cols=load_pool()
assets=json.loads((repo/'unreal/ForestSpike/Saved/ForestSpike/reports/fs_assets.report.json').read_text())['meshes']
poses={p['id']:p for p in json.loads((repo/'tools/forestspike/viewpoints.json').read_text())['poses']}
jobs=[]
for policy in ('legacy','policy'):
    for arm in ('A','B'):
        for pose in ('v1_agl50_p15','v1_agl200_p10'):
            for cull in (500,0):
                jobs.append({'name':f'forest_{arm}_{policy}_{pose}_cull{cull}','kind':'forest','arm':arm,'policy':policy,'pose_id':pose,'cull_m':cull})
for key in build['meshes']:
    radius=(bounds['meshes'][key]['render_sphere_radius_cm'] if bounds else build['meshes'][key]['policy']['sphere_radius_cm'])/100
    for boundary,screen in ((1,0.08),(2,0.03)):
        transition=math.sqrt(3)*radius/screen
        for side,ratio,expected_lod in (('near',0.9,boundary-1),('far',1.1,boundary)):
            jobs.append({'name':f'boundary_{key}_lod{boundary}_{side}','kind':'single','mesh':key,'policy':'policy','agl_m':50,
                         'distance_m':round(transition*ratio,5),'cull_m':500,'expected_lod':expected_lod,
                         'analytic_transition_m':transition,'bracket_ratio':ratio})
    for agl,distances in ((50,(80,240,480)),(200,(240,480))):
        for distance in distances:
            jobs.append({'name':f'single_{key}_agl{agl}_d{distance}','kind':'single','mesh':key,'policy':'policy','agl_m':agl,'distance_m':distance,'cull_m':500,
                         'expected_lod':0 if distance==80 else (1 if distance==240 else 2)})
    for distance in (450,550):
        for cull in (500,0):
            jobs.append({'name':f'cull_{key}_d{distance}_cull{cull}','kind':'cull','mesh':key,'policy':'policy','agl_m':50,'distance_m':distance,'cull_m':cull,
                         'expected_visible':distance==450 or cull==0})
if os.environ.get('ACW_FS_B01_BOUNDARY_ONLY')=='1':
    jobs=[job for job in jobs if job['name'].startswith('boundary_')]
    assert bounds and len(jobs)==20


def tree_state(h):
    row={'instance_count':h.get_instance_count()}
    for key in ('num_built_instances','num_built_render_instances','instance_count_to_render','instance_lod_distance_scale','forced_lod_model'):
        try:row[key]=h.get_editor_property(key)
        except Exception as exc:row[key]={'unavailable':str(exc)}
    return row


def set_mesh(h,key,policy):
    h.set_static_mesh(lib.load_asset(build['meshes'][key]['debug_'+policy]['path']))
    for slot in range(3):h.set_material(slot,None)
    h.set_forced_lod_model(0)
    h.set_lod_distance_scale(1)


def configure(job):
    for h in hs.values():
        h.clear_instances();h.set_visibility(False,True)
        h.set_cull_distances(0,job['cull_m']*100)
    if job['kind']=='forest':
        if job['arm']=='A':
            h=hs['Tree_A'];set_mesh(h,'Tree_A',job['policy'])
            place(h,pool,pool_cols,range(30200),pivot_shift(assets['Tree_A']));h.set_visibility(True,True)
        else:
            for vi,arch in enumerate(ARCHETYPES):
                key='Tree_B_'+arch;h=hs[key];set_mesh(h,key,job['policy'])
                idx=[i for i in range(30100) if int(pool[i*pool_cols+5])==vi]
                place(h,pool,pool_cols,idx,pivot_shift(assets[key]));h.set_visibility(True,True)
        p=poses[job['pose_id']]
        e,n,z=p['eye_enu'];loc=unreal.Vector(e*100,-n*100,z*100)
        rot=unreal.Rotator(0,p['pitch_deg'],p['heading_deg']-90)
    else:
        key=job['mesh'];h=hs['Tree_A'];set_mesh(h,key,'policy')
        origin=build['meshes'][key]['policy']['bounds_origin_cm']
        dz=origin[2]-job['agl_m']*100
        horizontal=math.sqrt((job['distance_m']*100)**2-dz**2)
        h.add_instances([unreal.Transform(unreal.Vector(horizontal-origin[0],-origin[1],0),unreal.Rotator(),unreal.Vector(1,1,1))],False,True)
        h.set_visibility(True,True)
        loc=unreal.Vector(0,0,job['agl_m']*100)
        rot=unreal.MathLibrary.find_look_at_rotation(loc,unreal.Vector(horizontal,0,origin[2]))
        radius=(bounds['meshes'][key]['render_sphere_radius_cm'] if bounds else build['meshes'][key]['policy']['sphere_radius_cm'])/100
        job['projected_sphere_diameter']=math.sqrt(3)*radius/job['distance_m']
        job['bounds_basis']='source-reconstructed all-LOD render sphere' if bounds else 'cached LOD0 sphere (historical diagnostic input)'
        job['bounds_receipt_sha256']=hashlib.sha256(Path(bounds_file).read_bytes()).hexdigest() if bounds else None
    cap_actor.set_actor_location_and_rotation(loc,rot,False,True)
    cap.set_editor_property('fov_angle',91.4928)
    unreal.log('FS_B01_TREE_BEGIN '+job['name'])
    # Native UE5.8 command calls BuildTreeIfOutdated(false, true), then
    # MarkRenderStateDirty. A fresh per-job log acknowledgement is required.
    unreal.SystemLibrary.execute_console_command(world,'foliage.RebuildFoliageTrees')
    unreal.log('FS_B01_TREE_END '+job['name'])
    job['tree_build_method']='native foliage.RebuildFoliageTrees; synchronous forced tree rebuild, normal automatic LOD'
    job['camera_cm']=[loc.x,loc.y,loc.z]
    job['camera_rot_roll_pitch_yaw']=[rot.roll,rot.pitch,rot.yaw]


state={'i':0,'phase':'prepare','ticks':0,'start':time.monotonic(),'captures':[]}


def finish(ok,error=None):
    unreal.unregister_slate_post_tick_callback(handle)
    with report_path.open('x',encoding='utf-8') as f:
        json.dump({'status':'PASS_FS_B01_LOD_CAPTURE' if ok else 'FAIL_FS_B01_LOD_CAPTURE','scope':'auto LOD-colored render capture, separate offline gate required',
                   'cvars':cvars,'capture_lod_distance_factor':cap.get_editor_property('lod_distance_factor'),
                   'captures':state['captures'],'error':error,'elapsed_s':time.monotonic()-state['start']},f,indent=2)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    unreal.SystemLibrary.quit_editor()


def tick(_dt):
    try:
        if time.monotonic()-state['start']>2400:raise RuntimeError('LOD capture timed out')
        if state['i']==len(jobs):finish(True);return
        job=jobs[state['i']]
        if state['phase']=='prepare':
            configure(job)
            unreal.AutomationLibrary.finish_loading_before_screenshot()
            state['ticks']=0;state['phase']='settle'
        cap.capture_scene()
        state['ticks']+=1
        if state['ticks']==52:
            unreal.log('FS_B01_RENDER_BEGIN '+job['name'])
            unreal.SystemLibrary.execute_console_command(world,'foliage.LogFoliageFrame')
        if state['ticks']<60:return
        # Flush the actual capture render target before export and hash.
        unreal.RenderingLibrary.read_render_target_pixel(world,rt,0,0)
        p=output/(job['name']+'.png')
        assert not p.exists()
        unreal.RenderingLibrary.export_render_target(world,rt,str(output),p.name)
        if p.read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n':raise RuntimeError('Invalid PNG export')
        record={'job':job,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'res':[1920,1080],
                'hism_state':{key:tree_state(h) for key,h in hs.items() if h.get_instance_count()}}
        with p.with_suffix('.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
        state['captures'].append(record)
        unreal.log('FS_B01_RENDER_END '+job['name'])
        unreal.log('FS_B01_LOD '+job['name'])
        state['i']+=1;state['phase']='prepare'
    except Exception:finish(False,traceback.format_exc())


unreal.EditorPythonScripting.set_keep_python_script_alive(True)
handle=unreal.register_slate_post_tick_callback(tick)
